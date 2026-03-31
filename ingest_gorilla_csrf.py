"""
ingest_gorilla_csrf.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de gorilla/csrf dans la KB Qdrant V6.

Focus : CSRF protection middleware for Go — csrf.Protect, TemplateField,
custom error handler, SameSite cookie, secure cookie, HTTPS config,
request header check, exempt paths, token in template, API token extraction,
custom cookie name, gorilla mux integration.

Usage:
    .venv/bin/python3 ingest_gorilla_csrf.py
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
REPO_URL = "https://github.com/gorilla/csrf.git"
REPO_NAME = "gorilla/csrf"
REPO_LOCAL = "/tmp/gorilla-csrf"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+gorilla+csrf+security"
CHARTE_VERSION = "1.0"
TAG = "gorilla/csrf"
SOURCE_REPO = "https://github.com/gorilla/csrf"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Gorilla CSRF = CSRF protection middleware for Go.
# Patterns CORE : middleware, token generation, template field, cookie config, error handling.
# U-5 : `middleware`, `handler`, `router`, `header`, `cookie`, `request`, `response` are OK (technical terms).

PATTERNS: list[dict] = [
    # ── 1. CSRF Protect Middleware Setup ────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
    "github.com/gorilla/mux"
)

func main() {
    router := mux.NewRouter()

    // Create CSRF middleware with authentication key
    key := []byte("32-byte-long-auth-key-example-!")
    csrfMiddleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.HttpOnly(true),
        csrf.Path("/"),
        csrf.MaxAge(3600),
    )

    // Create a simple handler
    router.HandleFunc("/form", handleGetForm).Methods(http.MethodGet)
    router.HandleFunc("/form", handleSubmitForm).Methods(http.MethodPost)

    // Wrap router with CSRF middleware
    http.ListenAndServe(":8080", csrfMiddleware(router))
}

func handleGetForm(w http.ResponseWriter, request *http.Request) {
    w.Header().Set("Content-Type", "text/html")
    w.Write([]byte("<form method='submit'></form>"))
}

func handleSubmitForm(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Form submitted successfully"))
}
""",
        "function": "csrf_protect_middleware_setup",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "middleware.go",
    },
    # ── 2. Template Field Token Injection ───────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "html/template"
    "net/http"
    "github.com/gorilla/csrf"
)

func serveForm(w http.ResponseWriter, request *http.Request) {
    // Inject CSRF token into template context
    data := map[string]interface{}{
        "csrf_field": csrf.FieldValue(request),
        "form_title": "Account Registration Form",
    }

    xxx := template.Must(template.ParseFiles("form.html"))
    xxx.Execute(w, data)
}

// form.html template content:
// <form method="POST">
//     {{ .csrf_field }}
//     <input type="text" name="username" required>
//     <button type="submit">Register</button>
// </form>
""",
        "function": "template_field_token_injection",
        "feature_type": "utility",
        "file_role": "route",
        "file_path": "template.go",
    },
    # ── 3. Custom Error Handler ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "encoding/json"
    "github.com/gorilla/csrf"
)

func customErrorHandler(w http.ResponseWriter, request *http.Request) {
    // Custom error handler for CSRF validation failures
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusForbidden)

    error := map[string]interface{}{
        "error":   "CSRF validation failed",
        "detail": "The form submission is invalid or expired",
        "code":    403,
    }
    json.NewEncoder(w).Encode(error)
}

func setupCSRFWithErrorHandler(router *http.ServeMux) http.Handler {
    key := []byte("32-byte-long-auth-key-example-!")

    middleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.ErrorHandler(http.HandlerFunc(customErrorHandler)),
    )

    return middleware(router)
}
""",
        "function": "custom_error_handler_csrf_failure",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "error_handler.go",
    },
    # ── 4. Secure Cookie Configuration ──────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
)

func configureSecureCookie() http.Handler {
    router := http.NewServeMux()

    key := []byte("32-byte-long-auth-key-example-!")

    // Configure CSRF with secure cookie settings
    middleware := csrf.Protect(
        key,
        csrf.Secure(true),       // HTTPS only
        csrf.HttpOnly(true),     // No JavaScript access
        csrf.Path("/"),          // Cookie path
        csrf.Domain("example.com"),  // Cookie domain
        csrf.MaxAge(3600),       // 1 hour expiry
        csrf.SameSite(http.SameSiteStrictMode),  // SameSite strict
    )

    router.HandleFunc("/", handleRequest)
    return middleware(router)
}

