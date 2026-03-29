"""
ingest_fastapi_users.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de fastapi-users/fastapi-users dans la KB Qdrant V6.

Usage:
    .venv/bin/python3 ingest_fastapi_users.py
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
REPO_URL = "https://github.com/fastapi-users/fastapi-users.git"
REPO_NAME = "fastapi-users/fastapi-users"
REPO_LOCAL = "/tmp/fastapi_users"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "fastapi-users/fastapi-users"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/fastapi-users/fastapi-users"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# Source: fastapi-users (lib → extracted from examples + tests + concrete impls)
# U-5: User→Xxx, UserManager→XxxManager, email→identifier where entity-specific
# Note: "email" is kept as-is — it's a field type, not an entity name

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS — SQLAlchemy 2.0
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Auth model — UUID PK, all auth fields ─────────────────────────────
    {
        "normalized_code": """\
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
""",
        "function": "auth_model_uuid_all_fields",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/db.py",
    },

    # ── 2. OAuth account model — provider + tokens ───────────────────────────
    {
        "normalized_code": """\
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    xxx_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("xxxs.id", ondelete="CASCADE"), nullable=False
    )
    oauth_name: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token: Mapped[str] = mapped_column(String(1024), nullable=False)
    expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    account_id: Mapped[str] = mapped_column(
        String(320), index=True, nullable=False
    )
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
""",
        "function": "oauth_account_model",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/db.py",
    },

    # ── 3. Auth model with OAuth accounts relationship ───────────────────────
    {
        "normalized_code": """\
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount", lazy="joined"
    )
""",
        "function": "auth_model_with_oauth_accounts",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/db.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMAS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 4. Auth read schema (public) ─────────────────────────────────────────
    {
        "normalized_code": """\
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class XxxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool = True
    is_superadmin: bool = False
    is_verified: bool = False
""",
        "function": "auth_read_schema_verified",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/schemas.py",
    },

    # ── 5. Auth create schema ────────────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class XxxCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    is_active: bool | None = True
    is_superadmin: bool | None = False
    is_verified: bool | None = False
""",
        "function": "auth_create_schema_verified",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/schemas.py",
    },

    # ── 6. Auth update schema ────────────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class XxxUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    password: str | None = Field(default=None, min_length=8, max_length=128)
    email: EmailStr | None = None
    is_active: bool | None = None
    is_superadmin: bool | None = None
    is_verified: bool | None = None
""",
        "function": "auth_update_schema_verified",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/schemas.py",
    },

    # ── 7. OAuth account schema ──────────────────────────────────────────────
    {
        "normalized_code": """\
import uuid

from pydantic import BaseModel, ConfigDict


class OAuthAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    oauth_name: str
    access_token: str
    expires_at: int | None = None
    refresh_token: str | None = None
    account_id: str
    account_email: str
""",
        "function": "oauth_account_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "app/schemas.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH STRATEGIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 8. JWT strategy — generate + decode ──────────────────────────────────
    {
        "normalized_code": """\
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import SecretStr

SecretType = str | SecretStr
JWT_ALGORITHM = "HS256"


def _get_secret_value(secret: SecretType) -> str:
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


def generate_jwt(
    data: dict[str, Any],
    secret: SecretType,
    lifetime_seconds: int | None = None,
    algorithm: str = JWT_ALGORITHM,
) -> str:
    payload = data.copy()
    if lifetime_seconds:
        expire = datetime.now(UTC) + timedelta(seconds=lifetime_seconds)
        payload["exp"] = expire
    return jwt.encode(payload, _get_secret_value(secret), algorithm=algorithm)


def decode_jwt(
    encoded_jwt: str,
    secret: SecretType,
    audience: list[str],
    algorithms: list[str] | None = None,
) -> dict[str, Any]:
    return jwt.decode(
        encoded_jwt,
        _get_secret_value(secret),
        audience=audience,
        algorithms=algorithms or [JWT_ALGORITHM],
    )
""",
        "function": "jwt_generate_decode_with_audience",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/jwt.py",
    },

    # ── 9. JWT strategy — write + read token ─────────────────────────────────
    {
        "normalized_code": """\
