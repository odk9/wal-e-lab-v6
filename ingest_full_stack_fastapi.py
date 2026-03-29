"""
ingest_full_stack_fastapi.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de fastapi/full-stack-fastapi-template dans la KB Qdrant V6.

Usage:
    .venv/bin/python3 ingest_full_stack_fastapi.py
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
)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/fastapi/full-stack-fastapi-template.git"
REPO_NAME = "fastapi/full-stack-fastapi-template"
REPO_LOCAL = "/tmp/full_stack_fastapi"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "fastapi/full-stack-fastapi-template"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/fastapi/full-stack-fastapi-template"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# Source: full-stack-fastapi-template (SQLModel → converti en SQLAlchemy 2.0 + Pydantic V2)
# U-5: User→Xxx, Item→Xxx, email→identifier, hashed_password→hashed_secret

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Auth entity model — UUID PK, hashed_secret, is_active, is_superadmin ──
    {
        "normalized_code": """\
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    identifier: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_secret: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
""",
        "function": "auth_entity_model_uuid",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models.py",
    },

    # ── 2. Owned entity model — FK + cascade delete ──────────────────────────
    {
        "normalized_code": """\
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    xxx_ref_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("xxx_refs.id", ondelete="CASCADE"), nullable=False
    )
    xxx_ref: Mapped["XxxRef | None"] = relationship(back_populates="xxxs")
""",
        "function": "owned_entity_model_fk_cascade",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMAS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 3. Auth create schema (admin) ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class XxxCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identifier: str = Field(max_length=255)
    secret: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_superadmin: bool = False
""",
        "function": "auth_create_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 4. Public registration schema ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class XxxRegister(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identifier: str = Field(max_length=255)
    secret: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
""",
        "function": "auth_register_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 5. Auth update schema (admin, all optional) ──────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class XxxUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identifier: str | None = Field(default=None, max_length=255)
    secret: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superadmin: bool | None = None
""",
        "function": "auth_update_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 6. Self-update schema (limited fields) ──────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class XxxUpdateMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str | None = Field(default=None, max_length=255)
    identifier: str | None = Field(default=None, max_length=255)
