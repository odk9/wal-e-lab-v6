#!/usr/bin/env python3
"""
Ingest Shuttle (Rust/Axum Hard) wirings into Qdrant KB.

Manual wirings extraction — no AST for Rust.
8 wirings covering:
  - Module import graph (main → routes → handlers → models → state)
  - Resource injection flow (shuttle macros → pool/secrets → state → router)
  - Router composition & nesting
  - SQLx query patterns
  - Secret management
  - Deployment metadata
  - File creation order
  - Test wiring (extract router, mock Shuttle resources)
"""

import os
import json
import time
import logging
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
except ImportError:
    raise ImportError("qdrant-client not installed. Run: pip install qdrant-client")

try:
    from embedder import embed_documents_batch
except ImportError:
    raise ImportError("embedder module not found. Ensure embedder.py is in current directory.")

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/shuttle-hq/shuttle.git"
REPO_NAME = "shuttle-hq/shuttle"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+shuttle+sqlx+tokio"
CHARTE_VERSION = "1.0"
TAG = "wirings/shuttle-hq/shuttle"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# WIRINGS DATA (8 manual wirings)
# ============================================================================

WIRINGS = [
    {
        "id": 1,
        "wiring_type": "import_graph",
        "description": "Rust module tree for Shuttle+Axum project structure: main.rs (shuttle macro entry point) imports routes module (Router builders), routes imports handlers (async request handlers), handlers imports models (sqlx::FromRow structs), models imports state (AppState definition). Cargo.toml declares shuttle-runtime, shuttle-axum, shuttle-shared-db, sqlx, axum, tokio, serde, uuid dependencies.",
        "modules": [
            "src/main.rs",
            "src/routes.rs",
            "src/handlers.rs",
            "src/models.rs",
            "src/state.rs",
            "Cargo.toml",
        ],
        "connections": [
            "src/main.rs imports mod routes, mod state, mod handlers",
            "src/routes.rs imports mod handlers, mod state",
            "src/handlers.rs imports mod models, mod state",
            "src/models.rs uses sqlx derive macros",
            "src/state.rs defines AppState struct",
            "Cargo.toml: shuttle-runtime, shuttle-axum, shuttle-shared-db, sqlx, axum",
        ],
        "code_example": """
// src/main.rs
#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
) -> shuttle_axum::ShuttleAxum {
    sqlx::migrate!().run(&pool).await?;

    let state = AppState { pool, secrets };
    let router = api_router(state);

    Ok(router.into())
}

mod routes;
mod handlers;
mod models;
mod state;

// src/routes.rs
use crate::handlers;
use crate::state::AppState;
use axum::{routing::*, Router};

pub fn api_router(state: AppState) -> Router {
    let xxxs_routes = Router::new()
        .route("/", get(handlers::list_xxxs).post(handlers::create_xxx))
        .route("/:id", get(handlers::get_xxx).put(handlers::update_xxx).delete(handlers::delete_xxx));

    Router::new()
        .nest("/xxxs", xxxs_routes)
        .with_state(state)
}

// src/state.rs
use sqlx::PgPool;
use shuttle_runtime::SecretStore;

pub struct AppState {
    pub pool: PgPool,
    pub secrets: SecretStore,
}

// src/models.rs
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct Xxx {
    pub id: i64,
    pub name: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

// src/handlers.rs
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use crate::models::Xxx;
use crate::state::AppState;

pub async fn list_xxxs(State(state): State<AppState>) -> Json<Vec<Xxx>> {
    let xxxs = sqlx::query_as::<_, Xxx>("SELECT * FROM xxxs")
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();
    Json(xxxs)
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 2,
        "wiring_type": "flow_pattern",
        "description": "Complete file creation order for Shuttle+Axum+SQLx project: 1) Cargo.toml (dependencies: shuttle-runtime, shuttle-axum, shuttle-shared-db, sqlx, axum, tokio, serde, uuid, chrono). 2) sqlx migrations/ folder (SQL files tracked by sqlx::migrate!()), e.g. migrations/001_create_xxxs.sql. 3) Shuttle.toml (project name, runtime=custom). 4) src/models.rs (data models with #[derive(FromRow, Serialize)], sqlx field attributes). 5) src/state.rs (AppState struct holding PgPool and SecretStore). 6) src/handlers.rs (CRUD handlers with State extractor). 7) src/routes.rs (Router composition and nesting). 8) src/main.rs (#[shuttle_runtime::main] entry point with resource injection and app initialization).",
        "modules": [
            "Cargo.toml",
            "Shuttle.toml",
            "migrations/001_create_xxxs.sql",
            "src/models.rs",
            "src/state.rs",
            "src/handlers.rs",
            "src/routes.rs",
            "src/main.rs",
        ],
        "connections": [
            "Cargo.toml declares all dependencies and features",
            "migrations/ SQL runs via sqlx::migrate!() in main.rs startup",
            "Shuttle.toml configures runtime metadata",
            "models.rs defines data shapes (FromRow + Serialize)",
            "state.rs wraps resources (pool, secrets) in AppState",
            "handlers.rs extracts State<AppState> and uses pool for queries",
            "routes.rs composes handlers into Router and applies state",
            "main.rs: #[shuttle_runtime::main] injects resources → sqlx::migrate!() → AppState → Router → ShuttleAxum",
        ],
        "code_example": """
// Cargo.toml
[package]
name = "shuttle-app"
version = "0.1.0"
edition = "2021"

[dependencies]
shuttle-runtime = "0.45"
shuttle-axum = "0.45"
shuttle-shared-db = { version = "0.45", features = ["postgres"] }
axum = "0.7"
tokio = { version = "1", features = ["full"] }
sqlx = { version = "0.7", features = ["postgres", "runtime-tokio-native-tls", "macros", "uuid", "chrono"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["serde", "v4"] }
chrono = { version = "0.4", features = ["serde"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["cors"] }

// migrations/001_create_xxxs.sql
CREATE TABLE xxxs (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

// Shuttle.toml
[project]
name = "shuttle-app"
runtime = "custom"

// src/models.rs
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct Xxx {
    pub id: i64,
    pub name: String,
    #[serde(with = "chrono::serde::ts_seconds")]
    pub created_at: DateTime<Utc>,
}

// src/state.rs
use shuttle_runtime::SecretStore;
use sqlx::PgPool;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub secrets: SecretStore,
}

// src/handlers.rs
use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};
use crate::models::Xxx;
use crate::state::AppState;

pub async fn list_xxxs(State(state): State<AppState>) -> Json<Vec<Xxx>> {
    let xxxs = sqlx::query_as::<_, Xxx>("SELECT * FROM xxxs ORDER BY created_at DESC")
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();
    Json(xxxs)
}

pub async fn create_xxx(
    State(state): State<AppState>,
    Json(payload): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let xxx = sqlx::query_as::<_, Xxx>(
        "INSERT INTO xxxs (name) VALUES ($1) RETURNING *"
    )
    .bind(&payload.name)
    .fetch_one(&state.pool)
    .await
    .unwrap();
    (StatusCode::CREATED, Json(xxx))
}

pub async fn get_xxx(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Option<Json<Xxx>> {
    sqlx::query_as::<_, Xxx>("SELECT * FROM xxxs WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .ok()
        .flatten()
        .map(Json)
}

// src/routes.rs
use axum::{routing::*, Router};
use crate::state::AppState;
use crate::handlers;

pub fn api_router(state: AppState) -> Router {
    let xxxs_routes = Router::new()
        .route("/", get(handlers::list_xxxs).post(handlers::create_xxx))
        .route("/:id", get(handlers::get_xxx).put(handlers::update_xxx).delete(handlers::delete_xxx));

    Router::new()
        .nest("/api/v1/xxxs", xxxs_routes)
        .with_state(state)
}

// src/main.rs
use shuttle_axum::ShuttleAxum;
use shuttle_runtime::SecretStore;
use sqlx::PgPool;
use crate::state::AppState;
use crate::routes::api_router;

mod models;
mod state;
mod handlers;
mod routes;

#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: PgPool,
    #[shuttle_runtime::Secrets] secrets: SecretStore,
) -> ShuttleAxum {
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .expect("Failed to run migrations");

    let state = AppState { pool, secrets };
    let router = api_router(state);

    Ok(router.into())
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 3,
        "wiring_type": "dependency_chain",
        "description": "Shuttle resource injection chain: #[shuttle_runtime::main] async fn main(...) declares resources via macro attributes (#[shuttle_shared_db::Postgres], #[shuttle_runtime::Secrets], #[shuttle_runtime::Metadata]). Shuttle runtime resolves and injects these resources as function parameters. PgPool and SecretStore are added to AppState. sqlx::migrate!().run(&pool) executes pending migrations before app starts. AppState is cloned and passed via Router.with_state(). ShuttleAxum wraps the Router for Shuttle deployment. No manual connection pooling or environment loading.",
        "modules": [
            "src/main.rs",
            "src/state.rs",
        ],
        "connections": [
            "#[shuttle_runtime::main] declares macro entry point",
            "#[shuttle_shared_db::Postgres] pool: PgPool parameter injection",
            "#[shuttle_runtime::Secrets] secrets: SecretStore parameter injection",
            "sqlx::migrate!().run(&pool) executes DB migrations",
            "AppState { pool, secrets } wraps injected resources",
            "Router.with_state(state) attaches AppState to all handlers",
            "ShuttleAxum return type signals Shuttle deployment",
        ],
        "code_example": """
#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
    #[shuttle_runtime::Metadata] metadata: shuttle_runtime::DeploymentMetadata,
) -> shuttle_axum::ShuttleAxum {
    // Migrations run before handlers start
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .expect("Failed to run migrations");

    // Wrap resources in AppState
    let state = AppState {
        pool,
        secrets,
        metadata,
    };

    // Build router with state attached
    let router = api_router(state);

    // Return ShuttleAxum for deployment
    Ok(router.into())
}

// AppState holds injected resources
pub struct AppState {
    pub pool: sqlx::PgPool,
    pub secrets: shuttle_runtime::SecretStore,
    pub metadata: shuttle_runtime::DeploymentMetadata,
}

// State extractor in handler
pub async fn list_xxxs(State(state): State<AppState>) -> Json<Vec<Xxx>> {
    sqlx::query_as::<_, Xxx>("SELECT * FROM xxxs")
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default()
        .into()
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 4,
        "wiring_type": "dependency_chain",
        "description": "Router composition with nesting in Shuttle+Axum: separate Router defined for each feature module (e.g., xxxs_routes, yyys_routes). Each router defines its own routes (.route(), .nest()). All feature routers are nested under API prefix (/api/v1) in main router. Main router is built with .with_state(state) to attach AppState. Nested structure allows feature isolation and reusability. Router composition happens in routes.rs module, called from main.rs after state creation.",
        "modules": [
            "src/routes.rs",
            "src/main.rs",
        ],
        "connections": [
            "src/routes.rs exports fn api_router(state: AppState) -> Router",
            "Each feature gets its own Router builder (xxxs_routes, yyys_routes, etc.)",
            ".route() adds individual endpoints",
            ".nest() adds feature routers under path prefix",
            "Main Router.new().nest(\"/api/v1\", ...) groups all features",
            ".with_state(state) attaches AppState for all handlers",
            "src/main.rs calls api_router(state) after state initialization",
        ],
        "code_example": """
// src/routes.rs
use axum::{routing::*, Router};
use crate::state::AppState;
use crate::handlers;

pub fn api_router(state: AppState) -> Router {
    // Feature 1: xxxs CRUD
    let xxxs_routes = Router::new()
        .route("/", get(handlers::list_xxxs).post(handlers::create_xxx))
        .route("/:id", get(handlers::get_xxx).put(handlers::update_xxx).delete(handlers::delete_xxx))
        .route("/:id/validate", post(handlers::validate_xxx));

    // Feature 2: yyys nested
    let yyys_routes = Router::new()
        .route("/", get(handlers::list_yyys).post(handlers::create_yyy))
        .route("/:id", get(handlers::get_yyy).delete(handlers::delete_yyy));

    // Health check
    let health = Router::new()
        .route("/health", get(handlers::health_check));

    // Compose all
    Router::new()
        .nest("/xxxs", xxxs_routes)
        .nest("/yyys", yyys_routes)
        .nest("/", health)
        .route("/api/docs", get(|| async { "API Docs" }))
        .with_state(state)
}

// src/main.rs
#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
) -> shuttle_axum::ShuttleAxum {
    sqlx::migrate!().run(&pool).await?;

    let state = AppState { pool, secrets };

    // api_router() handles all nesting internally
    let router = api_router(state);

    Ok(router.into())
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 5,
        "wiring_type": "flow_pattern",
        "description": "SQLx compile-time checked query patterns in Shuttle+Axum: sqlx::query_as!() macro (compile-time) or sqlx::query_as() builder (runtime). For SELECT: sqlx::query_as!(Xxx, \"SELECT * FROM xxxs WHERE id = $1\", id).fetch_optional(&pool) returns Result<Option<Xxx>>. For INSERT: sqlx::query!(\"INSERT INTO xxxs (...) VALUES ($1, $2)\", ...).execute(&pool) returns Result<PgQueryResult>. Positional parameters ($1, $2, ...) match Rust fn parameter order. All queries validated against migrations at compile time. Type inference from #[derive(FromRow)] on models.",
        "modules": [
            "src/handlers.rs",
            "src/models.rs",
            "migrations/",
        ],
        "connections": [
            "sqlx::FromRow derives on models (Xxx, Yyy, etc.)",
            "sqlx::query_as!() macro requires .sqlx/query-*.json (generated by sqlx prepare)",
            "sqlx::query_as() builder runtime-checked (no compile-time validation)",
            "Positional parameters ($1, $2) match function argument order",
            ".fetch_one() / .fetch_optional() / .fetch_all() return Result",
            "migrations/ SQL schema validated against queries",
        ],
        "code_example": """
// src/models.rs
use sqlx::FromRow;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct Xxx {
    pub id: i64,
    pub name: String,
    pub status: String,
    pub created_at: DateTime<Utc>,
}

// src/handlers.rs
use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};
use crate::models::Xxx;
use crate::state::AppState;

// SELECT optional (single row)
pub async fn get_xxx(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Option<Json<Xxx>> {
    sqlx::query_as::<_, Xxx>("SELECT id, name, status, created_at FROM xxxs WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .ok()
        .flatten()
        .map(Json)
}

// SELECT all (list)
pub async fn list_xxxs(State(state): State<AppState>) -> Json<Vec<Xxx>> {
    let xxxs = sqlx::query_as::<_, Xxx>("SELECT id, name, status, created_at FROM xxxs ORDER BY created_at DESC")
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();
    Json(xxxs)
}

// INSERT with auto-increment
pub async fn create_xxx(
    State(state): State<AppState>,
    Json(payload): Json<CreateXxxRequest>,
) -> (StatusCode, Json<Xxx>) {
    let xxx = sqlx::query_as::<_, Xxx>(
        "INSERT INTO xxxs (name, status) VALUES ($1, $2) RETURNING id, name, status, created_at"
    )
    .bind(&payload.name)
    .bind("active")
    .fetch_one(&state.pool)
    .await
    .expect("Failed to insert");

    (StatusCode::CREATED, Json(xxx))
}

// UPDATE by id
pub async fn update_xxx(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(payload): Json<UpdateXxxRequest>,
) -> (StatusCode, Json<Xxx>) {
    let xxx = sqlx::query_as::<_, Xxx>(
        "UPDATE xxxs SET name = $1, status = $2 WHERE id = $3 RETURNING id, name, status, created_at"
    )
    .bind(&payload.name)
    .bind(&payload.status)
    .bind(id)
    .fetch_one(&state.pool)
    .await
    .expect("Failed to update");

    (StatusCode::OK, Json(xxx))
}

// DELETE by id
pub async fn delete_xxx(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> StatusCode {
    let _ = sqlx::query!("DELETE FROM xxxs WHERE id = $1", id)
        .execute(&state.pool)
        .await;
    StatusCode::NO_CONTENT
}

// migrations/001_create_xxxs.sql
CREATE TABLE xxxs (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 6,
        "wiring_type": "dependency_chain",
        "description": "Secret management in Shuttle: #[shuttle_runtime::Secrets] attribute injects SecretStore resolved from Shuttle platform (or .Secrets.local file locally). SecretStore is a key-value store. secrets.get(\"KEY\") returns Option<String>. For required secrets, use .context(\"KEY not found\") with anyhow::Result or unwrap(). Secrets are passed via AppState to all handlers. No .env parsing or environment variables — Shuttle handles secret provisioning. In local development, create .Secrets.local file with KEY=VALUE pairs.",
        "modules": [
            "src/main.rs",
            "src/state.rs",
            ".Secrets.local",
        ],
        "connections": [
            "#[shuttle_runtime::Secrets] injects SecretStore from Shuttle platform",
            "AppState wraps SecretStore",
            "State(state) extractor in handlers accesses secrets",
            "secrets.get(\"KEY\") returns Option<String>",
            "Local development: .Secrets.local file for testing",
            "No environment variable loading needed",
        ],
        "code_example": """
// .Secrets.local (local development only)
DATABASE_URL=postgres://user:pass@localhost/db
API_KEY=test-key-12345
JWT_SECRET=my-secret-key

// src/main.rs
#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
) -> shuttle_axum::ShuttleAxum {
    // Optional: validate required secrets at startup
    let api_key = secrets.get("API_KEY").expect("API_KEY not set");
    let jwt_secret = secrets.get("JWT_SECRET").expect("JWT_SECRET not set");

    sqlx::migrate!().run(&pool).await?;

    let state = AppState {
        pool,
        secrets,
        api_key,
        jwt_secret,
    };

    let router = api_router(state);
    Ok(router.into())
}

// src/state.rs
use shuttle_runtime::SecretStore;
use sqlx::PgPool;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub secrets: SecretStore,
    pub api_key: String,
    pub jwt_secret: String,
}

// src/handlers.rs — using secrets in middleware or handlers
use axum::{
    http::StatusCode,
    middleware::Next,
    response::Response,
    Json,
};
use crate::state::AppState;

pub async fn validate_api_key(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::json!({"message": "valid"})>, StatusCode> {
    let auth_header = headers.get("X-API-Key").and_then(|h| h.to_str().ok());

    match auth_header {
        Some(key) if key == &state.api_key => Ok(Json(serde_json::json!({"message": "valid"}))),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

pub async fn get_secret_info(
    State(state): State<AppState>,
) -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "has_api_key": state.secrets.get("API_KEY").is_some(),
        "has_jwt_secret": state.secrets.get("JWT_SECRET").is_some(),
    }))
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 7,
        "wiring_type": "flow_pattern",
        "description": "Deployment metadata wiring in Shuttle: #[shuttle_runtime::Metadata] metadata: DeploymentMetadata optional parameter provides runtime deployment context. metadata.project_name() returns project name from Shuttle.toml. metadata.env() returns DeploymentEnv::Production or Local. metadata.server_name() returns unique service identifier. Used for conditional logic: if metadata.env == DeploymentEnv::Production { use_prod_db() } else { use_test_db() }. Metadata is immutable and provided by Shuttle runtime. Useful for feature flags, logging, and environment-specific behavior.",
        "modules": [
            "src/main.rs",
            "src/state.rs",
            "Shuttle.toml",
        ],
        "connections": [
            "#[shuttle_runtime::Metadata] injects DeploymentMetadata from Shuttle runtime",
            "metadata.project_name() from [project] name in Shuttle.toml",
            "metadata.env() indicates Production or Local environment",
            "Conditional logic branches on environment",
            "metadata available in AppState or as handler parameter",
        ],
        "code_example": """
// Shuttle.toml
[project]
name = "my-app"
runtime = "custom"

// src/main.rs
use shuttle_runtime::{DeploymentEnv, Metadata};

#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
    #[shuttle_runtime::Metadata] metadata: Metadata,
) -> shuttle_axum::ShuttleAxum {
    let project_name = metadata.project_name();
    let env = metadata.env();

    // Conditional behavior based on environment
    match env {
        DeploymentEnv::Production => {
            println!("[PROD] Deploying {}", project_name);
            // Use production secrets, additional logging, etc.
        }
        DeploymentEnv::Local => {
            println!("[LOCAL] Running {} locally", project_name);
            // Use test fixtures, relaxed logging
        }
    }

    sqlx::migrate!().run(&pool).await?;

    let state = AppState {
        pool,
        secrets,
        project_name: project_name.to_string(),
        is_production: env == DeploymentEnv::Production,
    };

    let router = api_router(state);
    Ok(router.into())
}

// src/state.rs
#[derive(Clone)]
pub struct AppState {
    pub pool: sqlx::PgPool,
    pub secrets: shuttle_runtime::SecretStore,
    pub project_name: String,
    pub is_production: bool,
}

// src/handlers.rs — conditional logic
pub async fn health_check(State(state): State<AppState>) -> Json<serde_json::Value> {
    let status = if state.is_production { "prod" } else { "local" };
    Json(serde_json::json!({
        "status": "ok",
        "project": state.project_name,
        "environment": status,
    }))
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "id": 8,
        "wiring_type": "flow_pattern",
        "description": "Test wiring for Shuttle+Axum: Shuttle runtime does NOT run during tests. Extract router building into separate fn api_router(pool, secrets) -> Router. Tests create an in-memory SQLite or PostgreSQL test database (sqlx::test fixture or test pool). Tests instantiate mock AppState with test pool and SecretStore. Tests call api_router(state) directly (no Shuttle macros). Use tower::ServiceExt::oneshot() or axum::test utilities for HTTP testing. Handlers remain unchanged — tests inject real pools, not mocks.",
        "modules": [
            "src/main.rs",
            "src/routes.rs",
            "src/handlers.rs",
            "tests/integration_tests.rs",
        ],
        "connections": [
            "src/routes.rs exports fn api_router(state: AppState) -> Router",
            "tests/integration_tests.rs imports api_router",
            "Test pool: sqlx::PgPool or :memory: SQLite",
            "Mock SecretStore: shuttle_runtime::SecretStore::default() or custom",
            "Test AppState: AppState { pool: test_pool, secrets: mock_secrets }",
            "api_router(test_state) returns Router for testing",
            "tower::ServiceExt::oneshot() or axum test utilities for HTTP",
        ],
        "code_example": """
// src/routes.rs
use axum::Router;
use crate::state::AppState;
use crate::handlers;

pub fn api_router(state: AppState) -> Router {
    Router::new()
        .nest("/api/v1/xxxs", xxxs_routes)
        .with_state(state)
}

// src/main.rs
#[shuttle_runtime::main]
async fn shuttle(
    #[shuttle_shared_db::Postgres] pool: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
) -> shuttle_axum::ShuttleAxum {
    sqlx::migrate!().run(&pool).await?;
    let state = AppState { pool, secrets };
    let router = api_router(state);
    Ok(router.into())
}

// tests/integration_tests.rs
#[cfg(test)]
mod tests {
    use axum::http::{Request, StatusCode};
    use tower::ServiceExt;
    use sqlx::postgres::PgPoolOptions;
    use shuttle_runtime::SecretStore;
    use crate::state::AppState;
    use crate::routes::api_router;
    use crate::models::Xxx;
    use body::Body;

    async fn test_setup() -> AppState {
        // Create test database pool (local test DB or Docker)
        let database_url = "postgres://user:pass@localhost/test_db";
        let pool = PgPoolOptions::new()
            .max_connections(5)
            .connect(database_url)
            .await
            .expect("Failed to create test pool");

        // Run migrations
        sqlx::migrate!().run(&pool).await.expect("Failed to run migrations");

        // Mock secrets
        let mut secrets = SecretStore::default();
        // Note: SecretStore doesn't expose public insert in production,
        // so create custom mock struct if needed for tests

        AppState { pool, secrets }
    }

    #[tokio::test]
    async fn test_list_xxxs() {
        let state = test_setup().await;
        let app = api_router(state);

        let response = app
            .oneshot(Request::builder().uri("/api/v1/xxxs").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_create_xxx() {
        let state = test_setup().await;
        let app = api_router(state);

        let body = serde_json::json!({"name": "Test Xxx"});
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/xxxs")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&body).unwrap()))
                    .unwrap()
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);
    }
}
""",
        "pattern_scope": "shuttle_deploy",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
]

# ============================================================================
# QDRANT CLIENT & COLLECTION
# ============================================================================


def connect_qdrant() -> QdrantClient:
    """Connect to local Qdrant instance."""
    if not os.path.exists(KB_PATH):
        logger.error(f"KB path {KB_PATH} not found. Run setup_collections.py first.")
        raise FileNotFoundError(KB_PATH)

    client = QdrantClient(path=KB_PATH)
    logger.info(f"Connected to Qdrant at {KB_PATH}")
    return client


def cleanup_existing_wirings(client: QdrantClient, tag: str) -> None:
    """Delete existing wirings for this repo before inserting new ones."""
    try:
        from qdrant_client.models import FilterSelector

        # Use FilterSelector to delete by tag
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="_tag",
                    match=MatchValue(value=tag)
                )
            ]
        )

        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(filter=filter_condition),
        )
        logger.info(f"Cleaned up existing wirings with tag={tag}")
    except Exception as e:
        logger.warning(f"Cleanup failed (may be first run): {e}")


def ingest_wirings(client: QdrantClient) -> None:
    """Insert 8 wirings into Qdrant."""
    import uuid

    if DRY_RUN:
        logger.info("[DRY RUN] Would insert the following wirings:")
        for wiring in WIRINGS:
            logger.info(f"  - {wiring['id']}: {wiring['wiring_type']} / {wiring['pattern_scope']}")
        return

    # Batch embed all descriptions
    descriptions = [w["description"] for w in WIRINGS]
    vectors = embed_documents_batch(descriptions)
    logger.info(f"Embedded {len(vectors)} descriptions")

    points = []
    for wiring, vector in zip(WIRINGS, vectors):
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=wiring,
        )
        points.append(point)

    try:
        client.upsert(
            collection_name=COLLECTION,
            points=points,
        )
        logger.info(f"Ingested {len(points)} wirings into {COLLECTION}")
    except Exception as e:
        logger.error(f"Failed to ingest wirings: {e}")
        raise


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    """Main ingest pipeline."""
    logger.info("=" * 80)
    logger.info(f"SHUTTLE WIRINGS INGESTION — {REPO_NAME}")
    logger.info(f"Repo: {REPO_URL}")
    logger.info(f"Language: {LANGUAGE} | Framework: {FRAMEWORK} | Stack: {STACK}")
    logger.info(f"Wirings: {len(WIRINGS)}")
    logger.info("=" * 80)

    # Connect
    client = connect_qdrant()

    # Check collection exists
    try:
        col = client.get_collection(COLLECTION)
        logger.info(f"Collection '{COLLECTION}' has {col.points_count} points")
    except Exception as e:
        logger.error(f"Collection '{COLLECTION}' not found: {e}")
        raise

    # Cleanup old wirings for this repo
    cleanup_existing_wirings(client, TAG)

    # Ingest
    ingest_wirings(client)

    logger.info("=" * 80)
    logger.info("Ingestion complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