import os

import jwt


class JWTStrategy:
    def __init__(
        self,
        secret: str,
        lifetime_seconds: int | None = 3600,
        token_audience: list[str] | None = None,
        algorithm: str = "HS256",
    ) -> None:
        self.secret = secret
        self.lifetime_seconds = lifetime_seconds
        self.token_audience = token_audience or ["fastapi-auth"]
        self.algorithm = algorithm

    async def write_token(self, xxx_id: str) -> str:
        data = {"sub": xxx_id, "aud": self.token_audience}
        return generate_jwt(
            data, self.secret, self.lifetime_seconds, algorithm=self.algorithm
        )

    async def read_token(self, token: str | None) -> str | None:
        if token is None:
            return None
        try:
            data = decode_jwt(
                token, self.secret, self.token_audience,
                algorithms=[self.algorithm],
            )
            return data.get("sub")
        except jwt.PyJWTError:
            return None
""",
        "function": "jwt_strategy_write_read_token",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/auth/strategy_jwt.py",
    },

    # ── 10. Cookie transport — login/logout via cookie ───────────────────────
    {
        "normalized_code": """\
from typing import Literal

from fastapi import Response, status
from fastapi.security import APIKeyCookie


class CookieTransport:
    def __init__(
        self,
        cookie_name: str = "auth_token",
        cookie_max_age: int | None = None,
        cookie_path: str = "/",
        cookie_domain: str | None = None,
        cookie_secure: bool = True,
        cookie_httponly: bool = True,
        cookie_samesite: Literal["lax", "strict", "none"] = "lax",
    ) -> None:
        self.cookie_name = cookie_name
        self.cookie_max_age = cookie_max_age
        self.cookie_path = cookie_path
        self.cookie_domain = cookie_domain
        self.cookie_secure = cookie_secure
        self.cookie_httponly = cookie_httponly
        self.cookie_samesite = cookie_samesite
        self.scheme = APIKeyCookie(name=self.cookie_name, auto_error=False)

    async def get_login_response(self, token: str) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            self.cookie_name,
            token,
            max_age=self.cookie_max_age,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response

    async def get_logout_response(self) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            self.cookie_name,
            "",
            max_age=0,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response
""",
        "function": "cookie_transport_login_logout",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/auth/transport_cookie.py",
    },

    # ── 11. Bearer transport — JSON token response ───────────────────────────
    {
        "normalized_code": """\
from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict


class BearerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"


class BearerTransport:
    def __init__(self, token_url: str) -> None:
        self.scheme = OAuth2PasswordBearer(token_url, auto_error=False)

    async def get_login_response(self, token: str) -> Response:
        bearer_response = BearerResponse(
            access_token=token, token_type="bearer"
        )
        return JSONResponse(bearer_response.model_dump())
""",
        "function": "bearer_transport_json_response",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/auth/transport_bearer.py",
    },

    # ── 12. Authentication backend — transport + strategy combo ──────────────
    {
        "normalized_code": """\
import os

from fastapi import Response, status


class AuthenticationBackend:
    def __init__(
        self,
        name: str,
        transport: BearerTransport | CookieTransport,
        get_strategy: callable,
    ) -> None:
        self.name = name
        self.transport = transport
        self.get_strategy = get_strategy

    async def login(self, strategy: JWTStrategy, xxx_id: str) -> Response:
        token = await strategy.write_token(xxx_id)
        return await self.transport.get_login_response(token)

    async def logout(
        self, strategy: JWTStrategy, token: str
    ) -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
""",
        "function": "auth_backend_transport_strategy",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/auth/backend.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # XXX MANAGER — hooks + business logic
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. XxxManager base — create with password hash + hooks ──────────────
    {
        "normalized_code": """\
import uuid
from typing import Any

import jwt
from fastapi import Request


