"""
ingest_wirings_full_stack_fastapi.py — Extrait et indexe les wirings (flux inter-modules)
de fastapi/full-stack-fastapi-template dans la KB Qdrant V6 (collection `wirings`).

Ce repo est un projet MEDIUM FastAPI : auth model (UUID), owned entities (FK + cascade),
dépendances en chaîne (get_db → get_current_user → get_current_active_superadmin),
JWT token flow, multiple schema sets par entité.

Usage:
    .venv/bin/python3 ingest_wirings_full_stack_fastapi.py
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
from extract_wirings import extract_all_wirings

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/fastapi/full-stack-fastapi-template.git"
REPO_NAME = "fastapi/full-stack-fastapi-template"
REPO_LOCAL = "/tmp/full-stack-fastapi-template"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "wirings/fastapi/full-stack-fastapi-template"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"


# ─── Wirings manuels (complètent l'extraction AST) ──────────────────────────
# Spécifiques au projet MEDIUM avec auth + owned entities
# Patterns que l'AST ne voit pas : conventions d'assemblage multi-schémas,
# chaînes de dépendances auth, JWT flow, ownership cascade.

MANUAL_WIRINGS: list[dict] = [
    # ── File creation order for Medium FastAPI project with auth + owned entities ──
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete file creation order for Medium FastAPI project with auth and owned entities. "
            "Shows how core/config.py, core/db.py, core/security.py, models.py, schemas.py, "
            "crud.py, deps.py, routes/, and main.py are assembled together. "
            "Auth model uses UUID primary key, owned entities use FK + cascade delete. "
            "Multiple schema sets per entity (Create, Update, SelfUpdate, Public, etc)."
        ),
        "modules": [
            "core/config.py", "core/db.py", "core/security.py", "models.py",
            "schemas.py", "crud.py", "deps.py", "routes/auth.py", "routes/xxxs.py", "main.py", "conftest.py",
        ],
        "connections": [
            "1. core/config.py — Settings, DATABASE_URL, SECRET_KEY (no local imports)",
            "2. core/db.py — create_async_engine(DATABASE_URL) + AsyncSessionLocal + get_db()",
            "3. core/security.py — JWT create/verify token, hash/verify password (no local imports)",
            "4. models.py — from core.db import Base; Auth(UUID pk), Xxx(UUID pk, owner_id FK + cascade)",
            "5. schemas.py — standalone Pydantic V2, multiple sets: XxxCreate, XxxUpdate, XxxPublic, etc (no DB import)",
            "6. crud.py — from models import Auth, Xxx; from core.db import AsyncSession; CRUD operations",
            "7. deps.py — from core.security import *; from models import Auth; get_db(), get_current_user(token+db), get_current_active_superadmin(current_user)",
            "8. routes/auth.py — login(db+email+pwd) → create_access_token, register(db+schema)",
            "9. routes/xxxs.py — CRUD routes with current_user dependency, ownership check on update/delete",
            "10. main.py — include_router(auth_router, prefix=/auth), include_router(xxxs_router, prefix=/xxxs), lifespan=lifespan",
            "11. conftest.py — override_get_db with SQLite, create test user, get auth token, provide authenticated TestClient",
        ],
        "code_example": """\
# === File creation order for Medium FastAPI Auth+Owned project ===

# 1. core/config.py (foundation — no local imports)
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
settings = Settings()

# 2. core/db.py (depends on: core/config.py)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from core.config import settings
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# 3. core/security.py (no local imports)
from datetime import datetime, timedelta, UTC
from jose import jwt
from passlib.context import CryptContext
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

# 4. models.py (depends on: core.db)
from uuid import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from core.db import Base
class Xxx(Base):
    __tablename__ = "xxxs"
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("auth.id", ondelete="CASCADE"))
    owner: Mapped["Auth"] = relationship(back_populates="xxxs")

# 5. schemas.py (standalone — no local imports)
from uuid import UUID
from pydantic import BaseModel, ConfigDict, StrictBool, field_serializer
class XxxCreate(BaseModel):
    title: str
class XxxUpdate(BaseModel):
    title: str | None = None
