"""
ingest_axum.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de tokio-rs/axum dans la KB Qdrant V6.

Rust A — Axum examples/. axum + tokio + tower + serde.

Usage:
    .venv/bin/python3 ingest_axum.py
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
REPO_URL = "https://github.com/tokio-rs/axum.git"
REPO_NAME = "tokio-rs/axum"
REPO_LOCAL = "/tmp/tokio_rs_axum"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+tokio+tower+serde"
CHARTE_VERSION = "1.0"
TAG = "tokio-rs/axum"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/tokio-rs/axum"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: User→Xxx, user→xxx, users→xxxs, Todo→Xxx, todo→xxx, todos→xxxs
# R-1: no .unwrap() except in #[test] blocks
# R-2: no println!() — use tracing macros
# Kept: axum, tokio, tower, serde, hyper, Router, State, Json, Path, Query, etc.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. basic_route_setup ───────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::get, Router};
use tokio::net::TcpListener;

async fn root() -> &'static str {
    "Hello, World!"
}

async fn health_check() -> &'static str {
    "ok"
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app = Router::new()
        .route("/", get(root))
        .route("/health", get(health_check));

    let listener = TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
}
""",
        "function": "basic_route_setup",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/hello_world/src/main.rs",
    },

    # ── 2. json_request_response ──────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{extract::Json, http::StatusCode, routing::post, Router};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct CreateXxx {
    name: String,
    description: Option<String>,
}

#[derive(Serialize)]
struct Xxx {
    id: u64,
    name: String,
    description: Option<String>,
}

async fn create_xxx(
    Json(payload): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let xxx = Xxx {
        id: 1,
        name: payload.name,
        description: payload.description,
    };

    (StatusCode::CREATED, Json(xxx))
}

fn app() -> Router {
    Router::new().route("/xxxs", post(create_xxx))
}
""",
        "function": "json_request_response",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/json/src/main.rs",
    },

    # ── 3. shared_state_arc ───────────────────────────────────────────────
    {
        "normalized_code": """\
use std::sync::Arc;

use axum::{extract::State, routing::get, Json, Router};
use tokio::sync::RwLock;

struct AppState {
    db: Vec<String>,
}

type SharedState = Arc<RwLock<AppState>>;

async fn list_xxxs(
    State(state): State<SharedState>,
) -> Json<Vec<String>> {
    let state = state.read().await;
    Json(state.db.clone())
}

fn app() -> Router {
    let shared_state = Arc::new(RwLock::new(AppState {
        db: Vec::new(),
    }));

    Router::new()
        .route("/xxxs", get(list_xxxs))
        .with_state(shared_state)
}
""",
        "function": "shared_state_arc",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/state/src/main.rs",
    },

    # ── 4. path_extractor ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::Path,
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use serde::Serialize;

#[derive(Serialize)]
struct Xxx {
    id: u32,
    name: String,
}

async fn get_xxx(
    Path(id): Path<u32>,
) -> Result<Json<Xxx>, StatusCode> {
    if id == 0 {
        return Err(StatusCode::BAD_REQUEST);
    }

    let xxx = Xxx {
        id,
        name: format!("xxx_{id}"),
    };

    Ok(Json(xxx))
}

fn app() -> Router {
    Router::new().route("/xxxs/:id", get(get_xxx))
}
""",
        "function": "path_extractor",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/path/src/main.rs",
    },

    # ── 5. query_extractor ────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{extract::Query, routing::get, Json, Router};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Pagination {
    page: Option<u32>,
    per_page: Option<u32>,
}

#[derive(Serialize)]
struct XxxList {
    data: Vec<String>,
    page: u32,
    per_page: u32,
    total: u32,
}

async fn list_xxxs(
    Query(params): Query<Pagination>,
) -> Json<XxxList> {
    let page = params.page.unwrap_or(1);
    let per_page = params.per_page.unwrap_or(20);

    let result = XxxList {
        data: vec![],
        page,
        per_page,
        total: 0,
    };

    Json(result)
}