class XxxManager:
    reset_password_token_secret: str
    verification_token_secret: str
    reset_password_token_lifetime_seconds: int = 3600
    verification_token_lifetime_seconds: int = 3600

    def __init__(self, xxx_db: Any, password_helper: Any = None) -> None:
        self.xxx_db = xxx_db
        self.password_helper = password_helper or PasswordHelper()

    async def create(
        self,
        xxx_create: XxxCreate,
        safe: bool = False,
        request: Request | None = None,
    ) -> Xxx:
        existing = await self.xxx_db.get_by_email(xxx_create.email)
        if existing is not None:
            raise XxxAlreadyExistsError()
        xxx_dict = xxx_create.model_dump(exclude_unset=True)
        password = xxx_dict.pop("password")
        xxx_dict["hashed_password"] = self.password_helper.hash(password)
        created_xxx = await self.xxx_db.create(xxx_dict)
        await self.on_after_register(created_xxx, request)
        return created_xxx

    async def authenticate(
        self, email: str, password: str
    ) -> Xxx | None:
        try:
            xxx = await self.xxx_db.get_by_email(email)
        except XxxNotExistsError:
            self.password_helper.hash(password)
            return None
        verified, updated_hash = self.password_helper.verify_and_update(
            password, xxx.hashed_password
        )
        if not verified:
            return None
        if updated_hash is not None:
            await self.xxx_db.update(
                xxx, {"hashed_password": updated_hash}
            )
        return xxx
""",
        "function": "xxx_manager_create_authenticate",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/manager.py",
    },

    # ── 14. on_after_register hook ───────────────────────────────────────────
    {
        "normalized_code": """\
import logging

from fastapi import Request

logger = logging.getLogger(__name__)


