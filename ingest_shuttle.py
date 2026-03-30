"""
ingest_shuttle.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de shuttle-hq/shuttle dans la KB Qdrant V6.

Rust C — Shuttle deployment platform. Axum + SQLx + Tokio.

Usage:
    .venv/bin/python3 ingest_shuttle.py
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
REPO_URL = "https://github.com/shuttle-hq/shuttle.git"
REPO_NAME = "shuttle-hq/shuttle"
REPO_LOCAL = "/tmp/shuttle_hq"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+shuttle+sqlx+tokio"
CHARTE_VERSION = "1.0"
TAG = "shuttle-hq/shuttle"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/shuttle-hq/shuttle"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Entity→Xxx, entity→xxx, entities→xxxs
# R-1: NO .unwrap() except in #[test]
# R-2: NO println!()
# Kept: shuttle, axum, sqlx, tokio, shuttle_runtime, ShuttleAxum,
#       PgPool, SecretStore, Metadata, Router, etc.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG — Shuttle entry points & resource injection
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. shuttle_main_entry ──────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use shuttle_axum::ShuttleAxum;

#[shuttle_runtime::main]
async fn main() -> ShuttleAxum {
    let router = Router::new()
        .route("/", axum::routing::get(hello_xxx));

    Ok(router.into())
}

async fn hello_xxx() -> &'static str {
    "Hello, Xxx!"
}
""",
        "function": "shuttle_main_entry",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/main.rs",
    },

    # ── 2. shuttle_axum_router ─────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::{get, post, put, delete}, Router};

fn xxx_router() -> Router {
    Router::new()
        .route("/xxxs", get(list_xxxs).post(create_xxx))
        .route("/xxxs/:id", get(get_xxx).put(update_xxx).delete(delete_xxx))
}
""",
        "function": "shuttle_axum_router",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/router.rs",
    },

    # ── 3. shuttle_postgres_injection ──────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use shuttle_axum::ShuttleAxum;
use shuttle_shared_db::Postgres;
use sqlx::PgPool;

#[shuttle_runtime::main]
async fn main(
    #[shuttle_shared_db::Postgres] pool: PgPool,
) -> ShuttleAxum {
    sqlx::migrate!()
        .run(&pool)
        .await
        .map_err(shuttle_runtime::CustomError::new)?;

    let router = Router::new()
        .route("/xxxs", axum::routing::get(list_xxxs))
        .with_state(pool);

    Ok(router.into())
}
""",
        "function": "shuttle_postgres_injection",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/main.rs",
    },

    # ── 4. shuttle_secrets ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use shuttle_axum::ShuttleAxum;
use shuttle_runtime::SecretStore;

#[shuttle_runtime::main]
async fn main(
    #[shuttle_runtime::Secrets] secrets: SecretStore,
) -> ShuttleAxum {
    let api_key = secrets
        .get("API_KEY")
        .expect("API_KEY secret not set");

    let state = AppState { api_key };
    let router = Router::new()
        .route("/xxxs", axum::routing::get(list_xxxs))
        .with_state(state);

    Ok(router.into())
}

#[derive(Clone)]
struct AppState {
    api_key: String,
}
""",
        "function": "shuttle_secrets",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/main.rs",
    },

    # ── 5. shuttle_metadata ────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use shuttle_axum::ShuttleAxum;
use shuttle_runtime::DeploymentMetadata;

#[shuttle_runtime::main]
async fn main(
    #[shuttle_runtime::Metadata] metadata: DeploymentMetadata,
) -> ShuttleAxum {
    let env = metadata.env;
    let project_name = metadata.project_name;

    let state = AppState {
        env: format!("{env:?}"),
        project_name,
    };

    let router = Router::new()
        .route("/info", axum::routing::get(get_info))
        .with_state(state);

    Ok(router.into())
}

#[derive(Clone)]
struct AppState {
    env: String,
    project_name: String,
}
""",
        "function": "shuttle_metadata",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/main.rs",
    },

    # ── 6. shuttle_multi_resource ──────────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use shuttle_axum::ShuttleAxum;
use shuttle_shared_db::Postgres;
use shuttle_runtime::{DeploymentMetadata, SecretStore};
use sqlx::PgPool;

