"""
ingest_structlog.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de structlog (structured logging pour Python) dans la KB Qdrant V6.

Focus : Patterns de logging structuré — configuration structlog, processors
(timestamper, json renderer, console renderer, add_log_level), binding context,
filtering events, stdlib integration, custom processors, exception rendering,
thread-local context, async support, testing avec CapturingLogger.

Usage:
    .venv/bin/python3 ingest_structlog.py
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
REPO_URL = "https://github.com/hynek/structlog.git"
REPO_NAME = "hynek/structlog"
REPO_LOCAL = "/tmp/structlog"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+structlog+logging"
CHARTE_VERSION = "1.0"
TAG = "hynek/structlog"
SOURCE_REPO = "https://github.com/hynek/structlog"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# structlog = structured logging library for Python.
# Patterns CORE : configuration, processors, context binding, filtering, stdlib integration.
# U-5 : `logger`, `processor`, `handler`, `formatter`, `filter`, `level`, `stream` sont OK (TECHNICAL_TERMS).

PATTERNS: list[dict] = [
    # ── 1. Configure structlog with processors chain ───────────────────────
    {
        "normalized_code": """\
import structlog


def configure_xxx_logger():
    \"\"\"Configure structlog with standard processor chain.

    Sets up JSON rendering to file, console pretty-print,
    and context binding.
    \"\"\"
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
""",
        "function": "configure_structlog_processors",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "src/structlog/__init__.py",
    },
    # ── 2. Bind context variables to logger ───────────────────────────────
    {
        "normalized_code": """\
import structlog


def bind_xxx_context(logger, user_id: int, request_id: str):
    \"\"\"Bind context variables (immutable copy).

    Returns new logger with context attached. Original logger
    remains unchanged.
    \"\"\"
    logger = logger.bind(user_id=user_id, request_id=request_id)
    return logger


def unbind_xxx_context(logger, *keys: str):
    \"\"\"Remove keys from logger context.

    Returns new logger with specified keys removed.
    \"\"\"
    logger = logger.unbind(*keys)
    return logger
""",
        "function": "bind_unbind_context_variables",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/_loggers.py",
    },
    # ── 3. JSON renderer processor ───────────────────────────────────────
    {
        "normalized_code": """\
import json
from structlog.processors import JSONRenderer


def create_json_renderer_processor():
    \"\"\"Create processor that renders log log_entry as JSON.

    Converts structured log_entry dict to JSON line, suitable
    for log aggregation systems (ELK, DataDog, Splunk).
    \"\"\"
    return JSONRenderer(serializer=json.dumps)


class CustomJsonRenderer:
    \"\"\"Custom JSON renderer with field ordering.\"\"\"

    def __call__(self, logger, name: str, log_entry_dict: dict) -> str:
        \"\"\"Render log_entry_dict to JSON with timestamp first.\"\"\"
        ordered = {
            "timestamp": log_entry_dict.pop("timestamp", ""),
            "level": log_entry_dict.pop("level", "info"),
            "logger": log_entry_dict.pop("logger_name", ""),
        }
        ordered.update(log_entry_dict)
        return json.dumps(ordered)
""",
        "function": "json_renderer_processor_setup",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 4. Console renderer for pretty-print ─────────────────────────────
    {
        "normalized_code": """\
from structlog.processors import KeyValueRenderer


def create_console_renderer_processor():
    \"\"\"Create processor for human-readable console output.

    Outputs key=value format, suitable for development
    and local debugging.
    \"\"\"
    return KeyValueRenderer(key_order=["timestamp", "level", "logger_name"])


class ColoredConsoleRenderer:
    \"\"\"Console renderer with color codes for severity.\"\"\"

    COLORS = {
        "debug": "\\033[36m",    # cyan
        "info": "\\033[32m",     # green
        "warning": "\\033[33m",  # yellow
        "error": "\\033[31m",    # red
        "critical": "\\033[35m", # magenta
    }
    RESET = "\\033[0m"

    def __call__(self, logger, name: str, log_entry_dict: dict) -> str:
        level = log_entry_dict.get("level", "info").lower()
        color = self.COLORS.get(level, "")
        msg = log_entry_dict.get("log_entry", "")
        return f"{color}{level.upper()}{self.RESET} {msg}"
