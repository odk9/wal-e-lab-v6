"""
ingest_spdlog.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de gabime/spdlog dans la KB Qdrant V6.

Focus : Fast C++ logging — basic logger, rotating file logger, daily file logger,
async logger, sinks (stdout, file, syslog), custom formatter, custom sink,
multi-sink logger, backtrace, flush policy, compile-time log level, thread pool.

Usage:
    .venv/bin/python3 ingest_spdlog.py
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
REPO_URL = "https://github.com/gabime/spdlog.git"
REPO_NAME = "gabime/spdlog"
REPO_LOCAL = "/tmp/spdlog"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+spdlog+logging"
CHARTE_VERSION = "1.0"
TAG = "gabime/spdlog"
SOURCE_REPO = "https://github.com/gabime/spdlog"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Spdlog = fast C++ logging library.
# Patterns CORE : basic logger, rotating file, daily file, async logger,
# multi-sink, custom formatter, custom sink, syslog, backtrace,
# flush policy, compile-time level, thread pool.
# Technical terms kept: logger, sink, encoder, level, format, handler, etc.

PATTERNS: list[dict] = [
    # ── 1. Basic Stdout Logger ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>

int main() {
    auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    console_sink->set_level(spdlog::level::debug);

    spdlog::sinks_init_list sink_list = { console_sink };
    auto logger = std::make_shared<spdlog::logger>("console", sink_list);

    logger->set_level(spdlog::level::debug);
    logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%^%l%$] %v");

    logger->info("Application started");
    logger->debug("Debug payload with context");
    logger->warn("Warning: resource limit approaching");
    logger->error("Error occurred: {}", "connection failed");

    return 0;
}
""",
        "function": "basic_stdout_logger_color",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/basic_stdout_logger.cpp",
    },
    # ── 2. Rotating File Logger ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/rotating_file_sink.h>

int main() {
    const size_t max_size = 1048576;
    const size_t max_files = 3;

    auto sink = std::make_shared<spdlog::sinks::rotating_file_sink_mt>(
        "/var/log/app.log", max_size, max_files
    );
    sink->set_level(spdlog::level::info);

    auto logger = std::make_shared<spdlog::logger>("file_logger", sink);
    logger->set_level(spdlog::level::debug);
    logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%l] %v");

    logger->info("Rotating file logger initialized");
    logger->debug("Debug: rotation triggers at {} bytes", max_size);
    logger->info("Request processed", 200);

    return 0;
}
""",
        "function": "rotating_file_logger_bysize",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/rotating_file_logger.cpp",
    },
    # ── 3. Daily File Logger ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/daily_file_sink.h>

int main() {
    auto sink = std::make_shared<spdlog::sinks::daily_file_sink_mt>(
        "/var/log/app", 2, 30
    );
    sink->set_level(spdlog::level::info);

    auto logger = std::make_shared<spdlog::logger>("daily_logger", sink);
    logger->set_level(spdlog::level::debug);
    logger->set_pattern("[%Y-%m-%d %H:%M:%S] [%l] %v");

    logger->info("Daily logger created");
    logger->debug("New log file at 2:30 AM every day");
    logger->info("LogEntry logged with timestamp: {}", "2026-03-31T10:15:00Z");

    return 0;
}
""",
        "function": "daily_file_logger_timestamp",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/daily_file_logger.cpp",
    },
    # ── 4. Async Logger Setup ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/async.h>
#include <spdlog/sinks/stdout_color_sinks.h>

int main() {
    spdlog::init_thread_pool(8192, 1);

    auto sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    std::vector<spdlog::sink_ptr> sinks{ sink };

    auto async_logger = std::make_shared<spdlog::async_logger>(
        "async_logger", sinks.begin(), sinks.end(),
        spdlog::thread_pool(), spdlog::async_overflow_policy::block
    );

    async_logger->set_level(spdlog::level::info);
    async_logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%l] %v");
    async_logger->flush_on(spdlog::level::err);

    async_logger->info("Async logger running");
    async_logger->debug("Non-blocking append to queue");

    spdlog::drop_all();
    return 0;
}
""",
        "function": "async_logger_thread_pool_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/async_logger.cpp",
    },
    # ── 5. Multi-Sink Logger ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/rotating_file_sink.h>

int main() {
    std::vector<spdlog::sink_ptr> sinks;

    auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    console_sink->set_level(spdlog::level::warn);
    sinks.push_back(console_sink);

    auto file_sink = std::make_shared<spdlog::sinks::rotating_file_sink_mt>(
        "/var/log/app.log", 1048576, 3
    );
    file_sink->set_level(spdlog::level::debug);
    sinks.push_back(file_sink);

    auto logger = std::make_shared<spdlog::logger>("multi_sink", sinks.begin(), sinks.end());
    logger->set_level(spdlog::level::debug);
    logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%l] %v");

    logger->debug("Debug to file only");
    logger->warn("Warning to both console and file");

    return 0;
}
""",
        "function": "multi_sink_logger_levels",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/multi_sink_logger.cpp",
    },
    # ── 6. Custom Formatter Pattern ───────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>

