"""
ingest_otel_python.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de open-telemetry/opentelemetry-python dans la KB Qdrant V6.

Focus : CORE patterns observability SDK (TracerProvider setup, span creation,
context propagation, metrics, logging, batch processing, OTLP export).

Usage:
    .venv/bin/python3 ingest_otel_python.py
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
REPO_URL = "https://github.com/open-telemetry/opentelemetry-python.git"
REPO_NAME = "open-telemetry/opentelemetry-python"
REPO_LOCAL = "/tmp/opentelemetry-python"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+opentelemetry+tracing+metrics"
CHARTE_VERSION = "1.0"
TAG = "open-telemetry/opentelemetry-python"
SOURCE_REPO = "https://github.com/open-telemetry/opentelemetry-python"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# OpenTelemetry = observability SDK (tracing + metrics + logging).
# Patterns CORE : TracerProvider setup, span creation, context propagation,
# metrics (counter, histogram, gauge), batch processing, OTLP exporters.
# U-5 : remplacer service → resource, span_event → signal (sauf pour span events)

PATTERNS: list[dict] = [
    # ── 1. TracerProvider setup with Resource ─────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracer_provider(endpoint: str = "http://localhost:4317") -> TracerProvider:
    \"\"\"Initialize TracerProvider with OTLP gRPC exporter and resource detection.\"\"\"
    resource = Resource.create({
        "xxx.name": "service",
        "xxx.version": "1.0.0",
        "xxx.namespace": "production",
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return provider
""",
        "function": "tracer_provider_setup_otlp_grpc",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 2. Create and configure tracer ────────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.trace import Tracer


def get_tracer(name: str, version: str | None = None) -> Tracer:
    \"\"\"Get a tracer instance from the global provider.\"\"\"
    provider = trace.get_tracer_provider()
    return provider.get_tracer(name, version=version, schema_url="")
""",
        "function": "get_tracer_instance",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 3. Start and end spans (basic pattern) ────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


def trace_operation(tracer) -> None:
    \"\"\"Start a span as current context using context manager.\"\"\"
    with tracer.start_as_current_span("xxx_operation") as span:
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.status_code", 200)
        try:
            result = perform_work()
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise
""",
        "function": "span_start_end_context_manager",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 4. Span attributes and span signals ──────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace


def record_span_metadata(tracer) -> None:
    \"\"\"Set span attributes and record span signals.\"\"\"
    with tracer.start_as_current_span("xxx_request") as span:
        span.set_attribute("xxx.id", 42)
        span.set_attribute("xxx.version", "v1")
        span.set_attribute("xxx.status", "completed")
        span.add_event(
            name="xxx_signal",
            attributes={
                "signal.type": "checkpoint",
                "signal.detail": "processing started",
            },
        )
        span.add_event("xxx_signal_final", {"signal.phase": "done"})
""",
        "function": "span_attributes_and_signals",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 5. Context propagation (inject/extract) ──────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.propagators.jaeger_trace import JaegerPropagator
from opentelemetry.propagators.textmap import TextMapPropagator


def propagate_context_http(
    tracer,
    headers_out: dict,
    headers_in: dict | None = None,
) -> None:
    \"\"\"Inject trace context into HTTP headers and extract from incoming.\"\"\"
    propagator: TextMapPropagator = JaegerPropagator()
    ctx = trace.get_current_span().get_span_context()
    carrier = {}
    propagator.inject(carrier, headers=headers_out)
    if headers_in:
        extracted_ctx = propagator.extract(headers_in)
        with trace.get_tracer(__name__).start_as_current_span(
            "xxx_child", context=extracted_ctx
        ) as span:
            span.set_attribute("xxx.propagated", True)
""",
        "function": "context_propagation_inject_extract",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 6. MeterProvider setup with OTLP ──────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader


def setup_meter_provider(endpoint: str = "http://localhost:4317") -> MeterProvider:
    \"\"\"Initialize MeterProvider with OTLP metric exporter.\"\"\"
    resource = Resource.create({"xxx.name": "service"})
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        interval_millis=60_000,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider
""",
        "function": "meter_provider_setup_otlp",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/metrics/__init__.py",
    },
    # ── 7. Counter instrument ─────────────────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import metrics


def create_and_record_counter(meter) -> None:
    \"\"\"Create a counter metric and record increments.\"\"\"
    counter = meter.create_counter(
        name="xxx_total",
        description="Total xxx operations",
        unit="1",
    )
    counter.add(
        amount=1,
        attributes={"xxx.type": "success", "xxx.endpoint": "/api/v1"},
    )
    counter.add(
        amount=3,
        attributes={"xxx.type": "failure", "xxx.reason": "timeout"},
    )
""",
        "function": "counter_metric_create_record",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/metrics/__init__.py",
    },
    # ── 8. Histogram and gauge instruments ────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import metrics