class XxxManager:
    async def on_after_register(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        logger.info("Xxx %s has registered.", xxx.id)

    async def on_after_login(
        self,
        xxx: Xxx,
        request: Request | None = None,
        response: Response | None = None,
    ) -> None:
        logger.info("Xxx %s logged in.", xxx.id)
""",
        "function": "on_after_register_hook",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 15. on_after_forgot_password hook ────────────────────────────────────
    {
        "normalized_code": """\
import logging

from fastapi import Request

logger = logging.getLogger(__name__)


class XxxManager:
    async def on_after_forgot_password(
        self, xxx: Xxx, token: str, request: Request | None = None
    ) -> None:
        logger.info(
            "Xxx %s forgot password. Reset token: %s", xxx.id, token
        )
""",
        "function": "on_after_forgot_password_hook",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 16. on_after_request_verify hook ─────────────────────────────────────
    {
        "normalized_code": """\
import logging

from fastapi import Request

logger = logging.getLogger(__name__)


class XxxManager:
    async def on_after_request_verify(
        self, xxx: Xxx, token: str, request: Request | None = None
    ) -> None:
        logger.info(
            "Verification requested for %s. Token: %s", xxx.id, token
        )
""",
        "function": "on_after_request_verify_hook",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 17. on_after_verify + on_after_reset_password hooks ──────────────────
    {
        "normalized_code": """\
import logging

from fastapi import Request

logger = logging.getLogger(__name__)


class XxxManager:
    async def on_after_verify(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        logger.info("Xxx %s has been verified.", xxx.id)

    async def on_after_reset_password(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        logger.info("Xxx %s has reset their password.", xxx.id)

    async def on_after_update(
        self,
        xxx: Xxx,
        update_dict: dict,
        request: Request | None = None,
    ) -> None:
        logger.info("Xxx %s updated: %s", xxx.id, list(update_dict.keys()))

    async def on_before_delete(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        logger.info("Xxx %s about to be deleted.", xxx.id)
""",
        "function": "on_after_verify_reset_update_hooks",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # EMAIL FLOWS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 18. Forgot password flow — token generation ──────────────────────────
    {
        "normalized_code": """\
from fastapi import Request


RESET_PASSWORD_TOKEN_AUDIENCE = "auth:reset"


class XxxManager:
    async def forgot_password(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        if not xxx.is_active:
            raise XxxInactiveError()
        token_data = {
            "sub": str(xxx.id),
            "password_fgpt": self.password_helper.hash(xxx.hashed_password),
            "aud": RESET_PASSWORD_TOKEN_AUDIENCE,
        }
        token = generate_jwt(
            token_data,
            self.reset_password_token_secret,
            self.reset_password_token_lifetime_seconds,
        )
        await self.on_after_forgot_password(xxx, token, request)
""",
        "function": "forgot_password_token_generation",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 19. Reset password flow — token verification + update hash ───────────
    {
        "normalized_code": """\
import jwt
from fastapi import Request


RESET_PASSWORD_TOKEN_AUDIENCE = "auth:reset"


class XxxManager:
    async def reset_password(
        self, token: str, password: str, request: Request | None = None
    ) -> Xxx:
        try:
            data = decode_jwt(
                token,
                self.reset_password_token_secret,
                [RESET_PASSWORD_TOKEN_AUDIENCE],
            )
        except jwt.PyJWTError:
            raise InvalidResetPasswordTokenError()
        try:
            xxx_id = data["sub"]
            password_fingerprint = data["password_fgpt"]
        except KeyError:
            raise InvalidResetPasswordTokenError()
        xxx = await self.xxx_db.get(xxx_id)
        valid, _ = self.password_helper.verify_and_update(
            xxx.hashed_password, password_fingerprint
        )
        if not valid:
            raise InvalidResetPasswordTokenError()
        if not xxx.is_active:
            raise XxxInactiveError()
        updated = await self._update(xxx, {"password": password})
        await self.on_after_reset_password(xxx, request)
        return updated
""",
        "function": "reset_password_token_verify_update",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 20. Request verify flow — token generation + send ────────────────────
    {
        "normalized_code": """\
from fastapi import Request


VERIFY_TOKEN_AUDIENCE = "auth:verify"


class XxxManager:
    async def request_verify(
        self, xxx: Xxx, request: Request | None = None
    ) -> None:
        if not xxx.is_active:
            raise XxxInactiveError()
        if xxx.is_verified:
            raise XxxAlreadyVerifiedError()
        token_data = {
            "sub": str(xxx.id),
            "email": xxx.email,
            "aud": VERIFY_TOKEN_AUDIENCE,
        }
        token = generate_jwt(
            token_data,
            self.verification_token_secret,
            self.verification_token_lifetime_seconds,
        )
        await self.on_after_request_verify(xxx, token, request)
""",
        "function": "request_verify_token_generation",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ── 21. Verify flow — token verification + is_verified=True ──────────────
    {
        "normalized_code": """\
import jwt
from fastapi import Request


VERIFY_TOKEN_AUDIENCE = "auth:verify"


class XxxManager:
    async def verify(
        self, token: str, request: Request | None = None
    ) -> Xxx:
        try:
            data = decode_jwt(
                token,
                self.verification_token_secret,
                [VERIFY_TOKEN_AUDIENCE],
            )
        except jwt.PyJWTError:
            raise InvalidVerifyTokenError()
        try:
            xxx_id = data["sub"]
            email = data["email"]
        except KeyError:
            raise InvalidVerifyTokenError()
        xxx = await self.xxx_db.get_by_email(email)
        if xxx is None or str(xxx.id) != xxx_id:
            raise InvalidVerifyTokenError()
        if xxx.is_verified:
            raise XxxAlreadyVerifiedError()
        verified_xxx = await self._update(xxx, {"is_verified": True})
        await self.on_after_verify(verified_xxx, request)
        return verified_xxx
""",
        "function": "verify_token_check_set_verified",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/manager.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # OAUTH2
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 22. OAuth2 callback — create or associate account ────────────────────
    {
        "normalized_code": """\
from fastapi import Request


class XxxManager:
    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> Xxx:
        oauth_dict = {
            "oauth_name": oauth_name,
            "access_token": access_token,
            "account_id": account_id,
            "account_email": account_email,
            "expires_at": expires_at,
            "refresh_token": refresh_token,
        }
        try:
            xxx = await self.xxx_db.get_by_oauth(oauth_name, account_id)
            for existing in xxx.oauth_accounts:
                if (
                    existing.account_id == account_id
                    and existing.oauth_name == oauth_name
                ):
                    xxx = await self.xxx_db.update_oauth(
                        xxx, existing, oauth_dict
                    )
            return xxx
        except XxxNotExistsError:
            pass
        try:
            xxx = await self.xxx_db.get_by_email(account_email)
            if not associate_by_email:
                raise XxxAlreadyExistsError()
            return await self.xxx_db.add_oauth(xxx, oauth_dict)
        except XxxNotExistsError:
            pass
        generated_pw = self.password_helper.generate()
        xxx_dict = {
            "email": account_email,
            "hashed_password": self.password_helper.hash(generated_pw),
            "is_verified": is_verified_by_default,
        }
        xxx = await self.xxx_db.create(xxx_dict)
        xxx = await self.xxx_db.add_oauth(xxx, oauth_dict)
        await self.on_after_register(xxx, request)
        return xxx
""",
        "function": "oauth_callback_create_or_associate",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "app/manager.py",
    },

    # ── 23. Google OAuth2 provider setup ─────────────────────────────────────
    {
        "normalized_code": """\
import os

from httpx_oauth.clients.google import GoogleOAuth2

google_oauth_client = GoogleOAuth2(
    client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
)
""",
        "function": "google_oauth2_provider_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/oauth_providers.py",
    },

    # ── 24. GitHub OAuth2 provider setup ─────────────────────────────────────
    {
        "normalized_code": """\
import os

from httpx_oauth.clients.github import GitHubOAuth2

github_oauth_client = GitHubOAuth2(
    client_id=os.environ["GITHUB_OAUTH_CLIENT_ID"],
    client_secret=os.environ["GITHUB_OAUTH_CLIENT_SECRET"],
)
""",
        "function": "github_oauth2_provider_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/oauth_providers.py",
    },

    # ── 25. OAuth2 authorize route — get authorization URL + CSRF ────────────
    {
        "normalized_code": """\
import secrets

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict

STATE_TOKEN_AUDIENCE = "auth:oauth-state"
CSRF_TOKEN_KEY = "csrftoken"


class OAuth2AuthorizeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    authorization_url: str


router = APIRouter(prefix="/auth/google", tags=["oauth"])


@router.get("/authorize", response_model=OAuth2AuthorizeResponse)
async def authorize(
    request: Request, response: Response, scopes: list[str] = Query(None)
) -> OAuth2AuthorizeResponse:
    callback_url = str(request.url_for("oauth_callback"))
    csrf_token = secrets.token_urlsafe(32)
    state_data: dict[str, str] = {CSRF_TOKEN_KEY: csrf_token}
    state = generate_jwt(
        {**state_data, "aud": STATE_TOKEN_AUDIENCE},
        state_secret,
        lifetime_seconds=3600,
    )
    authorization_url = await oauth_client.get_authorization_url(
        callback_url, state, scopes
    )
    response.set_cookie(
        "oauth_csrf", csrf_token, max_age=3600,
        secure=True, httponly=True, samesite="lax",
    )
    return OAuth2AuthorizeResponse(authorization_url=authorization_url)
""",
        "function": "oauth2_authorize_route_csrf",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/oauth.py",
    },

    # ── 26. OAuth2 callback route — CSRF verify + create/login ───────────────
    {
        "normalized_code": """\
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status

STATE_TOKEN_AUDIENCE = "auth:oauth-state"
CSRF_TOKEN_KEY = "csrftoken"

router = APIRouter(prefix="/auth/google", tags=["oauth"])


@router.get("/callback")
async def oauth_callback(
    request: Request,
    access_token_state: tuple = Depends(oauth2_authorize_callback),
) -> Response:
    token, state = access_token_state
    try:
        state_data = decode_jwt(state, state_secret, [STATE_TOKEN_AUDIENCE])
    except jwt.DecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    cookie_csrf = request.cookies.get("oauth_csrf")
    state_csrf = state_data.get(CSRF_TOKEN_KEY)
    if (
        not cookie_csrf
        or not state_csrf
        or not secrets.compare_digest(cookie_csrf, state_csrf)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    account_id, account_email = await oauth_client.get_id_email(
        token["access_token"]
    )
    if account_email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    xxx = await xxx_manager.oauth_callback(
        oauth_client.name,
        token["access_token"],
        account_id,
        account_email,
        token.get("expires_at"),
        token.get("refresh_token"),
        request,
        associate_by_email=False,
    )
    if not xxx.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    response = await auth_backend.login(strategy, xxx.id)
    return response
""",
        "function": "oauth2_callback_route_csrf_verify",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/oauth.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 27. Login route — OAuth2PasswordRequestForm → token ──────────────────
    {
        "normalized_code": """\
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth/jwt", tags=["auth"])


@router.post("/login")
async def login(
    request: Request,
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Response:
    xxx = await xxx_manager.authenticate(
        credentials.username, credentials.password
    )
    if xxx is None or not xxx.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )
    if requires_verification and not xxx.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_NOT_VERIFIED",
        )
    response = await auth_backend.login(strategy, str(xxx.id))
    await xxx_manager.on_after_login(xxx, request, response)
    return response
""",
        "function": "route_login_oauth2_form",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/auth.py",
    },

    # ── 28. Logout route ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/auth/jwt", tags=["auth"])


@router.post("/logout")
async def logout(
    xxx_token: tuple = Depends(get_current_xxx_token),
) -> Response:
    xxx, token = xxx_token
    return await auth_backend.logout(strategy, token)
""",
        "function": "route_logout",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/auth.py",
    },

    # ── 29. Register route ───────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    xxx_create: XxxCreate,
) -> XxxRead:
    try:
        created_xxx = await xxx_manager.create(
            xxx_create, safe=True, request=request
        )
    except XxxAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_ALREADY_EXISTS",
        )
    except InvalidPasswordError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "REGISTER_INVALID_PASSWORD", "reason": e.reason},
        )
    return XxxRead.model_validate(created_xxx)