#[shuttle_runtime::main]
async fn main(
    #[shuttle_shared_db::Postgres] pool: PgPool,
    #[shuttle_runtime::Secrets] secrets: SecretStore,
    #[shuttle_runtime::Metadata] metadata: DeploymentMetadata,
) -> ShuttleAxum {
    sqlx::migrate!()
        .run(&pool)
        .await
        .map_err(shuttle_runtime::CustomError::new)?;

    let api_key = secrets
        .get("API_KEY")
        .expect("API_KEY secret not set");

    let state = AppState {
        pool,
        api_key,
        env: format!("{:?}", metadata.env),
    };

    let router = Router::new()
        .route("/xxxs", axum::routing::get(list_xxxs).post(create_xxx))
        .route("/xxxs/:id", axum::routing::get(get_xxx))
        .with_state(state);

    Ok(router.into())
}

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    api_key: String,
    env: String,
}
""",
        "function": "shuttle_multi_resource",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/main.rs",
    },

    # ── 7. axum_service_impl ──────────────────────────────────────────────
    {
        "normalized_code": """\
use std::net::SocketAddr;

use axum::Router;
use shuttle_runtime::Service;

pub struct AxumService {
    router: Router,
}

impl AxumService {
    pub fn new(router: Router) -> Self {
        Self { router }
    }
}

#[shuttle_runtime::async_trait]
impl Service for AxumService {
    async fn bind(mut self, addr: SocketAddr) -> Result<(), shuttle_runtime::Error> {
        let listener = tokio::net::TcpListener::bind(addr).await?;
        axum::serve(listener, self.router)
            .await
            .map_err(shuttle_runtime::CustomError::new)?;
        Ok(())
    }
}
""",
        "function": "axum_service_impl",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "services/shuttle-axum/src/lib.rs",
    },

    # ── 8. rocket_service_impl ────────────────────────────────────────────
    {
        "normalized_code": """\
use std::net::SocketAddr;

use shuttle_runtime::Service;

pub struct RocketService {
    rocket: rocket::Rocket<rocket::Build>,
}

impl RocketService {
    pub fn new(rocket: rocket::Rocket<rocket::Build>) -> Self {
        Self { rocket }
    }
}

#[shuttle_runtime::async_trait]
impl Service for RocketService {
    async fn bind(mut self, addr: SocketAddr) -> Result<(), shuttle_runtime::Error> {
        let config = rocket::Config {
            address: addr.ip(),
            port: addr.port(),
            ..Default::default()
        };
        self.rocket
            .configure(config)
            .launch()
            .await
            .map_err(shuttle_runtime::CustomError::new)?;
        Ok(())
    }
}
""",
        "function": "rocket_service_impl",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "services/shuttle-rocket/src/lib.rs",
    },

    # ── 9. actix_service_impl ─────────────────────────────────────────────
    {
        "normalized_code": """\
use std::net::SocketAddr;

use actix_web::HttpServer;
use shuttle_runtime::Service;

pub struct ActixWebService<F> {
    factory: F,
}

impl<F> ActixWebService<F>
where
    F: Fn() -> actix_web::App<actix_web::middleware::Logger> + Send + Clone + 'static,
{
    pub fn new(factory: F) -> Self {
        Self { factory }
    }
}

#[shuttle_runtime::async_trait]
impl<F> Service for ActixWebService<F>
where
    F: Fn() -> actix_web::App<actix_web::middleware::Logger> + Send + Clone + 'static,
{
    async fn bind(mut self, addr: SocketAddr) -> Result<(), shuttle_runtime::Error> {
        HttpServer::new(self.factory)
            .bind(addr)
            .map_err(shuttle_runtime::CustomError::new)?
            .run()
            .await
            .map_err(shuttle_runtime::CustomError::new)?;
        Ok(())
    }
}
""",
        "function": "actix_service_impl",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "services/shuttle-actix-web/src/lib.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTE — Error handling
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 10. shuttle_error_handling ─────────────────────────────────────────
    {
        "normalized_code": """\
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("not found: {0}")]
    NotFound(String),

    #[error("bad request: {0}")]
    BadRequest(String),

    #[error("internal error: {0}")]
    Internal(String),

    #[error(transparent)]
    Sqlx(#[from] sqlx::Error),

    #[error(transparent)]
    Anyhow(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            AppError::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg.clone()),
            AppError::Sqlx(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
            AppError::Anyhow(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
        };
        (status, message).into_response()
    }
}

impl From<AppError> for shuttle_runtime::CustomError {
    fn from(err: AppError) -> Self {
        shuttle_runtime::CustomError::new(err)
    }
}
""",
        "function": "shuttle_error_handling",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "src/error.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MODEL — Traits & resource patterns
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. resource_input_builder_trait ───────────────────────────────────
    {
        "normalized_code": """\
use serde::{Deserialize, Serialize};
use shuttle_runtime::async_trait;

#[derive(Serialize, Deserialize)]
pub struct XxxInput {
    pub connection_string: String,
}