""",
        "function": "auth_self_update_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 7. Change password schema ────────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class UpdateSecret(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_secret: str = Field(min_length=8, max_length=128)
    new_secret: str = Field(min_length=8, max_length=128)
""",
        "function": "change_secret_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 8. Auth public response schema ───────────────────────────────────────
    {
        "normalized_code": """\
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class XxxPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identifier: str
    full_name: str | None = None
    is_active: bool
    is_superadmin: bool
    created_at: datetime | None = None
""",
        "function": "auth_public_response_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 9. Paginated list response schema ────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class XxxsPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: list[XxxPublic]
    count: int
""",
        "function": "paginated_list_response_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 10. Owned entity schemas (create + update + public) ──────────────────
    {
        "normalized_code": """\
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class XxxCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class XxxUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class XxxPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    xxx_ref_id: uuid.UUID
    created_at: datetime | None = None
""",
        "function": "owned_entity_schemas_crud",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 11. Token + TokenPayload schemas ─────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sub: str | None = None
""",
        "function": "token_schemas",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 12. New secret (password reset) schema ───────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field


class NewSecret(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    new_secret: str = Field(min_length=8, max_length=128)
""",
        "function": "new_secret_reset_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ── 13. Generic message response ─────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class XxxMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail: str
""",
        "function": "generic_message_response",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/models.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH / SECURITY
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 14. Create JWT access token ──────────────────────────────────────────
    {
        "normalized_code": """\
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

ALGORITHM = "HS256"
SECRET_KEY: str = os.environ["SECRET_KEY"]


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(UTC) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
""",
        "function": "create_jwt_access_token",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/core/security.py",
    },

    # ── 15. Verify + hash password (argon2) ──────────────────────────────────
    {
        "normalized_code": """\
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def verify_secret(
    plain_secret: str, hashed_secret: str
) -> tuple[bool, str | None]:
    return _password_hash.verify_and_update(plain_secret, hashed_secret)


def get_secret_hash(secret: str) -> str:
    return _password_hash.hash(secret)
""",
        "function": "verify_and_hash_secret_argon2",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/core/security.py",
    },

    # ── 16. Generate password reset token (JWT) ──────────────────────────────
    {
        "normalized_code": """\
import os
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
SECRET_KEY: str = os.environ["SECRET_KEY"]
RESET_TOKEN_EXPIRE_HOURS: int = 48


def generate_reset_token(identifier: str) -> str:
    now = datetime.now(UTC)
    expires = now + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"exp": expires.timestamp(), "nbf": now, "sub": identifier},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
""",
        "function": "generate_reset_token_jwt",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/utils.py",
    },

    # ── 17. Verify password reset token ──────────────────────────────────────
    {
        "normalized_code": """\
import os

import jwt
from jwt.exceptions import InvalidTokenError

ALGORITHM = "HS256"
SECRET_KEY: str = os.environ["SECRET_KEY"]


def verify_reset_token(token: str) -> str | None:
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return str(decoded["sub"])
    except InvalidTokenError:
        return None
""",
        "function": "verify_reset_token_jwt",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/utils.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DEPENDENCIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 18. DB session dependency (sync engine) ──────────────────────────────
    {
        "normalized_code": """\
import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DATABASE_URL: str = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
""",
        "function": "sync_session_dependency_engine",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/api/deps.py",
    },

    # ── 19. Get current authenticated xxx (OAuth2 + JWT decode) ──────────────
    {
        "normalized_code": """\
import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlalchemy.orm import Session

ALGORITHM = "HS256"
SECRET_KEY: str = os.environ["SECRET_KEY"]
API_V1_STR: str = "/api/v1"

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{API_V1_STR}/login/access-token"
)

TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_xxx(session: SessionDep, token: TokenDep) -> Xxx:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    xxx = session.get(Xxx, token_data.sub)
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    if not xxx.is_active:
        raise HTTPException(status_code=400, detail="Inactive xxx")
    return xxx


CurrentXxx = Annotated[Xxx, Depends(get_current_xxx)]
""",
        "function": "get_current_xxx_oauth2_jwt",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/api/deps.py",
    },

    # ── 20. Superadmin permission check dependency ───────────────────────────
    {
        "normalized_code": """\
from typing import Annotated

from fastapi import Depends, HTTPException


def get_current_active_superadmin(current_xxx: CurrentXxx) -> Xxx:
    if not current_xxx.is_superadmin:
        raise HTTPException(
            status_code=403, detail="Not enough privileges"
        )
    return current_xxx
""",
        "function": "superadmin_permission_dependency",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/api/deps.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 21. Create auth entity with secret hashing ───────────────────────────
    {
        "normalized_code": """\
from sqlalchemy.orm import Session


def create_xxx(session: Session, xxx_create: XxxCreate) -> Xxx:
    hashed = get_secret_hash(xxx_create.secret)
    data = xxx_create.model_dump(exclude={"secret"})
    db_xxx = Xxx(**data, hashed_secret=hashed)
    session.add(db_xxx)
    session.commit()
    session.refresh(db_xxx)
    return db_xxx
""",
        "function": "crud_create_auth_entity",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/crud.py",
    },

    # ── 22. Update auth entity with optional secret change ───────────────────
    {
        "normalized_code": """\
from typing import Any

from sqlalchemy.orm import Session


def update_xxx(
    session: Session, db_xxx: Xxx, xxx_in: XxxUpdate
) -> Any:
    update_data = xxx_in.model_dump(exclude_unset=True)
    if "secret" in update_data:
        update_data["hashed_secret"] = get_secret_hash(update_data.pop("secret"))
    for key, value in update_data.items():
        setattr(db_xxx, key, value)
    session.add(db_xxx)
    session.commit()
    session.refresh(db_xxx)
    return db_xxx
""",
        "function": "crud_update_auth_entity",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/crud.py",
    },

    # ── 23. Get auth entity by unique field ──────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_xxx_by_identifier(session: Session, identifier: str) -> Xxx | None:
    stmt = select(Xxx).where(Xxx.identifier == identifier)
    return session.execute(stmt).scalar_one_or_none()
""",
        "function": "crud_get_by_unique_field",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/crud.py",
    },

    # ── 24. Authenticate — timing-safe with dummy hash ───────────────────────
    {
        "normalized_code": """\
from sqlalchemy.orm import Session

DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "MjQyZWE1MzBjYjJlZTI0Yw$"
    "YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"
)


def authenticate(
    session: Session, identifier: str, secret: str
) -> Xxx | None:
    db_xxx = get_xxx_by_identifier(session=session, identifier=identifier)
    if not db_xxx:
        verify_secret(secret, DUMMY_HASH)
        return None
    verified, updated_hash = verify_secret(secret, db_xxx.hashed_secret)
    if not verified:
        return None
    if updated_hash:
        db_xxx.hashed_secret = updated_hash
        session.add(db_xxx)
        session.commit()
        session.refresh(db_xxx)
    return db_xxx
""",
        "function": "authenticate_timing_safe",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/crud.py",
    },

    # ── 25. Create owned entity ──────────────────────────────────────────────
    {
        "normalized_code": """\
import uuid

from sqlalchemy.orm import Session


def create_xxx(
    session: Session, xxx_in: XxxCreate, xxx_ref_id: uuid.UUID
) -> Xxx:
    data = xxx_in.model_dump()
    db_xxx = Xxx(**data, xxx_ref_id=xxx_ref_id)
    session.add(db_xxx)
    session.commit()
    session.refresh(db_xxx)
    return db_xxx
""",
        "function": "crud_create_owned_entity",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/crud.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — AUTH
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 26. Login access token route ─────────────────────────────────────────
    {
        "normalized_code": """\
import os
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(tags=["login"])

ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "11520")
)


@router.post("/login/access-token")
def login_access_token(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    xxx = authenticate(
        session=session,
        identifier=form_data.username,
        secret=form_data.password,
    )
    if not xxx:
        raise HTTPException(
            status_code=400, detail="Incorrect identifier or secret"
        )
    if not xxx.is_active:
        raise HTTPException(status_code=400, detail="Inactive account")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=create_access_token(
            xxx.id, expires_delta=access_token_expires
        )
    )
""",
        "function": "route_login_access_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/login.py",
    },

    # ── 27. Test token route ─────────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["login"])


@router.post("/login/test-token", response_model=XxxPublic)
def test_token(current_xxx: CurrentXxx) -> Any:
    return current_xxx
""",
        "function": "route_test_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/login.py",
    },

    # ── 28. Password recovery (anti-enumeration) ────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter

router = APIRouter(tags=["login"])


@router.post("/secret-recovery/{identifier}")
def recover_secret(identifier: str, session: SessionDep) -> XxxMessage:
    xxx = get_xxx_by_identifier(session=session, identifier=identifier)
    if xxx:
        reset_token = generate_reset_token(identifier=identifier)
        send_reset_notification(identifier=identifier, token=reset_token)
    return XxxMessage(
        detail="If that identifier is registered, a recovery link was sent"
    )
""",
        "function": "route_secret_recovery_anti_enum",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/login.py",
    },

    # ── 29. Reset password route ─────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["login"])


@router.post("/reset-secret/")
def reset_secret(session: SessionDep, body: NewSecret) -> XxxMessage:
    identifier = verify_reset_token(token=body.token)
    if not identifier:
        raise HTTPException(status_code=400, detail="Invalid token")
    xxx = get_xxx_by_identifier(session=session, identifier=identifier)
    if not xxx:
        raise HTTPException(status_code=400, detail="Invalid token")
    if not xxx.is_active:
        raise HTTPException(status_code=400, detail="Inactive account")
    xxx_update = XxxUpdate(secret=body.new_secret)
    update_xxx(session=session, db_xxx=xxx, xxx_in=xxx_update)
    return XxxMessage(detail="Secret updated successfully")
""",
        "function": "route_reset_secret",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/login.py",
    },

    # ── 30. Public registration (signup) ─────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.post("/signup", response_model=XxxPublic)
def register_xxx(session: SessionDep, xxx_in: XxxRegister) -> Any:
    existing = get_xxx_by_identifier(
        session=session, identifier=xxx_in.identifier
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An account with this identifier already exists",
        )
    xxx_create = XxxCreate.model_validate(xxx_in)
    return create_xxx(session=session, xxx_create=xxx_create)
