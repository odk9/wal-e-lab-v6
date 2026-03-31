"""
ingest_tracing_rs.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de tokio-rs/tracing dans la KB Qdrant V6.

Focus : Tracing/observability core patterns (subscriber init, span creation,
event logging, instrument async functions, layer filtering, formatter config,
JSON output, span attributes, custom layer impl, env filter, OpenTelemetry
integration, test subscriber).

Usage:
    .venv/bin/python3 ingest_tracing_rs.py
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
REPO_URL = "https://github.com/tokio-rs/tracing.git"
REPO_NAME = "tokio-rs/tracing"
REPO_LOCAL = "/tmp/tracing"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+tracing+logging+tokio"
CHARTE_VERSION = "1.0"
TAG = "tokio-rs/tracing"
SOURCE_REPO = "https://github.com/tokio-rs/tracing"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Tokio-rs/tracing = Rust structured logging & distributed tracing library.
# Core patterns from subscriber init, span creation, event logging,
# async instrumentation, layer filtering, formatter config, JSON output,
# span attributes, custom layer implementation, env filter, OpenTelemetry layer,
# and test subscriber.
# U-5 : `span`, `layer`, `subscriber`, `filter`, `event`, `span_id`, `trace_id`
#       are TECHNICAL TERMS — keep as-is.

PATTERNS: list[dict] = [
    # ── 1. Subscriber Initialization ────────────────────────────────────────────
    {
        "normalized_code": """\
use tracing::{dispatcher::set_default, Subscriber};
use tracing_subscriber::{fmt, filter::EnvFilter};

fn init_subscriber() {
    \"\"\"Initialize default tracing subscriber with fmt layer.

    Sets up span context, log_entry formatting, and log level filtering.
    Must be called once at application startup.
    \"\"\"
    let filter = EnvFilter::from_default_env()
        .add_directive("xxx=debug".parse().unwrap_or_else(|_| "info".parse().expect("hardcoded 'info' level must parse")));

    let subscriber = fmt()
        .with_filter(filter)
        .with_writer(std::io::stderr)
        .with_ansi(true)
        .with_level(true)
        .with_target(true)
        .with_thread_ids(false)
        .finish();

    set_default(subscriber);
}

#[tokio::main]
async fn main() {
    init_subscriber();

    tracing::info!("Application started");
    // Application logic
    tracing::info!("Application finished");
}
""",
        "function": "subscriber_init",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "tracing-subscriber/examples/subscriber_init.rs",
    },
    # ── 2. Span Creation and Management ─────────────────────────────────────────
    {
        "normalized_code": """\
use tracing::{span, Level, Span};

async fn process_request(request_id: String) {
    \"\"\"Create and enter tracing span for request processing.

    Spans track execution context (function, timing, metadata).
    All log_entries emitted within span scope include span attributes.
    \"\"\"
    let span = span!(
        Level::INFO,
        "process_request",
        request_id = %request_id,
        module = "handlers",
    );

    let _guard = span.enter();

    tracing::debug!("Received request");

    match fetch_data(&request_id).await {
        Ok(data) => {
            tracing::info!(data_size = data.len(), "Data fetched");
            process_data(data).await;
        }
        Err(e) => {
            tracing::error!(error = %e, "Failed to fetch data");
        }
    }

    tracing::debug!("Request processing complete");
}

#[inline]
async fn fetch_data(id: &str) -> Result<Vec<u8>, String> {
    Ok(vec![])
}

async fn process_data(_data: Vec<u8>) {
    // Process
}
""",
        "function": "span_creation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "tracing/examples/span_creation.rs",
    },
    # ── 3. Event Logging ────────────────────────────────────────────────────────
    {
        "normalized_code": """\
use tracing::{debug, info, warn, error, trace};

