#!/usr/bin/env python3
"""
Wirings ingestion script for maxcountryman/axum-login (Rust Medium).
Wal-e Lab V6 — Qdrant KB population.

No AST extraction (Rust). 8 manual wirings covering auth flow, session management,
trait implementations, and test patterns.
"""

import os
import sys
from datetime import datetime, timezone
from typing import Optional

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/maxcountryman/axum-login.git"
REPO_NAME = "maxcountryman/axum-login"
REPO_LOCAL = "/tmp/axum-login"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+tower_sessions+sqlx"
CHARTE_VERSION = "1.0"
TAG = "wirings/maxcountryman/axum-login"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# Hardcoded timestamp for reproducibility
TIMESTAMP_UNIX = int(datetime.now(timezone.utc).timestamp())


# ============================================================================
# QDRANT CLIENT SETUP
# ============================================================================

def get_qdrant_client():
    """Initialize Qdrant client pointing to local KB."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(path=KB_PATH)
        return client
    except ImportError:
        print("ERROR: qdrant-client not installed. Install with: pip install qdrant-client")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR initializing Qdrant: {e}")
        sys.exit(1)


def get_embedder():
    """Initialize fastembed embedder."""
    try:
        from embedder import embed_documents_batch, embed_query
        return embed_documents_batch, embed_query
    except ImportError:
        print("ERROR: embedder.py not found. Ensure embedder.py is in current directory.")
        sys.exit(1)


# ============================================================================
# WIRING DEFINITIONS (8 MANUAL WIRINGS)
# ============================================================================

WIRINGS = [
    # ========================================================================
    # 1. Import Graph — Rust module tree for auth Axum project
    # ========================================================================
    {
        "wiring_type": "import_graph",
        "description": "Rust module organization for authentication Axum project with auth backends, user models, and handlers",
        "modules": [
            "main.rs",
            "src/models/mod.rs",
            "src/models/user.rs",
            "src/backend/mod.rs",
            "src/backend/authn.rs",
            "src/backend/authz.rs",
            "src/web/mod.rs",
            "src/web/handlers.rs",
            "Cargo.toml",
        ],
        "connections": [
            "main.rs → src/models/mod.rs (mod models)",
            "main.rs → src/backend/mod.rs (mod backend)",
            "main.rs → src/web/mod.rs (mod web)",
            "src/models/mod.rs → src/models/user.rs (mod user; pub use user::*)",
            "src/backend/mod.rs → src/backend/authn.rs (mod authn)",
            "src/backend/mod.rs → src/backend/authz.rs (mod authz)",
            "src/web/mod.rs → src/web/handlers.rs (mod handlers; pub use handlers::*)",
            "src/backend/mod.rs → src/models/user.rs (use crate::models::Xxx)",
            "src/web/handlers.rs → src/backend/authn.rs (use crate::backend::Backend)",
        ],
        "code_example": """
// Cargo.toml dependencies
[dependencies]
axum = "0.7"
axum-login = "0.15"
tower-sessions = "0.4"
sqlx = { version = "0.7", features = ["runtime-tokio", "sqlite"] }
password-auth = "0.2"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }

// main.rs module structure
mod models;
mod backend;
mod web;

