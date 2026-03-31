"""
ingest_otel_go.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'OpenTelemetry Go (observability SDK) dans la KB Qdrant V6.

Focus : CORE patterns observability SDK (tracing, metrics, context propagation,
span lifecycle, resource, BatchSpanProcessor, TextMapPropagator).

Usage:
    .venv/bin/python3 ingest_otel_go.py
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
REPO_URL = "https://github.com/open-telemetry/opentelemetry-go.git"
REPO_NAME = "open-telemetry/opentelemetry-go"
REPO_LOCAL = "/tmp/opentelemetry-go"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+opentelemetry+tracing+metrics"
CHARTE_VERSION = "1.0"
TAG = "open-telemetry/opentelemetry-go"
SOURCE_REPO = "https://github.com/open-telemetry/opentelemetry-go"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# OpenTelemetry Go = observability SDK (tracing, metrics, context, exporters).
# Patterns CORE : SDK patterns, not instrumentation libraries.
# U-5 : Xxx/xxx substitutions applied (span → signal, event → span_record, etc.)

PATTERNS: list[dict] = [
    # ── 1. TracerProvider initialization with options ──────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)


func newTracerProvider(
	ctx context.Context,
	exporter sdktrace.SpanExporter,
) (*sdktrace.TracerProvider, error) {
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("my_service"),
		),
	)
	if err != nil {
		return nil, err
	}

	processor := sdktrace.NewBatchSpanProcessor(exporter)
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSpanProcessor(processor),
	)
	return tp, nil
}
""",
        "function": "tracer_provider_initialization_options",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/trace/provider.go",
    },
    # ── 2. Span creation with context and attributes ──────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)


func startSignalWithAttributes(ctx context.Context, tracer trace.Tracer) {
	ctx, signal := tracer.Start(ctx, "process_signal", trace.WithAttributes(
		attribute.String("component", "processor"),
		attribute.Int("worker_id", 42),
		attribute.Bool("cached", true),
	))
	defer signal.End()

	doWork(ctx)
}
""",
        "function": "span_start_with_context_and_attributes",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "sdk/trace/span.go",
    },
    # ── 3. Span events and status ──────────────────────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)


func recordSignalStateAndEvent(ctx context.Context, signal trace.Span, err error) {
	if err != nil {
		signal.SetStatus(codes.Error, "operation failed")
		signal.AddEvent("error_occurred", trace.WithAttributes(
			attribute.String("error_type", "validation"),
		))
		return
	}

	signal.AddEvent("operation_completed", trace.WithAttributes(
		attribute.Int("items_processed", 150),
	))
	signal.SetStatus(codes.Ok)
}
""",
        "function": "span_events_and_status_setting",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "sdk/trace/event.go",
    },
    # ── 4. Context propagation — TextMapPropagator Inject ─────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)


func injectTraceToHeaders(ctx context.Context, headers map[string]string) {
	propagator := otel.GetTextMapPropagator()
	carrier := propagation.MapCarrier(headers)
	propagator.Inject(ctx, carrier)
}


type MapCarrier map[string]string

func (m MapCarrier) Get(key string) string {
	return m[key]
}

func (m MapCarrier) Set(key string, value string) {
	m[key] = value
}

func (m MapCarrier) Keys() []string {
	xxx := make([]string, 0, len(m))
	for k := range m {
		xxx = append(xxx, k)
	}
	return xxx
}
""",
        "function": "context_propagator_inject_textmap",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "propagation/trace_context.go",
    },
    # ── 5. Context propagation — TextMapPropagator Extract ────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)


func extractTraceFromHeaders(ctx context.Context, headers map[string]string) context.Context {
	propagator := otel.GetTextMapPropagator()
	carrier := propagation.MapCarrier(headers)
	return propagator.Extract(ctx, carrier)
}
""",
        "function": "context_propagator_extract_textmap",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "propagation/trace_context.go",
    },
    # ── 6. MeterProvider initialization ──────────────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)