async fn handle_xxx_operation(xxx_id: u64, action: &str) {
    \"\"\"Emit structured log entries at different severity levels.

    Entries include span context automatically.
    Key-value fields are indexed for querying.
    \"\"\"
    trace!(target: "xxx_operation", "Entering handle_xxx_operation");

    info!(
        xxx_id = xxx_id,
        action = %action,
        timestamp = ?std::time::SystemTime::now(),
        "Starting operation"
    );

    match validate_input(xxx_id, action) {
        Ok(_) => {
            debug!(validated = true, "Input validation passed");
        }
        Err(validation_error) => {
            warn!(error = %validation_error, "Input validation failed");
            return;
        }
    }

    if let Err(e) = execute_action(action).await {
        error!(
            error = %e,
            action = %action,
            retry_count = 3,
            "Execution failed, will retry"
        );
        return;
    }

    info!(action = %action, duration_ms = 42, "Operation completed");
}

fn validate_input(_id: u64, _action: &str) -> Result<(), String> {
    Ok(())
}

async fn execute_action(_action: &str) -> Result<(), String> {
    Ok(())
}
""",
        "function": "event_logging",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "tracing-subscriber/examples/event_logging.rs",
    },
    # ── 4. Instrument Async Function ────────────────────────────────────────────
    {
        "normalized_code": """\
use tracing::instrument;

#[instrument(
    skip_all,
    fields(
        xxx_id = %xxx_id,
        request_type = %request_type,
    ),
    err(Display),
)]
async fn fetch_xxx_data(xxx_id: u64, request_type: &str) -> Result<Vec<u8>, String> {
    \"\"\"Automatically instrument async function with span.

    #[instrument] macro:
    - Creates span on function entry (name = function name)
    - Adds function parameters as span fields (filtered by skip_all)
    - Records function result/error
    - Automatically enters span context for function body
    \"\"\"
    tracing::debug!("Fetching data");

    if xxx_id == 0 {
        return Err("Invalid ID".to_string());
    }

    let data = match request_type {
        "fast" => fetch_fast(xxx_id).await?,
        "full" => fetch_full(xxx_id).await?,
        _ => return Err(format!("Unknown type: {}", request_type)),
    };

    tracing::info!(size = data.len(), "Data fetched successfully");
    Ok(data)
}

#[instrument(skip_all, ret(Display), err)]
async fn fetch_fast(_id: u64) -> Result<Vec<u8>, String> {
    Ok(vec![1, 2, 3])
}

#[instrument(skip_all)]
async fn fetch_full(_id: u64) -> Result<Vec<u8>, String> {
    Ok(vec![1, 2, 3, 4, 5])
}
""",
        "function": "instrument_async_fn",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "tracing/examples/instrument_async_fn.rs",
    },
    # ── 5. Layer Filtering and Composition ──────────────────────────────────────
    {
        "normalized_code": """\
use tracing_subscriber::{
    fmt,
    layer::SubscriberExt,
    filter::{EnvFilter, LevelFilter},
    util::SubscriberInitExt,
};

fn setup_layered_subscriber() {
    \"\"\"Stack multiple layers with selective filtering.

    Each layer applies different filters, formatters, or outputs.
    Layers are composed and applied in sequence.
    \"\"\"
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let fmt_layer = fmt::layer()
        .with_level(true)
        .with_target(false)
        .with_file(true)
        .with_line_number(true)
        .with_ansi(true);

    let debug_filter = EnvFilter::new("debug,xxx=trace");
    let debug_layer = fmt::layer()
        .with_filter(debug_filter)
        .with_writer(|| std::io::stderr);

    let subscriber = tracing_subscriber::registry()
        .with(env_filter)
        .with(fmt_layer.with_filter(LevelFilter::INFO))
        .with(debug_layer)
        .init();
}

#[tokio::main]
async fn main() {
    setup_layered_subscriber();

    tracing::info!("Info level detail");
    tracing::debug!("Debug level (filtered by layer)");
    tracing::trace!(target: "xxx", "Trace level (only in xxx=trace)");
}
""",
        "function": "layer_filtering",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "tracing-subscriber/examples/layer_filtering.rs",
    },
    # ── 6. Fmt Subscriber Configuration ─────────────────────────────────────────
    {
        "normalized_code": """\