""",
        "function": "route_register",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/register.py",
    },

    # ── 30. Forgot password route ────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Body, Depends, Request, status
from pydantic import EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request: Request,
    email: EmailStr = Body(..., embed=True),
) -> None:
    try:
        xxx = await xxx_manager.get_by_email(email)
    except XxxNotExistsError:
        return None
    try:
        await xxx_manager.forgot_password(xxx, request)
    except XxxInactiveError:
        pass
    return None
""",
        "function": "route_forgot_password",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/reset.py",
    },

    # ── 31. Reset password route ─────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Body, HTTPException, Request, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/reset-password")
async def reset_password(
    request: Request,
    token: str = Body(...),
    password: str = Body(...),
) -> None:
    try:
        await xxx_manager.reset_password(token, password, request)
    except (InvalidResetPasswordTokenError, XxxNotExistsError, XxxInactiveError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RESET_PASSWORD_BAD_TOKEN",
        )
    except InvalidPasswordError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "RESET_PASSWORD_INVALID", "reason": e.reason},
        )
""",
        "function": "route_reset_password",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/reset.py",
    },

    # ── 32. Request verify token route ───────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Body, Request, status
from pydantic import EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/request-verify-token", status_code=status.HTTP_202_ACCEPTED
)
async def request_verify_token(
    request: Request,
    email: EmailStr = Body(..., embed=True),
) -> None:
    try:
        xxx = await xxx_manager.get_by_email(email)
        await xxx_manager.request_verify(xxx, request)
    except (XxxNotExistsError, XxxInactiveError, XxxAlreadyVerifiedError):
        pass
    return None
""",
        "function": "route_request_verify_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/verify.py",
    },

    # ── 33. Verify route ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Body, HTTPException, Request, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify")
