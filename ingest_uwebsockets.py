"""
ingest_uwebsockets.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de uNetworking/uWebSockets dans la KB Qdrant V6.

C++ C — High-performance WebSocket & HTTP server. uWS + libuv + OpenSSL.

Usage:
    .venv/bin/python3 ingest_uwebsockets.py
"""

from __future__ import annotations

import os
import subprocess

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import (
    audit_report,
    build_payload,
    check_charte_violations,
    make_uuid,
    query_kb,
)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/uNetworking/uWebSockets.git"
REPO_NAME = "uNetworking/uWebSockets"
REPO_LOCAL = "/tmp/uwebsockets"
LANGUAGE = "cpp"
FRAMEWORK = "uwebsockets"
STACK = "uwebsockets+libuv+openssl"
CHARTE_VERSION = "1.0"
TAG = "uNetworking/uWebSockets"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/uNetworking/uWebSockets"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Entity names → Xxx/xxx/xxxs (minimal in this repo — mostly framework types)
# U-7: No printf/cout for debug; keep std::cout for idiomatic server startup messages
# Keep: uWS::App, uWS::SSLApp, uWS::WebSocket, uWS::HttpResponse, uWS::HttpRequest,
#       uWS::OpCode, uWS::LocalCluster, etc.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. app_hello_world — basic uWS::App setup ─────────────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

int main() {
\tuWS::App()
\t\t.get("/*", [](auto *res, auto *req) {
\t\t\tres->end("Hello World!");
\t\t})
\t\t.listen(3000, [](auto *listen_socket) {
\t\t\tif (listen_socket) {
\t\t\t\tstd::cout << "Listening on port 3000" << std::endl;
\t\t\t}
\t\t})
\t\t.run();

\treturn 0;
}
""",
        "function": "app_hello_world",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/HelloWorld.cpp",
    },

    # ── 2. ssl_app_setup — uWS::SSLApp with TLS config ───────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

int main() {
\tuWS::SSLApp({
\t\t.key_file_name = "key.pem",
\t\t.cert_file_name = "cert.pem",
\t\t.passphrase = "1234"
\t})
\t\t.get("/*", [](auto *res, auto *req) {
\t\t\tres->end("Hello HTTPS World!");
\t\t})
\t\t.listen(3000, [](auto *listen_socket) {
\t\t\tif (listen_socket) {
\t\t\t\tstd::cout << "Listening on port 3000 (SSL)" << std::endl;
\t\t\t}
\t\t})
\t\t.run();

\treturn 0;
}
""",
        "function": "ssl_app_setup",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/ServerName.cpp",
    },

    # ── 11. threaded_cluster — multi-threaded uWS::LocalCluster ───────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

int main() {
\tuWS::LocalCluster({
\t\t.num_threads = std::thread::hardware_concurrency()
\t}, [](uWS::App &app) {
\t\tapp
\t\t\t.get("/*", [](auto *res, auto *req) {
\t\t\t\tres->end("Hello from cluster!");
\t\t\t})
\t\t\t.listen(3000, [](auto *listen_socket) {
\t\t\t\tif (listen_socket) {
\t\t\t\t\tstd::cout << "Thread listening on port 3000" << std::endl;
\t\t\t\t}
\t\t\t});
\t});

\treturn 0;
}
""",
        "function": "threaded_cluster",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/LocalCluster.cpp",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — HTTP
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 3. http_get_handler — GET route with response ─────────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>

void setup_get_routes(uWS::App &app) {
\tapp.get("/xxxs", [](auto *res, auto *req) {
\t\tres->writeHeader("Content-Type", "application/json");
\t\tres->end(R"({"xxxs": []})");
\t});

\tapp.get("/xxxs/:id", [](auto *res, auto *req) {
\t\tstd::string id(req->getParameter("id"));
\t\tres->writeHeader("Content-Type", "application/json");
\t\tres->end(std::string(R"({"id": ")") + id + R"("})");
\t});
}
""",
        "function": "http_get_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/HttpGet.cpp",
    },

    # ── 4. http_post_handler — POST route with body reading ───────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>