func newMeterProvider(
	ctx context.Context,
	exporter sdkmetric.Exporter,
) (*sdkmetric.MeterProvider, error) {
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("my_service"),
		),
	)
	if err != nil {
		return nil, err
	}

	reader := sdkmetric.NewPeriodicReader(exporter)
	mp := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(reader),
	)
	return mp, nil
}
""",
        "function": "meter_provider_initialization_reader",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/metric/meter.go",
    },
    # ── 7. Counter instrument creation and recording ──────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel/metric"
)


func recordCounterMetric(ctx context.Context, meter metric.Meter) error {
	counter, err := meter.Int64Counter(
		"request_count",
		metric.WithDescription("number of HTTP requests"),
		metric.WithUnit("{request}"),
	)
	if err != nil {
		return err
	}

	counter.Add(ctx, 1)
	return nil
}
""",
        "function": "counter_instrument_creation_and_add",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "sdk/metric/instrument.go",
    },
    # ── 8. Histogram instrument creation and recording ───────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel/metric"
)


func recordHistogramMetric(ctx context.Context, meter metric.Meter) error {
	histogram, err := meter.Float64Histogram(
		"request_duration_ms",
		metric.WithDescription("request latency in milliseconds"),
		metric.WithUnit("ms"),
	)
	if err != nil {
		return err
	}

	histogram.Record(ctx, 42.5)
	return nil
}
""",
        "function": "histogram_instrument_creation_and_record",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "sdk/metric/instrument.go",
    },
    # ── 9. Resource creation with service attributes ──────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)


func newResource(ctx context.Context) (*resource.Resource, error) {
	return resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("backend_api"),
			semconv.ServiceVersionKey.String("1.2.3"),
			semconv.ServiceInstanceIDKey.String("host_001"),
		),
	)
}
""",
        "function": "resource_creation_service_attributes",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/resource/resource.go",
    },
    # ── 10. BatchSpanProcessor configuration ──────────────────────────────────
    {
        "normalized_code": """\
import (
	"time"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)


func configureBatchProcessor(
	exporter sdktrace.SpanExporter,
) sdktrace.SpanProcessor {
	processor := sdktrace.NewBatchSpanProcessor(
		exporter,
		sdktrace.WithMaxQueueSize(2048),
		sdktrace.WithBatchTimeout(5 * time.Second),
		sdktrace.WithExportTimeout(30 * time.Second),
		sdktrace.WithMaxExportBatchSize(512),
	)
	return processor
}
""",
        "function": "batch_span_processor_configuration_options",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/trace/batch_span_processor.go",
    },
    # ── 11. OTLP gRPC exporter setup ───────────────────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)


func newOTLPGRPCExporter(ctx context.Context) (sdktrace.SpanExporter, error) {
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint("collector.example.com:4317"),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}
	return exporter, nil
}
""",
        "function": "otlp_grpc_exporter_initialization",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "exporters/otlp/otlptrace/otlptracegrpc/exporter.go",
    },
    # ── 12. Global provider registration ───────────────────────────────────────
    {
        "normalized_code": """\
import (
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
)


func registerGlobalProviders(
	tp *sdktrace.TracerProvider,
	mp *sdkmetric.MeterProvider,
) {
	otel.SetTracerProvider(tp)
	otel.SetMeterProvider(mp)
}
""",
        "function": "global_provider_registration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "propagation.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "TracerProvider initialization with resource and processor",
    "span start with context and attributes",
    "span events and status code setting",
    "context propagation textmap inject",
    "context propagation textmap extract",
    "MeterProvider initialization with reader",
    "counter instrument creation and add",
    "histogram instrument creation and record",
    "resource creation service name",
    "batch span processor configuration",
    "OTLP gRPC exporter setup",
    "global provider registration",
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
    print(f"  {len(PATTERNS)} patterns extracted")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexed — KB: {count_after} points")

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
        print("  DRY_RUN — data removed")


if __name__ == "__main__":
    main()
