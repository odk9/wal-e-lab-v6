"""
ingest_resty.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de go-resty/resty dans la KB Qdrant V6.

Focus : HTTP client patterns (simple GET requests, POST with JSON, authentication,
retry configuration, timeout handling, multipart file uploads, custom middleware,
response unmarshaling, proxy configuration, TLS/TLS client configuration, request
hooks with logging, debug mode tracing).

Usage:
    .venv/bin/python3 ingest_resty.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/go-resty/resty.git"
REPO_NAME = "go-resty/resty"
REPO_LOCAL = "/tmp/resty"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+resty+http+api"
CHARTE_VERSION = "1.0"
TAG = "go-resty/resty"
SOURCE_REPO = "https://github.com/go-resty/resty"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Resty = idiomatic HTTP client library for Go.
# Patterns CORE : simple HTTP requests, request/response handling, authentication,
# retry and timeout configuration, file uploads, middleware, TLS, and debugging.
# U-5 : `client`, `request`, `response`, `error`, `header`, `cookie` sont OK (termes techniques).

PATTERNS: list[dict] = [
    # ── 1. Simple GET Request ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/go-resty/resty/v2"
)

func simple_get_request() {
    // Create client
    client := resty.New()

    // Execute GET request
    resp, err := client.R().
        Get("https://api.example.com/xxx")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    // Handle response
    log.Printf("Status: %d", resp.StatusCode())
    log.Printf("Body: %s", resp.String())
}
""",
        "function": "simple_get_request",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/simple_get.go",
    },
    # ── 2. POST with JSON Body ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/go-resty/resty/v2"
)

type XxxRequest struct {
    Title string `json:"title"`
    Body  string `json:"body"`
}

type XxxResponse struct {
    ID    int    `json:"id"`
    Title string `json:"title"`
}

func post_json_body() {
    client := resty.New()

    req := XxxRequest{
        Title: "Example",
        Body:  "Content here",
    }

    var resp XxxResponse
    _, err := client.R().
        SetHeader("Content-Type", "application/json").
        SetBody(req).
        SetResult(&resp).
        Submit("https://api.example.com/xxxs")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    log.Printf("Created ID: %d", resp.ID)
}
""",
        "function": "post_json_body",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/post_json.go",
    },
    # ── 3. Client with Auth Token ────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/go-resty/resty/v2"
)

func client_with_auth_token(auth_token string) {
    // Create client with base URL
    client := resty.New().
        SetBaseURL("https://api.example.com").
        SetHeader("Authorization", "Bearer " + auth_token).
        SetHeader("Content-Type", "application/json").
        SetHeader("Client-Agent", "MyApp/1.0")

    // Requests inherit headers
    resp, err := client.R().
        Get("/xxxs")

    if err != nil {
        log.Fatalf("Failed: %v", err)
    }

    log.Printf("Status: %d", resp.StatusCode())
}
""",
        "function": "client_with_auth_token",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/auth_client.go",
    },
    # ── 4. Retry Configuration ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "time"
    "github.com/go-resty/resty/v2"
)

func retry_config() {
    client := resty.New().
        SetRetryCount(3).
        SetRetryWaitTime(2 * time.Second).
        SetRetryMaxWaitTime(10 * time.Second).
        AddRetryCondition(func(r *resty.Response, err error) bool {
            // Retry on 5xx errors or network timeouts
            return err != nil || r.StatusCode() >= 500
        })

    resp, err := client.R().
        Get("https://api.example.com/xxx")

    if err != nil {
        log.Fatalf("All retries exhausted: %v", err)
    }

    log.Printf("Final status: %d", resp.StatusCode())
}
""",
        "function": "retry_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/retry.go",
    },
    # ── 5. Timeout Configuration ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "time"
    "github.com/go-resty/resty/v2"
)

func timeout_config() {
    client := resty.New().
        SetTimeout(5 * time.Second).
        SetDialTimeout(3 * time.Second).
        SetResponseTimeout(10 * time.Second)

    // Per-request timeout override
    resp, err := client.R().
        SetTimeout(15 * time.Second).
        Get("https://api.example.com/slow-endpoint")

    if err != nil {
        log.Fatalf("Request timeout: %v", err)
    }

    log.Printf("Status: %d", resp.StatusCode())
}
""",
        "function": "timeout_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/timeout.go",
    },
    # ── 6. Upload File Multipart ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "os"
    "github.com/go-resty/resty/v2"
)

func upload_file_multipart(file_path string, field_name string) {
    client := resty.New()

    // Open file
    file, err := os.Open(file_path)
    if err != nil {
        log.Fatalf("Cannot open file: %v", err)
    }
    defer file.Close()

    resp, err := client.R().
        SetFileReader(field_name, "filename.txt", file).
        SetFormData(map[string]string{
            "description": "Upload test",
        }).
        Submit("https://api.example.com/upload")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    log.Printf("Upload status: %d", resp.StatusCode())
}
""",
        "function": "upload_file_multipart",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/upload.go",
    },
    # ── 7. Custom Middleware ─────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/go-resty/resty/v2"
)

func custom_middleware() {
    client := resty.New()

    // Request middleware — modify request before sending
    client.OnBeforeRequest(func(_ *resty.Client, req *resty.Request) error {
        log.Printf("Sending %s to %s", req.Method, req.URL)
        req.SetHeader("X-Custom-Header", "value")
        return nil
    })

    // Response middleware — process response
    client.OnAfterResponse(func(_ *resty.Client, resp *resty.Response) error {
        log.Printf("Received status %d", resp.StatusCode())
        return nil
    })

    resp, err := client.R().
        Get("https://api.example.com/xxx")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    log.Printf("Done: %d", resp.StatusCode())
}
""",
        "function": "custom_middleware",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/middleware.go",
    },
    # ── 8. Response Unmarshaling ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "encoding/json"
    "log"
    "github.com/go-resty/resty/v2"
)