""",
        "function": "route_public_registration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — ENTITY MANAGEMENT (admin)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 31. List entities paginated + count (superadmin) ─────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import col, func, select

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superadmin)],
    response_model=XxxsPublic,
)
def list_xxxs(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    count_stmt = select(func.count()).select_from(Xxx)
    count = session.execute(count_stmt).scalar_one()
    stmt = (
        select(Xxx)
        .order_by(col(Xxx.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    data = list(session.execute(stmt).scalars().all())
    return XxxsPublic(data=data, count=count)
""",
        "function": "route_list_paginated_count_admin",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 32. Get xxx by id (permission: own or superadmin) ────────────────────
    {
        "normalized_code": """\
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.get("/{xxx_id}", response_model=XxxPublic)
def read_xxx_by_id(
    xxx_id: uuid.UUID, session: SessionDep, current_xxx: CurrentXxx
) -> Any:
    xxx = session.get(Xxx, xxx_id)
    if xxx == current_xxx:
        return xxx
    if not current_xxx.is_superadmin:
        raise HTTPException(
            status_code=403, detail="Not enough privileges"
        )
    if xxx is None:
        raise HTTPException(status_code=404, detail="Xxx not found")
    return xxx
""",
        "function": "route_get_by_id_permission_check",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 33. Admin create (superadmin, uniqueness check) ──────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.post(
    "/",
    dependencies=[Depends(get_current_active_superadmin)],
    response_model=XxxPublic,
)
def admin_create_xxx(session: SessionDep, xxx_in: XxxCreate) -> Any:
    existing = get_xxx_by_identifier(
        session=session, identifier=xxx_in.identifier
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An account with this identifier already exists",
        )
    return create_xxx(session=session, xxx_create=xxx_in)
""",
        "function": "route_admin_create_unique_check",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 34. Update self (PATCH /me) ──────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.patch("/me", response_model=XxxPublic)
def update_xxx_me(
    session: SessionDep, xxx_in: XxxUpdateMe, current_xxx: CurrentXxx
) -> Any:
    if xxx_in.identifier:
        existing = get_xxx_by_identifier(
            session=session, identifier=xxx_in.identifier
        )
        if existing and existing.id != current_xxx.id:
            raise HTTPException(
                status_code=409,
                detail="This identifier is already taken",
            )
    for key, value in xxx_in.model_dump(exclude_unset=True).items():
        setattr(current_xxx, key, value)
    session.add(current_xxx)
    session.commit()
    session.refresh(current_xxx)
    return current_xxx
""",
        "function": "route_update_self_me",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 35. Update password (PATCH /me/secret) ───────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.patch("/me/secret", response_model=XxxMessage)
def update_secret_me(
    session: SessionDep, body: UpdateSecret, current_xxx: CurrentXxx
) -> XxxMessage:
    verified, _ = verify_secret(body.current_secret, current_xxx.hashed_secret)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect secret")
    if body.current_secret == body.new_secret:
        raise HTTPException(
            status_code=400,
            detail="New secret cannot be the same as the current one",
        )
    current_xxx.hashed_secret = get_secret_hash(body.new_secret)
    session.add(current_xxx)
    session.commit()
    return XxxMessage(detail="Secret updated successfully")
""",
        "function": "route_update_secret_me",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 36. Get current xxx (GET /me) ────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.get("/me", response_model=XxxPublic)
def read_xxx_me(current_xxx: CurrentXxx) -> Any:
    return current_xxx
""",
        "function": "route_get_current_me",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 37. Delete self (with superadmin guard) ──────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.delete("/me")
def delete_xxx_me(session: SessionDep, current_xxx: CurrentXxx) -> XxxMessage:
    if current_xxx.is_superadmin:
        raise HTTPException(
            status_code=403,
            detail="Superadmins are not allowed to delete themselves",
        )
    session.delete(current_xxx)
    session.commit()
    return XxxMessage(detail="Account deleted successfully")
""",
        "function": "route_delete_self_superadmin_guard",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ── 38. Admin delete by id (cascade owned) ───────────────────────────────
    {
        "normalized_code": """\
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import col, delete

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.delete(
    "/{xxx_id}", dependencies=[Depends(get_current_active_superadmin)]
)
def admin_delete_xxx(
    session: SessionDep, current_xxx: CurrentXxx, xxx_id: uuid.UUID
) -> XxxMessage:
    xxx = session.get(Xxx, xxx_id)
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    if xxx == current_xxx:
        raise HTTPException(
            status_code=403,
            detail="Superadmins are not allowed to delete themselves",
        )
    stmt = delete(OwnedXxx).where(col(OwnedXxx.xxx_ref_id) == xxx_id)
    session.execute(stmt)
    session.delete(xxx)
    session.commit()
    return XxxMessage(detail="Deleted successfully")
""",
        "function": "route_admin_delete_cascade_owned",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/xxxs.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — OWNED ENTITY (per-xxx ownership)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 39. List owned entities (owner filter for non-superadmin) ─────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter
from sqlalchemy import col, func, select

router = APIRouter(prefix="/owned-xxxs", tags=["owned-xxxs"])


@router.get("/", response_model=XxxsPublic)
def list_owned_xxxs(
    session: SessionDep, current_xxx: CurrentXxx, skip: int = 0, limit: int = 100
) -> Any:
    if current_xxx.is_superadmin:
        count_stmt = select(func.count()).select_from(OwnedXxx)
        count = session.execute(count_stmt).scalar_one()
        stmt = (
            select(OwnedXxx)
            .order_by(col(OwnedXxx.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
    else:
        count_stmt = (
            select(func.count())
            .select_from(OwnedXxx)
            .where(OwnedXxx.xxx_ref_id == current_xxx.id)
        )
        count = session.execute(count_stmt).scalar_one()
        stmt = (
            select(OwnedXxx)
            .where(OwnedXxx.xxx_ref_id == current_xxx.id)
            .order_by(col(OwnedXxx.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
    data = list(session.execute(stmt).scalars().all())
    return XxxsPublic(data=data, count=count)
""",
        "function": "route_list_owned_entities_permission",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/owned_xxxs.py",
    },

    # ── 40. Get owned entity by id (ownership check) ────────────────────────
    {
        "normalized_code": """\
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/owned-xxxs", tags=["owned-xxxs"])


@router.get("/{xxx_id}", response_model=XxxPublic)
def read_owned_xxx(
    session: SessionDep, current_xxx: CurrentXxx, xxx_id: uuid.UUID
) -> Any:
    xxx = session.get(OwnedXxx, xxx_id)
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    if not current_xxx.is_superadmin and xxx.xxx_ref_id != current_xxx.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return xxx
""",
        "function": "route_get_owned_entity_ownership",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/owned_xxxs.py",
    },

    # ── 41. Create owned entity (owner = current_xxx) ────────────────────────
    {
        "normalized_code": """\
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/owned-xxxs", tags=["owned-xxxs"])


@router.post("/", response_model=XxxPublic)
def create_owned_xxx(
    session: SessionDep, current_xxx: CurrentXxx, xxx_in: XxxCreate
) -> Any:
    data = xxx_in.model_dump()
    db_xxx = OwnedXxx(**data, xxx_ref_id=current_xxx.id)
    session.add(db_xxx)
    session.commit()
    session.refresh(db_xxx)
    return db_xxx
""",
        "function": "route_create_owned_entity",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/owned_xxxs.py",
    },

    # ── 42. Update owned entity (ownership check) ───────────────────────────
    {
        "normalized_code": """\
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/owned-xxxs", tags=["owned-xxxs"])


@router.put("/{xxx_id}", response_model=XxxPublic)
def update_owned_xxx(
    session: SessionDep,
    current_xxx: CurrentXxx,
    xxx_id: uuid.UUID,
    xxx_in: XxxUpdate,
) -> Any:
    xxx = session.get(OwnedXxx, xxx_id)
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    if not current_xxx.is_superadmin and xxx.xxx_ref_id != current_xxx.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    for key, value in xxx_in.model_dump(exclude_unset=True).items():
        setattr(xxx, key, value)
    session.add(xxx)
    session.commit()
    session.refresh(xxx)
    return xxx
""",
        "function": "route_update_owned_entity_ownership",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/owned_xxxs.py",
    },

    # ── 43. Delete owned entity (ownership check) ───────────────────────────
    {
        "normalized_code": """\
import uuid

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/owned-xxxs", tags=["owned-xxxs"])


@router.delete("/{xxx_id}")
def delete_owned_xxx(
    session: SessionDep, current_xxx: CurrentXxx, xxx_id: uuid.UUID
) -> XxxMessage:
    xxx = session.get(OwnedXxx, xxx_id)
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    if not current_xxx.is_superadmin and xxx.xxx_ref_id != current_xxx.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    session.delete(xxx)
    session.commit()
    return XxxMessage(detail="Deleted successfully")
""",
        "function": "route_delete_owned_entity_ownership",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/owned_xxxs.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — UTILS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 44. Health check route ───────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True
""",
        "function": "route_health_check",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/api/routes/utils.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 45. Settings BaseSettings + env vars ─────────────────────────────────
    {
        "normalized_code": """\
import os
import secrets
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    PROJECT_NAME: str = "Xxx API"
    DATABASE_URL: str = "sqlite:///./app.db"

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
""",
        "function": "settings_base_env_vars",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/core/config.py",
    },

    # ── 46. CORS middleware configuration ────────────────────────────────────
    {
        "normalized_code": """\
from typing import Annotated, Any

from fastapi import FastAPI
from pydantic import AnyUrl, BeforeValidator
from starlette.middleware.cors import CORSMiddleware


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    if isinstance(v, list | str):
        return v
    raise ValueError(v)


CorsOrigins = Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)]


