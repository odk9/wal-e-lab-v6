"""
ingest_cpp_httplib.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de yhirose/cpp-httplib dans la KB Qdrant V6.

Focus : CORE patterns HTTP server/client (GET/POST routes, static files, SSL,
multipart, streaming, thread pool, error handlers, logging, redirects).

Usage:
    .venv/bin/python3 ingest_cpp_httplib.py
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
REPO_URL = "https://github.com/yhirose/cpp-httplib.git"
REPO_NAME = "yhirose/cpp-httplib"
REPO_LOCAL = "/tmp/cpp-httplib"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+httplib+http+api"
CHARTE_VERSION = "1.0"
TAG = "yhirose/cpp-httplib"
SOURCE_REPO = "https://github.com/yhirose/cpp-httplib"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# cpp-httplib = header-only C++ HTTP server/client library.
# Patterns CORE : server GET/POST routes, static files, SSL, multipart, streaming,
# thread pool, error handlers, middleware, redirects.
# U-5 : Keep HTTP terms (server, client, request, response, header, handler).

PATTERNS: list[dict] = [
    # ── 1. Server GET Route ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>

int main() {
    httplib::Server server;

    server.Get("/api/xxx", [](const httplib::Request &request, httplib::Response &response) {
        std::string xxx_id = request.get_param_value("id");
        if (xxx_id.empty()) {
            response.set_content("Missing id parameter", "text/plain");
            response.status = 400;
            return;
        }

        std::string result = "{\"id\": " + xxx_id + ", \"name\": \"example\"}";
        response.set_content(result, "application/json");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "server_get_route",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "example/server_get.cpp",
    },
    # ── 2. Server POST with JSON ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main() {
    httplib::Server server;

    server.submit("/api/xxxs", [](const httplib::Request &request, httplib::Response &response) {
        if (request.body.empty()) {
            response.status = 400;
            response.set_content("{\"error\": \"empty body\"}", "application/json");
            return;
        }

        try {
            json payload = json::parse(request.body);
            std::string name = payload["name"];
            int value = payload["value"];

            json result = {
                {"status", "created"},
                {"id", 123},
                {"name", name},
                {"value", value}
            };
            response.set_content(result.dump(), "application/json");
            response.status = 201;
        } catch (const std::exception &e) {
            response.status = 422;
            response.set_content("{\"error\": \"invalid json\"}", "application/json");
        }
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "server_post_json",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "example/server_post_json.cpp",
    },
    # ── 3. Server Static Files ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>

int main() {
    httplib::Server server;

    server.set_base_dir("./public");

    server.Get("/", [](const httplib::Request &request, httplib::Response &response) {
        response.set_redirect("/index.html");
    });

    server.Get("/static/<path>", [](const httplib::Request &request, httplib::Response &response) {
        std::string path = request.matches[1];
        if (!server.read_and_close_socket(response.get_socket(), path)) {
            response.status = 404;
            response.set_content("Not found", "text/plain");
        }
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "server_static_files",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "example/server_static.cpp",
    },
    # ── 4. Client GET Request ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <iostream>

int main() {
    httplib::Client client("https://api.example.com");

    if (!client.is_connection_alive()) {
        std::cerr << "Cannot connect to server" << std::endl;
        return 1;
    }

    auto response = client.Get("/api/xxxs?id=123");

    if (response && response->status == 200) {
        std::cout << "Response: " << response->body << std::endl;
    } else if (response) {
        std::cout << "Status: " << response->status << std::endl;
    } else {
        std::cerr << "Request failed" << std::endl;
    }

    return 0;
}
""",
        "function": "client_get_request",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/client_get.cpp",
    },
    # ── 5. Client POST with JSON ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main() {
    httplib::Client client("https://api.example.com");

    json payload = {
        {"name", "test"},
        {"value", 42}
    };

    auto response = client.submit("/api/xxxs", payload.dump(), "application/json");

    if (response && response->status == 201) {
        std::cout << "Created: " << response->body << std::endl;
    } else if (response) {
        std::cout << "Status: " << response->status << std::endl;
    } else {
        std::cerr << "request failed" << std::endl;
    }

    return 0;
}
""",
        "function": "client_post_json",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/client_post.cpp",
    },
    # ── 6. SSL Server Configuration ──────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>

int main() {
    httplib::SSLServer server(
        "server.crt",
        "server.key"
    );

    if (!server) {
        std::cerr << "Failed to initialize SSL server" << std::endl;
        return 1;
    }

    server.Get("/api/secure", [](const httplib::Request &request, httplib::Response &response) {
        response.set_content("Secure data", "text/plain");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8443);
    return 0;
}
""",
        "function": "ssl_server_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "example/ssl_server.cpp",
    },
    # ── 7. Multipart Form Upload ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <fstream>