""",
        "function": "console_renderer_pretty_print",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 5. Timestamper processor ─────────────────────────────────────────
    {
        "normalized_code": """\
from datetime import datetime, timezone
from structlog.processors import TimeStamper


def create_timestamper_processor():
    \"\"\"Create processor that adds ISO8601 timestamp to log_entries.

    Uses UTC timezone, formats as 2026-03-31T14:30:45.123Z.
    \"\"\"
    return TimeStamper(fmt="iso", utc=True, key="timestamp")


class CustomTimestamper:
    \"\"\"Custom timestamper with millisecond precision.\"\"\"

    def __call__(self, logger, name: str, event_dict: dict) -> dict:
        event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        return event_dict
""",
        "function": "timestamper_processor_iso8601",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 6. Filter events by severity level ───────────────────────────────
    {
        "normalized_code": """\
import logging
from structlog.stdlib import filter_by_level


def configure_xxx_with_filter(min_level: str = "info"):
    \"\"\"Configure stdlib logger with minimum level filter.

    Log_entries below min_level are discarded before processing.
    \"\"\"
    level_num = getattr(logging, min_level.upper(), logging.INFO)

    logging.basicConfig(level=level_num)

    root_logger = logging.getLogger()
    root_logger.setLevel(level_num)


class CustomLevelFilter:
    \"\"\"Filter processor that rejects log_entries below threshold.\"\"\"

    def __init__(self, min_level: str = "info"):
        self.min_level = min_level
        self.level_order = ["debug", "info", "warning", "error", "critical"]
        self.min_rank = self.level_order.index(min_level.lower())

    def __call__(self, logger, name: str, log_entry_dict: dict) -> dict:
        level = log_entry_dict.get("level", "info").lower()
        if self.level_order.index(level) < self.min_rank:
            raise structlog.DropEvent()
        return log_entry_dict
""",
        "function": "filter_events_by_level",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 7. Stdlib integration (bridge to logging) ──────────────────────────
    {
        "normalized_code": """\
import logging
import structlog


def configure_stdlib_integration():
    \"\"\"Configure structlog to use stdlib logger factory.

    Allows mix of structlog and stdlib logging in same app.
    Stdlib loggers automatically route through structlog processors.
    \"\"\"
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    return root
""",
        "function": "stdlib_logger_integration",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "src/structlog/stdlib.py",
    },
    # ── 8. Custom processor for business logic ──────────────────────────────
    {
        "normalized_code": """\
import time
from typing import Dict, Any


class DurationProcessor:
    \"\"\"Custom processor that measures and logs operation duration.\"\"\"

    def __init__(self):
        self.start_time = None

    def __call__(self, logger, name: str, log_entry_dict: Dict[str, Any]) -> Dict[str, Any]:
        if log_entry_dict.get("log_entry") == "xxx_started":
            self.start_time = time.time()
            return log_entry_dict

        if log_entry_dict.get("log_entry") == "xxx_completed":
            if self.start_time:
                duration = time.time() - self.start_time
                log_entry_dict["duration_ms"] = round(duration * 1000, 2)
                self.start_time = None

        return log_entry_dict


class MaskSensitiveProcessor:
    \"\"\"Mask PII from log_entry_dict before rendering.\"\"\"

    SENSITIVE_KEYS = {"password", "token", "api_key", "secret", "ssn"}

    def __call__(self, logger, name: str, log_entry_dict: Dict[str, Any]) -> Dict[str, Any]:
        for key in self.SENSITIVE_KEYS:
            if key in log_entry_dict:
                log_entry_dict[key] = "***REDACTED***"
        return log_entry_dict
""",
        "function": "custom_processor_duration_masking",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 9. Exception rendering with traceback ──────────────────────────────
    {
        "normalized_code": """\
import sys
import traceback
from structlog.processors import format_exc_info


def render_xxx_exception(logger, name: str, event_dict: dict) -> dict:
    \"\"\"Render exception info to formatted traceback string.

    Converts (exc_type, exc_value, exc_tb) tuple to readable string.
    \"\"\"
    if "exc_info" in event_dict:
        exc_info = event_dict.pop("exc_info")
        if exc_info is True:
            exc_info = sys.exc_info()

        if exc_info:
            event_dict["exception"] = "".join(
                traceback.format_exception(*exc_info)
            )

    return event_dict


