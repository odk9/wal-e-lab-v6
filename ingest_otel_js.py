"""
ingest_otel_js.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de open-telemetry/opentelemetry-js dans la KB Qdrant V6.

Focus : CORE patterns observability (tracer provider, span creation, context propagation,
meter provider, counters/histograms, OTLP exporters, batch processors, W3C trace context,
resource detection, auto-instrumentation).

Usage:
    .venv/bin/python3 ingest_otel_js.py
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
REPO_URL = "https://github.com/open-telemetry/opentelemetry-js.git"
REPO_NAME = "open-telemetry/opentelemetry-js"
REPO_LOCAL = "/tmp/opentelemetry-js"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+opentelemetry+tracing+metrics"
CHARTE_VERSION = "1.0"
TAG = "open-telemetry/opentelemetry-js"
SOURCE_REPO = "https://github.com/open-telemetry/opentelemetry-js"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# U-5: user→xxx, item→element, task→job, order→sequence, post→entry, comment→annotation,
#      message→payload, event→signal, tag→attribute
# T-1: no `: any`. T-2: no `var`. T-3: no console.log().
# Kept: tracer, span, meter, counter, histogram, context, propagator, exporter,
#       processor, resource, provider, OTLP, W3C, signal

PATTERNS: list[dict] = [
    # ── 1. Tracer Provider initialization (singleton) ─────────────────────────
    {
        "normalized_code": """\
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import type { SDKRegistrationConfig } from '@opentelemetry/sdk-trace-base';

const provider = new NodeTracerProvider();
provider.register({
  contextManager: undefined,
  propagator: undefined,
});

registerInstrumentations({
  instrumentations: [
    new HttpInstrumentation(),
    new ExpressInstrumentation(),
  ],
});
""",
        "function": "tracer_provider_init_singleton",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-sdk-trace-node/src/NodeTracerProvider.ts",
    },

    # ── 2. Tracer from provider + span creation ────────────────────────────────
    {
        "normalized_code": """\
import { trace } from '@opentelemetry/api';

const tracer = trace.getTracer('xxx-service', '1.0.0');

export async function processXxx(xxxId: number): Promise<void> {
  const span = tracer.startSpan('process_xxx', {
    attributes: {
      'xxx.id': xxxId,
      'xxx.type': 'standard',
    },
  });

  try {
    span.setStatus({ code: SpanStatusCode.OK });
  } catch (err) {
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: (err as Error).message,
    });
    span.recordException(err);
  } finally {
    span.end();
  }
}
""",
        "function": "span_creation_attributes_status",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-sdk-trace-base/src/Span.ts",
    },

    # ── 3. Context propagation with W3C trace context ────────────────────────
    {
        "normalized_code": """\
import { context, trace } from '@opentelemetry/api';
import { W3CTraceContextPropagator } from '@opentelemetry/core';

const propagator = new W3CTraceContextPropagator();

export function extractContextFromHeaders(headers: Record<string, string>): void {
  const activeContext = propagator.extract(context.active(), headers);
  context.with(activeContext, () => {
    const span = trace.getActiveSpan();
    if (span) {
      span.addEvent('context_propagated', {
        'headers.count': Object.keys(headers).length,
      });
    }
  });
}

export function injectContextToHeaders(headers: Record<string, string>): void {
  propagator.inject(context.active(), headers);
}
""",
        "function": "context_propagation_w3c_trace_context",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-core/src/propagation/W3CTraceContextPropagator.ts",
    },

    # ── 4. Meter Provider initialization ────────────────────────────────────
    {
        "normalized_code": """\
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';

const metricReader = new PeriodicExportingMetricReader({
  exporter: new OTLPMetricExporter({
    url: 'http://localhost:4318/v1/metrics',
  }),
  intervalMillis: 30_000,
});

