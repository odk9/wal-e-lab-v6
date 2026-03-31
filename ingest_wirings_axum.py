"""
Wal-e Lab V6 — Wirings Ingestion Script for Axum (Rust Simple)
Tokio-rs/Axum — GitHub Examples

REPO: https://github.com/tokio-rs/axum.git
NO AST extraction (Rust language) — 8 manual wirings hardcoded.

Wirings capture inter-module connections and patterns:
- import_graph: Module tree and dependency structure
- dependency_chain: Extractor-based DI and state management
- flow_pattern: Handler ordering and CRUD operations
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
# kb_utils import removed — check_charte not needed for wirings

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/tokio-rs/axum.git"
REPO_NAME = "tokio-rs/axum"
REPO_LOCAL = "/tmp/axum"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+tokio+tower+serde"
CHARTE_VERSION = "1.0"
TAG = "wirings/tokio-rs/axum"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

CREATED_AT = int(datetime.now().timestamp())

# ============================================================================
# WIRING PAYLOADS (8 manual wirings)
# ============================================================================

WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "Rust module tree for simple Axum API with separate handler, model, and state modules",
        "modules": ["main.rs", "handlers.rs", "models.rs", "state.rs"],
        "connections": [
            "main.rs → mod handlers (use handlers::*)",
            "main.rs → mod models (use models::*)",
            "main.rs → mod state (use state::*)",
            "handlers.rs → models (use crate::models::Xxx)",
            "handlers.rs → state (use crate::state::AppState)",
            "Cargo.toml declares: axum, tokio, serde, serde_json, tower, uuid",
        ],
        "code_example": """// src/main.rs
mod handlers;
mod models;
mod state;

use axum::Router;
use std::sync::Arc;
use tokio::sync::RwLock;

#[tokio::main]
async fn main() {
    let state = Arc::new(RwLock::new(AppState::new()));
    let app = Router::new().with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Complete Axum file creation order: Cargo.toml → models.rs → state.rs → handlers.rs → main.rs",
        "modules": ["Cargo.toml", "src/models.rs", "src/state.rs", "src/handlers.rs", "src/main.rs"],
        "connections": [
            "Cargo.toml defines dependencies",
            "models.rs: Serde structs (CreateXxx, UpdateXxx, Xxx response)",
            "state.rs: AppState with Arc<RwLock<HashMap<Uuid, Xxx>>>",
            "handlers.rs: async handler functions with extractors",
            "main.rs: Router setup, state injection, listener bind",
        ],
        "code_example": """// Cargo.toml
[dependencies]
axum = "0.7"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tower = "0.4"
uuid = { version = "1", features = ["v4", "serde"] }

// src/models.rs
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Xxx {
    pub id: uuid::Uuid,
    pub title: String,
}

// src/state.rs
use std::collections::HashMap;
use uuid::Uuid;
pub struct AppState {
    pub xxxs: HashMap<Uuid, Xxx>,
}

// src/handlers.rs
use axum::State;
pub async fn list_xxxs(State(state): State<Arc<RwLock<AppState>>>) -> Json<Vec<Xxx>> {}

// src/main.rs
let app = Router::new().with_state(state);
axum::serve(listener, app).await.unwrap();
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Extractor-based dependency injection in Axum handlers: order matters (State before Body, Json consumes body)",
        "modules": ["src/handlers.rs", "src/main.rs"],
        "connections": [
            "Handler signature declares extractors: State, Path<T>, Query<T>, Json<T>",
            "Axum extracts from request automatically in order",
            "State must come before body extractors",
            "Json<T> consumes body (can only appear once per handler)",
            "Path<T> extracted from URL parameters",
            "Query<T> extracted from query string parameters",
        ],
        "code_example": """// src/handlers.rs
use axum::extract::{Path, Query, State};
use axum::Json;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct ListQuery {
    pub skip: Option<i32>,
    pub limit: Option<i32>,
}

pub async fn create_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Json(payload): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let mut st = state.write().await;
    let xxx = Xxx { id: uuid::Uuid::new_v4(), title: payload.title };
    st.xxxs.insert(xxx.id, xxx.clone());
    (StatusCode::CREATED, Json(xxx))
}

pub async fn get_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Path(id): Path<uuid::Uuid>,
) -> Result<Json<Xxx>, StatusCode> {
    let st = state.read().await;
    st.xxxs.get(&id).cloned().map(Json).ok_or(StatusCode::NOT_FOUND)
}