class StructuredExceptionRenderer:
    \"\"\"Render exception as structured JSON with stack trace.\"\"\"

    def __call__(self, logger, name: str, log_entry_dict: dict) -> dict:
        if "exc_info" in log_entry_dict:
            exc_info = log_entry_dict.pop("exc_info")
            if exc_info is True:
                exc_info = sys.exc_info()

            if exc_info and exc_info[0] is not None:
                log_entry_dict["exception"] = {
                    "type": exc_info[0].__name__,
                    "payload": str(exc_info[1]),
                    "traceback": traceback.format_tb(exc_info[2]),
                }

        return log_entry_dict
""",
        "function": "exception_rendering_traceback",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/processors.py",
    },
    # ── 10. Thread-local context storage ────────────────────────────────────
    {
        "normalized_code": """\
import threading
from typing import Any, Dict


class ThreadLocalContext:
    \"\"\"Store logger context in thread-local storage.

    Each thread has isolated context dict, useful for web frameworks
    where each request runs in a thread.
    \"\"\"

    _local = threading.local()

    @classmethod
    def bind(cls, **kwargs: Any) -> None:
        if not hasattr(cls._local, "context"):
            cls._local.context = {}
        cls._local.context.update(kwargs)

    @classmethod
    def get(cls) -> Dict[str, Any]:
        if not hasattr(cls._local, "context"):
            cls._local.context = {}
        return cls._local.context.copy()

    @classmethod
    def clear(cls) -> None:
        cls._local.context = {}


def configure_xxx_thread_local():
    \"\"\"Configure structlog with thread-local context factory.\"\"\"
    import structlog
    structlog.configure(
        context_class=ThreadLocalContext.get,
        logger_factory=structlog.PrintLoggerFactory(),
    )
""",
        "function": "thread_local_context_storage",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/structlog/_context.py",
    },
    # ── 11. Async logging support ──────────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
import structlog


async def configure_async_xxx_logger():
    \"\"\"Configure structlog for async applications.

    Uses queue-based logger factory for thread-safe
    log_entry dispatching in async context.
    \"\"\"
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    return logger


async def log_async_event():
    \"\"\"Log log_entries from async context.\"\"\"
    logger = structlog.get_logger()
    logger.info("xxx_async_event", user_id=1, log_entry="processed")
    await asyncio.sleep(0.1)
    logger.info("xxx_async_complete")
""",
        "function": "async_logging_support",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "src/structlog/async_support.py",
    },
    # ── 12. Testing with CapturingLogger ────────────────────────────────────
    {
        "normalized_code": """\
import pytest
from structlog.testing import CapturingLogger


@pytest.fixture
def capturing_logger():
    \"\"\"Fixture for capturing logged log_entries in tests.\"\"\"
    return CapturingLogger()


def test_xxx_logging(capturing_logger):
    \"\"\"Test that log_entries are logged with correct structure.\"\"\"
    logger = capturing_logger

    logger.msg("test_event", user_id=42, status="ok")
    logger.msg("second_event", duration_ms=100)

    assert len(logger.calls) == 2
    assert logger.calls[0].method_name == "msg"
    assert logger.calls[0].kwargs == {"user_id": 42, "status": "ok"}

    captured = logger.calls[0]
    assert captured.log_entry == "test_event"


def test_xxx_context_binding(capturing_logger):
    \"\"\"Test context binding and unbinding.\"\"\"
    logger = capturing_logger.bind(request_id="abc123")

    logger.msg("xxx_event")

    call = logger.calls[0]
    assert call.log_entry == "xxx_event"
""",
        "function": "testing_capturing_logger",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_structlog_logging.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "configure structlog with processors chain",
    "bind context variables to logger",
    "JSON renderer processor for log events",
    "console renderer pretty-print output",
    "timestamper processor ISO8601",
    "filter events by severity level",
    "stdlib logger integration bridge",
    "custom processor for business logic",
    "exception rendering with traceback",
    "thread-local context storage",
    "async logging support asyncio",
    "testing with capturing logger fixture",
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