def record_histogram_and_gauge(meter) -> None:
    \"\"\"Record histogram (distribution) and gauge (current value) metrics.\"\"\"
    histogram = meter.create_histogram(
        name="xxx_duration_ms",
        description="Duration of xxx operations",
        unit="ms",
    )
    gauge = meter.create_gauge(
        name="xxx_size_bytes",
        description="Current size of xxx buffer",
        unit="byte",
    )
    histogram.record(45, attributes={"xxx.layer": "database"})
    histogram.record(120, attributes={"xxx.layer": "network"})
    gauge.callback(lambda _: [
        (512_000, {"xxx.pool": "A"}),
        (768_000, {"xxx.pool": "B"}),
    ])
""",
        "function": "histogram_gauge_metrics",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/metrics/__init__.py",
    },
    # ── 9. BatchSpanProcessor configuration ───────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_batch_processor(provider: TracerProvider, endpoint: str) -> None:
    \"\"\"Configure batch span processor with custom queue and export parameters.\"\"\"
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = BatchSpanProcessor(
        exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5_000,
        export_timeout_millis=30_000,
    )
    provider.add_span_processor(processor)
""",
        "function": "batch_span_processor_config",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "opentelemetry/sdk/trace/export/__init__.py",
    },
    # ── 10. Span links and relationships ──────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.trace import Link, SpanContext, TraceFlags, TraceState


def create_span_with_links(tracer) -> None:
    \"\"\"Create a span with links to related spans (correlation).\"\"\"
    parent_ctx = SpanContext(
        trace_id=0x1234567890abcdef,
        span_id=0xfedcba09876543210,
        is_remote=True,
        trace_flags=TraceFlags(0x01),
        trace_state=TraceState.create({"vendor": "value"}),
    )
    link = Link(parent_ctx, attributes={"xxx.relation": "caused-by"})
    with tracer.start_as_current_span(
        "xxx_async_job",
        links=[link],
        attributes={"xxx.queue": "priority"},
    ) as span:
        span.set_attribute("xxx.correlated", True)
""",
        "function": "span_links_and_relationships",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
    # ── 11. OTLP HTTP exporter alternative ────────────────────────────────────
    {
        "normalized_code": """\
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_otlp_http_exporter(
    provider: TracerProvider,
    endpoint: str = "http://localhost:4318/v1/traces",
) -> None:
    \"\"\"Configure OTLP HTTP exporter as alternative to gRPC.\"\"\"
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        timeout=10,
        headers={"Authorization": "Bearer token"},
    )
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
""",
        "function": "otlp_http_exporter_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "opentelemetry/exporter/otlp/proto/http/trace_exporter/__init__.py",
    },
    # ── 12. Exception handling and span status ───────────────────────────────
    {
        "normalized_code": """\
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


def handle_exception_in_span(tracer) -> None:
    \"\"\"Properly record exceptions and set error status on spans.\"\"\"
    try:
        with tracer.start_as_current_span("xxx_risky_operation") as span:
            raise ValueError("xxx validation failed")
    except ValueError as exc:
        span.record_exception(exc)
        span.set_status(
            Status(
                StatusCode.ERROR,
                description=f"xxx error: {exc.__class__.__name__}",
            )
        )
    except Exception as exc:
        span.set_status(Status(StatusCode.ERROR))
        span.set_attribute("exception.xxx", str(exc))
        raise
""",
        "function": "exception_handling_span_status",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "opentelemetry/sdk/trace/__init__.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "OpenTelemetry TracerProvider setup with OTLP gRPC exporter",
    "create tracer instance get_tracer global provider",
    "start span as current context manager with attributes",
    "record span events and attributes for observability",
    "inject extract context propagation HTTP headers",
    "MeterProvider setup OTLP metrics export",
    "create counter metric instrument record",
    "histogram gauge metrics measurement recording",
    "BatchSpanProcessor queue size export configuration",
    "span links correlation async job relationships",
    "OTLP HTTP exporter alternative gRPC protocol",
    "exception handling record exception span status error",
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
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
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