use tracing_subscriber::{fmt, filter::EnvFilter};
use std::io;

fn configure_fmt_subscriber() {
    \"\"\"Fine-grained formatter configuration.

    Controls output format: JSON, pretty-print, compact, etc.
    Configures timestamp, target, file/line, color, ansi.
    \"\"\"
    let env_filter = EnvFilter::from_default_env()
        .add_directive("xxx=debug".parse().unwrap_or_else(|_| "info".parse().expect("hardcoded 'info' level must parse")));

    let fmt_config = fmt()
        .with_max_level(tracing::Level::DEBUG)
        .with_filter(env_filter)
        .with_thread_ids(true)
        .with_thread_names(true)
        .with_file(true)
        .with_line_number(true)
        .with_level(true)
        .with_target(true)
        .with_ansi(cfg!(test).not())
        .with_writer(io::stderr)
        .with_span_list(true)
        .pretty()
        .finish();

    let _ = tracing::subscriber::set_default(fmt_config);
}

fn compact_subscriber() {
    \"\"\"Compact (non-pretty) formatter for production.\"\"\"
    tracing_subscriber::fmt()
        .compact()
        .with_max_level(tracing::Level::INFO)
        .init();
}

fn json_subscriber() {
    \"\"\"JSON output format for log aggregation systems.\"\"\"
    tracing_subscriber::fmt()
        .json()
        .with_current_span(true)
        .init();
}
""",
        "function": "fmt_subscriber_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "tracing-subscriber/examples/fmt_subscriber_config.rs",
    },
    # ── 7. JSON Output Layer ────────────────────────────────────────────────────
    {
        "normalized_code": """\
use tracing_subscriber::fmt;
use tracing_appender::non_blocking;
use std::fs::File;

fn setup_json_output() -> Result<(), Box<dyn std::error::Error>> {
    \"\"\"Configure JSON-formatted output to file or stdout.

    JSON format supports structured log ingestion (ElasticSearch,
    CloudWatch, DataDog, etc.).
    \"\"\"
    let file = File::create("tracing.jsonl")?;
    let (non_blocking_file, guard) = non_blocking(file);

    let json_subscriber = fmt()
        .json()
        .with_writer(non_blocking_file)
        .with_current_span(true)
        .with_span_list(true)
        .with_target(true)
        .with_level(true)
        .with_ansi(false)
        .finish();

    tracing::subscriber::set_default(json_subscriber);
    std::mem::forget(guard);

    Ok(())
}

fn json_stdout() {
    \"\"\"JSON output to stdout.\"\"\"
    tracing_subscriber::fmt()
        .json()
        .with_current_span(true)
        .with_ansi(false)
        .init();
}

fn json_pretty() {
    \"\"\"Pretty-printed JSON (dev only).\"\"\"
    tracing_subscriber::fmt()
        .json()
        .pretty()
        .init();
}
""",
        "function": "json_output_layer",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "tracing-appender/examples/json_output_layer.rs",
    },
    # ── 8. Span Attributes and Fields ───────────────────────────────────────────
    {
        "normalized_code": """\
use tracing::{span, Span, Level, field};

fn span_with_fields_and_attributes(xxx_id: u64) {
    \"\"\"Create span with mixed recorded and deferred fields.

    Recorded fields set on creation.
    Deferred fields (empty!) recorded later via span.record().
    \"\"\"
    let xxx_status = field::Empty;
    let span = span!(
        Level::INFO,
        "xxx_operation",
        xxx_id = xxx_id,
        xxx_status = &xxx_status,
        module = "handlers",
        version = "1.0",
    );

    let _guard = span.enter();

    tracing::debug!("Processing started");

    // Simulate processing
    let status = "in_progress";
    span.record("xxx_status", status);

    tracing::debug!("Processing updated");

    // Simulate completion
    span.record("xxx_status", "completed");
    tracing::info!("Processing finished");
}