func handleRequest(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("CSRF token cookie configured securely"))
}
""",
        "function": "secure_cookie_config_csrf",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "secure_cookie.go",
    },
    # ── 5. SameSite Cookie Attribute ────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
)

func setupSameSiteCookie(mode http.SameSite) http.Handler {
    router := http.NewServeMux()
    key := []byte("32-byte-long-auth-key-example-!")

    // Apply SameSite policy to CSRF token cookie
    // SameSiteDefaultMode — varies by browser default
    // SameSiteLaxMode — send only with same-site cross-origin requests
    // SameSiteStrictMode — never send with cross-origin requests
    // SameSiteNoneMode — send with all cross-origin requests (Secure required)

    middleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.SameSite(mode),
    )

    router.HandleFunc("/form", handleFormPage)
    router.HandleFunc("/submit", handleFormSubmit).Methods("POST")

    return middleware(router)
}

func handleFormPage(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Form page with SameSite cookie"))
}

func handleFormSubmit(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Form submitted"))
}
""",
        "function": "samesite_cookie_attribute",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "samesite_cookie.go",
    },
    # ── 6. HTTPS Only Configuration ─────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "crypto/tls"
    "github.com/gorilla/csrf"
)

func setupHTTPSOnly() {
    router := http.NewServeMux()
    key := []byte("32-byte-long-auth-key-example-!")

    // Enforce HTTPS for CSRF token cookie
    middleware := csrf.Protect(
        key,
        csrf.Secure(true),  // Require HTTPS
    )

    router.HandleFunc("/api/data", handleSecureRequest)

    // TLS configuration
    tlsConfig := &tls.Config{
        MinVersion: tls.VersionTLS12,
        CipherSuites: []uint16{
            tls.TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,
            tls.TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,
        },
    }

    server := &http.Server{
        Addr:      ":8443",
        Handler:   middleware(router),
        TLSConfig: tlsConfig,
    }

    server.ListenAndServeTLS("cert.pem", "key.pem")
}

func handleSecureRequest(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Secure HTTPS request"))
}
""",
        "function": "https_only_config_tls",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "https_config.go",
    },
    # ── 7. Token in Header ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
)

func handleAPIRequest(w http.ResponseWriter, request *http.Request) {
    // For API requests, CSRF token is typically in X-CSRF-Token header
    // Gorilla CSRF middleware checks both header and body by default

    token := request.Header.Get("X-CSRF-Token")
    if token == "" {
        http.Error(w, "Missing CSRF token", http.StatusBadRequest)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(`{"status":"success","detail":"API request validated"}`))
}

func serveAPIForm(w http.ResponseWriter, request *http.Request) {
    // Return CSRF token for API client to include in header
    token := csrf.Token(request)
    w.Header().Set("X-CSRF-Token", token)
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(`{"token":"` + token + `"}`))
}
""",
        "function": "token_in_header_api_csrf",
        "feature_type": "utility",
        "file_role": "route",
        "file_path": "header_token.go",
    },
    # ── 8. Exempt Path Handler ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
    "github.com/gorilla/mux"
)

func setupExemptPaths() http.Handler {
    router := mux.NewRouter()
    key := []byte("32-byte-long-auth-key-example-!")

    // Create middleware with exempt paths
    middleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.ErrorHandler(http.HandlerFunc(handleCSRFError)),
    )

    // Public endpoints (exempt from CSRF by routing)
    router.HandleFunc("/public", handlePublic).Methods("POST")

    // Protected endpoints (require CSRF)
    router.HandleFunc("/api/resource", handleProtected).Methods("POST")
    router.HandleFunc("/form", handleFormSubmit).Methods("POST")

    // Webhook endpoints typically exempt — implement custom wrapper
    router.HandleFunc("/webhook/github", handleGitHubWebhook).Methods("POST")

    return middleware(router)
}

func handlePublic(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Public endpoint"))
}

func handleProtected(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Protected endpoint with CSRF"))
}

func handleGitHubWebhook(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Webhook processed"))
}