void setup_post_routes(uWS::App &app) {
\tapp.post("/xxxs", [](auto *res, auto *req) {
\t\tstd::string buffer;

\t\tres->onAborted([]() {});

\t\tres->onData([res, buffer = std::move(buffer)](
\t\t\tstd::string_view chunk, bool is_last
\t\t) mutable {
\t\t\tbuffer.append(chunk);
\t\t\tif (is_last) {
\t\t\t\tres->writeHeader("Content-Type", "application/json");
\t\t\t\tres->end(buffer);
\t\t\t}
\t\t});
\t});
}
""",
        "function": "http_post_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/HttpPost.cpp",
    },

    # ── 9. request_body_reading — chunked body reading via onData ─────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <functional>
#include <string>

void read_body(
\tuWS::HttpResponse<false> *res,
\tstd::function<void(std::string)> callback
) {
\tstd::string buffer;

\tres->onAborted([res]() {
\t\tres->writeStatus("500 Internal Server Error");
\t\tres->end("Aborted");
\t});

\tres->onData([res, buffer = std::move(buffer), callback = std::move(callback)](
\t\tstd::string_view chunk, bool is_last
\t) mutable {
\t\tbuffer.append(chunk);
\t\tif (is_last) {
\t\t\tcallback(std::move(buffer));
\t\t}
\t});
}
""",
        "function": "request_body_reading",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/BodyReading.cpp",
    },

    # ── 12. url_routing_params — manual URL parameter parsing ─────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>

void setup_param_routes(uWS::App &app) {
\tapp.get("/xxxs/:id", [](auto *res, auto *req) {
\t\tstd::string id(req->getParameter("id"));
\t\tres->end(std::string("Xxx ID: ") + id);
\t});

\tapp.get("/xxxs/:id/details", [](auto *res, auto *req) {
\t\tstd::string id(req->getParameter("id"));
\t\tstd::string_view query = req->getQuery();
\t\tstd::string_view header_val = req->getHeader("authorization");
\t\tres->end(std::string("Xxx ") + id + " details");
\t});
}
""",
        "function": "url_routing_params",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/Routing.cpp",
    },

    # ── 13. http_response_headers — writeHeader + writeStatus ─────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

void setup_header_routes(uWS::App &app) {
\tapp.get("/xxxs", [](auto *res, auto *req) {
\t\tres->writeStatus("200 OK");
\t\tres->writeHeader("Content-Type", "application/json");
\t\tres->writeHeader("Cache-Control", "no-cache");
\t\tres->writeHeader("X-Request-Id", req->getHeader("x-request-id"));
\t\tres->end(R"({"status": "ok"})");
\t});

\tapp.get("/xxxs/not-found", [](auto *res, auto *req) {
\t\tres->writeStatus("404 Not Found");
\t\tres->writeHeader("Content-Type", "application/json");
\t\tres->end(R"({"error": "not found"})");
\t});
}
""",
        "function": "http_response_headers",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/Headers.cpp",
    },

    # ── 14. cors_preflight — OPTIONS handler for CORS ─────────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