def setup_cors(app: FastAPI, origins: list[str]) -> None:
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
""",
        "function": "cors_middleware_configuration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/main.py",
    },

    # ── 47. API router aggregation ───────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, FastAPI

api_router = APIRouter()
api_router.include_router(login_router)
api_router.include_router(xxxs_router)
api_router.include_router(utils_router)
api_router.include_router(owned_xxxs_router)

app = FastAPI(title="Xxx API", version="1.0.0")
app.include_router(api_router, prefix="/api/v1")
""",
        "function": "api_router_aggregation",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/api/main.py",
    },

    # ── 48. Init DB — create first superadmin ────────────────────────────────
    {
        "normalized_code": """\
import os

from sqlalchemy import select
from sqlalchemy.orm import Session


def init_db(session: Session) -> None:
    first_identifier = os.environ["FIRST_SUPERADMIN"]
    first_secret = os.environ["FIRST_SUPERADMIN_SECRET"]
    stmt = select(Xxx).where(Xxx.identifier == first_identifier)
    xxx = session.execute(stmt).scalar_one_or_none()
    if not xxx:
        xxx_in = XxxCreate(
            identifier=first_identifier,
            secret=first_secret,
            is_superadmin=True,
        )
        create_xxx(session=session, xxx_create=xxx_in)
""",
        "function": "init_db_create_first_superadmin",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/core/db.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 49. Send email via SMTP ──────────────────────────────────────────────
    {
        "normalized_code": """\
import logging
import os

import emails

logger = logging.getLogger(__name__)


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_tls = os.environ.get("SMTP_TLS", "true").lower() == "true"
    smtp_ssl = os.environ.get("SMTP_SSL", "false").lower() == "true"
    smtp_from = os.environ.get("EMAILS_FROM_EMAIL", "")
    smtp_from_name = os.environ.get("EMAILS_FROM_NAME", "")
    smtp_login = os.environ.get("SMTP_LOGIN")
    smtp_secret = os.environ.get("SMTP_SECRET")

    if not smtp_host:
        raise RuntimeError("SMTP not configured")

    msg = emails.Message(
        subject=subject,
        html=html_content,
        mail_from=(smtp_from_name, smtp_from),
    )
    smtp_options: dict = {"host": smtp_host, "port": smtp_port}
    if smtp_tls:
        smtp_options["tls"] = True
    elif smtp_ssl:
        smtp_options["ssl"] = True
    if smtp_login:
        smtp_options["user"] = smtp_login  # SMTP protocol key
    if smtp_secret:
        smtp_options["password"] = smtp_secret
    response = msg.send(to=email_to, smtp=smtp_options)
    logger.info("send email result: %s", response)
""",
        "function": "send_email_smtp",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/utils.py",
    },

    # ── 50. Email data dataclass + template rendering ────────────────────────
    {
        "normalized_code": """\
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Template


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(
    *, template_name: str, context: dict[str, Any]
) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    return Template(template_str).render(context)
""",
        "function": "email_data_template_rendering",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/utils.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 51. Conftest — fixtures (client, db, superadmin token, normal token) ─
    {
        "normalized_code": """\
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.core.db import engine, init_db
from src.main import app


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        init_db(session)
        yield session


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superadmin_token_headers(client: TestClient) -> dict[str, str]:
    login_data = {"username": "admin@example.com", "password": "changethis"}
    r = client.post("/api/v1/login/access-token", data=login_data)
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture(scope="module")
def normal_xxx_token_headers(
    client: TestClient, db: Session
) -> dict[str, str]:
    login_data = {"username": "test@example.com", "password": "testpass123"}
    r = client.post("/api/v1/login/access-token", data=login_data)
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}
""",
        "function": "conftest_auth_fixtures",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/conftest.py",
    },

    # ── 52. Test login — get token ───────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_get_access_token(client: TestClient) -> None:
    login_data = {"username": "admin@example.com", "password": "changethis"}
    r = client.post("/api/v1/login/access-token", data=login_data)
    tokens = r.json()
    assert r.status_code == 200
    assert "access_token" in tokens
    assert tokens["access_token"]
""",
        "function": "test_login_get_access_token",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_login.py",
    },

    # ── 53. Test login — invalid credentials ─────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_get_access_token_incorrect_secret(client: TestClient) -> None:
    login_data = {"username": "admin@example.com", "password": "wrong"}
    r = client.post("/api/v1/login/access-token", data=login_data)
    assert r.status_code == 400
""",
        "function": "test_login_invalid_credentials",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_login.py",
    },

    # ── 54. Test token validation ────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_use_access_token(
    client: TestClient, superadmin_token_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/login/test-token",
        headers=superadmin_token_headers,
    )
    result = r.json()
    assert r.status_code == 200
    assert "identifier" in result
