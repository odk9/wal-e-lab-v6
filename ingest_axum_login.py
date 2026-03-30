"""
ingest_axum_login.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de maxcountryman/axum-login dans la KB Qdrant V6.

Rust B — Auth middleware for Axum. tower_sessions + sqlx.

Usage:
    .venv/bin/python3 ingest_axum_login.py
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
REPO_URL = "https://github.com/maxcountryman/axum-login.git"
REPO_NAME = "maxcountryman/axum-login"
REPO_LOCAL = "/tmp/axum_login"
LANGUAGE = "rust"
FRAMEWORK = "axum"
STACK = "axum+tower_sessions+sqlx"
CHARTE_VERSION = "1.0"
TAG = "maxcountryman/axum-login"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/maxcountryman/axum-login"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: User→Xxx, user→xxx, users→xxxs
#       Keep: auth, AuthUser, AuthnBackend, AuthzBackend, AuthSession,
#             axum, tower_sessions, sqlx, username (technical term)
# R-1: NO .unwrap() except in #[test]. R-2: NO println!().

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODEL LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. AuthUser trait implementation ───────────────────────────────────
    {
        "normalized_code": """\
use axum_login::AuthUser;

#[derive(Clone, Debug, sqlx::FromRow)]
pub struct Xxx {
\tpub id: i64,
\tpub username: String,
\tpub password_hash: String,
}

impl AuthUser for Xxx {
\ttype Id = i64;

\tfn id(&self) -> Self::Id {
\t\tself.id
\t}

\tfn session_auth_hash(&self) -> &[u8] {
\t\tself.password_hash.as_bytes()
\t}
}
""",
        "function": "auth_user_trait_impl",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/xxx.rs",
    },

    # ── 2. AuthnBackend authenticate ───────────────────────────────────────
    {
        "normalized_code": """\
use async_trait::async_trait;
use axum_login::{AuthnBackend, AuthUser};
use password_auth::verify_password;
use sqlx::SqlitePool;
use tokio::task;

use crate::xxx::Xxx;

#[derive(Clone, Debug)]
pub struct Backend {
\tpub db: SqlitePool,
}

impl Backend {
\tpub fn new(db: SqlitePool) -> Self {
\t\tSelf { db }
\t}
}

#[derive(Clone, Debug, serde::Deserialize)]
pub struct Credentials {
\tpub username: String,
\tpub password: String,
\tpub next: Option<String>,
}

#[async_trait]
impl AuthnBackend for Backend {
\ttype User = Xxx;
\ttype Credentials = Credentials;
\ttype Error = std::convert::Infallible;

\tasync fn authenticate(
\t\t&self,
\t\tcreds: Self::Credentials,
\t) -> Result<Option<Self::User>, Self::Error> {
\t\tlet xxx: Option<Xxx> = sqlx::query_as("SELECT * FROM xxxs WHERE username = ?")
\t\t\t.bind(&creds.username)
\t\t\t.fetch_optional(&self.db)
\t\t\t.await
\t\t\t.ok()
\t\t\t.flatten();

\t\tlet xxx = match xxx {
\t\t\tSome(xxx) => xxx,
\t\t\tNone => return Ok(None),
\t\t};

\t\tlet verified = task::spawn_blocking(move || {
\t\t\tverify_password(creds.password, &xxx.password_hash).is_ok()
\t\t})
\t\t.await
\t\t.ok()
\t\t.unwrap_or(false);

\t\tif verified {
\t\t\tlet xxx: Option<Xxx> = sqlx::query_as("SELECT * FROM xxxs WHERE username = ?")
\t\t\t\t.bind(&creds.username)
\t\t\t\t.fetch_optional(&self.db)
\t\t\t\t.await
\t\t\t\t.ok()
\t\t\t\t.flatten();
\t\t\tOk(xxx)
\t\t} else {
\t\t\tOk(None)
\t\t}
\t}
}
""",
        "function": "authn_backend_authenticate",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/backend.rs",
    },

    # ── 3. AuthnBackend get_user ───────────────────────────────────────────
    {
        "normalized_code": """\
use async_trait::async_trait;
use axum_login::AuthnBackend;
use sqlx::SqlitePool;

use crate::xxx::Xxx;