void setup_cors(uWS::App &app) {
\tapp.options("/*", [](auto *res, auto *req) {
\t\tres->writeHeader("Access-Control-Allow-Origin", "*");
\t\tres->writeHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
\t\tres->writeHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
\t\tres->writeHeader("Access-Control-Max-Age", "86400");
\t\tres->end();
\t});

\tapp.get("/*", [](auto *res, auto *req) {
\t\tres->writeHeader("Access-Control-Allow-Origin", "*");
\t\tres->end("Hello CORS World!");
\t});
}
""",
        "function": "cors_preflight",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/CORS.cpp",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — WebSocket
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 5. websocket_handler — full ws<XxxData> handler ───────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>
#include <string_view>

struct XxxData {
\tstd::string name;
\tint xxx_id = 0;
};

void setup_websocket(uWS::App &app) {
\tapp.ws<XxxData>("/*", {
\t\t.compression = uWS::SHARED_COMPRESSOR,
\t\t.maxPayloadLength = 16 * 1024,
\t\t.idleTimeout = 120,

\t\t.open = [](auto *ws) {
\t\t\tXxxData *data = ws->getUserData();
\t\t\tdata->name = "anonymous";
\t\t},

\t\t.message = [](auto *ws, std::string_view message, uWS::OpCode op_code) {
\t\t\tws->send(message, op_code);
\t\t},

\t\t.drain = [](auto *ws) {
\t\t\tsize_t buffered = ws->getBufferedAmount();
\t\t\tif (buffered > 0) {
\t\t\t\t/* backpressure handling */
\t\t\t}
\t\t},

\t\t.close = [](auto *ws, int code, std::string_view message) {
\t\t\t/* cleanup on close */
\t\t}
\t});
}
""",
        "function": "websocket_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/WebSocket.cpp",
    },

    # ── 6. pubsub_pattern — ws subscribe + publish ────────────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>
#include <string_view>

struct XxxData {
\tstd::string topic;
};

void setup_pubsub(uWS::App &app) {
\tapp.ws<XxxData>("/*", {
\t\t.open = [](auto *ws) {
\t\t\tws->subscribe("broadcast");
\t\t\tws->subscribe("xxxs/updates");
\t\t},

\t\t.message = [](auto *ws, std::string_view message, uWS::OpCode op_code) {
\t\t\t/* publish to all subscribers of the topic */
\t\t\tws->publish("broadcast", message, op_code);
\t\t},

\t\t.close = [](auto *ws, int code, std::string_view message) {
\t\t\t/* unsubscribe happens automatically on close */
\t\t}
\t});
}
""",
        "function": "pubsub_pattern",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/PubSub.cpp",
    },

    # ── 7. per_socket_user_data — XxxData struct for connection state ─────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>
#include <string_view>
#include <vector>

struct XxxData {
\tstd::string name;
\tint xxx_id = 0;
\tbool is_authenticated = false;
\tstd::vector<std::string> subscriptions;
};

void setup_user_data_ws(uWS::App &app) {
\tapp.ws<XxxData>("/*", {
\t\t.open = [](auto *ws) {
\t\t\tXxxData *data = ws->getUserData();
\t\t\tdata->name = "guest";
\t\t\tdata->xxx_id = 0;
\t\t\tdata->is_authenticated = false;
\t\t},

\t\t.message = [](auto *ws, std::string_view message, uWS::OpCode op_code) {
\t\t\tXxxData *data = ws->getUserData();
\t\t\tif (!data->is_authenticated) {
\t\t\t\tws->send("Please authenticate first", uWS::OpCode::TEXT);
\t\t\t\treturn;
\t\t\t}
\t\t\tws->send(message, op_code);
\t\t},

\t\t.close = [](auto *ws, int code, std::string_view message) {
\t\t\t/* XxxData is freed automatically */
\t\t}
\t});
}
""",
        "function": "per_socket_user_data",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/UserData.cpp",
    },

    # ── 8. streaming_response — chunked write with tryEnd ─────────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>
#include <string_view>

void setup_streaming(uWS::App &app) {
\tapp.get("/xxxs/stream", [](auto *res, auto *req) {
\t\tres->writeHeader("Content-Type", "application/octet-stream");

\t\tbool aborted = false;
\t\tres->onAborted([&aborted]() {
\t\t\taborted = true;
\t\t});

\t\t/* chunked write example */
\t\tstd::string chunk = "data chunk content";
\t\tauto [ok, has_backpressure] = res->tryEnd(chunk, chunk.size() * 3);

\t\tif (!ok) {
\t\t\t/* could not send everything — register writable callback */
\t\t\tres->onWritable([res, chunk](uintptr_t offset) -> bool {
\t\t\t\tauto [ok, done] = res->tryEnd(
\t\t\t\t\tchunk.substr(offset),
\t\t\t\t\tchunk.size()
\t\t\t\t);
\t\t\t\treturn ok;
\t\t\t});
\t\t}
\t});
}
""",
        "function": "streaming_response",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/Streaming.cpp",
    },

    # ── 10. backpressure_handling — getBufferedAmount + drain ──────────────────
    {
        "normalized_code": """\