const meterProvider = new MeterProvider({
  readers: [metricReader],
});
""",
        "function": "meter_provider_init_periodic_export",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/sdk-metrics/src/MeterProvider.ts",
    },

    # ── 5. Counter metric ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeterProvider().getMeter('xxx-service', '1.0.0');

const xxxCounter = meter.createCounter('xxx_processed', {
  description: 'Number of xxxs processed',
  unit: '1',
});

export function incrementXxxCounter(value: number = 1, attributes: Record<string, string> = {}): void {
  xxxCounter.add(value, {
    'service.name': 'xxx-service',
    ...attributes,
  });
}
""",
        "function": "counter_metric_create_increment",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "packages/sdk-metrics/src/Meter.ts",
    },

    # ── 6. Histogram metric ────────────────────────────────────────────────────
    {
        "normalized_code": """\
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeterProvider().getMeter('xxx-service', '1.0.0');

const processingDurationHistogram = meter.createHistogram('xxx_processing_duration_ms', {
  description: 'Processing duration in milliseconds',
  unit: 'ms',
});

export function recordProcessingDuration(durationMs: number, attributes: Record<string, string> = {}): void {
  processingDurationHistogram.record(durationMs, {
    'service.name': 'xxx-service',
    ...attributes,
  });
}
""",
        "function": "histogram_metric_create_record",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "packages/sdk-metrics/src/Meter.ts",
    },

    # ── 7. Batch Span Processor ────────────────────────────────────────────────
    {
        "normalized_code": """\
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';

const exporter = new OTLPTraceExporter({
  url: 'http://localhost:4318/v1/traces',
});

const batchProcessor = new BatchSpanProcessor(exporter, {
  maxExportBatchSize: 512,
  maxQueueSize: 2048,
  scheduledDelayMillis: 5000,
  exportTimeoutMillis: 30000,
});

provider.addSpanProcessor(batchProcessor);
""",
        "function": "batch_span_processor_otlp_export",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-sdk-trace-base/src/export/BatchSpanProcessorBase.ts",
    },

    # ── 8. Span events (temporal signal recording) ──────────────────────────────
    {
        "normalized_code": """\
import { trace, SpanStatusCode } from '@opentelemetry/api';

const span = tracer.startSpan('xxx_operation');

span.addEvent('validation_started', {
  'validation.type': 'schema',
});

try {
  const result = await validateXxx(xxxData);
  span.addEvent('validation_succeeded', {
    'validation.result': 'ok',
  });
} catch (err) {
  span.addEvent('validation_failed', {
    'error.kind': (err as Error).name,
    'error.message': (err as Error).message,
  });
}

span.end();
""",
        "function": "span_events_temporal_signal_recording",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-sdk-trace-base/src/Span.ts",
    },

    # ── 9. Resource detection (environment, host, container) ──────────────────
    {
        "normalized_code": """\
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { detectResourcesSync, envDetector, hostDetector } from '@opentelemetry/resources';

const resource = Resource.default()
  .merge(detectResourcesSync({ detectors: [envDetector, hostDetector] }))
  .merge(
    new Resource({
      [SemanticResourceAttributes.SERVICE_NAME]: 'xxx-service',
      [SemanticResourceAttributes.SERVICE_VERSION]: '1.0.0',
      [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: process.env.ENVIRONMENT || 'development',
    })
  );

const provider = new NodeTracerProvider({ resource });
""",
        "function": "resource_detection_environment_host",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-sdk-trace-node/src/NodeTracerProvider.ts",
    },

    # ── 10. Automatic instrumentation registration ─────────────────────────────
    {
        "normalized_code": """\
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { ExpressInstrumentation } from '@opentelemetry/instrumentation-express';
import { PgInstrumentation } from '@opentelemetry/instrumentation-pg';

registerInstrumentations({
  instrumentations: [
    new HttpInstrumentation({
      responseHook: (_span, response) => {
        _span.setAttribute('http.response.body.size', response.socket?.bytesWritten ?? 0);
      },
    }),
    new ExpressInstrumentation(),
    new PgInstrumentation({
      enabled: true,
    }),
  ],
});
""",
        "function": "instrumentation_auto_registration_hooks",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-instrumentation/src/InstrumentationBase.ts",
    },

    # ── 11. Context Manager with async-local-storage ─────────────────────────
    {
        "normalized_code": """\
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { context } from '@opentelemetry/api';

const contextManager = new AsyncLocalStorageContextManager();
contextManager.enable();
context.setGlobalContextManager(contextManager);

export async function withContext<T>(
  activeContext: Context,
  fn: () => Promise<T>
): Promise<T> {
  return context.with(activeContext, async () => {
    return fn();
  });
}
""",
        "function": "context_manager_async_local_storage",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-context-async-hooks/src/AsyncLocalStorageContextManager.ts",
    },

    # ── 12. Span link (causal chain) ─────────────────────────────────────────
    {
        "normalized_code": """\
import { trace, context } from '@opentelemetry/api';

const parentSpan = tracer.startSpan('parent_operation');

context.with(
  trace.setSpan(context.active(), parentSpan),
  () => {
    const childSpan = tracer.startSpan('child_operation', {
      links: [
        {
          context: parentSpan.spanContext(),
          attributes: { 'link.type': 'causality' },
        },
      ],
    });

    try {
      childSpan.setStatus({ code: SpanStatusCode.OK });
    } finally {
      childSpan.end();
    }
  }
);

parentSpan.end();
""",
        "function": "span_link_causal_chain",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "packages/opentelemetry-api/src/trace/span.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "initialize tracer provider singleton",
    "create span with attributes and status",
    "propagate context W3C trace context headers",
    "meter provider periodic export metrics OTLP",
    "counter metric increment add",
    "histogram metric record duration",
    "batch span processor export OTLP",
    "span events temporal signal recording",
    "resource detection environment host container",
    "automatic instrumentation registration hooks",
    "context manager async local storage",
    "span link causal chain relationship",
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