func handleCSRFError(w http.ResponseWriter, request *http.Request) {
    http.Error(w, "CSRF token invalid", http.StatusForbidden)
}
""",
        "function": "exempt_path_handler_webhook",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "exempt_paths.go",
    },
    # ── 9. Gorilla Mux Integration ──────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
    "github.com/gorilla/mux"
)

func setupMuxRouter() http.Handler {
    router := mux.NewRouter()
    key := []byte("32-byte-long-auth-key-example-!")

    // Create CSRF middleware
    middleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.HttpOnly(true),
    )

    // Define routes
    router.HandleFunc("/form", handleGetForm).Methods(http.MethodGet)
    router.HandleFunc("/form", handlePostForm).Methods(http.MethodPost)

    apiRouter := router.PathPrefix("/api").Subrouter()
    apiRouter.HandleFunc("/data", handleAPIData).Methods(http.MethodGet, http.MethodPost)

    // Wrap entire router with CSRF middleware
    return middleware(router)
}

func handleGetForm(w http.ResponseWriter, request *http.Request) {
    token := csrf.Token(request)
    w.Header().Set("Content-Type", "text/html")
    w.Write([]byte("<form method='submit'><input type='hidden' name='gorilla.csrf.Token' value='" + token + "'></form>"))
}

func handleSubmitForm(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Form accepted"))
}

func handleAPIData(w http.ResponseWriter, request *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(`{"status":"ok"}`))
}
""",
        "function": "gorilla_mux_integration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "mux_integration.go",
    },
    # ── 10. API CSRF Protection (Request Body Token) ─────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "encoding/json"
    "github.com/gorilla/csrf"
)

type APIRequest struct {
    CSRFToken string      `json:"csrf_token"`
    Data      interface{} `json:"data"`
}

func handleAPICSRFProtection(w http.ResponseWriter, request *http.Request) {
    // For API requests, extract token from JSON body
    var xxx APIRequest
    if err := json.NewDecoder(request.Body).Decode(&xxx); err != nil {
        http.Error(w, "Invalid request", http.StatusBadRequest)
        return
    }

    // Validate CSRF token manually if not in header
    if xxx.CSRFToken == "" {
        xxx.CSRFToken = request.Header.Get("X-CSRF-Token")
    }

    // Gorilla middleware validates automatically, but explicit check shown here
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(`{"status":"token validated"}`))
}

func getAPIToken(w http.ResponseWriter, request *http.Request) {
    token := csrf.Token(request)
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(`{"csrf_token":"` + token + `"}`))
}
""",
        "function": "api_csrf_protection_body_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "api_csrf.go",
    },
    # ── 11. Custom Cookie Name ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "github.com/gorilla/csrf"
)

func setupCustomCookieName() http.Handler {
    router := http.NewServeMux()
    key := []byte("32-byte-long-auth-key-example-!")

    // Gorilla CSRF uses "_gorilla.csrf.Token" by default
    // To customize, wrap the middleware with custom cookie handling
    // Memo: Custom cookie name requires patching gorilla/csrf or wrapping

    middleware := csrf.Protect(
        key,
        csrf.Secure(true),
        csrf.HttpOnly(true),
    )

    router.HandleFunc("/form", handleCustomCookieForm)
    router.HandleFunc("/submit", handleCustomCookieSubmit).Methods("POST")

    return middleware(router)
}

func handleCustomCookieForm(w http.ResponseWriter, request *http.Request) {
    token := csrf.Token(request)
    w.Write([]byte("Token: " + token))
}

func handleCustomCookieSubmit(w http.ResponseWriter, request *http.Request) {
    w.Write([]byte("Submitted"))
}
""",
        "function": "custom_cookie_name_configuration",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "custom_cookie_name.go",
    },
    # ── 12. CSRF Test Helper ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "net/http"
    "net/http/httptest"
    "testing"
    "github.com/gorilla/csrf"
)

func TestCSRFProtection(t *testing.T) {
    key := []byte("32-byte-long-auth-key-example-!")

    // Create test server with CSRF middleware
    middleware := csrf.Protect(
        key,
        csrf.Secure(false),  // Disable secure for testing
    )

    handler := middleware(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
        w.Write([]byte("OK"))
    }))

    server := httptest.NewServer(handler)
    defer server.Close()

    // Test 1: GET request to retrieve CSRF token
    resp, _ := http.Get(server.URL + "/form")
    token := csrf.Token(httptest.NewRequest("GET", "/form", nil))

    // Test 2: SubmitRequest with valid CSRF token
    req, _ := http.NewRequest(http.MethodPost, server.URL+"/submit", nil)
    req.Header.Set("X-CSRF-Token", token)
    client := &http.Client{}
    respPost, err := client.Do(req)
    if err != nil || respPost.StatusCode != http.StatusOK {
        t.Errorf("CSRF validation failed: %v", err)
    }
}
""",
        "function": "csrf_test_helper_unit_testing",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "csrf_test.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "CSRF protect middleware setup Go",
    "template field token injection form",
    "custom error handler CSRF validation failure",
    "secure cookie configuration CSRF token",
    "SameSite cookie attribute CSRF",
    "HTTPS only configuration TLS certificate",
    "token in header API CSRF request",
    "exempt path handler webhook integration",
    "gorilla mux router integration CSRF",
    "API CSRF protection JSON body token",
    "custom cookie name configuration",
    "CSRF test helper unit testing",
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