class XxxSelfUpdate(BaseModel):
    title: str
class XxxPublic(BaseModel):
    id: UUID
    title: str
    model_config = ConfigDict(from_attributes=True)

# 6. crud.py (depends on: models, core.db)
from sqlalchemy.ext.asyncio import AsyncSession
from models import Xxx, Auth
async def create_xxx(db: AsyncSession, owner_id: UUID, xxx_in: XxxCreate) -> Xxx:
    xxx = Xxx(owner_id=owner_id, **xxx_in.model_dump())
    db.add(xxx)
    await db.commit()
    await db.refresh(xxx)
    return xxx

# 7. deps.py (depends on: core/security, models, core/db)
from core.security import decode_token
from models import Auth
from core.db import get_db
async def get_current_user(token: str, db: AsyncSession = Depends(get_db)) -> Auth:
    user_id = decode_token(token)
    user = await db.get(Auth, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid token")
    return user
async def get_current_active_superadmin(current_user: Auth = Depends(get_current_user)) -> Auth:
    if not current_user.is_superadmin:
        raise HTTPException(403, "Not a superadmin")
    return current_user

# 8. routes/auth.py (depends on: crud, schemas, deps, core/security)
from crud import create_auth, get_auth_by_identifier
router = APIRouter(prefix="/auth", tags=["auth"])
@router.post("/login", response_model=TokenResponse)
async def login(email: str, password: str, db: AsyncSession = Depends(get_db)) -> dict:
    user = await get_auth_by_identifier(db, email)
    if not user or not verify_password(password, user.hashed_secret):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

# 9. routes/xxxs.py (depends on: crud, schemas, deps)
router = APIRouter(prefix="/xxxs", tags=["xxxs"])
@router.post("/", response_model=XxxPublic, status_code=201)
async def create_xxx(
    xxx_in: XxxCreate,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    return await crud.create_xxx(db, current_user.id, xxx_in)
@router.put("/{xxx_id}", response_model=XxxPublic)
async def update_xxx(
    xxx_id: UUID = Path(...),
    xxx_in: XxxUpdate = None,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx or xxx.owner_id != current_user.id:
        raise HTTPException(403, "Not authorized")
    return await crud.update_xxx(db, xxx, xxx_in)

# 10. main.py (depends on: routes/auth, routes/xxxs, core/db, models)
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield
app = FastAPI(lifespan=lifespan)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(xxxs_router, prefix="/api/v1")

# 11. conftest.py (depends on: main, core/db, models)
from starlette.testclient import TestClient
from main import app
from core.db import get_db, Base
TEST_DATABASE_URL = "sqlite://"
@pytest.fixture(scope="function")
def client():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    def override_get_db():
        db = SessionLocal(bind=engine)
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Auth dependency injection chain ──────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Complete auth dependency injection chain for Medium FastAPI project. "
            "Shows how get_db() is the root, get_current_user(token+db) chains on top, "
            "and get_current_active_superadmin(current_user) adds final auth check. "
            "Each level adds a constraint: has session, has valid token, is superadmin. "
            "Routes pick the appropriate level based on their authorization needs."
        ),
        "modules": ["deps.py", "routes/auth.py", "routes/xxxs.py", "core/security.py"],
        "connections": [
            "deps.py: get_db() → root dependency, AsyncSession from pool",
            "deps.py: get_current_user(token: str, db = Depends(get_db)) → decode JWT, fetch Auth from db",
            "deps.py: get_current_active_superadmin(current_user = Depends(get_current_user)) → check is_superadmin flag",
            "routes/auth.py: login(db: AsyncSession = Depends(get_db)) → level 1, public",
            "routes/xxxs.py: create_xxx(..., current_user = Depends(get_current_user), db = Depends(get_db)) → level 2, authenticated",
            "routes/admin.py: delete_xxx(..., current_user = Depends(get_current_active_superadmin), db = Depends(get_db)) → level 3, superadmin only",
        ],
        "code_example": """\
# === Auth Dependency Injection Chain ===

# deps.py — The dependency chain
from core.security import decode_token
from core.db import get_db

async def get_current_user(
    token: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Auth:
    try:
        user_id = decode_token(token)
    except JWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.get(Auth, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid or inactive user")
    return user

async def get_current_active_superadmin(
    current_user: Auth = Depends(get_current_user),
) -> Auth:
    if not current_user.is_superadmin:
        raise HTTPException(403, "Only superadmin allowed")
    return current_user

# routes/auth.py — Level 1 (public, db only)
@router.post("/login")
async def login(
    email: str,
    password: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await get_auth_by_identifier(db, email)
    if not user or not verify_password(password, user.hashed_secret):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token}

# routes/xxxs.py — Level 2 (authenticated user)
@router.post("/", response_model=XxxPublic)
async def create_xxx(
    xxx_in: XxxCreate,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    return await crud.create_xxx(db, current_user.id, xxx_in)

# routes/admin.py — Level 3 (superadmin only)
@router.delete("/{xxx_id}")
async def delete_xxx(
    xxx_id: UUID = Path(...),
    current_user: Auth = Depends(get_current_active_superadmin),  # Force superadmin
    db: AsyncSession = Depends(get_db),
) -> None:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx:
        raise HTTPException(404, "Not found")
    await db.delete(xxx)
    await db.commit()
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── UUID primary key pattern ─────────────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "UUID primary key pattern for Medium FastAPI project. "
            "Shows how UUID4 is generated by default on models, how Pydantic schemas "
            "use UUID4 field type, and how path parameters validate UUID format. "
            "Unlike int autoincrement, UUIDs don't expose sequence information."
        ),
        "modules": ["models.py", "schemas.py", "routes/xxxs.py"],
        "connections": [
            "models.py: id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)",
            "schemas.py: id: UUID — Pydantic field type is UUID (validates format on input)",
            "routes/xxxs.py: xxx_id: UUID = Path(...) — path parameter is UUID, not int",
            "No sequence leaking via ID values (UUIDs are cryptographically opaque)",
        ],
        "code_example": """\
# === UUID Primary Key Pattern ===

# models.py (SQLAlchemy)
from uuid import UUID, uuid4
class Xxx(Base):
    __tablename__ = "xxxs"
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("auth.id"))

# schemas.py (Pydantic V2)
from uuid import UUID
class XxxResponse(BaseModel):
    id: UUID
    title: str
    model_config = ConfigDict(from_attributes=True)

# routes/xxxs.py (FastAPI)
from uuid import UUID
@router.get("/{xxx_id}", response_model=XxxResponse)
async def get_xxx(
    xxx_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx:
        raise HTTPException(404, "Not found")
    return xxx
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Owned entity with authorization check ────────────────────────────
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Owned entity CRUD with authorization check pattern. "
            "Shows how owned entities (FK to Auth) are updated/deleted only by owner. "
            "Routes verify entity.owner_id == current_user.id before allowing mutation. "
            "Cascade delete when user is deleted (ON DELETE CASCADE in FK)."
        ),
        "modules": ["models.py", "routes/xxxs.py", "crud.py"],
        "connections": [
            "models.py: Xxx has owner_id: Mapped[UUID] + ForeignKey(..., ondelete='CASCADE')",
            "routes/xxxs.py: update/delete routes check xxx.owner_id == current_user.id",
            "crud.py: update_xxx / delete_xxx assume ownership already checked by route",
        ],
        "code_example": """\
# === Owned Entity CRUD with Authorization ===

# models.py (SQLAlchemy)
class Xxx(Base):
    __tablename__ = "xxxs"
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("auth.id", ondelete="CASCADE"))
    title: str

# routes/xxxs.py — authorization check in route
@router.put("/{xxx_id}", response_model=XxxPublic)
async def update_xxx(
    xxx_id: UUID = Path(...),
    xxx_in: XxxUpdate,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx:
        raise HTTPException(404, "Not found")
    # *** Authorization check ***
    if xxx.owner_id != current_user.id:
        raise HTTPException(403, "Not authorized to modify")
    # Proceed with update
    return await crud.update_xxx(db, xxx, xxx_in)

@router.delete("/{xxx_id}", status_code=204)
async def delete_xxx(
    xxx_id: UUID = Path(...),
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx:
        raise HTTPException(404, "Not found")
    # *** Authorization check ***
    if xxx.owner_id != current_user.id:
        raise HTTPException(403, "Not authorized to delete")
    await db.delete(xxx)
    await db.commit()

# crud.py — no auth check (assumed done by route)
async def update_xxx(db: AsyncSession, xxx: Xxx, xxx_in: XxxUpdate) -> Xxx:
    for field, value in xxx_in.model_dump(exclude_unset=True).items():
        setattr(xxx, field, value)
    await db.commit()
    await db.refresh(xxx)
    return xxx
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── JWT token flow end-to-end ────────────────────────────────────────
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete JWT token flow from login to authenticated request. "
            "Shows how core/security.py creates and verifies tokens, "
            "how routes return tokens on login, and how deps.py extracts and validates tokens from headers. "
            "Token contains user_id, expires in 30 minutes, validated on every protected route."
        ),
        "modules": ["core/security.py", "routes/auth.py", "deps.py"],
        "connections": [
            "routes/auth.py: login → verify password → create_access_token(user_id, exp)",
            "core/security.py: create_access_token → JWT encode with SECRET_KEY + HS256",
            "Client stores token, sends in Authorization header",
            "deps.py: get_current_user(token header) → decode JWT → fetch Auth from db",
            "core/security.py: decode_token → JWT decode, check exp, return user_id",
        ],
        "code_example": """\
# === Complete JWT Token Flow ===

# core/security.py
from datetime import datetime, timedelta, UTC
from jose import jwt, JWTError
from passlib.context import CryptContext
from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt

def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise JWTError("No sub in token")
        return user_id
    except JWTError:
        raise JWTError("Invalid token")

# routes/auth.py
@router.post("/login", response_model=TokenResponse)
async def login(
    email: str,
    password: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await get_auth_by_identifier(db, email)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    if not pwd_context.verify(password, user.hashed_secret):
        raise HTTPException(401, "Invalid email or password")
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}

# deps.py
from core.security import decode_token
async def get_current_user(
    token: str = Header(..., alias="authorization"),
    db: AsyncSession = Depends(get_db),
) -> Auth:
    if not token.startswith("Bearer "):
        raise HTTPException(401, "Invalid token format")
    token_only = token[7:]
    try:
        user_id = decode_token(token_only)
    except JWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.get(Auth, UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid or inactive user")
    return user
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Multiple schema sets per entity ──────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Multiple schema sets pattern for Medium FastAPI project. "
            "Shows how a single entity (Xxx) has 5-7 different Pydantic schemas "
            "for different contexts: Create (admin only), Register (public), "
            "Update (partial), SelfUpdate (user updates own), Public (response, redacted), etc. "
            "Each schema is used for input validation or response serialization as needed."
        ),
        "modules": ["schemas.py", "routes/auth.py", "routes/xxxs.py"],
        "connections": [
            "schemas.py: XxxCreate (all fields, admin only) + XxxUpdate (partial) + XxxSelfUpdate (subset) + XxxPublic (response) + XxxChangePassword",
            "routes/auth.py: register(XxxRegister) — public signup, fewer fields than Create",
            "routes/xxxs.py: create(XxxCreate) — create owned entity, update(XxxUpdate) — partial",
            "routes/auth.py: change_password(XxxChangePassword) — old + new password",
            "All routes return XxxPublic or AuthPublic (no hashed_secret, sensitive fields redacted)",
        ],
        "code_example": """\
# === Multiple Schema Sets per Entity ===

# schemas.py (Pydantic V2)
from uuid import UUID
from pydantic import BaseModel, ConfigDict, StrictBool, EmailStr, field_serializer

# For Auth entity
class AuthCreate(BaseModel):
    identifier: EmailStr
    password: str

class AuthRegister(BaseModel):
    identifier: EmailStr
    password: str

class AuthUpdate(BaseModel):
    identifier: EmailStr | None = None

class AuthChangePassword(BaseModel):
    old_password: str
    new_password: str

class AuthPublic(BaseModel):
    id: UUID
    identifier: str
    is_active: StrictBool
    is_superadmin: StrictBool
    model_config = ConfigDict(from_attributes=True)

# For owned Xxx entity
class XxxCreate(BaseModel):
    title: str
    description: str | None = None

class XxxUpdate(BaseModel):
    title: str | None = None
    description: str | None = None

class XxxSelfUpdate(BaseModel):
    title: str
    description: str | None = None

class XxxPublic(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    model_config = ConfigDict(from_attributes=True)

# routes/auth.py — different schemas for different endpoints
@router.post("/register", response_model=AuthPublic, status_code=201)
async def register(auth_in: AuthRegister, db: AsyncSession = Depends(get_db)) -> Auth:
    return await crud.create_auth(db, auth_in)

@router.post("/change-password")
async def change_password(
    pwd_in: AuthChangePassword,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthPublic:
    return await crud.change_password(db, current_user, pwd_in)

# routes/xxxs.py — multiple schemas per entity
@router.post("/", response_model=XxxPublic, status_code=201)
async def create_xxx(
    xxx_in: XxxCreate,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    return await crud.create_xxx(db, current_user.id, xxx_in)

@router.put("/{xxx_id}", response_model=XxxPublic)
async def update_xxx(
    xxx_id: UUID = Path(...),
    xxx_in: XxxUpdate,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    xxx = await db.get(Xxx, xxx_id)
    if not xxx or xxx.owner_id != current_user.id:
        raise HTTPException(403, "Not authorized")
    return await crud.update_xxx(db, xxx, xxx_in)
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Test fixture wiring for auth project ──────────────────────────────
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Test fixture wiring for Medium FastAPI auth project. "
            "Shows how conftest.py creates test user, obtains auth token, "
            "provides authenticated TestClient with overridden get_db. "
            "Uses SQLite in-memory for test isolation, fresh DB per test session."
        ),
        "modules": ["conftest.py", "main.py", "core/db.py", "models.py", "crud.py"],
        "connections": [
            "conftest.py → from core.db import Base, get_db",
            "conftest.py → from main import app",
            "conftest.py → from crud import create_auth",
            "conftest.py → override_get_db with SQLite in-memory engine",
            "conftest.py → create test Auth(identifier='test@test.com', hashed_password=...)",
            "conftest.py → call login route to get access_token",
            "conftest.py → provide client fixture with authorization header",
        ],
        "code_example": """\
# === Test Fixture Wiring — conftest.py (auth project) ===

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from core.db import Base, get_db
from main import app
from models import Auth
from core.security import get_password_hash

TEST_DATABASE_URL = "sqlite://"  # in-memory


@pytest.fixture(scope="function")
def engine():
    test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session(engine):
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()
    yield db
    db.close()


def override_get_db(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass
    return _override_get_db


@pytest.fixture(scope="function")
def client(db_session):
    app.dependency_overrides[get_db] = override_get_db(db_session)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user_auth(db_session):
    test_user = Auth(
        identifier="test@test.com",
        hashed_secret=get_password_hash("testpassword123"),
        is_active=True,
        is_superadmin=False,
    )
    db_session.add(test_user)
    db_session.commit()
    db_session.refresh(test_user)
    return test_user


@pytest.fixture(scope="function")
def client_with_auth(client, test_user_auth):
    # Get auth token
    login_response = client.post("/api/v1/auth/login", data={
        "username": "test@test.com",
        "password": "testpassword123",
    })
    access_token = login_response.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {access_token}"}
    return client


# Usage in tests
def test_create_xxx(client_with_auth):
    response = client_with_auth.post("/api/v1/xxxs/", json={"title": "Test Xxx"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Xxx"
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Cascade delete on owned entities ──────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Cascade delete pattern for owned entities. "
            "When an Auth user is deleted, all their owned Xxx entities are automatically deleted. "
            "This is configured via ForeignKey(ondelete='CASCADE') and ensures referential integrity. "
            "No orphaned rows left when a user is deleted."
        ),
        "modules": ["models.py", "routes/auth.py"],
        "connections": [
            "models.py: owner_id: Mapped[UUID] = mapped_column(UUID, ForeignKey('auth.id', ondelete='CASCADE'))",
            "Database automatically deletes all Xxx rows where owner_id == deleted_auth.id",
            "No explicit cleanup code needed in application (handled by DB constraint)",
            "routes/auth.py: delete_user endpoint triggers cascade (if exists)",
        ],
        "code_example": """\
# === Cascade Delete on Owned Entities ===

# models.py (SQLAlchemy)
from sqlalchemy.orm import Mapped, mapped_column, relationship
class Xxx(Base):
    __tablename__ = "xxxs"
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        UUID,
        ForeignKey("auth.id", ondelete="CASCADE"),  # ← Cascade delete
    )
    owner: Mapped["Auth"] = relationship(back_populates="xxxs")

class Auth(Base):
    __tablename__ = "auth"
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    identifier: Mapped[str] = mapped_column(String, unique=True, index=True)
    xxxs: Mapped[list[Xxx]] = relationship(back_populates="owner", cascade="all, delete-orphan")

# When a user is deleted, the database automatically deletes all owned Xxx rows
# Example: DELETE FROM auth WHERE id = '123' → automatically deletes all xxxs with owner_id = '123'

# routes/auth.py (if user deletion is supported)
@router.delete("/me")
async def delete_self(
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.delete(current_user)  # Cascade delete all owned entities
    await db.commit()
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Lifespan with init_db for auth project ───────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Lifespan wiring for Medium FastAPI auth project. "
            "init_db() creates all tables at startup via Base.metadata.create_all(), "
            "including auth and owned entity tables. Required for schemathesis to work. "
            "Also optional: seed default superadmin user on startup."
        ),
        "modules": ["main.py", "core/db.py", "models.py"],
        "connections": [
            "main.py: lifespan() → await init_db()",
            "core/db.py: init_db() → async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)",
            "core/db.py: optional seed_superadmin() → create default admin user if not exists",
            "models.py: Base.metadata contains all table definitions (Auth + Xxx + ...)",
            "main.py: app = FastAPI(lifespan=lifespan) → tables + default user exist before first request",
        ],
        "code_example": """\
# === Lifespan Wiring — Medium Auth Project ===

# core/db.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from core.config import settings

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Optional: seed default superadmin
    await seed_superadmin()

async def seed_superadmin() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(Auth).where(Auth.is_superadmin == True)
        )
        if not existing.scalars().first():
            admin = Auth(
                identifier="admin@example.com",
                hashed_secret=get_password_hash("changeme"),
                is_active=True,
                is_superadmin=True,
            )
            session.add(admin)
            await session.commit()

# main.py
from contextlib import asynccontextmanager
from core.db import init_db

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    print("✅ Tables created, default admin user ready")
    yield
    print("🛑 Shutting down")

app = FastAPI(lifespan=lifespan)
# Tables exist before first request → schemathesis works
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },
]