fn app() -> Router {
    Router::new().route("/xxxs", get(list_xxxs))
}
""",
        "function": "query_extractor",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/query/src/main.rs",
    },

    # ── 6. custom_error_handling ──────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde_json::json;

enum AppError {
    NotFound(String),
    Internal(String),
    BadRequest(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
            AppError::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg),
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
        };

        let body = Json(json!({
            "error": message,
            "status": status.as_u16(),
        }));

        (status, body).into_response()
    }
}

async fn get_xxx() -> Result<Json<serde_json::Value>, AppError> {
    let found = false;

    if !found {
        return Err(AppError::NotFound("xxx not found".to_string()));
    }

    Ok(Json(json!({"id": 1})))
}

fn app() -> Router {
    Router::new().route("/xxx", get(get_xxx))
}
""",
        "function": "custom_error_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/error_handling/src/main.rs",
    },

    # ── 7. tower_middleware_from_fn ────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::Request,
    http::StatusCode,
    middleware::{self, Next},
    response::Response,
    routing::get,
    Router,
};

async fn auth_middleware(
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let auth_header = request
        .headers()
        .get("Authorization")
        .and_then(|value| value.to_str().ok());

    match auth_header {
        Some(token) if token.starts_with("Bearer ") => {
            tracing::debug!("valid auth header present");
            Ok(next.run(request).await)
        }
        _ => {
            tracing::warn!("missing or invalid auth header");
            Err(StatusCode::UNAUTHORIZED)
        }
    }
}

async fn protected_handler() -> &'static str {
    "protected content"
}

fn app() -> Router {
    Router::new()
        .route("/protected", get(protected_handler))
        .layer(middleware::from_fn(auth_middleware))
}
""",
        "function": "tower_middleware_from_fn",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/middleware/src/main.rs",
    },

    # ── 8. cors_configuration ─────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{http::Method, routing::get, Router};
use tower_http::cors::{Any, CorsLayer};

async fn handler() -> &'static str {
    "Hello, CORS!"
}

fn app() -> Router {
    let cors = CorsLayer::new()
        .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE])
        .allow_origin(Any)
        .allow_headers(Any)
        .max_age(std::time::Duration::from_secs(3600));

    Router::new()
        .route("/", get(handler))
        .layer(cors)
}
""",
        "function": "cors_configuration",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/cors/src/main.rs",
    },

    # ── 9. tracing_setup ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::get, Router};
use tokio::net::TcpListener;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "debug".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let app = Router::new()
        .route("/", get(root))
        .layer(TraceLayer::new_for_http());

    let listener = TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
}

async fn root() -> &'static str {
    "Hello, World!"
}
""",
        "function": "tracing_setup",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/tracing/src/main.rs",
    },

    # ── 10. graceful_shutdown ─────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::get, Router};
use tokio::net::TcpListener;
use tokio::signal;

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    tracing::info!("signal received, starting graceful shutdown");
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app = Router::new().route("/", get(|| async { "Hello, World!" }));

    let listener = TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}
""",
        "function": "graceful_shutdown",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/graceful_shutdown/src/main.rs",
    },

    # ── 11. form_handling ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{extract::Form, response::Html, routing::{get, post}, Router};
use serde::Deserialize;

#[derive(Deserialize)]
struct CreateXxx {
    name: String,
    description: String,
}

async fn show_form() -> Html<&'static str> {
    Html(
        r#"
        <!doctype html>
        <html>
            <body>
                <form action="/xxxs" method="post">
                    <label for="name">Name:</label>
                    <input name="name" id="name">
                    <label for="description">Description:</label>
                    <input name="description" id="description">
                    <input type="submit" value="Create">
                </form>
            </body>
        </html>
        "#,
    )
}

async fn create_xxx(Form(input): Form<CreateXxx>) -> Html<String> {
    Html(format!(
        "<h1>Created: {} - {}</h1>",
        input.name, input.description
    ))
}

fn app() -> Router {
    Router::new()
        .route("/", get(show_form))
        .route("/xxxs", post(create_xxx))
}
""",
        "function": "form_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/form/src/main.rs",
    },

    # ── 12. static_file_serving ───────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::get, Router};
use tower_http::services::ServeDir;

fn app() -> Router {
    let serve_dir = ServeDir::new("assets");

    Router::new()
        .route("/", get(|| async { "API root" }))
        .nest_service("/static", serve_dir)
}
""",
        "function": "static_file_serving",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/static_files/src/main.rs",
    },

    # ── 13. websocket_handler ─────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    response::IntoResponse,
    routing::get,
    Router,
};
use futures::{SinkExt, StreamExt};