async def verify(
    request: Request,
    token: str = Body(..., embed=True),
) -> XxxRead:
    try:
        xxx = await xxx_manager.verify(token, request)
        return XxxRead.model_validate(xxx)
    except (InvalidVerifyTokenError, XxxNotExistsError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VERIFY_BAD_TOKEN",
        )
    except XxxAlreadyVerifiedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VERIFY_ALREADY_VERIFIED",
        )
""",
        "function": "route_verify_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/routes/verify.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DEPENDENCIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 34. get_xxx_manager dependency ───────────────────────────────────────
    {
        "normalized_code": """\
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


async def get_xxx_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator:
    yield XxxDatabase(session, Xxx)


async def get_xxx_manager(
    xxx_db: XxxDatabase = Depends(get_xxx_db),
) -> AsyncGenerator:
    yield XxxManager(xxx_db)
""",
        "function": "get_xxx_manager_dependency",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/deps.py",
    },

    # ── 35. current_active_xxx / current_superadmin / current_verified ───────
    {
        "normalized_code": """\
from typing import Annotated

from fastapi import Depends, HTTPException, status


async def get_current_active_xxx(
    xxx: Xxx = Depends(get_current_xxx),
) -> Xxx:
    if not xxx.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive"
        )
    return xxx


async def get_current_verified_xxx(
    xxx: Xxx = Depends(get_current_active_xxx),
) -> Xxx:
    if not xxx.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not verified"
        )
    return xxx