# ─── Ingestion ───────────────────────────────────────────────────────────────

def clone_repo() -> None:
    """Clone le repo si absent."""
    import os
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo déjà cloné → {REPO_LOCAL}")
        return
    print(f"  Cloning {REPO_URL}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, REPO_LOCAL],
        check=True, capture_output=True,
    )
    print(f"  ✅ Cloné → {REPO_LOCAL}")


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION WIRINGS — {REPO_NAME}")
    print(f"{'='*60}\n")

    # ── 0. Init Qdrant ──────────────────────────────────────────────
    client = QdrantClient(path=KB_PATH)

    # Vérifier que la collection existe
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        print(f"  ❌ Collection '{COLLECTION}' n'existe pas. Lancer setup_collections.py d'abord.")
        return

    count_before = client.count(COLLECTION).count
    print(f"  KB avant : {count_before} wirings")

    # ── 1. Cleanup ancien tag ───────────────────────────────────────
    print(f"\n  Cleanup tag '{TAG}'...")
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
            )
        ),
    )
    after_cleanup = client.count(COLLECTION).count
    print(f"  Après cleanup : {after_cleanup} wirings")

    # ── 2. Clone repo + extraction AST ──────────────────────────────
    clone_repo()

    print("\n  Extraction AST des wirings...")
    ast_wirings = extract_all_wirings(
        REPO_LOCAL,
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        pattern_scope="crud_auth",
    )
    print(f"  → {len(ast_wirings)} wirings extraits par AST")

    # ── 3. Combiner AST + manuels ───────────────────────────────────
    all_wirings = ast_wirings + MANUAL_WIRINGS
    print(f"  + {len(MANUAL_WIRINGS)} wirings manuels")
    print(f"  = {len(all_wirings)} wirings total")

    # ── 4. Embedding ────────────────────────────────────────────────
    print("\n  Embedding des descriptions...")
    descriptions = [w["description"] for w in all_wirings]
    vectors = embed_documents_batch(descriptions)
    print(f"  → {len(vectors)} vecteurs générés ({len(vectors[0])} dims)")

    # ── 5. Upsert dans Qdrant ───────────────────────────────────────
    print("\n  Indexation dans Qdrant...")
    points: list[PointStruct] = []
    for wiring, vector in zip(all_wirings, vectors):
        payload = {
            **wiring,
            "charte_version": CHARTE_VERSION,
            "created_at": int(time.time()),
            "_tag": TAG,
        }
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        ))

    client.upsert(collection_name=COLLECTION, points=points)
    count_after = client.count(COLLECTION).count
    print(f"  ✅ {len(points)} wirings indexés")
    print(f"  KB après : {count_after} wirings")

    # ── 6. Verification queries ─────────────────────────────────────
    print("\n  Vérification par queries sémantiques...")
    test_queries = [
        ("file creation order medium FastAPI auth project", "flow_pattern"),
        ("auth dependency injection chain get_current_user", "dependency_chain"),
        ("UUID primary key FastAPI Pydantic", "dependency_chain"),
        ("owned entity authorization check owner_id", "flow_pattern"),
        ("JWT token login flow access_token", "flow_pattern"),
        ("multiple schema sets Create Update Public", "dependency_chain"),
        ("test fixture conftest auth token TestClient", "flow_pattern"),
        ("cascade delete owned entities ForeignKey", "dependency_chain"),
        ("lifespan init_db seed superadmin startup", "dependency_chain"),
    ]

    all_pass = True
    for query_text, expected_type in test_queries:
        qvec = embed_query(query_text)
        results = client.query_points(
            collection_name=COLLECTION,
            query=qvec,
            query_filter=Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=LANGUAGE))]
            ),
            limit=1,
            with_payload=True,
        )

        if results.points:
            top = results.points[0]
            wtype = top.payload.get("wiring_type", "?")
            score = top.score
            desc = top.payload.get("description", "?")[:80]
            status = "✅" if wtype == expected_type else "⚠️"
            if wtype != expected_type:
                all_pass = False
            print(f"  {status} [{score:.4f}] '{query_text[:50]}' → {wtype} ({desc}...)")
        else:
            print(f"  ❌ '{query_text[:50]}' → no results")
            all_pass = False

    # ── 7. Cleanup si dry run ───────────────────────────────────────
    if DRY_RUN:
        print("\n  🧹 DRY_RUN — suppression des wirings...")
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
                )
            ),
        )
        final_count = client.count(COLLECTION).count
        print(f"  KB final : {final_count} wirings (nettoyé)")
    else:
        final_count = count_after

    # ── 8. Rapport ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RAPPORT INGESTION WIRINGS — {REPO_NAME}")
    print(f"{'='*60}")
    print(f"  Mode            : {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"  Wirings AST     : {len(ast_wirings)}")
    print(f"  Wirings manuels : {len(MANUAL_WIRINGS)}")
    print(f"  Wirings total   : {len(all_wirings)}")
    print(f"  KB avant        : {count_before}")
    print(f"  KB après        : {final_count}")
    print(f"  Queries         : {'✅ ALL PASS' if all_pass else '⚠️  SOME MISMATCH'}")
    verdict = "✅ PASS" if len(all_wirings) > 0 and not DRY_RUN else "🧪 DRY RUN OK" if DRY_RUN else "❌ FAIL"
    print(f"  Verdict         : {verdict}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