pub struct XxxOutput {
    pub pool: sqlx::PgPool,
}

#[async_trait]
pub trait ResourceInputBuilder {
    type Input: Serialize + for<'de> Deserialize<'de>;
    type Output;

    fn config(&self) -> &Self::Input;

    async fn build(self) -> Result<Self::Output, shuttle_runtime::Error>;
}
""",
        "function": "resource_input_builder_trait",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "runtime/src/resource.rs",
    },

    # ── 12. into_resource_trait ────────────────────────────────────────────
    {
        "normalized_code": """\
use shuttle_runtime::async_trait;

#[async_trait]
pub trait IntoResource<T> {
    async fn into_resource(self) -> Result<T, shuttle_runtime::Error>;
}

#[async_trait]
impl IntoResource<sqlx::PgPool> for sqlx::PgPool {
    async fn into_resource(self) -> Result<sqlx::PgPool, shuttle_runtime::Error> {
        Ok(self)
    }
}

#[async_trait]
impl IntoResource<String> for String {
    async fn into_resource(self) -> Result<String, shuttle_runtime::Error> {
        Ok(self)
    }
}
""",
        "function": "into_resource_trait",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "runtime/src/resource.rs",
    },

    # ── 13. shuttle_service_trait ──────────────────────────────────────────
    {
        "normalized_code": """\
use std::net::SocketAddr;

use shuttle_runtime::async_trait;

#[async_trait]
pub trait Service: Send {
    /// Bind to the given address and start serving.
    async fn bind(mut self, addr: SocketAddr) -> Result<(), shuttle_runtime::Error>;
}
""",
        "function": "shuttle_service_trait",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "runtime/src/lib.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG — Background tasks & workspace
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 14. session_delete_task ────────────────────────────────────────────
    {
        "normalized_code": """\
use std::time::Duration;

use sqlx::PgPool;
use tokio::time::interval;
use tracing::info;

pub async fn delete_expired_xxxs(pool: PgPool) {
    let mut ticker = interval(Duration::from_secs(60 * 60));
    loop {
        ticker.tick().await;
        let result = sqlx::query("DELETE FROM xxxs WHERE expired_at < NOW()")
            .execute(&pool)
            .await;
        match result {
            Ok(r) => info!("Deleted {} expired xxxs", r.rows_affected()),
            Err(e) => tracing::error!("Failed to delete expired xxxs: {e}"),
        }
    }
}

pub fn spawn_cleanup_task(pool: PgPool) -> tokio::task::JoinHandle<()> {
    tokio::spawn(delete_expired_xxxs(pool))
}
""",
        "function": "session_delete_task",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/tasks.rs",
    },

    # ── 15. shuttle_workspace_shared ──────────────────────────────────────
    {
        "normalized_code": """\
# Cargo.toml (workspace root)
# [workspace]
# members = [
#     "common",
#     "services/xxx-api",
#     "services/xxx-worker",
# ]
#
# [workspace.dependencies]
# shuttle-runtime = "0.47"
# shuttle-axum = "0.47"
# shuttle-shared-db = "0.47"
# sqlx = { version = "0.7", features = ["runtime-tokio", "postgres"] }
# tokio = { version = "1", features = ["full"] }
# axum = "0.7"
# serde = { version = "1", features = ["derive"] }

# common/src/lib.rs
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct XxxId(pub String);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct XxxPayload {
    pub name: String,
    pub status: String,
}

pub fn validate_xxx_payload(payload: &XxxPayload) -> Result<(), String> {
    if payload.name.is_empty() {
        return Err("name must not be empty".to_string());
    }
    Ok(())
}
""",
        "function": "shuttle_workspace_shared",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "common/src/lib.rs",
    },
]


# ─── Audit queries ────────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "shuttle runtime main entry point",
    "shuttle postgres resource injection",
    "shuttle secrets configuration",
    "axum service shuttle deployment",
    "shuttle error handling thiserror",
    "resource input builder trait",
    "shuttle multi resource main",
    "shuttle service bind trait",
]


# ─── Fonctions ────────────────────────────────────────────────────────────────

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
            client=client, collection=COLLECTION, query_vector=vec,
            language=LANGUAGE, limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q, "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q, "function": "NO_RESULT", "file_role": "?",
                "score": 0.0, "code_preview": "", "norm_ok": False,
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
        repo_name=REPO_NAME, dry_run=DRY_RUN, count_before=count_initial,
        count_after=count_now, patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed, query_results=query_results,
        violations=violations,
    )
    print(report)


if __name__ == "__main__":
    main()