#[async_trait]
impl AuthnBackend for Backend {
\ttype User = Xxx;
\ttype Credentials = Credentials;
\ttype Error = std::convert::Infallible;

\tasync fn get_user(
\t\t&self,
\t\txxx_id: &i64,
\t) -> Result<Option<Self::User>, Self::Error> {
\t\tlet xxx: Option<Xxx> = sqlx::query_as("SELECT * FROM xxxs WHERE id = ?")
\t\t\t.bind(xxx_id)
\t\t\t.fetch_optional(&self.db)
\t\t\t.await
\t\t\t.ok()
\t\t\t.flatten();

\t\tOk(xxx)
\t}
}
""",
        "function": "authn_backend_get_user",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/backend.rs",
    },

    # ── 4. AuthzBackend get_group_permissions ──────────────────────────────
    {
        "normalized_code": """\
use std::collections::HashSet;

use async_trait::async_trait;
use axum_login::AuthzBackend;
use sqlx::SqlitePool;

use crate::xxx::Xxx;

#[derive(Clone, Debug, PartialEq, Eq, Hash, sqlx::FromRow)]
pub struct Permission {
\tpub name: String,
}

impl From<&str> for Permission {
\tfn from(name: &str) -> Self {
\t\tPermission {
\t\t\tname: name.to_string(),
\t\t}
\t}
}

#[async_trait]
impl AuthzBackend for Backend {
\ttype Permission = Permission;

\tasync fn get_group_permissions(
\t\t&self,
\t\txxx: &Xxx,
\t) -> Result<HashSet<Self::Permission>, Self::Error> {
\t\tlet permissions: Vec<Permission> = sqlx::query_as(
\t\t\tr#"
\t\t\tSELECT DISTINCT permissions.name
\t\t\tFROM xxxs
\t\t\tJOIN xxxs_groups ON xxxs.id = xxxs_groups.xxx_id
\t\t\tJOIN groups_permissions ON xxxs_groups.group_id = groups_permissions.group_id
\t\t\tJOIN permissions ON groups_permissions.permission_id = permissions.id
\t\t\tWHERE xxxs.id = ?
\t\t\t"#,
\t\t)
\t\t.bind(xxx.id)
\t\t.fetch_all(&self.db)
\t\t.await
\t\t.ok()
\t\t.unwrap_or_default();

\t\tOk(permissions.into_iter().collect())
\t}
}
""",
        "function": "authz_backend_permissions",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/backend.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMA LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 5. Credentials struct ──────────────────────────────────────────────
    {
        "normalized_code": """\
#[derive(Clone, Debug, serde::Deserialize)]
pub struct Credentials {
\tpub username: String,
\tpub password: String,
\tpub next: Option<String>,
}
""",
        "function": "credentials_struct",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/schema.rs",
    },

    # ── 6. Permission struct ──────────────────────────────────────────────
    {
        "normalized_code": """\
#[derive(Clone, Debug, PartialEq, Eq, Hash, sqlx::FromRow)]
pub struct Permission {
\tpub name: String,
}

impl From<&str> for Permission {
\tfn from(name: &str) -> Self {
\t\tPermission {
\t\t\tname: name.to_string(),
\t\t}
\t}
}
""",
        "function": "permission_struct",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/permission.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTE LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 7. Login handler ──────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{extract::Form, response::Redirect};
use axum_login::AuthSession;

use crate::backend::{Backend, Credentials};

pub async fn login(
\tauth_session: AuthSession<Backend>,
\tForm(creds): Form<Credentials>,
) -> impl axum::response::IntoResponse {
\tlet xxx = match auth_session.authenticate(creds.clone()).await {
\t\tOk(Some(xxx)) => xxx,
\t\tOk(None) => return Redirect::to("/login").into_response(),
\t\tErr(_) => return Redirect::to("/login").into_response(),
\t};

\tif let Err(_) = auth_session.login(&xxx).await {
\t\treturn Redirect::to("/login").into_response();
\t}

\tlet next = creds.next.unwrap_or_else(|| "/".to_string());
\tRedirect::to(&next).into_response()
}
""",
        "function": "login_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes.rs",
    },

    # ── 8. Logout handler ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::response::Redirect;
use axum_login::AuthSession;

use crate::backend::Backend;