async def get_current_superadmin(
    xxx: Xxx = Depends(get_current_active_xxx),
) -> Xxx:
    if not xxx.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges"
        )
    return xxx


CurrentActiveXxx = Annotated[Xxx, Depends(get_current_active_xxx)]
CurrentVerifiedXxx = Annotated[Xxx, Depends(get_current_verified_xxx)]
CurrentSuperadmin = Annotated[Xxx, Depends(get_current_superadmin)]
""",
        "function": "current_active_verified_superadmin_deps",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/deps.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 36. Auth backend wiring (JWT bearer) ─────────────────────────────────
    {
        "normalized_code": """\
import os


SECRET = os.environ["SECRET_KEY"]

bearer_transport = BearerTransport(token_url="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
""",
        "function": "auth_backend_jwt_bearer_wiring",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/auth_config.py",
    },

    # ── 37. Auth backend wiring (cookie) ─────────────────────────────────────
    {
        "normalized_code": """\
import os


SECRET = os.environ["SECRET_KEY"]

cookie_transport = CookieTransport(
    cookie_name="auth_token",
    cookie_max_age=3600,
    cookie_secure=True,
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend_cookie = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
""",
        "function": "auth_backend_cookie_wiring",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/auth_config.py",
    },

    # ── 38. App wiring — all auth routers ────────────────────────────────────
    {
        "normalized_code": """\
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.db import create_db_and_tables


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(title="Xxx API", version="1.0.0", lifespan=lifespan)

app.include_router(auth_router, prefix="/auth/jwt")
app.include_router(register_router, prefix="/auth")
app.include_router(reset_password_router, prefix="/auth")
app.include_router(verify_router, prefix="/auth")
app.include_router(xxxs_router, prefix="/xxxs")
app.include_router(oauth_router, prefix="/auth/google")
""",
        "function": "app_wiring_all_auth_routers",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/main.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # PASSWORD HELPER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 39. Password helper — argon2 + bcrypt ────────────────────────────────
    {
        "normalized_code": """\
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher


class PasswordHelper:
    def __init__(self) -> None:
        self.password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))

    def verify_and_update(
        self, plain_password: str, hashed_password: str
    ) -> tuple[bool, str | None]:
        return self.password_hash.verify_and_update(
            plain_password, hashed_password
        )

    def hash(self, password: str) -> str:
        return self.password_hash.hash(password)

    def generate(self) -> str:
        return secrets.token_urlsafe()
""",
        "function": "password_helper_argon2_bcrypt",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "app/password.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ASYNC DB SETUP
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 40. Async session + DB init + get_xxx_db ─────────────────────────────
    {
        "normalized_code": """\
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./app.db"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
""",
        "function": "async_session_db_init",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "app/db.py",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 41. Test register ────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_register_valid(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "strongpass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert "id" in data
    assert data["is_active"] is True
    assert data["is_verified"] is False


def test_register_existing_email(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "strongpass123"},
    )
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "strongpass123"},
    )
    assert response.status_code == 400
""",
        "function": "test_register_valid_and_duplicate",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_register.py",
    },

    # ── 42. Test login ───────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_login_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "test@example.com", "password": "correctpass"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "test@example.com", "password": "wrongpass"},
    )
    assert response.status_code == 400