int main() {
    httplib::Server server;

    server.Submit("/upload", [](const httplib::Request &request, httplib::Response &response) {
        for (size_t i = 0; i < request.files.size(); ++i) {
            const auto &file = request.files[i];
            std::string filename = file.second.filename;
            const auto &content = file.second.content;

            std::ofstream output(filename, std::ios::binary);
            output.write(content.data(), content.size());
            output.close();
        }

        response.set_content("Files uploaded successfully", "text/plain");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "multipart_form_upload",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "example/multipart_upload.cpp",
    },
    # ── 8. Content Reader (Streaming) ────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>

int main() {
    httplib::Server server;

    server.Submit("/stream", [](const httplib::Request &request, httplib::Response &response,
                               const httplib::ContentReader &content_reader) {
        std::string chunk;
        content_reader([&](const char *data, size_t len) {
            chunk.append(data, len);
            if (chunk.length() > 1024) {
                std::cout << "Received " << chunk.length() << " bytes" << std::endl;
                chunk.clear();
            }
            return true;
        });

        response.set_content("Stream received", "text/plain");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "content_reader_streaming",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/streaming_content.cpp",
    },
    # ── 9. Thread Pool Configuration ─────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <thread>

int main() {
    httplib::Server server;

    server.set_post_routing_handler([](const httplib::Request &, httplib::Response &) {
        return httplib::Server::HandlerResponse::Unhandled;
    });

    server.set_thread_pool_size(16, 1);

    server.Get("/api/xxx", [](const httplib::Request &request, httplib::Response &response) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        response.set_content("Response from thread pool", "text/plain");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "thread_pool_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "example/thread_pool.cpp",
    },
    # ── 10. Custom Error Handler ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main() {
    httplib::Server server;

    server.set_exception_handler([](const httplib::Request &request, httplib::Response &response, std::exception_ptr ep) {
        try {
            std::rethrow_exception(ep);
        } catch (const std::exception &e) {
            json error = {
                {"error", "internal_error"},
                {"detail", e.what()},
                {"path", request.path}
            };
            response.set_content(error.dump(), "application/json");
            response.status = 500;
        }
    });

    server.set_error_handler([](const httplib::Request &request, httplib::Response &response) {
        json error = {
            {"error", "not_found"},
            {"path", request.path},
            {"status", response.status}
        };
        response.set_content(error.dump(), "application/json");
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "error_handler_custom",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/error_handlers.cpp",
    },
    # ── 11. Logger Middleware ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>
#include <iostream>
#include <iomanip>
#include <sstream>

int main() {
    httplib::Server server;

    server.set_pre_routing_handler([](const httplib::Request &request, httplib::Response &response) {
        auto now = std::chrono::system_clock::now();
        auto time = std::chrono::system_clock::to_time_t(now);

        std::cout << std::put_time(std::localtime(&time), "%Y-%m-%d %H:%M:%S")
                  << " [" << request.method << "] " << request.path;
        if (!request.query_string.empty()) {
            std::cout << "?" << request.query_string;
        }
        std::cout << std::endl;
        return httplib::Server::HandlerResponse::Unhandled;
    });

    server.Get("/api/xxx", [](const httplib::Request &request, httplib::Response &response) {
        response.set_content("OK", "text/plain");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "logger_middleware",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/logging.cpp",
    },
    # ── 12. Redirect Handler ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <httplib.h>

int main() {
    httplib::Server server;

    server.Get("/", [](const httplib::Request &request, httplib::Response &response) {
        response.set_redirect("/home");
    });

    server.Get("/old-path", [](const httplib::Request &request, httplib::Response &response) {
        response.set_redirect("/new-path", httplib::StatusCode::MovedPermanently_301);
    });

    server.Get("/home", [](const httplib::Request &request, httplib::Response &response) {
        response.set_content("Welcome to home", "text/html");
        response.status = 200;
    });

    server.Get("/new-path", [](const httplib::Request &request, httplib::Response &response) {
        response.set_content("New location", "text/html");
        response.status = 200;
    });

    server.listen("0.0.0.0", 8080);
    return 0;
}
""",
        "function": "redirect_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "example/redirects.cpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "server GET route HTTP request response",
    "server POST JSON payload request body",
    "server static files public directory",
    "client GET request connection",
    "client POST JSON request header",
    "SSL server certificate key HTTPS",
    "multipart form upload files POST",
    "content reader streaming callback",
    "thread pool configuration server",
    "error handler exception custom",
    "logger middleware pre routing request",
    "redirect handler moved permanently",
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