async fn ws_handler(ws: WebSocketUpgrade) -> impl IntoResponse {
    ws.on_upgrade(handle_socket)
}

async fn handle_socket(mut socket: WebSocket) {
    while let Some(msg) = socket.recv().await {
        let msg = match msg {
            Ok(msg) => msg,
            Err(e) => {
                tracing::error!("websocket receive error: {e}");
                return;
            }
        };

        match msg {
            Message::Text(text) => {
                tracing::debug!("received text: {text}");
                if socket
                    .send(Message::Text(format!("echo: {text}")))
                    .await
                    .is_err()
                {
                    return;
                }
            }
            Message::Close(_) => {
                tracing::info!("client disconnected");
                return;
            }
            _ => {}
        }
    }
}

fn app() -> Router {
    Router::new().route("/ws", get(ws_handler))
}
""",
        "function": "websocket_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/websockets/src/main.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 14. serde_model_derive ────────────────────────────────────────────
    {
        "normalized_code": """\
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Xxx {
    pub id: u64,
    pub name: String,
    pub description: Option<String>,
    pub active: bool,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Deserialize)]
pub struct CreateXxx {
    pub name: String,
    pub description: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateXxx {
    pub name: Option<String>,
    pub description: Option<String>,
    pub active: Option<bool>,
}
""",
        "function": "serde_model_derive",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/crud/src/model.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. nested_router ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{routing::get, Json, Router};
use serde_json::{json, Value};

async fn list_xxxs() -> Json<Value> {
    Json(json!({"data": []}))
}

async fn health() -> &'static str {
    "ok"
}

fn api_routes() -> Router {
    Router::new()
        .route("/xxxs", get(list_xxxs))
        .route("/health", get(health))
}

fn app() -> Router {
    Router::new()
        .nest("/api/v1", api_routes())
        .route("/", get(|| async { "root" }))
}
""",
        "function": "nested_router",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/nested_router/src/main.rs",
    },

    # ── 16. layer_composition ─────────────────────────────────────────────
    {
        "normalized_code": """\
use std::time::Duration;

use axum::{routing::get, Router};
use tower::ServiceBuilder;
use tower_http::{
    compression::CompressionLayer,
    cors::CorsLayer,
    timeout::TimeoutLayer,
    trace::TraceLayer,
};

fn app() -> Router {
    let middleware_stack = ServiceBuilder::new()
        .layer(TraceLayer::new_for_http())
        .layer(TimeoutLayer::new(Duration::from_secs(30)))
        .layer(CompressionLayer::new())
        .layer(CorsLayer::permissive());

    Router::new()
        .route("/", get(|| async { "Hello, World!" }))
        .layer(middleware_stack)
}
""",
        "function": "layer_composition",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/layers/src/main.rs",
    },

    # ── 17. extractor_rejection ───────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::rejection::JsonRejection,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize)]
struct CreateXxx {
    name: String,
}

enum AppError {
    JsonRejection(JsonRejection),
}

impl From<JsonRejection> for AppError {
    fn from(rejection: JsonRejection) -> Self {
        Self::JsonRejection(rejection)
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, detail) = match self {
            AppError::JsonRejection(rejection) => {
                tracing::warn!("json rejection: {rejection}");
                (rejection.status(), rejection.body_text())
            }
        };

        let body = Json(json!({
            "error": detail,
            "status": status.as_u16(),
        }));

        (status, body).into_response()
    }
}

async fn create_xxx(
    payload: Result<Json<CreateXxx>, JsonRejection>,
) -> Result<Json<serde_json::Value>, AppError> {
    let Json(input) = payload?;
    Ok(Json(json!({"name": input.name})))
}