pub async fn list_xxxs(
    State(state): State<Arc<RwLock<AppState>>>,
    Query(q): Query<ListQuery>,
) -> Json<Vec<Xxx>> {
    let st = state.read().await;
    Json(st.xxxs.values().cloned().collect())
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "State sharing pattern: AppState wrapped in Arc<RwLock<T>> for thread-safe mutable access across handlers",
        "modules": ["src/state.rs", "src/handlers.rs", "src/main.rs"],
        "connections": [
            "AppState struct defined in state.rs",
            "Wrapped: Arc<RwLock<AppState>>",
            "Router.with_state(state) registers shared state",
            "Handler receives State(state): State<Arc<RwLock<AppState>>>",
            "state.read().await for immutable access",
            "state.write().await for mutable access",
        ],
        "code_example": """// src/state.rs
use std::collections::HashMap;
use uuid::Uuid;

pub struct AppState {
    pub xxxs: HashMap<Uuid, Xxx>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            xxxs: HashMap::new(),
        }
    }
}

// src/main.rs
use std::sync::Arc;
use tokio::sync::RwLock;

#[tokio::main]
async fn main() {
    let state = Arc::new(RwLock::new(AppState::new()));
    let app = Router::new()
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

// src/handlers.rs
pub async fn create_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Json(payload): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let mut st = state.write().await;
    st.xxxs.insert(xxx.id, xxx.clone());
    (StatusCode::CREATED, Json(xxx))
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "CRUD handler pattern for Axum: create (POST), list (GET), get (GET/:id), update (PUT/:id), delete (DELETE/:id)",
        "modules": ["src/handlers.rs"],
        "connections": [
            "create: async fn(State, Json<CreateXxx>) → (StatusCode, Json<Xxx>)",
            "list: async fn(State) → Json<Vec<Xxx>>",
            "get: async fn(State, Path<Uuid>) → Result<Json<Xxx>, StatusCode>",
            "update: async fn(State, Path<Uuid>, Json<UpdateXxx>) → Result<Json<Xxx>, StatusCode>",
            "delete: async fn(State, Path<Uuid>) → StatusCode",
        ],
        "code_example": """use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};

pub async fn create_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Json(payload): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let mut st = state.write().await;
    let xxx = Xxx { id: uuid::Uuid::new_v4(), title: payload.title };
    st.xxxs.insert(xxx.id, xxx.clone());
    (StatusCode::CREATED, Json(xxx))
}

pub async fn list_xxxs(
    State(state): State<Arc<RwLock<AppState>>>,
) -> Json<Vec<Xxx>> {
    let st = state.read().await;
    Json(st.xxxs.values().cloned().collect())
}

pub async fn get_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Path(id): Path<uuid::Uuid>,
) -> Result<Json<Xxx>, StatusCode> {
    let st = state.read().await;
    st.xxxs.get(&id).cloned().map(Json).ok_or(StatusCode::NOT_FOUND)
}

pub async fn update_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Path(id): Path<uuid::Uuid>,
    Json(payload): Json<UpdateXxx>,
) -> Result<Json<Xxx>, StatusCode> {
    let mut st = state.write().await;
    if let Some(xxx) = st.xxxs.get_mut(&id) {
        xxx.title = payload.title;
        Ok(Json(xxx.clone()))
    } else {
        Err(StatusCode::NOT_FOUND)
    }
}

pub async fn delete_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Path(id): Path<uuid::Uuid>,
) -> StatusCode {
    let mut st = state.write().await;
    if st.xxxs.remove(&id).is_some() {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::NOT_FOUND
    }
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Router composition: nested routes with prefix, middleware, and state injection for modular Axum apps",
        "modules": ["src/main.rs"],
        "connections": [
            "Router::new() creates base router",
            "Route definitions: .route(\"/path\", method(handler))",
            ".nest(\"/api/v1/xxxs\", xxxs_routes) for prefix nesting",
            ".with_state(state) injects shared state",
            ".layer(ServiceBuilder::new().layer(...)) for middleware",
            "axum::serve(listener, app) starts server",
        ],
        "code_example": """use axum::{
    routing::{get, post, put, delete},
    Router,
};
use std::sync::Arc;
use tokio::sync::RwLock;

#[tokio::main]
async fn main() {
    let state = Arc::new(RwLock::new(AppState::new()));

    let xxx_routes = Router::new()
        .route("/", get(list_xxxs).post(create_xxx))
        .route("/:id", get(get_xxx).put(update_xxx).delete(delete_xxx));

    let app = Router::new()
        .nest("/api/v1/xxxs", xxx_routes)
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:3000")
        .await
        .unwrap();

    axum::serve(listener, app)
        .await
        .unwrap();
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Error handling pattern: custom error type implementing IntoResponse trait for automatic HTTP responses",
        "modules": ["src/main.rs", "src/handlers.rs"],
        "connections": [
            "Define AppError enum (NotFound, InternalError, ValidationError)",
            "impl IntoResponse for AppError → (StatusCode, Json<ErrorResponse>)",
            "Handlers return Result<Json<T>, AppError>",
            "Or simple: Err(StatusCode::NOT_FOUND) for quick errors",
        ],
        "code_example": """use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

#[derive(Debug)]
pub enum AppError {
    NotFound(String),
    InternalError(String),
    ValidationError(String),
}

#[derive(Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_message) = match self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
            AppError::InternalError(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg),
            AppError::ValidationError(msg) => (StatusCode::BAD_REQUEST, msg),
        };
        (status, Json(ErrorResponse { error: error_message })).into_response()
    }
}