fn record_dynamic_fields(span: &Span) {
    \"\"\"Record fields after span creation.\"\"\"
    span.record("result", "success");
    span.record("duration_ms", 123);
    span.record("error_count", 0);
}

#[tracing::instrument(skip(data))]
fn process_with_fields(data: Vec<u8>) {
    tracing::Span::current()
        .record("data_size", data.len())
        .record("processed_at", field::debug(std::time::SystemTime::now()));
}
""",
        "function": "span_attributes_fields",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "tracing/examples/span_attributes_fields.rs",
    },
    # ── 9. Custom Layer Implementation ──────────────────────────────────────────
    {
        "normalized_code": """\
use tracing_subscriber::layer::{Context, Layer};
use tracing_core::{subscriber::Subscriber, span, Event};
use std::fmt;

pub struct CustomLayerXxx {
    name: String,
}

impl<S> Layer<S> for CustomLayerXxx
where
    S: Subscriber,
{
    \"\"\"Custom tracing layer for specialized processing.

    Implement Layer trait to hook into span/log_entry lifecycle.
    Use Context<S> to access span registry and metadata.
    \"\"\"

    fn on_new_span(
        &self,
        attrs: &span::Attributes<'_>,
        id: &span::Id,
        ctx: Context<'_, S>,
    ) {
        let metadata = attrs.metadata();
        tracing::debug!(
            layer = %self.name,
            span_name = metadata.name(),
            span_id = ?id,
            "New span"
        );
    }

    fn on_enter(&self, id: &span::Id, ctx: Context<'_, S>) {
        if let Some(span) = ctx.span(id) {
            tracing::debug!(
                layer = %self.name,
                span_name = span.metadata().name(),
                "Entering span"
            );
        }
    }

    fn on_event(&self, log_entry: &Event<'_>, ctx: Context<'_, S>) {
        let metadata = log_entry.metadata();
        tracing::debug!(
            layer = %self.name,
            target = metadata.target(),
            "Log_entry recorded"
        );
    }

    fn on_close(&self, id: span::Id, ctx: Context<'_, S>) {
        if let Some(span) = ctx.span(&id) {
            tracing::debug!(
                layer = %self.name,
                span_name = span.metadata().name(),
                "Span closed"
            );
        }
    }
}

impl CustomLayerXxx {
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
        }
    }
}
""",
        "function": "custom_layer_impl",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "tracing-subscriber/examples/custom_layer_impl.rs",
    },
    # ── 10. EnvFilter Configuration ─────────────────────────────────────────────
    {
        "normalized_code": """\
use tracing_subscriber::filter::EnvFilter;

fn env_filter_examples() {
    \"\"\"EnvFilter directive syntax for fine-grained log level control.

    Format: target=level,module::submodule=level
    Levels: trace, debug, info, warn, error
    Default: info
    \"\"\"

    // Single level for all targets
    let filter = EnvFilter::new("debug");

    // Target-specific levels
    let filter = EnvFilter::new("info,xxx=debug,database=trace");

    // From environment variable (RUST_LOG)
    let filter = EnvFilter::from_default_env()
        .add_directive("xxx=debug".parse().unwrap_or_else(|_| "info".parse().expect("hardcoded 'info' level must parse")));

    // Complex: multiple targets, hierarchical
    let filter = EnvFilter::new(
        "info,\
         hyper=warn,\
         xxx::core=trace,\
         xxx::database=debug,\
         tokio=warn,\
         tracing_appender=debug"
    );

    // Fallback if parsing fails
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,xxx=debug"));

    tracing_subscriber::fmt()
        .with_filter(filter)
        .init();
}

fn dynamic_filter_reloading() {
    \"\"\"(Advanced) Support filter reloading without restart.\"\"\"
    // Use tracing-subscriber reloading feature
    // Out of scope for basic patterns
}
""",
        "function": "env_filter_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "tracing-subscriber/examples/env_filter_config.rs",
    },
    # ── 11. OpenTelemetry Layer Integration ─────────────────────────────────────
    {
        "normalized_code": """\