""",
        "function": "test_token_validation",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_login.py",
    },

    # ── 55. Test CRUD owned — create ─────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_create_owned_xxx(
    client: TestClient, superadmin_token_headers: dict[str, str]
) -> None:
    data = {"title": "Foo", "description": "Bar"}
    response = client.post(
        "/api/v1/owned-xxxs/",
        headers=superadmin_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == data["title"]
    assert content["description"] == data["description"]
    assert "id" in content
    assert "xxx_ref_id" in content
""",
        "function": "test_create_owned_entity",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_owned_xxxs.py",
    },

    # ── 56. Test CRUD owned — permission denied ──────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_read_owned_xxx_not_enough_permissions(
    client: TestClient,
    normal_xxx_token_headers: dict[str, str],
    db: Session,
) -> None:
    response = client.get(
        "/api/v1/owned-xxxs/{xxx_id}",
        headers=normal_xxx_token_headers,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"
""",
        "function": "test_owned_entity_permission_denied",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_owned_xxxs.py",
    },

    # ── 57. Test registration ────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_register_xxx(client: TestClient) -> None:
    data = {
        "identifier": "new@example.com",
        "secret": "strongsecret123",
        "full_name": "New Xxx",
    }
    r = client.post("/api/v1/xxxs/signup", json=data)
    assert r.status_code == 200
    created = r.json()
    assert created["identifier"] == data["identifier"]
    assert created["full_name"] == data["full_name"]
""",
        "function": "test_public_registration",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_xxxs.py",
    },

    # ── 58. Test get me ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_get_xxx_me(
    client: TestClient, superadmin_token_headers: dict[str, str]
) -> None:
    r = client.get("/api/v1/xxxs/me", headers=superadmin_token_headers)
    current_xxx = r.json()
    assert current_xxx
    assert current_xxx["is_active"] is True
    assert current_xxx["is_superadmin"]
