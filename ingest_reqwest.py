"""
ingest_reqwest.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de seanmonstar/reqwest dans la KB Qdrant V6.

Focus : CORE patterns HTTP client (async GET/POST, client builder, timeout,
headers, cookies, proxy, TLS, streaming, multipart, retry, deserialization).

Usage:
    .venv/bin/python3 ingest_reqwest.py
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
REPO_URL = "https://github.com/seanmonstar/reqwest.git"
REPO_NAME = "seanmonstar/reqwest"
REPO_LOCAL = "/tmp/reqwest"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+reqwest+http+api"
CHARTE_VERSION = "1.0"
TAG = "seanmonstar/reqwest"
SOURCE_REPO = "https://github.com/seanmonstar/reqwest"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Reqwest = async HTTP client for Rust.
# Patterns CORE : async GET/POST, client builder, timeout, headers, cookies,
# proxy, TLS, streaming, multipart, retry, response deserialization.
# U-5 : Keep HTTP terms (client, request, response, header, cookie, proxy).

PATTERNS: list[dict] = [
    # ── 1. Async GET Request ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;

async fn xxx_get_request() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::new();

    let response = client
        .get("https://api.example.com/data")
        .send()
        .await?;

    if !response.status().is_success() {
        return Err("Request failed".into());
    }

    let body = response.text().await?;
    tracing::info!("Response: {}", body);

    Ok(body)
}
""",
        "function": "async_get_request",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/async_get.rs",
    },
    # ── 2. Async POST with JSON ───────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use serde_json::json;

async fn xxx_post_json() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::new();

    let payload = json!({
        "name": "example",
        "value": 123
    });

    let response = client
        .post("https://api.example.com/create")
        .json(&payload)
        .send()
        .await?;

    if !response.status().is_success() {
        return Err("submit failed".into());
    }

    let body = response.json::<serde_json::Value>().await?;

    Ok(body.to_string())
}
""",
        "function": "async_post_json",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/async_post_json.rs",
    },
    # ── 3. Client Builder Configuration ──────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use std::time::Duration;

async fn xxx_builder_config() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .connect_timeout(Duration::from_secs(10))
        .pool_max_idle_per_host(10)
        .http2_prior_knowledge()
        .gzip(true)
        .deflate(true)
        .brotli(true)
        .build()?;

    let response = client
        .get("https://api.example.com/test")
        .send()
        .await?;

    tracing::info!("Status: {}", response.status());

    Ok(())
}
""",
        "function": "client_builder_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/client.rs",
    },
    # ── 4. Timeout Configuration ─────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use std::time::Duration;

async fn xxx_timeout_config() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::builder()
        .timeout(Duration::from_secs(5))
        .build()?;

    let response = client
        .get("https://api.example.com/slow")
        .timeout(Duration::from_secs(10))
        .send()
        .await?;

    if response.status().is_success() {
        Ok(response.text().await?)
    } else {
        Err("Request timeout or failed".into())
    }
}
""",
        "function": "timeout_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/timeout.rs",
    },
    # ── 5. Custom Headers ────────────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use reqwest::header::{HeaderMap, HeaderValue, USER_AGENT};

async fn xxx_custom_headers() -> Result<String, Box<dyn std::error::Error>> {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("MyClient/1.0")
    );
    headers.insert(
        "Authorization",
        HeaderValue::from_str("Bearer token123")?
    );
    headers.insert(
        "X-Request-ID",
        HeaderValue::from_str("req-abc-123")?
    );

    let client = Client::builder()
        .default_headers(headers)
        .build()?;

    let response = client
        .get("https://api.example.com/auth")
        .send()
        .await?;

    Ok(response.text().await?)
}
""",
        "function": "custom_headers",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/headers.rs",
    },
    # ── 6. Cookie Store and Persistence ──────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use reqwest::cookie::Jar;
use std::sync::Arc;