use opentelemetry::global;
use tracing_subscriber::layer::SubscriberExt;
use tracing_opentelemetry::OpenTelemetryLayer;

fn setup_opentelemetry() -> Result<(), Box<dyn std::error::Error>> {
    \"\"\"Integrate tracing with OpenTelemetry (OTLP protocol).

    Exports spans to OpenTelemetry Collector for correlation
    with distributed tracing systems (Jaeger, Tempo, etc.).
    \"\"\"
    let tracer = opentelemetry_jaeger::new_pipeline()
        .install_simple()?;

    let otel_layer = OpenTelemetryLayer::new(tracer);

    let subscriber = tracing_subscriber::registry()
        .with(otel_layer)
        .with(tracing_subscriber::fmt::layer())
        .init();

    Ok(())
}

fn setup_otlp_exporter() -> Result<(), Box<dyn std::error::Error>> {
    \"\"\"Export to OTLP endpoint (gRPC).\"\"\"
    use opentelemetry::sdk::trace::Config;
    use opentelemetry::sdk::Resource;
    use opentelemetry::KeyValue;

    let resource = Resource::default().merge(Resource::new(vec![
        KeyValue::new("service.name", "xxx-service"),
        KeyValue::new("service.version", "1.0.0"),
    ]));

    let tracer = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(opentelemetry_otlp::new_exporter().tonic())
        .with_trace_config(Config::default().with_resource(resource))
        .install_simple()?;

    let otel_layer = OpenTelemetryLayer::new(tracer);

    tracing_subscriber::registry()
        .with(otel_layer)
        .with(tracing_subscriber::fmt::layer())
        .init();

    Ok(())
}
""",
        "function": "opentelemetry_layer",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "tracing-opentelemetry/examples/opentelemetry_layer.rs",
    },
    # ── 12. Test Subscriber (Testing/Debugging) ─────────────────────────────────
    {
        "normalized_code": """\
#[cfg(test)]
mod tests {
    use tracing::{debug, info, trace};
    use tracing_subscriber::layer::SubscriberExt;

    #[test]
    fn test_with_tracing() {
        \"\"\"Enable tracing output during test runs.

        Use tracing_test crate (or manual setup) to capture
        and assert on emitted entries.
        \"\"\"
        let subscriber = tracing_subscriber::registry()
            .with(tracing_subscriber::fmt::layer().pretty());

        let guard = tracing::subscriber::set_default(subscriber);

        info!(test_id = 1, "Starting test");
        debug!("Test running");

        // Test assertions
        assert_eq!(1 + 1, 2);

        info!("Test completed");
        drop(guard);
    }

    #[test]
    fn test_subscriber_capturing() {
        \"\"\"Capture entries for assertion.\"\"\"
        use tracing_test::traced_test;

        let result = run_xxx_operation();
        assert!(result.is_ok());
    }

    #[tracing::instrument]
    fn run_xxx_operation() -> Result<(), String> {
        info!("Operation started");
        debug!(status = "processing");
        Ok(())
    }

    #[tokio::test]
    async fn test_async_spans() {
        \"\"\"Test async spans with instrumentation.\"\"\"
        let result = async_xxx_operation(42).await;
        assert_eq!(result, 42);
    }

    #[tracing::instrument]
    async fn async_xxx_operation(xxx: u64) -> u64 {
        trace!("Async operation");
        xxx
    }
}
""",
        "function": "test_subscriber",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tracing-subscriber/tests/test_subscriber.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "subscriber initialization setup",
    "span creation and scope",
    "event logging structured fields",
    "instrument async function decorator",
    "layer filtering composition",
    "fmt subscriber configuration formatting",
    "JSON output log aggregation",
    "span attributes fields recording",
    "custom layer trait implementation",
    "env filter directive syntax",
    "OpenTelemetry tracing export",
    "test subscriber mock capture",
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