""",
        "function": "test_get_current_me",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_xxxs.py",
    },

    # ── 59. Test password reset flow ─────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_reset_secret(client: TestClient, db: Session) -> None:
    token = generate_reset_token(identifier="test@example.com")
    data = {"new_secret": "newsecret123", "token": token}
    r = client.post("/api/v1/reset-secret/", json=data)
    assert r.status_code == 200
    assert r.json() == {"detail": "Secret updated successfully"}


def test_reset_secret_invalid_token(
    client: TestClient, superadmin_token_headers: dict[str, str]
) -> None:
    data = {"new_secret": "newsecret123", "token": "invalid"}
    r = client.post(
        "/api/v1/reset-secret/",
        headers=superadmin_token_headers,
        json=data,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid token"
""",
        "function": "test_secret_reset_flow",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/api/routes/test_login.py",
    },

    # ── 60. Alembic env.py pattern ───────────────────────────────────────────
    {
        "normalized_code": """\
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.orm import DeclarativeBase

config = context.config

assert config.config_file_name is not None
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ["DATABASE_URL"]


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
""",
        "function": "alembic_env_pattern",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "alembic/env.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "JWT authentication login return access token",
    "get current authenticated user FastAPI dependency",
    "SQLAlchemy model with foreign key relationship",
    "background task send email FastAPI",
    "superuser permission check dependency",
    "user registration with password hashing bcrypt",
    "paginated list response with total count",
]