def test_login_inactive(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "inactive@example.com", "password": "correctpass"},
    )
    assert response.status_code == 400
""",
        "function": "test_login_success_wrong_inactive",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_auth.py",
    },

    # ── 43. Test forgot + reset password ─────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_forgot_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 202


def test_forgot_password_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert response.status_code == 202


def test_reset_password_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid", "password": "newpass123"},
    )
    assert response.status_code == 400
""",
        "function": "test_forgot_reset_password_flow",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_reset.py",
    },

    # ── 44. Test verify flow ─────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_request_verify_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/request-verify-token",
        json={"email": "unverified@example.com"},
    )
    assert response.status_code == 202


def test_verify_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/verify",
        json={"token": "invalid"},
    )
    assert response.status_code == 400
""",
        "function": "test_verify_token_flow",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_verify.py",
    },

    # ── 45. Test get me / patch me ───────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_get_me(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/xxxs/me", headers=authenticated_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["is_active"] is True


def test_patch_me(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    response = client.patch(
        "/api/v1/xxxs/me",
        headers=authenticated_headers,
        json={"email": "updated@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "updated@example.com"
""",
        "function": "test_get_patch_me",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxxs.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "OAuth2 Google provider get authorization URL",
    "email verification token generate and send",
    "forgot password reset token flow",
    "JWT bearer token strategy create and decode",
    "user manager hook on after register",
    "SQLAlchemy user model with UUID primary key and oauth accounts",
    "cookie authentication strategy FastAPI",
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
        if (i + 1) % 10 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points prepared")

    print(f"  Upserting {len(points)} points into '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print("  Upsert done.")
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

    # ── Step 1: Prerequisites ────────────────────────────────────────────
    print("── Step 1: Prerequisites")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERROR: collection '{COLLECTION}' not found.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}': {count_initial} points (initial)")

    # ── Step 2: Clone ────────────────────────────────────────────────────
    print("\n── Step 2: Clone")
    clone_repo()

    # ── Step 3-4: Extraction + Normalization ─────────────────────────────
    print(f"\n── Step 3-4: {len(PATTERNS)} patterns extracted and normalized")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads built.")

    # ── Step 5: Indexation ───────────────────────────────────────────────
    print("\n── Step 5: Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []
    verdict = "FAIL"

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count after indexation: {count_after}")

        # ── Step 6: Audit ────────────────────────────────────────────────
        print("\n── Step 6: Audit")
        print("\n  6a. Semantic queries:")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        # 6b. Discrimination check
        print("\n  6b. Discrimination check:")
        oauth_queries = [r for r in query_results if "OAuth" in r["query"]]
        for r in oauth_queries:
            ft = r.get("file_role", "")
            if ft in ("crud",):
                print(f"    WARN: OAuth query returned CRUD pattern: {r['function']}")

        print("\n  6c. Normalization audit:")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    No violations detected ✓")

        scores_valid = all(0.0 <= r["score"] <= 1.0 for r in query_results)
        no_empty = all(r["function"] != "NO_RESULT" for r in query_results)
        verdict = "PASS" if (scores_valid and no_empty and not violations) else "FAIL"

    finally:
        # ── Step 7: Cleanup/conservation ─────────────────────────────────
        print(f"\n── Step 7: {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points deleted. Count final: {count_final}")
            if count_final == count_initial:
                print(f"  Count back to {count_initial} ✓")
            else:
                print(f"  WARN: final ({count_final}) != initial ({count_initial})")
            print("  DRY_RUN — data deleted")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")
            print(f"  To remove: filter _tag='{TAG}' via FilterSelector")

    # ── Step 8: Report ───────────────────────────────────────────────────
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
    print(f"  Verdict: {'✅ PASS' if verdict == 'PASS' else '❌ FAIL'}")
    if verdict == "FAIL" and violations:
        print(f"  {len(violations)} blocking violations")


if __name__ == "__main__":
    main()