type XxxData struct {
    ID    int    `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

func response_unmarshaling() {
    client := resty.New()

    var data XxxData
    resp, err := client.R().
        SetResult(&data).
        Get("https://api.example.com/xxx/1")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    // SetResult automatically unmarshals JSON into data
    log.Printf("ID: %d, Name: %s", data.ID, data.Name)

    // Manual unmarshaling fallback
    var raw map[string]interface{}
    if err := json.Unmarshal(resp.Body(), &raw); err != nil {
        log.Fatalf("Unmarshal failed: %v", err)
    }

    log.Printf("Raw: %v", raw)
}
""",
        "function": "response_unmarshaling",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/unmarshal.go",
    },
    # ── 9. Proxy Configuration ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "net/url"
    "github.com/go-resty/resty/v2"
)

func proxy_config(proxy_url string) {
    client := resty.New()

    // Set HTTP proxy
    proxyURL, err := url.Parse(proxy_url)
    if err != nil {
        log.Fatalf("Invalid proxy URL: %v", err)
    }

    client.SetProxy(proxy_url)

    // For HTTPS with proxy authentication
    client.SetProxyURL("http://proxyauth:pass@proxy.example.com:3128")

    resp, err := client.R().
        Get("https://api.example.com/xxx")

    if err != nil {
        log.Fatalf("Request via proxy failed: %v", err)
    }

    log.Printf("Status: %d", resp.StatusCode())
}
""",
        "function": "proxy_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/proxy.go",
    },
    # ── 10. TLS Client Configuration ─────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "crypto/tls"
    "log"
    "github.com/go-resty/resty/v2"
)

func tls_client_config(cert_file string, key_file string) {
    // Load client certificate and key
    certs, err := tls.LoadX509KeyPair(cert_file, key_file)
    if err != nil {
        log.Fatalf("Failed to load cert: %v", err)
    }

    client := resty.New()

    // Configure TLS
    client.SetTLSClientConfig(&tls.Config{
        Certificates:       []tls.Certificate{certs},
        InsecureSkipVerify: false,
        MinVersion:         tls.VersionTLS12,
    })

    resp, err := client.R().
        Get("https://secure.example.com/xxx")

    if err != nil {
        log.Fatalf("TLS request failed: %v", err)
    }

    log.Printf("Status: %d", resp.StatusCode())
}
""",
        "function": "tls_client_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/tls.go",
    },
    # ── 11. Request Hooks with Logging ──────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "time"
    "github.com/go-resty/resty/v2"
)

func request_hooks_logging() {
    client := resty.New()

    // Hook: Log request details before sending
    client.OnBeforeRequest(func(_ *resty.Client, req *resty.Request) error {
        log.Printf("[REQ] %s %s", req.Method, req.URL)
        for k, v := range req.Header {
            log.Printf("  Header: %s = %v", k, v)
        }
        return nil
    })

    // Hook: Log response details
    client.OnAfterResponse(func(_ *resty.Client, resp *resty.Response) error {
        elapsed := resp.ReceivedAt.Sub(resp.Request.Time)
        log.Printf("[RES] Status: %d, Time: %v", resp.StatusCode(), elapsed)
        log.Printf("  Content-Type: %s", resp.Header().Get("Content-Type"))
        return nil
    })

    // Hook: Log errors
    client.OnError(func(_ *resty.Client, err error) {
        log.Printf("[ERR] %v", err)
    })

    _, _ = client.R().Get("https://api.example.com/xxx")
}
""",
        "function": "request_hooks_logging",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/hooks.go",
    },
    # ── 12. Debug Mode and Tracing ──────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/go-resty/resty/v2"
)

func debug_mode_trace() {
    client := resty.New().
        SetDebug(true)

    // Alternative: per-request tracing
    resp, err := client.R().
        SetDoNotParseResponse(false).
        Get("https://api.example.com/xxx")

    if err != nil {
        log.Fatalf("Request failed: %v", err)
    }

    // Debug output shows full request/response including headers and body
    log.Printf("Status: %d", resp.StatusCode())
    log.Printf("Response Length: %d bytes", len(resp.Body()))

    // Manual trace with custom logging
    client.OnBeforeRequest(func(_ *resty.Client, req *resty.Request) error {
        log.Printf("[TRACE] Request Body: %s", string(req.Body.([]byte)))
        return nil
    })

    client.OnAfterResponse(func(_ *resty.Client, resp *resty.Response) error {
        log.Printf("[TRACE] Response Body: %s", resp.String())
        return nil
    })
}
""",
        "function": "debug_mode_trace",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/debug.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "simple HTTP GET request client",
    "POST request JSON body marshaling",
    "HTTP client with bearer token authentication",
    "retry configuration exponential backoff strategy",
    "timeout configuration dial and response",
    "multipart file upload form data",
    "custom middleware request response hooks",
    "response unmarshaling JSON struct binding",
    "proxy configuration HTTP HTTPS",
    "TLS client certificate key pair configuration",
    "request hooks logging trace audit",
    "debug mode request response tracing",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