def clone_repo() -> None:
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo déjà cloné : {REPO_LOCAL}")
        return
    print(f"  Clonage {REPO_URL} → {REPO_LOCAL} ...")
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
    )
    print("  Cloné.")


def build_payloads() -> list[dict]:
    payloads = []
    all_violations = []
    for p in PATTERNS:
        v = check_charte_violations(p["normalized_code"], p["function"])
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
        print("  PRE-INDEX violations détectées :")
        for v in all_violations:
            print(f"    WARN: {v}")
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    print(f"  Embedding {len(codes)} patterns (batch) ...")
    vectors = embed_documents_batch(codes)
    print(f"  {len(vectors)} vecteurs générés.")

    points = []
    for i, (vec, payload) in enumerate(zip(vectors, payloads)):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
        if (i + 1) % 10 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points préparés")

    print(f"  Upsert {len(points)} points dans '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print("  Upsert terminé.")
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = client.query_points(
            collection_name=COLLECTION, query=vec, limit=1
        ).points
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
        violations.extend(check_charte_violations(code, fn))
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
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)

    # ── Étape 1 : Prérequis ─────────────────────────────────────────────
    print("── Étape 1 : Prérequis")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERREUR: collection '{COLLECTION}' introuvable.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}' : {count_initial} points (initial)")

    # ── Étape 2 : Clone ─────────────────────────────────────────────────
    print("\n── Étape 2 : Clone")
    clone_repo()

    # ── Étape 3-4 : Extraction + Normalisation ──────────────────────────
    print(f"\n── Étape 3-4 : {len(PATTERNS)} patterns extraits et normalisés")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads construits.")

    # ── Étape 5 : Indexation ────────────────────────────────────────────
    print("\n── Étape 5 : Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []
    verdict = "FAIL"

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count KB après indexation : {count_after}")

        # ── Étape 6 : Audit ─────────────────────────────────────────────
        print("\n── Étape 6 : Audit qualité")
        print("\n  6b. Queries sémantiques :")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:35s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        print("\n  6c. Audit normalisation :")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    Aucune violation détectée ✓")

        scores_valid = all(0.0 <= r["score"] <= 1.0 for r in query_results)
        no_empty = all(r["function"] != "NO_RESULT" for r in query_results)
        verdict = "PASS" if (scores_valid and no_empty and not violations) else "FAIL"

    finally:
        # ── Étape 7 : Cleanup ou conservation ───────────────────────────
        print(f"\n── Étape 7 : {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points supprimés. Count final : {count_final}")
            if count_final == count_initial:
                print(f"  Count revenu à {count_initial} ✓")
            else:
                print(f"  WARN: count final ({count_final}) != initial ({count_initial})")
            print("  MODE TEST — données supprimées")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  MODE PRODUCTION — {n_indexed} patterns conservés en KB")
            print(f"  Count total : {count_final}")
            print(f"  Pour supprimer : filter _tag='{TAG}' via FilterSelector")

    # ── Étape 8 : Rapport ───────────────────────────────────────────────
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
    print(f"  Verdict : {'✅ PASS' if verdict == 'PASS' else '❌ FAIL'}")
    if verdict == "FAIL" and violations:
        print(f"  {len(violations)} violations bloquantes")


if __name__ == "__main__":
    main()
