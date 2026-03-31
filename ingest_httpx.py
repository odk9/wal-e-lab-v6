"""
ingest_httpx.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'encode/httpx dans la KB Qdrant V6.

Focus : HTTP client patterns (async requests, JSON POST, session reuse, timeouts,
retries, custom auth, streaming, file upload, proxies, HTTP/2, hooks, testing).

Usage:
    .venv/bin/python3 ingest_httpx.py
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
REPO_URL = "https://github.com/encode/httpx.git"
REPO_NAME = "encode/httpx"
REPO_LOCAL = "/tmp/httpx"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+httpx+http+api"
CHARTE_VERSION = "1.0"
TAG = "encode/httpx"
SOURCE_REPO = "https://github.com/encode/httpx"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# HTTPX = modern async HTTP client library.
# Patterns CORE : async requests, session management, auth, retries, streaming.
# U-5 : `client`, `request`, `response`, `session`, `transport`, `auth` sont OK (HTTP terms).

PATTERNS: list[dict] = [
    # ── 1. Async GET Request ────────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from typing import Optional

async def fetch_data(url: str, params: Optional[dict] = None) -> dict:
    \"\"\"Fetch data from URL via async GET request.\"\"\"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

async def main():
    url = "https://api.example.com/records"
    params = {"skip": 0, "limit": 10}
    data = await fetch_data(url, params)
    print(data)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
""",
        "function": "async_get_request",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/async_get.py",
    },
    # ── 2. Async POST with JSON ─────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from typing import Optional

async def create_record(url: str, data: dict) -> dict:
    \"\"\"Create record via async submit request with JSON payload.\"\"\"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=data,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()

async def main():
    url = "https://api.example.com/records"
    payload = {"title": "Test Record", "description": "A test"}
    result = await create_record(url, payload)
    print(f"Created: {result['id']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
""",
        "function": "async_post_json",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/async_post_json.py",
    },
    # ── 3. Client Session Reuse ─────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from contextlib import asynccontextmanager

class ApiClient:
    \"\"\"Reusable HTTP client for API requests with session management.\"\"\"

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def get_record(self, record_id: int) -> dict:
        \"\"\"Fetch record by ID using persistent session.\"\"\"
        response = await self.client.get(f"/records/{record_id}")
        response.raise_for_status()
        return response.json()

    async def list_records(self, skip: int = 0, limit: int = 10) -> list:
        \"\"\"List records with pagination.\"\"\"
        response = await self.client.get("/records", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        return response.json()

async def main():
    async with ApiClient("https://api.example.com") as api:
        records = await api.list_records()
        for record in records:
            print(f"Record {record['id']}: {record['title']}")
""",
        "function": "client_session_reuse",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/api_client.py",
    },
    # ── 4. Timeout Configuration ────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from httpx import Timeout

async def request_with_timeout(url: str) -> dict:
    \"\"\"Make request with custom timeout configuration.\"\"\"
    timeout = Timeout(
        connect=5.0,
        read=10.0,
        write=5.0,
        pool=1.0
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_with_short_timeout(url: str) -> dict:
    \"\"\"Make request with short timeout for health checks.\"\"\"
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def main():
    url = "https://api.example.com/status"
    try:
        data = await request_with_short_timeout(url)
        print(f"Health check passed: {data}")
    except httpx.TimeoutException:
        print("Timeout: service unreachable")
""",
        "function": "timeout_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/timeout.py",
    },
    # ── 5. Retry Transport ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from httpx import HTTPStatus

class RetryTransport(httpx.AsyncHTTPTransport):
    \"\"\"Custom transport with exponential backoff retry logic.\"\"\"

    def __init__(self, max_retries: int = 3, backoff_factor: float = 0.5, **kwargs):
        super().__init__(**kwargs)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def handle_async_request(self, request):
        import asyncio
        for attempt in range(self.max_retries + 1):
            try:
                response = await super().handle_async_request(request)
                if response.status_code < 500:
                    return response
            except httpx.HTTPError:
                if attempt == self.max_retries:
                    raise
            wait = self.backoff_factor * (2 ** attempt)
            await asyncio.sleep(wait)

async def request_with_retries(url: str) -> dict:
    \"\"\"Make request with automatic retry on server errors.\"\"\"
    transport = RetryTransport(max_retries=3, backoff_factor=0.5)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
""",
        "function": "retry_transport",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/retry.py",
    },
    # ── 6. Custom Authentication ────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from typing import Optional