pub async fn get_xxx(
    State(state): State<Arc<RwLock<AppState>>>,
    Path(id): Path<uuid::Uuid>,
) -> Result<Json<Xxx>, AppError> {
    let st = state.read().await;
    st.xxxs.get(&id).cloned().map(Json)
        .ok_or_else(|| AppError::NotFound(format!("Xxx {} not found", id)))
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Testing pattern for Axum: use axum::test::TestClient or tower::ServiceExt, no external HTTP server needed",
        "modules": ["src/main.rs", "tests/integration_test.rs"],
        "connections": [
            "Build app router in test setup",
            "Create TestClient from router",
            "client.get(\"/api/v1/xxxs\").send().await to make requests",
            "assert_eq!(response.status(), StatusCode::OK)",
            "Use tokio::test macro for async tests",
            "No external server binding needed",
        ],
        "code_example": """#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use axum::test::TestClient;

    #[tokio::test]
    async fn test_create_xxx() {
        let state = Arc::new(RwLock::new(AppState::new()));
        let app = Router::new()
            .route(\"/api/v1/xxxs\", post(create_xxx))
            .with_state(state);

        let client = TestClient::new(app);

        let response = client
            .post(\"/api/v1/xxxs\")
            .json(&CreateXxx { title: \"Test\".to_string() })
            .send()
            .await;

        assert_eq!(response.status(), StatusCode::CREATED);
    }

    #[tokio::test]
    async fn test_list_xxxs() {
        let state = Arc::new(RwLock::new(AppState::new()));
        let app = Router::new()
            .route(\"/api/v1/xxxs\", get(list_xxxs))
            .with_state(state);

        let client = TestClient::new(app);
        let response = client.get(\"/api/v1/xxxs\").send().await;

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_get_nonexistent_xxx() {
        let state = Arc::new(RwLock::new(AppState::new()));
        let app = Router::new()
            .route(\"/api/v1/xxxs/:id\", get(get_xxx))
            .with_state(state);

        let client = TestClient::new(app);
        let response = client
            .get(\"/api/v1/xxxs/00000000-0000-0000-0000-000000000000\")
            .send()
            .await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_wirings() -> None:
    """Validate all wirings against Charte — no-op for Rust (Charte applies to Python)."""
    print("[INFO] Rust wirings — Charte validation skipped (Charte applies to Python/FastAPI)")


def clone_repo() -> None:
    """Clone Axum repo if not already present."""
    if os.path.exists(REPO_LOCAL):
        print(f"[INFO] Repository already exists at {REPO_LOCAL}")
        return

    print(f"[INFO] Cloning {REPO_URL} to {REPO_LOCAL}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, REPO_LOCAL],
        check=True,
        capture_output=True,
    )
    print("[OK] Repository cloned")


def cleanup_collection(client: QdrantClient) -> None:
    """Remove all existing points with TAG from collection."""
    print(f"[INFO] Cleanup: removing all wirings with tag {TAG}...")
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="_tag",
                            match=MatchValue(value=TAG),
                        )
                    ]
                )
            ),
        )
        print("[OK] Cleanup complete")
    except Exception as e:
        print(f"[WARN] Cleanup error: {e}")


def embed_wirings() -> list[tuple[int, str]]:
    """Embed all wirings using fastembed."""
    print(f"[INFO] Embedding {len(WIRINGS)} wirings...")
    descriptions = [w["description"] for w in WIRINGS]
    embeddings = embed_documents_batch(descriptions)
    print(f"[OK] Embedded {len(embeddings)} wirings")
    return list(enumerate(embeddings))


def upsert_wirings(client: QdrantClient, embeddings: list[tuple[int, str]]) -> None:
    """Upsert wirings to Qdrant collection."""
    print(f"[INFO] Upserting {len(embeddings)} wirings to collection {COLLECTION}...")

    points = []
    for idx, emb in embeddings:
        wiring = WIRINGS[idx]
        point_id = uuid.uuid4().int % (2**63 - 1)  # Qdrant point ID
        points.append(
            PointStruct(
                id=point_id,
                vector=emb,
                payload={
                    "wiring_type": wiring["wiring_type"],
                    "description": wiring["description"],
                    "modules": wiring["modules"],
                    "connections": wiring["connections"],
                    "code_example": wiring["code_example"],
                    "pattern_scope": wiring["pattern_scope"],
                    "language": wiring["language"],
                    "framework": wiring["framework"],
                    "stack": wiring["stack"],
                    "source_repo": wiring["source_repo"],
                    "charte_version": wiring["charte_version"],
                    "created_at": wiring["created_at"],
                    "_tag": wiring["_tag"],
                },
            )
        )

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"[OK] Upserted {len(points)} wirings")


def verify_wirings(client: QdrantClient) -> None:
    """Verify wirings in KB using semantic search with language filter."""
    print("[INFO] Verification: querying KB for Axum wirings...")

    test_queries = [
        ("Router composition and state management", "dependency_chain"),
        ("CRUD handler patterns", "flow_pattern"),
        ("Extractor-based dependency injection", "dependency_chain"),
    ]

    for query_text, expected_type in test_queries:
        print(f"  Query: {query_text}")
        query_vec = embed_query(query_text)

        results = client.query_points(
            collection_name=COLLECTION,
            query=query_vec,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="language",
                        match=MatchValue(value=LANGUAGE),
                    ),
                    FieldCondition(
                        key="_tag",
                        match=MatchValue(value=TAG),
                    ),
                ]
            ),
            limit=3,
            with_payload=True,
        ).points

        if results:
            for hit in results:
                print(
                    f"    → {hit.payload['wiring_type']}: {hit.payload['description'][:60]}..."
                )
        else:
            print(f"    [WARN] No results found")

    print("[OK] Verification complete")


def report(elapsed: float) -> None:
    """Print final report."""
    print("\n" + "=" * 80)
    print(f"WIRING INGESTION REPORT — {REPO_NAME}")
    print("=" * 80)
    print(f"Repo URL:          {REPO_URL}")
    print(f"Language:          {LANGUAGE}")
    print(f"Framework:         {FRAMEWORK}")
    print(f"Stack:             {STACK}")
    print(f"Collection:        {COLLECTION}")
    print(f"Wirings ingested:  {len(WIRINGS)}")
    print(f"Tag:               {TAG}")
    print(f"Charte version:    {CHARTE_VERSION}")
    print(f"KB path:           {KB_PATH}")
    print(f"Elapsed time:      {elapsed:.2f}s")
    print(f"Dry run:           {DRY_RUN}")
    print("=" * 80)


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    """Orchestrate wiring ingestion."""
    start = time.time()

    print(f"\n{'=' * 80}")
    print(f"Wal-e Lab V6 — Wirings Ingestion: {REPO_NAME}")
    print(f"Language: {LANGUAGE} | Framework: {FRAMEWORK}")
    print(f"{'=' * 80}\n")

    # Step 1: Clone repo
    clone_repo()

    # Step 2: Normalize (skipped for Rust)
    normalize_wirings()

    # Step 3: Initialize Qdrant
    print(f"[INFO] Connecting to Qdrant at {KB_PATH}...")
    client = QdrantClient(path=KB_PATH)
    print("[OK] Connected to Qdrant")

    # Step 4: Cleanup
    cleanup_collection(client)

    # Step 5: Embed
    embeddings = embed_wirings()

    # Step 6: Upsert
    if not DRY_RUN:
        upsert_wirings(client, embeddings)
    else:
        print(f"[DRY-RUN] Would upsert {len(embeddings)} wirings")

    # Step 7: Verify
    if not DRY_RUN:
        verify_wirings(client)

    # Step 8: Report
    elapsed = time.time() - start
    report(elapsed)
    print()


if __name__ == "__main__":
    main()
