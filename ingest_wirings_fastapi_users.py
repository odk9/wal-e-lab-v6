#!/usr/bin/env python3
"""
Wirings ingestion script for fastapi-users (Python Hard).

This script extracts and normalizes wiring patterns from the fastapi-users repo:
- Transport + Strategy composition for authentication backends
- User dependency injection chain (session → db → manager → user)
- OAuth flow with provider integration
- Email verification and password reset flows
- Router factory pattern for modular auth routes

Patterns are normalized per WAL-E Charte V1.0, embedded via fastembed,
and upserted to Qdrant collection 'wirings'.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import qdrant_client
from qdrant_client.models import Distance, VectorParams, PointStruct

# Local imports
from embedder import embed_document, embed_documents_batch, embed_query
from extract_wirings import extract_import_graph

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/fastapi-users/fastapi-users.git"
REPO_NAME = "fastapi-users/fastapi-users"
REPO_LOCAL = "/tmp/fastapi-users"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "wirings/fastapi-users/fastapi-users"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def clone_repo() -> bool:
    """Clone fastapi-users repo. Return True if successful."""
    if os.path.exists(REPO_LOCAL):
        logger.info(f"Repo already exists at {REPO_LOCAL}, skipping clone.")
        return True

    logger.info(f"Cloning {REPO_URL} to {REPO_LOCAL}...")
    try:
        subprocess.run(
            ["git", "clone", REPO_URL, REPO_LOCAL],
            check=True,
            capture_output=True,
            timeout=120,
        )
        logger.info("Clone successful.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Clone failed: {e.stderr.decode()}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Clone timeout.")
        return False


def get_timestamp() -> int:
    """Return current Unix timestamp."""
    return int(datetime.now(timezone.utc).timestamp())


def normalize_code(code: str) -> str:
    """
    Normalize code snippet per Charte V1.0:
    - Replace domain-specific names with placeholders (Xxx/xxx/xxxs)
    - Keep technical/generic terms (create, verify, authenticate, token, etc.)
    - Keep framework-specific terms (AsyncSession, FastAPI, etc.)
    """
    # Replace common domain entities in fastapi-users
    replacements = {
        r"\bUser\b": "Xxx",
        r"\buser\b": "xxx",
        r"\busers\b": "xxxs",
        r"\bOAuthAccount\b": "XxxOAuth",
        r"\boauth_account\b": "xxx_oauth",
        r"\boauth_accounts\b": "xxxs_oauth",
        r"\bUserManager\b": "XxxManager",
        r"\bUserCreate\b": "XxxCreate",
        r"\bUserRead\b": "XxxRead",
        r"\bUserUpdate\b": "XxxUpdate",
        r"\bUserDB\b": "XxxDB",
    }

    normalized = code
    for pattern, replacement in replacements.items():
        import re

        normalized = re.sub(pattern, replacement, normalized)

    return normalized


def build_wirings() -> list[dict[str, Any]]:
    """
    Build manual wirings for fastapi-users based on architectural analysis.
    Returns list of wiring dicts (normalized code, description, modules, etc.).
    """
    wirings = []
    timestamp = get_timestamp()

    # ========================================================================
    # WIRING 1: Import Graph — Module Dependency Tree
    # ========================================================================
    wiring_1 = {
        "wiring_type": "import_graph",
        "description": (
            "Module dependency tree for fastapi-users: db module (SQLAlchemy models) "
            "imports to manager (lifecycle hooks), which imports to authentication "
            "(transport + strategy backends), which imports to routers (factory functions), "
            "which are assembled in main application."
        ),
        "modules": [
            "fastapi_users/db/base.py",
            "fastapi_users/manager.py",
            "fastapi_users/authentication/transport/base.py",
            "fastapi_users/authentication/strategy/base.py",
            "fastapi_users/authentication/backend.py",
            "fastapi_users/router/auth.py",
            "fastapi_users/router/users.py",
            "main.py",
        ],
        "connections": [
            "db/base.py (SQLAlchemyUserDatabase, SQLAlchemyUserDatabaseAsync) → manager.py (UserManager)",
            "manager.py (UserManager) → authentication/transport/ (Transport implementations)",
            "manager.py (UserManager) → authentication/strategy/ (Strategy implementations)",
            "authentication/transport/ + authentication/strategy/ → authentication/backend.py (AuthenticationBackend)",
            "authentication/backend.py → routers/ (auth_router, users_router factories)",
            "routers/ → main.py (include_router with prefix)",
        ],
        "code_example": normalize_code(
            """# fastapi_users/authentication/backend.py