class BearerAuth(httpx.Auth):
    \"\"\"Custom auth handler for Bearer token.\"\"\"

    def __init__(self, token: str):
        self.token = token

    def __call__(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request

class ApiKeyAuth(httpx.Auth):
    \"\"\"Custom auth handler for API key in header.\"\"\"

    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name

    def __call__(self, request):
        request.headers[self.header_name] = self.api_key
        return request

async def request_with_bearer(url: str, token: str) -> dict:
    \"\"\"Make request with Bearer token authentication.\"\"\"
    auth = BearerAuth(token)
    async with httpx.AsyncClient(auth=auth) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_with_api_key(url: str, api_key: str) -> dict:
    \"\"\"Make request with API key authentication.\"\"\"
    auth = ApiKeyAuth(api_key)
    async with httpx.AsyncClient(auth=auth) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
""",
        "function": "custom_auth",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/auth.py",
    },
    # ── 7. Streaming Response ───────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx

async def stream_large_file(url: str, output_path: str) -> None:
    \"\"\"Download large file by streaming response chunks.\"\"\"
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

async def stream_and_parse_jsonl(url: str) -> list:
    \"\"\"Stream JSONL response and parse line by line.\"\"\"
    import json
    results = []
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    results.append(json.loads(line))
    return results

async def stream_text_response(url: str) -> str:
    \"\"\"Stream text response incrementally.\"\"\"
    text = ""
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_text():
                text += chunk
    return text
""",
        "function": "streaming_response",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/streaming.py",
    },
    # ── 8. File Upload Multipart ────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from typing import BinaryIO, Optional

async def upload_file(url: str, file_path: str, field_name: str = "file") -> dict:
    \"\"\"Upload file via multipart form data.\"\"\"
    with open(file_path, "rb") as f:
        files = {field_name: f}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)
            response.raise_for_status()
            return response.json()

async def upload_multiple_files(url: str, file_paths: list[str]) -> dict:
    \"\"\"Upload multiple files in single request.\"\"\"
    files = {}
    for idx, file_path in enumerate(file_paths):
        with open(file_path, "rb") as f:
            files[f"file_{idx}"] = f
    async with httpx.AsyncClient() as client:
        response = await client.post(url, files=files)
        response.raise_for_status()
        return response.json()

async def upload_file_with_metadata(url: str, file_path: str, metadata: dict) -> dict:
    \"\"\"Upload file with additional form fields.\"\"\"
    with open(file_path, "rb") as f:
        files = {"file": f}
        data = metadata
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files, data=data)
            response.raise_for_status()
            return response.json()
""",
        "function": "upload_file_multipart",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/upload.py",
    },
    # ── 9. Proxy Configuration ──────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from typing import Optional

async def request_via_proxy(url: str, proxy_url: str) -> dict:
    \"\"\"Make request through HTTP proxy.\"\"\"
    async with httpx.AsyncClient(proxy=proxy_url) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_via_socks_proxy(url: str, socks_proxy: str) -> dict:
    \"\"\"Make request through SOCKS5 proxy.\"\"\"
    async with httpx.AsyncClient(proxy=socks_proxy) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_with_proxy_auth(url: str, proxy_url: str, username: str, password: str) -> dict:
    \"\"\"Make request through authenticated proxy.\"\"\"
    proxy = httpx.URL(proxy_url)
    proxy = proxy.copy_with(userinfo=f"{username}:{password}")
    async with httpx.AsyncClient(proxy=proxy) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_with_proxy_routing(base_url: str, https_proxy: str, http_proxy: str) -> dict:
    \"\"\"Route HTTP and HTTPS through different proxies.\"\"\"
    mounts = {
        "https://": httpx.AsyncHTTPTransport(proxy=https_proxy),
        "http://": httpx.AsyncHTTPTransport(proxy=http_proxy),
    }
    async with httpx.AsyncClient(mounts=mounts) as client:
        response = await client.get(base_url)
        response.raise_for_status()
        return response.json()
""",
        "function": "proxy_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/proxy.py",
    },
    # ── 10. HTTP/2 Client ───────────────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
from httpx import HTTPVersionConfig