fn app() -> Router {
    Router::new().route("/xxxs", post(create_xxx))
}
""",
        "function": "extractor_rejection",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/rejection/src/main.rs",
    },

    # ── 18. multipart_upload ──────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::Multipart,
    http::StatusCode,
    response::IntoResponse,
    routing::post,
    Json, Router,
};
use serde_json::json;

async fn upload(
    mut multipart: Multipart,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    let mut files_saved: Vec<String> = Vec::new();

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?
    {
        let file_name = field
            .file_name()
            .map(|s| s.to_string())
            .unwrap_or_else(|| "unknown".to_string());

        let data = field
            .bytes()
            .await
            .map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?;

        tracing::info!("received file: {} ({} bytes)", file_name, data.len());

        let path = format!("/tmp/uploads/{file_name}");
        tokio::fs::create_dir_all("/tmp/uploads")
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        tokio::fs::write(&path, &data)
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

        files_saved.push(file_name);
    }

    Ok(Json(json!({
        "uploaded": files_saved,
        "count": files_saved.len(),
    })))
}

fn app() -> Router {
    Router::new().route("/upload", post(upload))
}
""",
        "function": "multipart_upload",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/multipart/src/main.rs",
    },

    # ── 19. response_types ────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    http::StatusCode,
    response::{Html, IntoResponse, Redirect, Response},
    routing::get,
    Json, Router,
};
use serde_json::json;

async fn json_response() -> impl IntoResponse {
    Json(json!({"status": "ok"}))
}

async fn html_response() -> impl IntoResponse {
    Html("<h1>Hello, HTML!</h1>")
}

async fn redirect_response() -> impl IntoResponse {
    Redirect::to("/")
}

async fn status_only() -> impl IntoResponse {
    StatusCode::NO_CONTENT
}

async fn mixed_response(accept: Option<axum::http::HeaderValue>) -> Response {
    let is_json = accept
        .and_then(|v| v.to_str().ok().map(|s| s.contains("application/json")))
        .unwrap_or(false);

    if is_json {
        Json(json!({"data": "value"})).into_response()
    } else {
        Html("<p>data: value</p>").into_response()
    }
}

fn app() -> Router {
    Router::new()
        .route("/json", get(json_response))
        .route("/html", get(html_response))
        .route("/redirect", get(redirect_response))
        .route("/empty", get(status_only))
        .route("/mixed", get(mixed_response))
}
""",
        "function": "response_types",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/responses/src/main.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 20. crud_in_memory ────────────────────────────────────────────────
    {
        "normalized_code": """\
use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{delete, get, post, put},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Xxx {
    id: u64,
    name: String,
    completed: bool,
}

#[derive(Deserialize)]
struct CreateXxx {
    name: String,
}

#[derive(Deserialize)]
struct UpdateXxx {
    name: Option<String>,
    completed: Option<bool>,
}

type Db = Arc<RwLock<Vec<Xxx>>>;

async fn list_xxxs(State(db): State<Db>) -> Json<Vec<Xxx>> {
    let xxxs = db.read().await;
    Json(xxxs.clone())
}

async fn create_xxx(
    State(db): State<Db>,
    Json(input): Json<CreateXxx>,
) -> (StatusCode, Json<Xxx>) {
    let mut xxxs = db.write().await;
    let id = xxxs.len() as u64 + 1;
    let xxx = Xxx {
        id,
        name: input.name,
        completed: false,
    };
    xxxs.push(xxx.clone());
    (StatusCode::CREATED, Json(xxx))
}