pub async fn logout(auth_session: AuthSession<Backend>) -> impl axum::response::IntoResponse {
\tif let Err(_) = auth_session.logout().await {
\t\treturn Redirect::to("/").into_response();
\t}
\tRedirect::to("/login").into_response()
}
""",
        "function": "logout_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes.rs",
    },

    # ── 9. Protected route ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use axum::response::{IntoResponse, Redirect};
use axum_login::AuthSession;

use crate::backend::Backend;

pub async fn protected(
\tauth_session: AuthSession<Backend>,
) -> impl IntoResponse {
\tmatch auth_session.user {
\t\tSome(ref xxx) => format!("Logged in as: {}", xxx.username).into_response(),
\t\tNone => Redirect::to("/login").into_response(),
\t}
}
""",
        "function": "protected_route",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 10. Session config with SqliteStore ────────────────────────────────
    {
        "normalized_code": """\
use tower_sessions::{cookie::Key, Expiry, SessionManagerLayer};
use tower_sessions_sqlx_store::SqliteStore;
use sqlx::SqlitePool;
use time::Duration;

pub async fn session_layer(
\tpool: &SqlitePool,
) -> SessionManagerLayer<SqliteStore> {
\tlet session_store = SqliteStore::new(pool.clone());
\tsession_store.migrate().await.expect("session migration");

\tlet key = Key::generate();

\tSessionManagerLayer::new(session_store)
\t\t.with_secure(false)
\t\t.with_expiry(Expiry::OnInactivity(Duration::days(1)))
\t\t.with_signed(key)
}
""",
        "function": "session_config_sqlx",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/config.rs",
    },

    # ── 11. AuthManagerLayer builder ───────────────────────────────────────
    {
        "normalized_code": """\
use axum_login::AuthManagerLayerBuilder;
use tower_sessions::SessionManagerLayer;
use tower_sessions_sqlx_store::SqliteStore;

use crate::backend::Backend;

pub fn auth_layer(
\tbackend: Backend,
\tsession_layer: SessionManagerLayer<SqliteStore>,
) -> axum_login::AuthManagerLayer<Backend, SqliteStore> {
\tAuthManagerLayerBuilder::new(backend, session_layer).build()
}
""",
        "function": "auth_manager_layer",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/config.rs",
    },

    # ── 12. login_required middleware ──────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use axum_login::login_required;

use crate::backend::Backend;