int main() {
    auto sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();

    auto logger = std::make_shared<spdlog::logger>("custom_format", sink);

    logger->set_pattern("[%H:%M:%S] [%^%l%$] [%n:%@] %v");

    logger->info("Custom format with thread id: {}", 123);
    logger->warn("Warning at line: {}", __LINE__);
    logger->error("Error in function: {}", __func__);

    logger->set_pattern("[%Y-%m-%d] [%l] %v [%s:%#]");
    logger->info("Changed pattern with source location");

    return 0;
}
""",
        "function": "custom_formatter_pattern_config",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/custom_formatter.cpp",
    },
    # ── 7. Custom Sink Implementation ─────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/base_sink.h>

class CustomSink : public spdlog::sinks::base_sink<std::mutex> {
    void sink_it_(const spdlog::details::log_msg& msg) override {
        spdlog::memory_buf_t formatted;
        sink->formatter()->format(msg, formatted);

        std::string output = fmt::to_string(formatted);
        ProcessLogMessage(output);
    }

    void flush_() override {
        FlushStorage();
    }

private:
    void ProcessLogMessage(const std::string& msg) {
        std::cerr << "[CUSTOM] " << msg;
    }

    void FlushStorage() {
        std::cerr << "Flushed" << std::endl;
    }
};

int main() {
    auto custom_sink = std::make_shared<CustomSink>();
    auto logger = std::make_shared<spdlog::logger>("custom_sink", custom_sink);

    logger->info("Custom sink processing");
    logger->flush();

    return 0;
}
""",
        "function": "custom_sink_implementation_base",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/custom_sink.cpp",
    },
    # ── 8. Syslog Logger ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/syslog_sink.h>

int main() {
    std::string ident = "myapp";
    int syslog_facility = LOG_USER;

    auto syslog_sink = std::make_shared<spdlog::sinks::syslog_sink_mt>(
        ident, syslog_facility, false
    );

    auto logger = std::make_shared<spdlog::logger>("syslog_logger", syslog_sink);
    logger->set_level(spdlog::level::info);
    logger->set_pattern("[%n] [%l] %v");

    logger->info("Application started via syslog");
    logger->warn("System resource warning");
    logger->error("Critical error logged to syslog");

    return 0;
}
""",
        "function": "syslog_logger_system_integration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/syslog_logger.cpp",
    },
    # ── 9. Backtrace Logger ───────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>

int main() {
    auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    auto logger = std::make_shared<spdlog::logger>("backtrace_logger", console_sink);

    logger->set_level(spdlog::level::debug);
    logger->enable_backtrace(32);

    logger->debug("Debug payload 1");
    logger->debug("Debug payload 2");
    logger->debug("Debug payload 3");

    logger->info("Error detected, dumping backtrace");
    logger->dump_backtrace();

    return 0;
}
""",
        "function": "backtrace_logger_ringbuffer",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/backtrace_logger.cpp",
    },
    # ── 10. Flush Policy Configuration ────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>

int main() {
    auto sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    auto logger = std::make_shared<spdlog::logger>("flush_policy", sink);

    logger->set_level(spdlog::level::debug);
    logger->set_pattern("[%Y-%m-%d %H:%M:%S] [%l] %v");

    logger->flush_on(spdlog::level::err);

    logger->debug("Debug message, buffered");
    logger->info("Info message, buffered");
    logger->warn("Warning, buffered");
    logger->error("Error forces flush to disk");

    logger->flush();

    return 0;
}
""",
        "function": "flush_policy_level_configuration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/flush_policy_logger.cpp",
    },
    # ── 11. Compile-Time Log Level ────────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>

#define SPDLOG_ACTIVE_LEVEL SPDLOG_LEVEL_DEBUG

int ProcessRequest(int request_id) {
    SPDLOG_DEBUG("Processing request {}", request_id);
    SPDLOG_INFO("Request {} accepted", request_id);
    SPDLOG_WARN("Request {} slow", request_id);

    return 0;
}

int main() {
    auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    auto logger = std::make_shared<spdlog::logger>("compile_level", console_sink);

    spdlog::set_default_logger(logger);
    spdlog::set_level(spdlog::level::debug);

    ProcessRequest(123);

    return 0;
}
""",
        "function": "compile_time_level_macro_active",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/compile_time_level.cpp",
    },
    # ── 12. Thread Pool Configuration ─────────────────────────────────────────
    {
        "normalized_code": """\
#include <spdlog/spdlog.h>
#include <spdlog/async.h>
#include <spdlog/sinks/rotating_file_sink.h>

int main() {
    size_t queue_size = 16384;
    size_t thread_count = 2;

    spdlog::init_thread_pool(queue_size, thread_count);

    auto file_sink = std::make_shared<spdlog::sinks::rotating_file_sink_mt>(
        "/var/log/app.log", 1048576, 3
    );

    std::vector<spdlog::sink_ptr> sinks{ file_sink };

    auto async_logger = std::make_shared<spdlog::async_logger>(
        "async_thread_pool", sinks.begin(), sinks.end(),
        spdlog::thread_pool(),
        spdlog::async_overflow_policy::block
    );

    async_logger->set_level(spdlog::level::info);
    async_logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%l] %v");

    async_logger->info("Async logger with thread pool configured");

    spdlog::drop_all();
    return 0;
}
""",
        "function": "thread_pool_config_queue_size",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/thread_pool_logger.cpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "basic logger stdout color console output",
    "rotating file logger size-based rotation backup",
    "daily file logger timestamp rotation schedule",
    "async logger thread pool non-blocking queue",
    "multi-sink logger different level per sink",
    "custom formatter pattern color codes",
    "custom sink base implementation derive",
    "syslog logger system integration facility",
    "backtrace logger ringbuffer enable dump",
    "flush policy error level forced flush",
    "compile-time log level macro active",
    "C++ spdlog logging configuration setup",
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