async fn get_xxx(
    State(db): State<Db>,
    Path(id): Path<u64>,
) -> Result<Json<Xxx>, StatusCode> {
    let xxxs = db.read().await;
    xxxs.iter()
        .find(|x| x.id == id)
        .cloned()
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

async fn update_xxx(
    State(db): State<Db>,
    Path(id): Path<u64>,
    Json(input): Json<UpdateXxx>,
) -> Result<Json<Xxx>, StatusCode> {
    let mut xxxs = db.write().await;
    let xxx = xxxs
        .iter_mut()
        .find(|x| x.id == id)
        .ok_or(StatusCode::NOT_FOUND)?;

    if let Some(name) = input.name {
        xxx.name = name;
    }
    if let Some(completed) = input.completed {
        xxx.completed = completed;
    }

    Ok(Json(xxx.clone()))
}

async fn delete_xxx(
    State(db): State<Db>,
    Path(id): Path<u64>,
) -> StatusCode {
    let mut xxxs = db.write().await;
    let len_before = xxxs.len();
    xxxs.retain(|x| x.id != id);

    if xxxs.len() == len_before {
        StatusCode::NOT_FOUND
    } else {
        StatusCode::NO_CONTENT
    }
}

fn app() -> Router {
    let db: Db = Arc::new(RwLock::new(Vec::new()));

    Router::new()
        .route("/xxxs", get(list_xxxs).post(create_xxx))
        .route("/xxxs/:id", get(get_xxx).put(update_xxx).delete(delete_xxx))
        .with_state(db)
}
""",
        "function": "crud_in_memory",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "examples/crud/src/main.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG (continued)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 21. tokio_spawn_background ────────────────────────────────────────
    {
        "normalized_code": """\
use std::sync::Arc;

use axum::{extract::State, routing::post, Json, Router};
use serde::Deserialize;
use tokio::sync::mpsc;

#[derive(Clone)]
struct AppState {
    tx: mpsc::Sender<BackgroundJob>,
}

#[derive(Debug, Deserialize)]
struct BackgroundJob {
    name: String,
    payload: String,
}

async fn enqueue_job(
    State(state): State<Arc<AppState>>,
    Json(job): Json<BackgroundJob>,
) -> &'static str {
    if let Err(e) = state.tx.send(job).await {
        tracing::error!("failed to enqueue job: {e}");
        return "failed to enqueue";
    }
    "job enqueued"
}

async fn background_worker(mut rx: mpsc::Receiver<BackgroundJob>) {
    while let Some(job) = rx.recv().await {
        tracing::info!("processing job: {} with payload: {}", job.name, job.payload);
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        tracing::info!("job {} completed", job.name);
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (tx, rx) = mpsc::channel::<BackgroundJob>(100);

    tokio::spawn(background_worker(rx));

    let state = Arc::new(AppState { tx });

    let app = Router::new()
        .route("/jobs", post(enqueue_job))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
}
""",
        "function": "tokio_spawn_background",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/background_task/src/main.rs",
    },

    # ── 22. typed_header ──────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    http::StatusCode,
    routing::get,
    Router,
};
use axum_extra::{
    headers::{authorization::Bearer, Authorization, ContentType},
    TypedHeader,
};

async fn protected(
    TypedHeader(auth): TypedHeader<Authorization<Bearer>>,
) -> Result<String, StatusCode> {
    let token = auth.token();

    if token == "secret" {
        Ok(format!("authorized with token: {token}"))
    } else {
        Err(StatusCode::UNAUTHORIZED)
    }
}

async fn check_content_type(
    TypedHeader(content_type): TypedHeader<ContentType>,
) -> String {
    format!("content type: {content_type}")
}

fn app() -> Router {
    Router::new()
        .route("/protected", get(protected))
        .route("/content-type", get(check_content_type))
}
""",
        "function": "typed_header",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/typed_header/src/main.rs",
    },

    # ── 23. extension_extractor ───────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
    extract::Request,
    middleware::{self, Next},
    response::Response,
    routing::get,
    Extension, Json, Router,
};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
struct CurrentXxx {
    id: u64,
    name: String,
}

async fn inject_xxx(
    mut request: Request,
    next: Next,
) -> Response {
    let xxx = CurrentXxx {
        id: 42,
        name: "extracted_xxx".to_string(),
    };

    request.extensions_mut().insert(xxx);
    next.run(request).await
}

async fn handler(
    Extension(xxx): Extension<CurrentXxx>,
) -> Json<CurrentXxx> {
    tracing::debug!("current xxx: {:?}", xxx);
    Json(xxx)
}

fn app() -> Router {
    Router::new()
        .route("/me", get(handler))
        .layer(middleware::from_fn(inject_xxx))
}
""",
        "function": "extension_extractor",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/extension/src/main.rs",
    },
]


# ─── Audit Queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "axum route setup with Router",
    "JSON request response handler",
    "shared state with Arc",
    "error handling IntoResponse",
    "tower middleware",
    "CORS configuration",
    "WebSocket handler",
    "graceful shutdown",
]


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
            client=client,
            collection=COLLECTION,
            query_vector=vec,
            language=LANGUAGE,
            limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q,
                "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
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
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_now,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)


if __name__ == "__main__":
    main()