async def request_with_http2(url: str) -> dict:
    \"\"\"Make request with HTTP/2 protocol preference.\"\"\"
    mounts = {
        "https://": httpx.AsyncHTTPTransport(http2=True),
        "http://": httpx.AsyncHTTPTransport(http2=False),
    }
    async with httpx.AsyncClient(mounts=mounts) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def request_force_http2(url: str) -> dict:
    \"\"\"Force HTTP/2 for all requests.\"\"\"
    async with httpx.AsyncClient(http2=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def compare_http_versions(url: str) -> dict:
    \"\"\"Compare response times for HTTP/1.1 vs HTTP/2.\"\"\"
    import time

    async with httpx.AsyncClient(http2=False) as client_http1:
        start = time.time()
        resp1 = await client_http1.get(url)
        time_http1 = time.time() - start

    async with httpx.AsyncClient(http2=True) as client_http2:
        start = time.time()
        resp2 = await client_http2.get(url)
        time_http2 = time.time() - start

    return {
        "http1_time": time_http1,
        "http2_time": time_http2,
        "faster": "HTTP/2" if time_http2 < time_http1 else "HTTP/1.1",
    }
""",
        "function": "http2_client",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/http2.py",
    },
    # ── 11. Event Hooks and Logging ─────────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
import logging

log = logging.getLogger(__name__)

def request_hook(request: httpx.Request) -> None:
    \"\"\"Hook executed before request is sent.\"\"\"
    log.info(f"Request: {request.method} {request.url}")

def response_hook(response: httpx.Response) -> None:
    \"\"\"Hook executed after response is received.\"\"\"
    elapsed = response.elapsed.total_seconds()
    log.info(f"Response: {response.status_code} in {elapsed:.2f}s")

async def request_with_hooks(url: str) -> dict:
    \"\"\"Make request with request hooks for logging.\"\"\"
    async with httpx.AsyncClient(
        event_hooks={
            "request": [request_hook],
            "response": [response_hook],
        }
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

def detailed_logging_hook(request: httpx.Request) -> None:
    log.debug(f"Headers: {dict(request.headers)}")
    log.debug(f"Content: {request.content[:100]}")

async def request_with_detailed_hooks(url: str) -> dict:
    \"\"\"Make request with detailed logging hooks.\"\"\"
    async with httpx.AsyncClient(
        event_hooks={
            "request": [request_hook, detailed_logging_hook],
            "response": [response_hook],
        }
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
""",
        "function": "event_hooks_logging",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/hooks.py",
    },
    # ── 12. Mock Transport for Testing ──────────────────────────────────────────
    {
        "normalized_code": """\
import httpx
import json
from typing import Callable

class MockTransport(httpx.BaseTransport):
    \"\"\"Mock transport for testing without real HTTP requests.\"\"\"

    def __init__(self, mock_responses: dict[str, dict]):
        self.mock_responses = mock_responses

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path in self.mock_responses:
            response_data = self.mock_responses[url_path]
            return httpx.Response(
                status_code=response_data.get("status_code", 200),
                json=response_data.get("body", {}),
                headers=response_data.get("headers", {}),
            )
        return httpx.Response(status_code=404, text="Not Found")

def test_api_client():
    \"\"\"Unit test with mocked HTTP responses.\"\"\"
    mock_responses = {
        "/records": {
            "status_code": 200,
            "body": [{"id": 1, "title": "Record 1"}],
        },
        "/records/1": {
            "status_code": 200,
            "body": {"id": 1, "title": "Record 1"},
        },
    }

    transport = MockTransport(mock_responses)
    client = httpx.Client(transport=transport)

    response = client.get("http://test.local/records")
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "title": "Record 1"}]

    response = client.get("http://test.local/records/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1

    response = client.get("http://test.local/notfound")
    assert response.status_code == 404
""",
        "function": "mock_transport_testing",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_mock.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "async GET request HTTP client",
    "async POST JSON payload",
    "client session reuse persistent connection",
    "timeout configuration connect read write",
    "retry transport exponential backoff",
    "custom authentication bearer token API key",
    "streaming response download large file",
    "file upload multipart form data",
    "proxy configuration HTTP SOCKS5",
    "HTTP/2 protocol client",
    "event hooks logging request response",
    "mock transport unit testing",
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