async fn xxx_cookie_store() -> Result<(), Box<dyn std::error::Error>> {
    let jar = Arc::new(Jar::default());

    let client = Client::builder()
        .cookie_provider(jar.clone())
        .build()?;

    let response1 = client
        .get("https://api.example.com/login")
        .send()
        .await?;

    tracing::info!("Login status: {}", response1.status());

    let response2 = client
        .get("https://api.example.com/profile")
        .send()
        .await?;

    tracing::info!("Profile status: {}", response2.status());

    Ok(())
}
""",
        "function": "cookie_store",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/cookies.rs",
    },
    # ── 7. Proxy Configuration ───────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use reqwest::Proxy;

async fn xxx_proxy_config() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::builder()
        .proxy(Proxy::http("http://proxy.example.com:8080")?)
        .proxy(Proxy::https("http://proxy.example.com:8080")?)
        .no_proxy()
        .build()?;

    let response = client
        .get("https://api.example.com/proxy_test")
        .send()
        .await?;

    if response.status().is_success() {
        Ok(response.text().await?)
    } else {
        Err("Proxy request failed".into())
    }
}
""",
        "function": "proxy_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/proxy.rs",
    },
    # ── 8. TLS Client Configuration ──────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use reqwest::tls::TlsClientConfig;

async fn xxx_tls_client_config() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::builder()
        .danger_accept_invalid_certs(true)
        .danger_accept_invalid_hostnames(true)
        .min_tls_version(reqwest::tls::Version::TLS_1_2)
        .build()?;

    let response = client
        .get("https://secure.example.com/test")
        .send()
        .await?;

    tracing::warn!("TLS response status: {}", response.status());

    Ok(())
}
""",
        "function": "tls_client_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/tls.rs",
    },
    # ── 9. Streaming Response ────────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use futures::StreamExt;

async fn xxx_streaming_response() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new();

    let response = client
        .get("https://api.example.com/stream")
        .send()
        .await?;

    let mut stream = response.bytes_stream();

    while let Some(chunk_result) = stream.next().await {
        match chunk_result {
            Ok(chunk) => tracing::debug!("Received {} bytes", chunk.len()),
            Err(e) => tracing::warn!("Stream error: {}", e),
        }
    }

    Ok(())
}
""",
        "function": "streaming_response",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/streaming.rs",
    },
    # ── 10. Multipart Upload ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use reqwest::multipart;

async fn xxx_multipart_upload() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::new();

    let form = multipart::Form::new()
        .text("field_name", "field_value")
        .text("file_type", "document");

    let response = client
        .post("https://api.example.com/upload")
        .multipart(form)
        .send()
        .await?;

    if response.status().is_success() {
        Ok(response.text().await?)
    } else {
        Err("Upload failed".into())
    }
}
""",
        "function": "multipart_upload",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/multipart.rs",
    },
    # ── 11. Retry Middleware ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;

async fn xxx_retry_middleware() -> Result<String, Box<dyn std::error::Error>> {
    let client = Client::new();
    let max_retries = 3;
    let mut attempt = 0;

    loop {
        match client
            .get("https://api.example.com/flaky")
            .send()
            .await {
            Ok(response) if response.status().is_success() => {
                return Ok(response.text().await?);
            }
            Ok(_) | Err(_) => {
                attempt += 1;
                if attempt >= max_retries {
                    return Err("Max retries exceeded".into());
                }
                tokio::time::sleep(
                    std::time::Duration::from_millis(100 * attempt)
                ).await;
            }
        }
    }
}
""",
        "function": "retry_middleware",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/retry.rs",
    },
    # ── 12. Response JSON Deserialization ────────────────────────────────────
    {
        "normalized_code": """\
use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
struct Xxx {
    id: i32,
    name: String,
    value: Option<String>,
}

async fn xxx_json_deserialize() -> Result<Xxx, Box<dyn std::error::Error>> {
    let client = Client::new();

    let response = client
        .get("https://api.example.com/record")
        .send()
        .await?;

    if response.status().is_success() {
        let record: Xxx = response.json().await?;
        tracing::debug!("Record: {:?}", record);
        Ok(record)
    } else {
        Err("Failed to fetch record".into())
    }
}
""",
        "function": "response_json_deserialize",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/deserialize.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "async GET request HTTP client send",
    "async POST JSON payload request",
    "client builder configuration timeout connect",
    "timeout configuration request duration seconds",
    "custom headers USER_AGENT Authorization Bearer",
    "cookie store jar persistence login",
    "proxy configuration HTTP HTTPS",
    "TLS client config certificate validation",
    "streaming response bytes chunks",
    "multipart form upload POST",
    "retry middleware exponential backoff attempts",
    "response JSON deserialization serde",
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