#include <uWebSockets/App.h>

#include <string>
#include <string_view>

struct XxxData {
\tsize_t pending_bytes = 0;
};

void setup_backpressure(uWS::App &app) {
\tapp.ws<XxxData>("/*", {
\t\t.maxBackpressure = 1024 * 1024,

\t\t.message = [](auto *ws, std::string_view message, uWS::OpCode op_code) {
\t\t\tsize_t buffered = ws->getBufferedAmount();
\t\t\tif (buffered > 512 * 1024) {
\t\t\t\t/* too much backpressure — skip or queue */
\t\t\t\treturn;
\t\t\t}
\t\t\tws->send(message, op_code);
\t\t},

\t\t.drain = [](auto *ws) {
\t\t\tsize_t buffered = ws->getBufferedAmount();
\t\t\tXxxData *data = ws->getUserData();
\t\t\tdata->pending_bytes = buffered;
\t\t\t/* buffer drained — safe to send more data */
\t\t},

\t\t.close = [](auto *ws, int code, std::string_view message) {
\t\t\t/* connection closed */
\t\t}
\t});
}
""",
        "function": "backpressure_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/Backpressure.cpp",
    },
]


# ─── Audit queries ───────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "uwebsockets app setup listen",
    "uwebsockets websocket handler",
    "uwebsockets pub sub pattern",
    "uwebsockets streaming response",
    "uwebsockets SSL configuration",
    "uwebsockets request body reading",
    "uwebsockets backpressure drain",
    "uwebsockets threaded cluster",
]


# ─── Functions ───────────────────────────────────────────────────────────────

def clone_repo() -> None:
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo already cloned: {REPO_LOCAL}")
        return
    print(f"  Cloning {REPO_URL} → {REPO_LOCAL} ...")
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
    )
    print("  Cloned.")


def build_payloads() -> list[dict]:
    payloads = []
    all_violations = []
    for p in PATTERNS:
        v = check_charte_violations(
            p["normalized_code"], p["function"], language=LANGUAGE
        )
        all_violations.extend(v)
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
    if all_violations:
        print("  PRE-INDEX violations:")
        for v in all_violations:
            print(f"    WARN: {v}")
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    print(f"  Embedding {len(codes)} patterns (batch) ...")
    vectors = embed_documents_batch(codes)
    print(f"  {len(vectors)} vectors generated.")

    points = []
    for i, (vec, payload) in enumerate(zip(vectors, payloads)):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
        if (i + 1) % 5 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points prepared")

    print(f"  Upserting {len(points)} points into '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print("  Upsert done.")
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(
            client=client,
            collection=COLLECTION,
            query_vector=vec,
            language=LANGUAGE,
            limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q,
                "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
            })
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
        ),
        limit=100,
    )
    points = scroll_result[0]
    violations = []
    for point in points:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        violations.extend(check_charte_violations(code, fn, language=LANGUAGE))
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
            )
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN (test)' if DRY_RUN else 'PRODUCTION'}")
    print(f"  Language: {LANGUAGE} | Stack: {STACK}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)

    print("── Step 1: Prerequisites")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERROR: collection '{COLLECTION}' not found.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}': {count_initial} points (initial)")

    print("\n── Step 2: Clone")
    clone_repo()

    print(f"\n── Step 3-4: {len(PATTERNS)} patterns extracted and normalized")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads built.")

    print("\n── Step 5: Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count after indexation: {count_after}")

        print("\n── Step 6: Audit")
        print(f"\n  6a. Semantic queries (filtered by language={LANGUAGE}):")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        print("\n  6b. Normalization audit:")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    No violations detected ✓")

    finally:
        print(f"\n── Step 7: {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points deleted. Count final: {count_final}")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")

    count_now = client.count(collection_name=COLLECTION).count
    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_now,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)


if __name__ == "__main__":
    main()