pub fn protected_routes() -> Router {
\tRouter::new()
\t\t.route("/protected", axum::routing::get(super::routes::protected))
\t\t.route_layer(login_required!(Backend, login_url = "/login"))
}
""",
        "function": "login_required_middleware",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/router.rs",
    },

    # ── 13. permission_required middleware ─────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use axum_login::permission_required;

use crate::backend::Backend;

pub fn admin_routes() -> Router {
\tRouter::new()
\t\t.route("/admin", axum::routing::get(super::routes::admin_dashboard))
\t\t.route_layer(permission_required!(Backend, login_url = "/login", "admin.read"))
}
""",
        "function": "permission_required_middleware",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/router.rs",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # OAUTH2 LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 14. OAuth2 backend ─────────────────────────────────────────────────
    {
        "normalized_code": """\
use async_trait::async_trait;
use axum_login::{AuthnBackend, AuthUser};
use oauth2::{
\tbasic::BasicClient, reqwest::async_http_client, AuthorizationCode, CsrfToken,
\tTokenResponse,
};
use sqlx::SqlitePool;

use crate::xxx::Xxx;

#[derive(Clone, Debug)]
pub struct OAuthBackend {
\tpub db: SqlitePool,
\tpub client: BasicClient,
}

#[derive(Clone, Debug, serde::Deserialize)]
pub struct OAuthCredentials {
\tpub code: String,
\tpub old_state: CsrfToken,
\tpub new_state: CsrfToken,
}

#[async_trait]
impl AuthnBackend for OAuthBackend {
\ttype User = Xxx;
\ttype Credentials = OAuthCredentials;
\ttype Error = Box<dyn std::error::Error + Send + Sync>;

\tasync fn authenticate(
\t\t&self,
\t\tcreds: Self::Credentials,
\t) -> Result<Option<Self::User>, Self::Error> {
\t\tif creds.old_state.secret() != creds.new_state.secret() {
\t\t\treturn Ok(None);
\t\t}

\t\tlet token = self
\t\t\t.client
\t\t\t.exchange_code(AuthorizationCode::new(creds.code))
\t\t\t.request_async(async_http_client)
\t\t\t.await?;

\t\tlet profile: serde_json::Value = reqwest::Client::new()
\t\t\t.get("https://api.example.com/xxx")
\t\t\t.bearer_auth(token.access_token().secret())
\t\t\t.send()
\t\t\t.await?
\t\t\t.json()
\t\t\t.await?;

\t\tlet username = profile["login"]
\t\t\t.as_str()
\t\t\t.ok_or("missing login field")?
\t\t\t.to_string();

\t\tlet xxx: Option<Xxx> = sqlx::query_as(
\t\t\t"SELECT * FROM xxxs WHERE username = ? OR INSERT INTO xxxs (username, password_hash) VALUES (?, '')",
\t\t)
\t\t.bind(&username)
\t\t.bind(&username)
\t\t.fetch_optional(&self.db)
\t\t.await?;

\t\tOk(xxx)
\t}

\tasync fn get_user(
\t\t&self,
\t\txxx_id: &i64,
\t) -> Result<Option<Self::User>, Self::Error> {
\t\tlet xxx: Option<Xxx> = sqlx::query_as("SELECT * FROM xxxs WHERE id = ?")
\t\t\t.bind(xxx_id)
\t\t\t.fetch_optional(&self.db)
\t\t\t.await?;

\t\tOk(xxx)
\t}
}
""",
        "function": "oauth2_backend",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/oauth_backend.rs",
    },

    # ── 15. OAuth2 callback handler ────────────────────────────────────────
    {
        "normalized_code": """\
use axum::{
\textract::Query,
\tresponse::{IntoResponse, Redirect},
};
use axum_login::AuthSession;
use oauth2::CsrfToken;

use crate::oauth_backend::{OAuthBackend, OAuthCredentials};

#[derive(Debug, serde::Deserialize)]
pub struct AuthzResp {
\tpub code: String,
\tpub state: String,
}

pub async fn oauth_callback(
\tauth_session: AuthSession<OAuthBackend>,
\tQuery(AuthzResp { code, state }): Query<AuthzResp>,
) -> impl IntoResponse {
\tlet old_state = match auth_session.backend.get_csrf_state().await {
\t\tOk(Some(state)) => state,
\t\t_ => return Redirect::to("/login").into_response(),
\t};

\tlet creds = OAuthCredentials {
\t\tcode,
\t\told_state,
\t\tnew_state: CsrfToken::new(state),
\t};

\tlet xxx = match auth_session.authenticate(creds).await {
\t\tOk(Some(xxx)) => xxx,
\t\t_ => return Redirect::to("/login").into_response(),
\t};

\tif let Err(_) = auth_session.login(&xxx).await {
\t\treturn Redirect::to("/login").into_response();
\t}

\tRedirect::to("/").into_response()
}
""",
        "function": "oauth2_callback_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes.rs",
    },

    # ── 16. Full app router composition ────────────────────────────────────
    {
        "normalized_code": """\
use axum::Router;
use axum_login::{login_required, AuthManagerLayerBuilder};
use sqlx::SqlitePool;
use tower_sessions::{cookie::Key, Expiry, SessionManagerLayer};
use tower_sessions_sqlx_store::SqliteStore;
use time::Duration;

use crate::backend::Backend;

pub async fn app(pool: SqlitePool) -> Router {
\tlet session_store = SqliteStore::new(pool.clone());
\tsession_store.migrate().await.expect("session migration");

\tlet key = Key::generate();
\tlet session_layer = SessionManagerLayer::new(session_store)
\t\t.with_secure(false)
\t\t.with_expiry(Expiry::OnInactivity(Duration::days(1)))
\t\t.with_signed(key);

\tlet backend = Backend::new(pool);
\tlet auth_layer = AuthManagerLayerBuilder::new(backend, session_layer).build();

\tlet protected_router = Router::new()
\t\t.route("/", axum::routing::get(super::routes::protected))
\t\t.route_layer(login_required!(Backend, login_url = "/login"));

\tlet public_router = Router::new()
\t\t.route("/login", axum::routing::get(super::routes::login_page))
\t\t.route("/login", axum::routing::post(super::routes::login))
\t\t.route("/logout", axum::routing::get(super::routes::logout));

\tRouter::new()
\t\t.merge(protected_router)
\t\t.merge(public_router)
\t\t.layer(auth_layer)
}
""",
        "function": "app_router_composition",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/app.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "auth user trait implementation",
    "authenticate backend with sqlx",
    "login handler form credentials",
    "logout session handler",
    "protected route auth session",
    "session configuration tower",
    "permission required middleware",
    "OAuth2 callback handler",
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