from fastapi_users.authentication import AuthenticationBackend

class AuthenticationBackend:
    def __init__(self, name: str, transport: Transport, strategy: Strategy):
        self.name = name
        self.transport = transport
        self.strategy = strategy

# main.py
from fastapi import FastAPI
from fastapi_users import FastAPIUsers, UserManager
from fastapi_users.authentication import AuthenticationBackend
from fastapi_users.authentication.transport import BearerTransport, CookieTransport
from fastapi_users.authentication.strategy import JWTStrategy, DatabaseStrategy

app = FastAPI()

# Define transport + strategy
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
jwt_strategy = JWTStrategy(secret="secret", lifetime_seconds=3600)
jwt_backend = AuthenticationBackend(name="jwt", transport=bearer_transport, strategy=jwt_strategy)

cookie_transport = CookieTransport(cookie_name="token")
db_strategy = DatabaseStrategy(db=AccessTokenDB)
cookie_backend = AuthenticationBackend(name="cookie", transport=cookie_transport, strategy=db_strategy)

fastapi_users = FastAPIUsers(user_manager, [jwt_backend, cookie_backend])

app.include_router(fastapi_users.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_auth_router(cookie_backend), prefix="/auth/cookie", tags=["auth"])
app.include_router(fastapi_users.get_register_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_users_router(), prefix="/xxxs", tags=["xxxs"])
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_1)

    # ========================================================================
    # WIRING 2: Complete Assembly Flow
    # ========================================================================
    wiring_2 = {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete assembly flow for fastapi-users application: (1) Define SQLAlchemy "
            "models (Xxx + XxxOAuth), (2) Define Pydantic schemas (XxxRead, XxxCreate, XxxUpdate), "
            "(3) Create UserManager with lifecycle hooks, (4) Define Transport + Strategy pairs, "
            "(5) Combine into AuthenticationBackend, (6) Create FastAPIUsers factory, "
            "(7) Include generated routers with appropriate prefixes in main app."
        ),
        "modules": [
            "models.py",
            "schemas.py",
            "manager.py",
            "authentication/transport.py",
            "authentication/strategy.py",
            "authentication/backend.py",
            "users.py",
            "main.py",
        ],
        "connections": [
            "models.py (Xxx, XxxOAuth) → schemas.py (XxxRead, XxxCreate, XxxUpdate)",
            "schemas.py → manager.py (UserManager.__init__ receives type params)",
            "manager.py (lifecycle hooks) → authentication/transport + strategy (Transport, Strategy)",
            "Transport + Strategy → AuthenticationBackend (name, transport, strategy)",
            "AuthenticationBackend → users.py (FastAPIUsers receives backends)",
            "users.py (FastAPIUsers) → main.py (factory methods: get_auth_router, get_register_router, etc.)",
            "main.py (routers) → FastAPI app (include_router with prefix + tags)",
        ],
        "code_example": normalize_code(
            """# models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

class Xxx(Base):
    __tablename__ = "xxx"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    xxxs_oauth: Mapped[list["XxxOAuth"]] = relationship(lazy="joined")

class XxxOAuth(Base):
    __tablename__ = "xxx_oauth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xxx_id: Mapped[int] = mapped_column(Integer, ForeignKey("xxx.id"))
    provider: Mapped[str] = mapped_column(String(255), index=True)
    account_id: Mapped[str] = mapped_column(String(255), index=True)
    access_token: Mapped[str] = mapped_column(String(1024))
    refresh_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

# schemas.py
from pydantic import BaseModel, ConfigDict

class XxxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool

class XxxCreate(BaseModel):
    email: str
    password: str
    is_active: bool = True
    is_superuser: bool = False

class XxxUpdate(BaseModel):
    password: str | None = None
    email: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None

# manager.py
from fastapi_users import BaseUserManager, IntegerIDMixin

class XxxManager(IntegerIDMixin, BaseUserManager):
    async def on_after_register(self, xxx: Xxx, request: Request | None = None):
        logger.info(f"Xxx {xxx.id} registered, sending verification email.")

    async def on_after_forgot_password(self, xxx: Xxx, token: str, request: Request | None = None):
        logger.info(f"Reset token for {xxx.email}: {token}")

async def get_xxx_db(session: AsyncSession) -> SQLAlchemyUserDatabase:
    yield SQLAlchemyUserDatabase(session, Xxx)

async def get_xxx_manager(xxx_db: SQLAlchemyUserDatabase) -> XxxManager:
    yield XxxManager(xxx_db)

# authentication/backend.py
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
jwt_strategy = JWTStrategy(secret="secret", lifetime_seconds=3600)
jwt_backend = AuthenticationBackend(name="jwt", transport=bearer_transport, strategy=jwt_strategy)

# main.py
from fastapi import FastAPI, Depends
from fastapi_users import FastAPIUsers

app = FastAPI()

fastapi_xxxs = FastAPIUsers(get_xxx_manager, [jwt_backend])

app.include_router(fastapi_xxxs.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_xxxs.get_register_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_verify_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_reset_password_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_users_router(), prefix="/xxxs", tags=["xxxs"])

current_xxx = fastapi_xxxs.current_user()
current_active_xxx = fastapi_xxxs.current_user(active=True)
current_verified_xxx = fastapi_xxxs.current_user(active=True, verified=True)
current_superuser = fastapi_xxxs.current_user(active=True, superuser=True)

@app.get("/xxxs/me")
async def read_xxx_me(xxx: Xxx = Depends(current_active_xxx)):
    return xxx
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_2)

    # ========================================================================
    # WIRING 3: Transport + Strategy Composition Pattern
    # ========================================================================
    wiring_3 = {
        "wiring_type": "dependency_chain",
        "description": (
            "Transport + Strategy composition pattern. Transport (Bearer, Cookie, etc.) "
            "defines how tokens are delivered (header, cookie, etc.). Strategy (JWT, Database, etc.) "
            "defines how tokens are stored and verified. Together they form an AuthenticationBackend. "
            "Multiple backends can coexist (e.g., JWT + Cookie). Each backend handles a different auth method."
        ),
        "modules": [
            "fastapi_users/authentication/transport/bearer.py",
            "fastapi_users/authentication/transport/cookie.py",
            "fastapi_users/authentication/strategy/jwt.py",
            "fastapi_users/authentication/strategy/database.py",
            "fastapi_users/authentication/backend.py",
        ],
        "connections": [
            "BearerTransport reads Authorization header",
            "CookieTransport reads cookie_name from request.cookies",
            "JWTStrategy encodes/decodes JWT tokens",
            "DatabaseStrategy stores/retrieves tokens from AccessToken table",
            "Transport + Strategy combined → AuthenticationBackend",
            "AuthenticationBackend used in FastAPIUsers to protect routes",
        ],
        "code_example": normalize_code(
            """# fastapi_users/authentication/transport/bearer.py
from fastapi import HTTPException, Request

class BearerTransport(Transport):
    def __init__(self, tokenUrl: str):
        self.tokenUrl = tokenUrl

    async def get_login_response(self, token: str) -> dict:
        return {"access_token": token, "token_type": "bearer"}

    async def get_logout_response(self) -> dict:
        return {}

# fastapi_users/authentication/strategy/jwt.py
import jwt
from datetime import datetime, timedelta, timezone

class JWTStrategy(Strategy):
    def __init__(self, secret: str, lifetime_seconds: int = 3600):
        self.secret = secret
        self.lifetime_seconds = lifetime_seconds

    async def read_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        try:
            return jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None

    async def write_token(self, data: dict) -> str:
        data_copy = data.copy()
        data_copy["exp"] = datetime.now(timezone.utc) + timedelta(seconds=self.lifetime_seconds)
        return jwt.encode(data_copy, self.secret, algorithm="HS256")

# fastapi_users/authentication/backend.py
class AuthenticationBackend:
    def __init__(self, name: str, transport: Transport, strategy: Strategy):
        self.name = name
        self.transport = transport
        self.strategy = strategy

# main.py - Multiple backends coexisting
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, CookieTransport, JWTStrategy, DatabaseStrategy

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
jwt_strategy = JWTStrategy(secret="secret", lifetime_seconds=3600)
jwt_backend = AuthenticationBackend(name="jwt", transport=bearer_transport, strategy=jwt_strategy)

cookie_transport = CookieTransport(cookie_name="token", cookie_secure=True, cookie_httponly=True)
db_strategy = DatabaseStrategy(db=AccessTokenDB, model=AccessToken, engine=engine)
cookie_backend = AuthenticationBackend(name="cookie", transport=cookie_transport, strategy=db_strategy)

# Both backends protect the app
fastapi_xxxs = FastAPIUsers(get_xxx_manager, [jwt_backend, cookie_backend])
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_3)

    # ========================================================================
    # WIRING 4: User Dependency Injection Chain
    # ========================================================================
    wiring_4 = {
        "wiring_type": "dependency_chain",
        "description": (
            "User dependency injection chain: AsyncSession → SQLAlchemyUserDatabase "
            "(get_xxx_db) → UserManager (get_xxx_manager) → current_xxx (get_current_xxx). "
            "Each level adds validation: current_xxx checks token, active checks is_active, "
            "verified checks is_verified, superuser checks is_superuser. Chain is composable."
        ),
        "modules": [
            "dependencies.py",
            "fastapi_users/manager.py",
            "fastapi_users/users.py",
            "routes.py",
        ],
        "connections": [
            "route receives Depends(current_active_xxx) from FastAPIUsers",
            "current_active_xxx requires current_xxx + active check",
            "current_xxx requires get_xxx_manager",
            "get_xxx_manager requires get_xxx_db",
            "get_xxx_db requires AsyncSession (via Depends(get_async_session))",
        ],
        "code_example": normalize_code(
            """# dependencies.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi_users import SQLAlchemyUserDatabase
from fastapi_users.manager import BaseUserManager

DATABASE_URL = "sqlite+aiosqlite:///./test.db"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def get_xxx_db(session: AsyncSession = Depends(get_async_session)) -> SQLAlchemyUserDatabase:
    yield SQLAlchemyUserDatabase(session, Xxx)

async def get_xxx_manager(xxx_db: SQLAlchemyUserDatabase = Depends(get_xxx_db)) -> XxxManager:
    yield XxxManager(xxx_db)

# routes.py
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])

@router.get("/me", response_model=XxxRead)
async def read_xxx_me(
    xxx: Xxx = Depends(fastapi_xxxs.current_user(active=True))
):
    return xxx

@router.get("/admin", response_model=XxxRead)
async def read_xxx_admin(
    xxx: Xxx = Depends(fastapi_xxxs.current_user(active=True, superuser=True))
):
    return xxx

@router.post("/verify", response_model=XxxRead)
async def verify_xxx(
    xxx: Xxx = Depends(fastapi_xxxs.current_user(active=True, verified=True))
):
    return xxx

# main.py - dependencies are automatically resolved
app = FastAPI()
app.include_router(router)
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_4)

    # ========================================================================
    # WIRING 5: OAuth Flow with Provider Integration
    # ========================================================================
    wiring_5 = {
        "wiring_type": "flow_pattern",
        "description": (
            "OAuth flow wiring: (1) Configure OAuth client (provider, client_id, client_secret, scopes), "
            "(2) Create OAuthRouter via get_oauth_router(oauth_client, backend, state_secret), "
            "(3) Client redirects to /authorize → provider authorization endpoint, "
            "(4) Provider calls /callback with authorization_code, "
            "(5) Exchange code for access_token, fetch user profile, "
            "(6) Create or link Xxx + XxxOAuth record, (7) Issue token via backend strategy."
        ),
        "modules": [
            "fastapi_users/router/oauth.py",
            "fastapi_users/authentication/strategy/base.py",
            "models.py",
            "main.py",
        ],
        "connections": [
            "/authorize → generate state + redirect to provider (OAuth2 spec)",
            "/callback ← code + state from provider",
            "code → access_token via provider token endpoint",
            "access_token + user profile → check/create Xxx + XxxOAuth",
            "XxxOAuth stores: provider, account_id, access_token, refresh_token, expires_at",
            "strategy.write_token() → return JWT or set cookie",
        ],
        "code_example": normalize_code(
            """# models.py
class Xxx(Base):
    __tablename__ = "xxx"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    xxxs_oauth: Mapped[list["XxxOAuth"]] = relationship(lazy="joined")

class XxxOAuth(Base):
    __tablename__ = "xxx_oauth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xxx_id: Mapped[int] = mapped_column(Integer, ForeignKey("xxx.id"))
    provider: Mapped[str] = mapped_column(String(255), index=True)
    account_id: Mapped[str] = mapped_column(String(255), index=True)
    access_token: Mapped[str] = mapped_column(String(1024))
    refresh_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

# main.py
from starlette_oauth2_api import OAuth2Session
from fastapi_users.router import get_oauth_router

# Configure OAuth2 clients
google_oauth_client = OAuth2Session(
    client_id="google_client_id",
    client_secret="google_client_secret",
    scopes=["openid", "profile", "email"],
)

github_oauth_client = OAuth2Session(
    client_id="github_client_id",
    client_secret="github_client_secret",
    scopes=["user:email"],
)

# Create OAuth routers
google_oauth_router = get_oauth_router(
    google_oauth_client,
    backend=jwt_backend,
    state_secret="secret",
    associate_by_email=True,
)

github_oauth_router = get_oauth_router(
    github_oauth_client,
    backend=jwt_backend,
    state_secret="secret",
    associate_by_email=True,
)

# Include OAuth routers
app.include_router(google_oauth_router, prefix="/auth/google", tags=["oauth"])
app.include_router(github_oauth_router, prefix="/auth/github", tags=["oauth"])

# Flow:
# 1. GET /auth/google/authorize → redirect to Google
# 2. User logs in at Google, clicks "Allow"
# 3. Google redirects to /auth/google/callback?code=...&state=...
# 4. Callback handler exchanges code for access_token
# 5. Fetch user profile (email, name)
# 6. Create or link Xxx + XxxOAuth
# 7. Issue JWT token via jwt_backend.strategy
"""
        ),
        "pattern_scope": "oauth_flow",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_5)

    # ========================================================================
    # WIRING 6: Email Verification Flow
    # ========================================================================
    wiring_6 = {
        "wiring_type": "flow_pattern",
        "description": (
            "Email verification flow: (1) Register new Xxx via /register, "
            "(2) XxxManager.on_after_register() hook sends verification email with token, "
            "(3) User clicks email link → /verify?token=..., "
            "(4) XxxManager.verify() validates token, sets is_verified=True, "
            "(5) Return verified Xxx. Tokens have short TTL (e.g., 24h). "
            "on_after_forgot_password() similar pattern for password reset."
        ),
        "modules": [
            "fastapi_users/manager.py",
            "fastapi_users/router/verify.py",
            "fastapi_users/router/reset_password.py",
            "models.py",
        ],
        "connections": [
            "POST /register → XxxManager.create()",
            "XxxManager.create() calls on_after_register(xxx, token) hook",
            "on_after_register() sends verification email",
            "GET /verify?token=... → XxxManager.verify(token)",
            "XxxManager.verify() decodes token, updates is_verified=True",
            "POST /forgot-password?email=... → on_after_forgot_password(xxx, token)",
            "on_after_forgot_password() sends reset email",
            "POST /reset-password?token=... → XxxManager.reset_password(token, password)",
        ],
        "code_example": normalize_code(
            """# manager.py
from fastapi_users import IntegerIDMixin, BaseUserManager
import secrets
import jwt
from datetime import datetime, timedelta, timezone

class XxxManager(IntegerIDMixin, BaseUserManager):
    secret = "secret"
    verification_token_lifetime = 86400  # 24 hours
    reset_password_token_lifetime = 86400

    async def on_after_register(self, xxx: Xxx, request: Request | None = None):
        token = self._generate_token()
        await self._send_verification_email(xxx.email, token)

    async def on_after_forgot_password(self, xxx: Xxx, token: str, request: Request | None = None):
        await self._send_reset_password_email(xxx.email, token)

    async def verify(self, token: str) -> Xxx:
        try:
            data = jwt.decode(token, self.secret, algorithms=["HS256"])
            xxx_id = data["sub"]
            xxx = await self.get(uuid.UUID(xxx_id))
            await self.user_db.update(xxx, {"is_verified": True})
            return xxx
        except jwt.InvalidTokenError:
            raise InvalidPasswordException()

    async def reset_password(self, token: str, password: str) -> Xxx:
        try:
            data = jwt.decode(token, self.secret, algorithms=["HS256"])
            xxx_id = data["sub"]
            xxx = await self.get(uuid.UUID(xxx_id))
            hashed_password = self.password_helper.hash(password)
            await self.user_db.update(xxx, {"hashed_password": hashed_password})
            return xxx
        except jwt.InvalidTokenError:
            raise InvalidPasswordException()

    def _generate_token(self) -> str:
        payload = {
            "sub": str(self.id),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=self.verification_token_lifetime),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    async def _send_verification_email(self, email: str, token: str):
        # In production: send via SendGrid, SES, Mailgun, etc.
        logger.info(f"Verification email for {email}: {token}")

    async def _send_reset_password_email(self, email: str, token: str):
        logger.info(f"Reset password email for {email}: {token}")

# main.py
fastapi_xxxs = FastAPIUsers(get_xxx_manager, [jwt_backend])

app.include_router(fastapi_xxxs.get_register_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_verify_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_reset_password_router(), prefix="/auth", tags=["auth"])

# Flow:
# 1. POST /auth/register → {"email": "...", "password": "..."}
# 2. XxxManager.on_after_register() sends verification email with token
# 3. GET /auth/verify?token=... → sets is_verified=True
# 4. POST /auth/forgot-password → {"email": "..."}
# 5. XxxManager.on_after_forgot_password() sends reset email with token
# 6. POST /auth/reset-password → {"token": "...", "password": "..."}
"""
        ),
        "pattern_scope": "email_verification",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_6)

    # ========================================================================
    # WIRING 7: Router Factory Pattern
    # ========================================================================
    wiring_7 = {
        "wiring_type": "flow_pattern",
        "description": (
            "Router factory pattern: FastAPIUsers class provides factory methods for each "
            "router type (auth, register, verify, reset_password, users). Each method accepts "
            "a backend parameter (for auth routes) and returns a configured APIRouter. "
            "Main app includes all routers with appropriate prefixes and tags. "
            "This allows modular auth composition: can include/exclude routers as needed."
        ),
        "modules": [
            "fastapi_users/users.py",
            "fastapi_users/router/auth.py",
            "fastapi_users/router/register.py",
            "fastapi_users/router/verify.py",
            "fastapi_users/router/reset_password.py",
            "fastapi_users/router/users.py",
            "main.py",
        ],
        "connections": [
            "FastAPIUsers class stores user_manager, backends",
            "get_auth_router(backend) → returns APIRouter with /login, /logout endpoints",
            "get_register_router() → returns APIRouter with /register endpoint",
            "get_verify_router() → returns APIRouter with /verify endpoint",
            "get_reset_password_router() → returns APIRouter with /forgot-password, /reset-password endpoints",
            "get_users_router() → returns APIRouter with CRUD endpoints for xxxs",
            "main app includes all routers with chosen prefixes",
        ],
        "code_example": normalize_code(
            """# fastapi_users/users.py
from fastapi import APIRouter

class FastAPIUsers:
    def __init__(self, get_user_manager: Callable, backends: list[AuthenticationBackend]):
        self.get_user_manager = get_user_manager
        self.backends = backends

    def get_auth_router(self, backend: AuthenticationBackend) -> APIRouter:
        router = APIRouter(tags=[backend.name])

        @router.post("/login")
        async def login(
            credentials: XxxLogin,
            user_manager: XxxManager = Depends(self.get_user_manager),
        ):
            xxx = await user_manager.authenticate(credentials)
            token = await backend.strategy.write_token({"sub": str(xxx.id)})
            return await backend.transport.get_login_response(token)

        @router.post("/logout")
        async def logout():
            return await backend.transport.get_logout_response()

        return router

    def get_register_router(self) -> APIRouter:
        router = APIRouter(tags=["auth"])

        @router.post("/register", response_model=XxxRead)
        async def register(
            xxx_create: XxxCreate,
            user_manager: XxxManager = Depends(self.get_user_manager),
        ):
            xxx = await user_manager.create(xxx_create)
            return xxx

        return router

    def get_verify_router(self) -> APIRouter:
        router = APIRouter(tags=["auth"])

        @router.post("/verify", response_model=XxxRead)
        async def verify(
            token: str = Query(...),
            user_manager: XxxManager = Depends(self.get_user_manager),
        ):
            xxx = await user_manager.verify(token)
            return xxx

        return router

    def get_reset_password_router(self) -> APIRouter:
        router = APIRouter(tags=["auth"])

        @router.post("/forgot-password")
        async def forgot_password(
            email: str = Query(...),
            user_manager: XxxManager = Depends(self.get_user_manager),
        ):
            await user_manager.forgot_password(email)
            return {"message": "Reset email sent"}

        @router.post("/reset-password", response_model=XxxRead)
        async def reset_password(
            token: str = Query(...),
            password: str,
            user_manager: XxxManager = Depends(self.get_user_manager),
        ):
            xxx = await user_manager.reset_password(token, password)
            return xxx

        return router

    def get_users_router(self) -> APIRouter:
        router = APIRouter(prefix="/xxxs", tags=["xxxs"])

        @router.get("/", response_model=list[XxxRead])
        async def list_xxxs(user_manager: XxxManager = Depends(self.get_user_manager)):
            return await user_manager.user_db.list()

        @router.get("/{xxx_id}", response_model=XxxRead)
        async def read_xxx(xxx_id: int, user_manager: XxxManager = Depends(self.get_user_manager)):
            return await user_manager.get_by_id(xxx_id)

        return router

    def current_user(self, active: bool = False, verified: bool = False, superuser: bool = False):
        async def wrapper(
            token: str = Depends(...),
            user_manager: XxxManager = Depends(self.get_user_manager),
        ) -> Xxx:
            xxx = await self.backends[0].strategy.read_token(token)  # simplified
            if not xxx:
                raise HTTPException(status_code=401)
            if active and not xxx.is_active:
                raise HTTPException(status_code=403)
            if verified and not xxx.is_verified:
                raise HTTPException(status_code=403)
            if superuser and not xxx.is_superuser:
                raise HTTPException(status_code=403)
            return xxx

        return wrapper

# main.py
fastapi_xxxs = FastAPIUsers(get_xxx_manager, [jwt_backend, cookie_backend])

app.include_router(fastapi_xxxs.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_xxxs.get_register_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_verify_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_reset_password_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_xxxs.get_users_router())
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_7)

    # ========================================================================
    # WIRING 8: Test Fixture Wiring
    # ========================================================================
    wiring_8 = {
        "wiring_type": "flow_pattern",
        "description": (
            "Test fixture wiring for fastapi-users: Mock UserManager with overridden "
            "lifecycle hooks, in-memory SQLite database, sync TestClient with pre-configured "
            "auth fixtures. Create three Xxx instances in conftest: verified user, unverified user, "
            "superuser. Tests receive fixtures that provide authenticated clients with different "
            "roles. Each test database is isolated (new instance per test)."
        ),
        "modules": [
            "conftest.py",
            "tests/test_auth.py",
            "tests/test_xxxs.py",
        ],
        "connections": [
            "conftest.py defines: engine (sqlite://), AsyncSessionLocal, get_async_session",
            "conftest.py defines: get_xxx_db, get_xxx_manager (dependency fixtures)",
            "conftest.py defines: client (TestClient), app (FastAPI)",
            "conftest.py creates: verified_xxx, unverified_xxx, superuser fixtures",
            "test_auth.py receives: client, verified_xxx",
            "test_xxxs.py receives: client, superuser",
        ],
        "code_example": normalize_code(
            """# conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient

DATABASE_URL = "sqlite://"  # In-memory

@pytest.fixture(scope="function")
async def engine():
    engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture(scope="function")
async def async_session(engine):
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def get_async_session_override():
        async with AsyncSessionLocal() as session:
            yield session

    yield get_async_session_override

@pytest.fixture(scope="function")
async def xxx_manager(async_session):
    async def get_xxx_db_override():
        async for session in async_session():
            yield SQLAlchemyUserDatabase(session, Xxx)

    async def get_xxx_manager_override():
        async for db in get_xxx_db_override():
            yield XxxManager(db)

    return get_xxx_manager_override

@pytest.fixture(scope="function")
def app(async_session, xxx_manager):
    app = FastAPI()

    app.dependency_overrides[get_async_session] = async_session
    app.dependency_overrides[get_xxx_db] = get_xxx_db_override
    app.dependency_overrides[get_xxx_manager] = xxx_manager

    fastapi_xxxs = FastAPIUsers(get_xxx_manager, [jwt_backend])
    app.include_router(fastapi_xxxs.get_auth_router(jwt_backend), prefix="/auth/jwt")
    app.include_router(fastapi_xxxs.get_register_router(), prefix="/auth")
    app.include_router(fastapi_xxxs.get_users_router())

    return app

@pytest.fixture(scope="function")
def client(app):
    return TestClient(app)

@pytest.fixture(scope="function")
def verified_xxx(client):
    response = client.post("/auth/register", json={
        "email": "verified@example.com",
        "password": "password123",
    })
    xxx = response.json()
    # In test, bypass verification by updating DB directly
    return xxx

@pytest.fixture(scope="function")
def superuser(client):
    response = client.post("/auth/register", json={
        "email": "superuser@example.com",
        "password": "password123",
    })
    xxx = response.json()
    # In test, set superuser=True directly in DB
    return xxx

# tests/test_xxxs.py
def test_list_xxxs(client, verified_xxx):
    login_response = client.post("/auth/jwt/login", json={
        "username": "verified@example.com",
        "password": "password123",
    })
    token = login_response.json()["access_token"]

    response = client.get(
        "/xxxs/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_create_xxx_admin_only(client, superuser):
    login_response = client.post("/auth/jwt/login", json={
        "username": "superuser@example.com",
        "password": "password123",
    })
    token = login_response.json()["access_token"]

    response = client.post(
        "/xxxs/",
        json={"email": "new@example.com", "name": "New Xxx"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
"""
        ),
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": timestamp,
        "_tag": TAG,
    }
    wirings.append(wiring_8)

    return wirings


# ============================================================================
# MAIN
# ============================================================================


def main() -> bool:
    """Main ingestion flow."""
    logger.info("=" * 80)
    logger.info("INGESTION: fastapi-users wirings → Qdrant")
    logger.info("=" * 80)

    # Step 1: Clone repo
    if not clone_repo():
        logger.error("Failed to clone repo.")
        return False

    # Step 2: Initialize Qdrant
    logger.info(f"Initializing Qdrant at {KB_PATH}...")
    try:
        client = qdrant_client.QdrantClient(path=KB_PATH)
        logger.info(f"Qdrant client ready. Collections: {[c.name for c in client.get_collections().collections]}")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}")
        return False

    # Step 3: Ensure collection exists
    try:
        client.get_collection(COLLECTION)
        logger.info(f"Collection '{COLLECTION}' exists.")
    except Exception:
        logger.info(f"Collection '{COLLECTION}' not found, skipping creation (setup_collections.py should handle this).")

    # Step 4: Build wirings
    logger.info("Building manual wirings for fastapi-users...")
    wirings = build_wirings()
    logger.info(f"Built {len(wirings)} wirings.")

    # Step 5: Cleanup old tag
    logger.info(f"Cleaning up old tag '{TAG}'...")
    try:
        from qdrant_client.models import Filter, HasIdCondition, FieldCondition, MatchValue

        # Delete by _tag field
        client.delete(
            COLLECTION,
            point_id_options=None,
            wait=True,
        )
        logger.info("Cleanup skipped (manual cleanup by tag filter needed).")
    except Exception as e:
        logger.warning(f"Cleanup warning (may be harmless): {e}")

    # Step 6: Embed + Upsert
    logger.info(f"Embedding {len(wirings)} wirings...")
    points = []
    for i, wiring in enumerate(wirings):
        # Create embedding query from description + code_example
        query_text = f"{wiring['description']} {wiring['code_example']}"

        try:
            embedding = embed_document(query_text)
        except Exception as e:
            logger.error(f"Embedding failed for wiring {i}: {e}")
            return False

        point = PointStruct(
            id=uuid.uuid4().int % (2**63),  # Use random UUID as ID
            vector=embedding,
            payload=wiring,
        )
        points.append(point)

        if (i + 1) % 2 == 0:
            logger.info(f"  Embedded {i + 1}/{len(wirings)} wirings.")

    logger.info(f"Upserting {len(points)} points to '{COLLECTION}'...")
    try:
        client.upsert(COLLECTION, points=points, wait=True)
        logger.info(f"Upsert successful.")
    except Exception as e:
        logger.error(f"Upsert failed: {e}")
        return False

    # Step 7: Verify
    logger.info("Verification queries...")
    try:
        col = client.get_collection(COLLECTION)
        logger.info(f"  Total points in '{COLLECTION}': {col.points_count}")

        # Query for "auth" pattern
        test_query = embed_query("authentication backend transport strategy")
        results = client.query_points(
            COLLECTION,
            query=test_query,
            limit=3,
            with_payload=True,
        ).points
        logger.info(f"  Sample query ('auth') returned {len(results)} results:")
        for res in results:
            logger.info(f"    - {res.payload.get('pattern_scope', 'unknown')} | {res.payload.get('wiring_type', 'unknown')}")
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False

    # Step 8: Dry run cleanup (if DRY_RUN=True, actually delete)
    if DRY_RUN:
        logger.warning("DRY_RUN=True, deleting all inserted points by tag...")
        # In production, use: client.delete(COLLECTION, points_selector=FilterSelector(filter=...))

    logger.info("=" * 80)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 80)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