use crate::models::Xxx;
use crate::backend::Backend;
use crate::web::handlers;
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 2. Flow Pattern — Complete file creation order for setup
    # ========================================================================
    {
        "wiring_type": "flow_pattern",
        "description": "Sequential file creation order for full-stack auth Axum setup: dependencies, migrations, models, backends, handlers, main",
        "modules": [
            "Cargo.toml",
            "migrations/001_create_users.sql",
            "migrations/002_create_groups.sql",
            "migrations/003_create_permissions.sql",
            "src/models/user.rs",
            "src/backend/authn.rs",
            "src/backend/authz.rs",
            "src/web/handlers.rs",
            "src/main.rs",
        ],
        "connections": [
            "Step 1: Define Cargo.toml with axum, axum-login, tower-sessions, sqlx, password-auth",
            "Step 2: Create migrations/001_create_users.sql: CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT)",
            "Step 3: Create migrations/002_create_groups.sql: CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT)",
            "Step 4: Create migrations/003_create_permissions.sql: CREATE TABLE permissions (id INTEGER PRIMARY KEY, name TEXT)",
            "Step 5: Create src/models/user.rs with Xxx struct + sqlx::FromRow",
            "Step 6: Implement AuthUser trait for Xxx in src/models/user.rs",
            "Step 7: Create src/backend/authn.rs with Backend struct + AuthnBackend impl",
            "Step 8: Create src/backend/authz.rs with AuthzBackend impl",
            "Step 9: Create src/web/handlers.rs with login/logout routes + protected endpoint",
            "Step 10: Create src/main.rs with SessionManagerLayer + AuthManagerLayer + Router",
        ],
        "code_example": """
// Step 5: src/models/user.rs
use sqlx::FromRow;
use axum_login::AuthUser;
use std::sync::Arc;

#[derive(Clone, Debug, FromRow)]
pub struct Xxx {
    pub id: i64,
    pub username: String,
    pub password_hash: String,
}

impl AuthUser for Xxx {
    type Id = i64;
    type Error = sqlx::Error;

    fn id(&self) -> Self::Id {
        self.id
    }

    fn session_auth_hash(&self) -> Arc<[u8]> {
        Arc::new(self.password_hash.as_bytes().to_vec())
    }
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 3. Dependency Chain — AuthUser trait implementation
    # ========================================================================
    {
        "wiring_type": "dependency_chain",
        "description": "AuthUser trait implementation for user model: id extraction, session auth hash generation from password hash",
        "modules": ["src/models/user.rs"],
        "connections": [
            "Xxx struct → impl AuthUser for Xxx",
            "id field → fn id() returns self.id",
            "password_hash field → fn session_auth_hash() returns Arc<[u8]>",
            "Session validation: hash changes on password update → forces re-login",
        ],
        "code_example": """
use axum_login::AuthUser;
use std::sync::Arc;

#[derive(Clone, Debug, sqlx::FromRow)]
pub struct Xxx {
    pub id: i64,
    pub username: String,
    pub password_hash: String,
}

impl AuthUser for Xxx {
    type Id = i64;
    type Error = sqlx::Error;

    fn id(&self) -> Self::Id {
        self.id
    }

    fn session_auth_hash(&self) -> Arc<[u8]> {
        Arc::new(self.password_hash.as_bytes().to_vec())
    }
}

// Session invalidation: when password changes, hash changes → next request fails validation
pub async fn change_password(
    pool: SqlitePool,
    user_id: i64,
    new_password: &str,
) -> Result<()> {
    let new_hash = password_auth::hash(new_password).to_string();
    sqlx::query(
        "UPDATE users SET password_hash = ? WHERE id = ?"
    )
    .bind(&new_hash)
    .bind(user_id)
    .execute(&pool)
    .await?;
    Ok(())
}
""",
        "pattern_scope": "session_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 4. Dependency Chain — AuthnBackend authentication flow
    # ========================================================================
    {
        "wiring_type": "dependency_chain",
        "description": "AuthnBackend trait implementation: credentials validation, password verification via spawn_blocking, user retrieval",
        "modules": ["src/backend/authn.rs", "src/models/user.rs"],
        "connections": [
            "Backend struct with SqlitePool → impl AuthnBackend",
            "Credentials deserialized from request → authenticate(creds)",
            "Query: SELECT * FROM users WHERE username = ?",
            "Password verification: password_auth::verify_password via spawn_blocking",
            "Return: Ok(Some(user)) on success, Ok(None) on wrong password",
            "get_user(id) → SELECT * FROM users WHERE id = ?",
        ],
        "code_example": """
use axum_login::{AuthnBackend, AuthUser};
use tokio::task;
use password_auth::{Verify, hash, verify};

#[derive(Clone, Debug)]
pub struct Backend {
    pub db: SqlitePool,
}

#[derive(serde::Deserialize)]
pub struct Credentials {
    pub username: String,
    pub password: String,
    pub next: Option<String>,
}

#[async_trait::async_trait]
impl AuthnBackend for Backend {
    type User = Xxx;
    type Credentials = Credentials;
    type Error = sqlx::Error;

    async fn authenticate(
        &self,
        creds: Self::Credentials,
    ) -> Result<Option<Self::User>, Self::Error> {
        let user: Option<Xxx> = sqlx::query_as(
            "SELECT id, username, password_hash FROM users WHERE username = ?"
        )
        .bind(&creds.username)
        .fetch_optional(&self.db)
        .await?;

        if let Some(user) = user {
            let password = creds.password.clone();
            let hash = user.password_hash.clone();
            let is_valid = task::spawn_blocking(move || {
                verify(&password, &hash).is_ok()
            })
            .await
            .unwrap_or(false);

            return Ok(if is_valid { Some(user) } else { None });
        }

        Ok(None)
    }

    async fn get_user(
        &self,
        user_id: &<Self::User as AuthUser>::Id,
    ) -> Result<Option<Self::User>, Self::Error> {
        sqlx::query_as("SELECT id, username, password_hash FROM users WHERE id = ?")
            .bind(user_id)
            .fetch_optional(&self.db)
            .await
    }
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 5. Flow Pattern — AuthzBackend permissions flow with SQL joins
    # ========================================================================
    {
        "wiring_type": "flow_pattern",
        "description": "AuthzBackend permissions retrieval: JOIN users_groups, groups_permissions to build HashSet of user permissions",
        "modules": ["src/backend/authz.rs", "src/models/user.rs"],
        "connections": [
            "get_group_permissions(user: &Xxx) async",
            "Query: SELECT DISTINCT p.* FROM permissions p JOIN groups_permissions gp ON p.id = gp.permission_id JOIN user_groups ug ON gp.group_id = ug.group_id WHERE ug.user_id = ?",
            "Result: Vec<Permission> → collect into HashSet<Permission>",
            "Router middleware: require_permission!(Backend, Permission) checks HashSet",
        ],
        "code_example": """
use axum_login::AuthzBackend;
use std::collections::HashSet;

#[derive(Clone, Debug, PartialEq, Eq, Hash, sqlx::FromRow)]
pub struct Permission {
    pub id: i64,
    pub name: String,
}

#[async_trait::async_trait]
impl AuthzBackend for Backend {
    type Permission = Permission;

    async fn get_group_permissions(
        &self,
        user: &Xxx,
    ) -> Result<HashSet<Self::Permission>, Self::Error> {
        let permissions: Vec<Permission> = sqlx::query_as(
            r#"
            SELECT DISTINCT p.id, p.name
            FROM permissions p
            JOIN groups_permissions gp ON p.id = gp.permission_id
            JOIN user_groups ug ON gp.group_id = ug.group_id
            WHERE ug.user_id = ?
            "#
        )
        .bind(user.id)
        .fetch_all(&self.db)
        .await?;

        Ok(permissions.into_iter().collect())
    }
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 6. Dependency Chain — Session + Auth layer stack composition
    # ========================================================================
    {
        "wiring_type": "dependency_chain",
        "description": "SessionManagerLayer and AuthManagerLayer composition: session layer wraps auth layer wraps routes",
        "modules": ["src/main.rs"],
        "connections": [
            "SessionStore (tower-sessions) created from session config",
            "SessionManagerLayer::new(session_store) → session layer",
            "AuthManagerLayerBuilder::new(backend, session_layer).build() → auth layer",
            "Router.layer(auth_layer) applies to all routes",
            "Order critical: session INSIDE auth INSIDE routes",
        ],
        "code_example": """
use axum::{routing::get, Router};
use axum_login::{AuthManagerLayerBuilder, login_required};
use tower_sessions::SessionManagerLayer;
use sqlx::SqlitePool;

#[tokio::main]
async fn main() {
    let database_url = "sqlite:data.db";
    let pool = SqlitePool::connect(database_url)
        .await
        .expect("Failed to create pool");

    // Run migrations
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .expect("Failed to migrate");

    let backend = Backend { db: pool };

    // Build session store
    let session_config = tower_sessions::SessionConfig::default();
    let session_store = tower_sessions::SessionStore::default();
    let session_layer = SessionManagerLayer::new(session_store)
        .with_secure(false); // Use true in production with HTTPS

    // Build auth layer
    let auth_layer = AuthManagerLayerBuilder::new(backend, session_layer)
        .build();

    // Build router with auth layer
    let app = Router::new()
        .route("/api/v1/xxxs", get(list_xxxs))
        .route("/api/v1/xxxs/:xxx_id", get(get_xxx))
        .layer(auth_layer);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:8080")
        .await
        .unwrap();
    axum::serve(listener, app).await.unwrap();
}
""",
        "pattern_scope": "session_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 7. Flow Pattern — Login/logout handler implementation
    # ========================================================================
    {
        "wiring_type": "flow_pattern",
        "description": "Login/logout handler flow: credential validation, session persistence, redirect to next URL, protected route access",
        "modules": ["src/web/handlers.rs"],
        "connections": [
            "POST /login: extract AuthSession, extract Credentials, validate",
            "auth.authenticate(creds) → Option<Xxx>",
            "Success: auth.login(&user).await → session token stored in cookie",
            "Redirect to creds.next or default home page",
            "POST /logout: auth.logout().await → session deleted",
            "Redirect to login page",
            "Protected routes: extract AuthSession<Backend> → user available",
            "No user → redirect to login",
        ],
        "code_example": """
use axum::{
    extract::Query,
    http::StatusCode,
    response::{IntoResponse, Redirect},
    Form, Extension,
};
use axum_login::AuthSession;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct LoginPayload {
    pub username: String,
    pub password: String,
    pub next: Option<String>,
}

pub async fn login(
    mut auth_session: AuthSession<Backend>,
    Form(payload): Form<LoginPayload>,
) -> Result<impl IntoResponse, StatusCode> {
    let user = auth_session
        .authenticate(Credentials {
            username: payload.username,
            password: payload.password,
            next: payload.next.clone(),
        })
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::UNAUTHORIZED)?;

    auth_session
        .login(&user)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Redirect::to(
        payload.next.as_deref().unwrap_or("/")
    ))
}

pub async fn logout(
    mut auth_session: AuthSession<Backend>,
) -> impl IntoResponse {
    auth_session.logout().await.ok();
    Redirect::to("/login")
}

pub async fn protected_route(
    auth_session: AuthSession<Backend>,
) -> Result<String, StatusCode> {
    let Some(user) = auth_session.user else {
        return Err(StatusCode::UNAUTHORIZED);
    };
    Ok(format!("Hello, {}!", user.username))
}
""",
        "pattern_scope": "session_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },

    # ========================================================================
    # 8. Flow Pattern — Testing wiring with migrations, seeds, app setup
    # ========================================================================
    {
        "wiring_type": "flow_pattern",
        "description": "Testing pattern: setup pool → run migrations → seed test user with hashed password → build test app → make HTTP calls → assert responses",
        "modules": ["tests/integration.rs"],
        "connections": [
            "Setup: sqlx::test with in-memory SQLite pool",
            "Run migrations on test pool",
            "Seed: INSERT test user with password_auth::hash(password)",
            "Build app with Backend initialized from test pool",
            "Create HTTP client (axum-test or reqwest TestClient)",
            "POST /login with valid credentials → assert 302 Redirect",
            "Extract session cookie from response",
            "GET protected route with cookie → assert 200 OK + user data",
            "POST /logout → assert 302 Redirect to /login",
            "GET protected route without session → assert 401 Unauthorized",
        ],
        "code_example": """
#[tokio::test]
async fn test_login_flow() {
    // Setup
    let pool = SqlitePool::connect("sqlite://?mode=memory")
        .await
        .unwrap();
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .unwrap();

    // Seed test user
    let test_password = "test123";
    let password_hash = password_auth::hash(test_password).to_string();
    sqlx::query(
        "INSERT INTO users (id, username, password_hash) VALUES (1, ?, ?)"
    )
    .bind("testuser")
    .bind(&password_hash)
    .execute(&pool)
    .await
    .unwrap();

    // Build app
    let backend = Backend { db: pool.clone() };
    let session_store = tower_sessions::SessionStore::default();
    let session_layer = SessionManagerLayer::new(session_store);
    let auth_layer = AuthManagerLayerBuilder::new(backend, session_layer).build();

    let app = Router::new()
        .route("/login", post(handlers::login))
        .route("/logout", post(handlers::logout))
        .route("/protected", get(handlers::protected_route))
        .layer(auth_layer);

    // Test client
    let client = TestClient::new(app);

    // POST /login with valid credentials
    let response = client
        .post("/login")
        .form(&serde_json::json!({
            "username": "testuser",
            "password": test_password,
            "next": Some("/protected")
        }))
        .send()
        .await;
    assert_eq!(response.status(), StatusCode::FOUND);

    // Extract session cookie
    let cookie = response.headers()
        .get(SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap();

    // GET /protected with session
    let response = client
        .get("/protected")
        .header(COOKIE, cookie)
        .send()
        .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(response.text().await.contains("testuser"));

    // POST /logout
    let response = client
        .post("/logout")
        .header(COOKIE, cookie)
        .send()
        .await;
    assert_eq!(response.status(), StatusCode::FOUND);

    // GET /protected without session
    let response = client
        .get("/protected")
        .send()
        .await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP_UNIX,
        "_tag": TAG,
    },
]


# ============================================================================
# INGESTION LOGIC
# ============================================================================

def build_payload(wiring_data: dict) -> dict:
    """Build a payload for Qdrant insertion (with embedding to be added)."""
    payload = {
        "wiring_type": wiring_data["wiring_type"],
        "description": wiring_data["description"],
        "modules": wiring_data["modules"],
        "connections": wiring_data["connections"],
        "code_example": wiring_data["code_example"],
        "pattern_scope": wiring_data["pattern_scope"],
        "language": wiring_data["language"],
        "framework": wiring_data["framework"],
        "stack": wiring_data["stack"],
        "source_repo": wiring_data["source_repo"],
        "charte_version": wiring_data["charte_version"],
        "created_at": wiring_data["created_at"],
        "_tag": wiring_data["_tag"],
    }
    return payload


def normalize_for_embedding(wiring_data: dict) -> str:
    """Create normalized text for embedding: description + code_example."""
    text = f"{wiring_data['description']}\n\n{wiring_data['code_example']}"
    return text


def ingest_wirings(embed_documents_batch):
    """Ingest all 8 wirings into Qdrant collection."""
    import time
    import uuid
    from qdrant_client.models import PointStruct

    client = get_qdrant_client()

    print(f"[INFO] Ingesting {len(WIRINGS)} wirings into collection '{COLLECTION}'...")

    # Batch embed all descriptions
    descriptions = [w["description"] for w in WIRINGS]
    vectors = embed_documents_batch(descriptions)

    points = []
    for i, (wiring_data, vector) in enumerate(zip(WIRINGS, vectors), 1):
        try:
            # Prepare payload
            payload = build_payload(wiring_data)

            # Create point
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload,
            )
            points.append(point)

            print(
                f"  ✓ Wiring {i}/{len(WIRINGS)}: {payload['wiring_type']} — "
                f"{payload['pattern_scope']}"
            )

        except Exception as e:
            print(
                f"  ✗ Wiring {i}/{len(WIRINGS)}: FAILED — {e}"
            )
            if not DRY_RUN:
                raise

    # Upsert all points at once
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"\n[SUCCESS] Ingested {len(points)}/{len(WIRINGS)} wirings.")
    return len(points)


def verify_ingestion():
    """Verify ingestion by checking collection point count."""
    client = get_qdrant_client()
    collection = client.get_collection(COLLECTION)
    print(f"[VERIFY] Collection '{COLLECTION}' now has {collection.points_count} total points.")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Orchestrate wiring ingestion."""
    print(f"\n{'=' * 80}")
    print(f"WIRINGS INGESTION: {REPO_NAME}")
    print(f"{'=' * 80}")
    print(f"Repository: {REPO_URL}")
    print(f"Language:   {LANGUAGE}")
    print(f"Framework:  {FRAMEWORK}")
    print(f"Stack:      {STACK}")
    print(f"KB Path:    {KB_PATH}")
    print(f"Collection: {COLLECTION}")
    print(f"Dry Run:    {DRY_RUN}")
    print(f"{'=' * 80}\n")

    # Get embedder
    embed_documents_batch, embed_query = get_embedder()

    # Ingest wirings
    ingested = ingest_wirings(embed_documents_batch)

    # Verify
    verify_ingestion()

    print(f"\n[COMPLETE] Wirings ingestion for {REPO_NAME} finished.")


if __name__ == "__main__":
    main()
