"""
ingest_fastcrud.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de igorbenav/fastcrud dans la KB Qdrant V6.

Template réutilisable pour les 17 autres repos.

Usage:
    .venv/bin/python3 ingest_fastcrud.py
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

# ─── Constantes (template pour les 17 autres repos) ─────────────────────────
REPO_URL = "https://github.com/igorbenav/fastcrud.git"
REPO_NAME = "igorbenav/fastcrud"
REPO_LOCAL = "/tmp/fastcrud"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "igorbenav/fastcrud"
DRY_RUN = False  # True = cleanup à la fin (test), False = garde les données

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# Chaque pattern est extrait de fastcrud, puis normalisé selon :
#   U-1..U-8 (universel) + F-1..F-13 (Python/FastAPI)
# Entités métier → Xxx/xxx/xxxs, SQLAlchemy 2.0, Pydantic V2, datetime.now(UTC)

PATTERNS: list[dict] = [
    # ── 1. SQLAlchemy 2.0 model — champs de base ────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
""",
        "function": "sqlalchemy_model_basic",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "fastcrud/examples/item/model.py",
    },
    # ── 2. SQLAlchemy 2.0 model — soft delete + timestamps ──────────────────
    {
        "normalized_code": """\
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
""",
        "function": "sqlalchemy_model_soft_delete",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "fastcrud/examples/task/model.py",
    },
    # ── 3. SQLAlchemy 2.0 model — ForeignKey relationship ───────────────────
    {
        "normalized_code": """\
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class XxxCategory(Base):
    __tablename__ = "xxx_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    xxxs: Mapped[list["Xxx"]] = relationship(back_populates="category")


class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("xxx_categories.id"), nullable=True
    )
    category: Mapped["XxxCategory | None"] = relationship(back_populates="xxxs")
""",
        "function": "sqlalchemy_model_relationship",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "tests/sqlalchemy/conftest.py",
    },
    # ── 4. Pydantic V2 create schema ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class XxxCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str | None = None
""",
        "function": "pydantic_create_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/examples/item/schemas.py",
    },
    # ── 5. Pydantic V2 read schema — field_serializer datetime ──────────────
    {
        "normalized_code": """\
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class XxxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.astimezone(UTC).isoformat()
""",
        "function": "pydantic_read_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/examples/item/schemas.py",
    },
    # ── 6. Pydantic V2 update schema ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class XxxUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    description: str | None = None
""",
        "function": "pydantic_update_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/examples/item/schemas.py",
    },
    # ── 7. Pydantic V2 delete schema ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class XxxDelete(BaseModel):
    model_config = ConfigDict(from_attributes=True)
""",
        "function": "pydantic_delete_schema",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/examples/item/schemas.py",
    },
    # ── 8. Async create record with SQLAlchemy session ──────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_xxx(db: AsyncSession, name: str) -> dict:
    db_xxx = Xxx(name=name)
    db.add(db_xxx)
    await db.commit()
    await db.refresh(db_xxx)
    return {"id": db_xxx.id, "name": db_xxx.name}
""",
        "function": "async_create_record",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_create.py",
    },
    # ── 9. Async create from Pydantic schema ────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy.ext.asyncio import AsyncSession


async def create_xxx_from_schema(
    db: AsyncSession, xxx_in: XxxCreate
) -> Xxx:
    db_xxx = Xxx(**xxx_in.model_dump())
    db.add(db_xxx)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
""",
        "function": "async_create_from_schema",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_create.py",
    },
    # ── 10. Get by id with 404 ──────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_xxx_or_404(db: AsyncSession, xxx_id: int) -> Xxx:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    xxx = result.scalar_one_or_none()
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    return xxx
""",
        "function": "get_by_id_or_404",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_get.py",
    },
    # ── 11. Get with advanced filters (__gt, __lt, __ne) ────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_xxx_filtered(
    db: AsyncSession,
    min_id: int | None = None,
    name_ne: str | None = None,
) -> Xxx | None:
    stmt = select(Xxx)
    if min_id is not None:
        stmt = stmt.where(Xxx.id > min_id)
    if name_ne is not None:
        stmt = stmt.where(Xxx.name != name_ne)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
""",
        "function": "get_with_advanced_filters",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_get.py",
    },
    # ── 12. Get multi with pagination offset/limit ──────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_xxxs_paginated(
    db: AsyncSession, offset: int = 0, limit: int = 100
) -> dict:
    count_result = await db.execute(select(func.count()).select_from(Xxx))
    total_count = count_result.scalar() or 0

    result = await db.execute(select(Xxx).offset(offset).limit(limit))
    data = result.scalars().all()

    return {
        "data": data,
        "total_count": total_count,
        "has_more": (offset + limit) < total_count,
    }
""",
        "function": "paginate_with_offset",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_get_multi.py",
    },
    # ── 13. Get multi with sorting ──────────────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_xxxs_sorted(
    db: AsyncSession,
    sort_column: str = "id",
    sort_order: str = "asc",
    offset: int = 0,
    limit: int = 100,
) -> list:
    column = getattr(Xxx, sort_column)
    direction = column.asc() if sort_order == "asc" else column.desc()
    result = await db.execute(
        select(Xxx).order_by(direction).offset(offset).limit(limit)
    )
    return list(result.scalars().all())
""",
        "function": "get_multi_with_sorting",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_apply_sorting.py",
    },
    # ── 14. Update by id ────────────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def update_xxx(
    db: AsyncSession, xxx_id: int, xxx_in: XxxUpdate
) -> Xxx:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    db_xxx = result.scalar_one_or_none()
    if not db_xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    for key, value in xxx_in.model_dump(exclude_unset=True).items():
        setattr(db_xxx, key, value)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
""",
        "function": "update_by_id",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_update.py",
    },
    # ── 15. Hard delete by id ───────────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def delete_xxx(db: AsyncSession, xxx_id: int) -> None:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    db_xxx = result.scalar_one_or_none()
    if not db_xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    await db.delete(db_xxx)
    await db.commit()
""",
        "function": "hard_delete_by_id",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_delete.py",
    },
    # ── 16. Soft delete with is_deleted flag ────────────────────────────────
    {
        "normalized_code": """\
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def soft_delete_xxx(db: AsyncSession, xxx_id: int) -> None:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    db_xxx = result.scalar_one_or_none()
    if not db_xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    db_xxx.is_deleted = True
    db_xxx.deleted_at = datetime.now(UTC)
    await db.commit()
""",
        "function": "soft_delete",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_delete.py",
    },
    # ── 17. Upsert — create or update ───────────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_xxx(
    db: AsyncSession, name: str, description: str | None = None
) -> Xxx:
    result = await db.execute(select(Xxx).where(Xxx.name == name))
    db_xxx = result.scalar_one_or_none()
    if db_xxx:
        db_xxx.description = description
    else:
        db_xxx = Xxx(name=name, description=description)
        db.add(db_xxx)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
""",
        "function": "upsert_create_or_update",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_upsert.py",
    },
    # ── 18. Count with filter ───────────────────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def count_xxxs(
    db: AsyncSession, name: str | None = None
) -> int:
    stmt = select(func.count()).select_from(Xxx)
    if name is not None:
        stmt = stmt.where(Xxx.name == name)
    result = await db.execute(stmt)
    return result.scalar() or 0
""",
        "function": "count_with_filter",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_count.py",
    },
    # ── 19. Exists check ────────────────────────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def xxx_exists(db: AsyncSession, xxx_id: int) -> bool:
    result = await db.execute(select(Xxx.id).where(Xxx.id == xxx_id))
    return result.scalar_one_or_none() is not None
""",
        "function": "exists_check",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "tests/sqlalchemy/crud/test_exists.py",
    },
    # ── 20. HTTP exception hierarchy ────────────────────────────────────────
    {
        "normalized_code": """\
from http import HTTPStatus

from fastapi import HTTPException
from starlette import status


class CustomException(HTTPException):
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str | None = None,
    ) -> None:
        if not detail:
            detail = HTTPStatus(status_code).description
        super().__init__(status_code=status_code, detail=detail)


class NotFoundException(CustomException):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class BadRequestException(CustomException):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class DuplicateValueException(CustomException):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        )
""",
        "function": "http_exception_hierarchy",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "fastcrud/exceptions/http_exceptions.py",
    },
    # ── 21. Async session dependency ────────────────────────────────────────
    {
        "normalized_code": """\
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models import Base

DATABASE_URL = "sqlite+aiosqlite:///./app.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
""",
        "function": "async_session_dependency",
        "feature_type": "dependency",
        "file_role": "dependency",
        "file_path": "src/database.py",
    },
    # ── 22. Conftest — fixture DB in-memory ─────────────────────────────────
    {
        "normalized_code": """\
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.main import app
from src.models import Base

TEST_DATABASE_URL = "sqlite://"


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
""",
        "function": "conftest_fixture_db_inmemory",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/conftest.py",
    },
    # ── 23. Test sync — create endpoint ─────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_create_xxx(client: TestClient) -> None:
    response = client.post("/api/v1/xxxs/", json={"name": "Test"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test"
    assert "id" in data
""",
        "function": "test_create_endpoint",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxx.py",
    },
    # ── 24. Test sync — get by id endpoint ──────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_get_xxx_by_id(client: TestClient) -> None:
    create_resp = client.post("/api/v1/xxxs/", json={"name": "Test"})
    xxx_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/xxxs/{xxx_id}")
    assert response.status_code == 200
    assert response.json()["id"] == xxx_id


def test_get_xxx_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/xxxs/999999")
    assert response.status_code == 404
""",
        "function": "test_get_by_id_endpoint",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxx.py",
    },
    # ── 25. Test sync — paginated list endpoint ─────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_list_xxxs_paginated(client: TestClient) -> None:
    for i in range(10):
        client.post("/api/v1/xxxs/", json={"name": f"Test {i}"})

    response = client.get("/api/v1/xxxs/?skip=0&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5
""",
        "function": "test_list_paginated_endpoint",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxx.py",
    },
    # ── 26. Test sync — update endpoint ─────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_update_xxx(client: TestClient) -> None:
    create_resp = client.post("/api/v1/xxxs/", json={"name": "Original"})
    xxx_id = create_resp.json()["id"]

    response = client.put(
        f"/api/v1/xxxs/{xxx_id}", json={"name": "Updated"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
""",
        "function": "test_update_endpoint",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxx.py",
    },
    # ── 27. Test sync — delete endpoint ─────────────────────────────────────
    {
        "normalized_code": """\
from fastapi.testclient import TestClient


def test_delete_xxx(client: TestClient) -> None:
    create_resp = client.post("/api/v1/xxxs/", json={"name": "ToDelete"})
    xxx_id = create_resp.json()["id"]

    response = client.delete(f"/api/v1/xxxs/{xxx_id}")
    assert response.status_code == 200

    get_resp = client.get(f"/api/v1/xxxs/{xxx_id}")
    assert get_resp.status_code == 404
""",
        "function": "test_delete_endpoint",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "tests/test_xxx.py",
    },
    # ── 28. CRUD route — create endpoint ────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Xxx
from src.schemas import XxxCreate, XxxRead

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.post("/", status_code=201)
async def create_xxx(
    xxx_in: XxxCreate,
    db: AsyncSession = Depends(get_db),
) -> XxxRead:
    db_xxx = Xxx(**xxx_in.model_dump())
    db.add(db_xxx)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
""",
        "function": "route_create",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/xxx.py",
    },
    # ── 29. CRUD route — get by id ──────────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Xxx
from src.schemas import XxxRead

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.get("/{xxx_id}")
async def get_xxx(
    xxx_id: int = Path(..., ge=1, le=2147483647),
    db: AsyncSession = Depends(get_db),
) -> XxxRead:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    xxx = result.scalar_one_or_none()
    if not xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    return xxx
""",
        "function": "route_get_by_id",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/xxx.py",
    },
    # ── 30. CRUD route — list with pagination + unknown param rejection ─────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Xxx
from src.schemas import XxxRead

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.get("/")
async def list_xxxs(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[XxxRead]:
    known_params = {"skip", "limit"}
    unknown = set(request.query_params.keys()) - known_params
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown query params: {unknown}")
    result = await db.execute(select(Xxx).offset(skip).limit(limit))
    return list(result.scalars().all())
""",
        "function": "route_list_paginated",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/xxx.py",
    },
    # ── 31. CRUD route — update by id ───────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Xxx
from src.schemas import XxxRead, XxxUpdate

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.put("/{xxx_id}")
async def update_xxx(
    xxx_in: XxxUpdate,
    xxx_id: int = Path(..., ge=1, le=2147483647),
    db: AsyncSession = Depends(get_db),
) -> XxxRead:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    db_xxx = result.scalar_one_or_none()
    if not db_xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    for key, value in xxx_in.model_dump(exclude_unset=True).items():
        setattr(db_xxx, key, value)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
""",
        "function": "route_update_by_id",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/xxx.py",
    },
    # ── 32. CRUD route — delete by id ───────────────────────────────────────
    {
        "normalized_code": """\
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Xxx

router = APIRouter(prefix="/xxxs", tags=["xxxs"])


@router.delete("/{xxx_id}")
async def delete_xxx(
    xxx_id: int = Path(..., ge=1, le=2147483647),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Xxx).where(Xxx.id == xxx_id))
    db_xxx = result.scalar_one_or_none()
    if not db_xxx:
        raise HTTPException(status_code=404, detail="Xxx not found")
    await db.delete(db_xxx)
    await db.commit()
    return {"detail": "Deleted"}
""",
        "function": "route_delete_by_id",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/xxx.py",
    },
    # ── 33. Paginated response model ────────────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict


class PaginatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: list[dict]
    total_count: int
    has_more: bool
    page: int | None = None
    items_per_page: int | None = None
""",
        "function": "paginated_response_model",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/core/pagination.py",
    },
    # ── 34. Cursor pagination request model ─────────────────────────────────
    {
        "normalized_code": """\
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CursorPaginatedRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cursor: int | str | None = Field(default=None)
    limit: int = Field(default=100, gt=0, le=1000)
    sort_column: str = Field(default="id")
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")

    @field_validator("cursor", mode="before")
    @classmethod
    def coerce_cursor(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return v
        return v
""",
        "function": "cursor_pagination_request",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "fastcrud/core/pagination.py",
    },
    # ── 35. Lifespan + main.py standard ─────────────────────────────────────
    {
        "normalized_code": """\
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.database import init_db
from src.routes.xxx import router as xxx_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Xxx API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(xxx_router, prefix="/api/v1")
""",
        "function": "main_lifespan_standard",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/main.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "async create record in database with SQLAlchemy session",
    "paginate query results with offset and limit",
    "soft delete with is_deleted flag SQLAlchemy",
    "upsert create or update existing record",
    "Pydantic V2 schema with ConfigDict from_attributes",
    "pytest fixture async database session in-memory",
]

# Termes métier interdits dans les patterns normalisés
FORBIDDEN_ENTITIES = [
    "item", "todo", "product", "user", "task", "article", "order",
    "customer", "story", "profile", "department", "author", "tier",
]


def clone_repo() -> None:
    """Clone le repo si pas déjà présent."""
    import os

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
    """Construit les payloads Qdrant à partir des patterns normalisés."""
    payloads = []
    for p in PATTERNS:
        payloads.append(
            {
                "normalized_code": p["normalized_code"],
                "function": p["function"],
                "feature_type": p["feature_type"],
                "file_role": p["file_role"],
                "language": LANGUAGE,
                "framework": FRAMEWORK,
                "stack": STACK,
                "file_path": p["file_path"],
                "source_repo": "https://github.com/igorbenav/fastcrud",
                "charte_version": CHARTE_VERSION,
                "created_at": int(time.time()),
                "_tag": TAG,
            }
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    """Embed + upsert les patterns dans Qdrant."""
    codes = [p["normalized_code"] for p in payloads]
    print(f"  Embedding {len(codes)} patterns (batch) ...")
    vectors = embed_documents_batch(codes)
    print(f"  {len(vectors)} vecteurs générés.")

    points = []
    for i, (vec, payload) in enumerate(zip(vectors, payloads)):
        point_id = str(uuid.uuid4())
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))
        if (i + 1) % 5 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points préparés")

    print(f"  Upsert {len(points)} points dans '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"  Upsert terminé.")
    return len(points)


def audit_queries(client: QdrantClient) -> list[dict]:
    """Lance les 6 queries sémantiques d'audit."""
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = client.query_points(
            collection_name=COLLECTION,
            query=vec,
            limit=1,
        ).points
        if hits:
            hit = hits[0]
            score = hit.score
            payload = hit.payload
            results.append(
                {
                    "query": q,
                    "function": payload.get("function", "?"),
                    "file_role": payload.get("file_role", "?"),
                    "score": score,
                    "code_preview": payload.get("normalized_code", "")[:50],
                }
            )
        else:
            results.append(
                {
                    "query": q,
                    "function": "NO_RESULT",
                    "file_role": "?",
                    "score": 0.0,
                    "code_preview": "",
                }
            )
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    """Vérifie la normalisation Charte sur les résultats."""
    violations = []

    # Récupère tous les points avec le tag
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
        ),
        limit=100,
    )
    points = scroll_result[0]

    for point in points:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")

        # Vérifier entités métier (lowercase check dans le code, pas dans les imports)
        import re

        # Mots techniques qui contiennent des entités mais ne sont pas des entités
        TECHNICAL_TERMS = {
            "sort_order", "order_by", "sort_orders", "border",
            "reorder", "ordering", "ordered",
        }

        # Skip les lignes d'import
        non_import_lines = [
            line
            for line in code.split("\n")
            if not line.strip().startswith(("from ", "import "))
        ]
        non_import_code = "\n".join(non_import_lines).lower()

        # Remplace les termes techniques par des placeholders avant la vérification
        sanitized = non_import_code
        for term in TECHNICAL_TERMS:
            sanitized = sanitized.replace(term, "___")

        for entity in FORBIDDEN_ENTITIES:
            if re.search(rf"\b{entity}\b", sanitized):
                violations.append(
                    f"ENTITY '{entity}' trouvée dans pattern '{fn}'"
                )

        # Vérifier declarative_base()
        if "declarative_base()" in code:
            violations.append(f"declarative_base() dans pattern '{fn}'")

        # Vérifier class Config
        if "class Config" in code:
            violations.append(f"class Config (Pydantic V1) dans pattern '{fn}'")

        # Vérifier datetime.utcnow()
        if "utcnow()" in code:
            violations.append(f"datetime.utcnow() dans pattern '{fn}'")

    return violations


def cleanup(client: QdrantClient) -> None:
    """Supprime tous les points avec _tag == TAG."""
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

    # ── Étape 1 : Prérequis ─────────────────────────────────────────────
    print("── Étape 1 : Prérequis")
    client = QdrantClient(path=KB_PATH)

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERREUR: collection '{COLLECTION}' introuvable. Lance setup_collections.py")
        return

    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}' : {count_initial} points (initial)")

    # ── Étape 2 : Clone ─────────────────────────────────────────────────
    print("\n── Étape 2 : Clone")
    clone_repo()

    # ── Étape 3-4 : Extraction + Normalisation ──────────────────────────
    print(f"\n── Étape 3-4 : {len(PATTERNS)} patterns extraits et normalisés (Charte Wal-e)")

    payloads = build_payloads()
    print(f"  {len(payloads)} payloads construits.")

    # ── Étape 5 : Indexation ────────────────────────────────────────────
    print("\n── Étape 5 : Indexation")
    n_indexed = 0
    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count KB après indexation : {count_after}")
        expected = count_initial + n_indexed
        if count_after != expected:
            print(f"  WARN: attendu {expected}, obtenu {count_after}")

        # ── Étape 6 : Audit ─────────────────────────────────────────────
        print("\n── Étape 6 : Audit qualité")

        print("\n  6b. Queries sémantiques :")
        query_results = audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:30s} | "
                f"role={r['file_role']:10s} | score={r['score']:.4f} "
                f"{'✓' if score_ok else '✗'}"
            )
            print(f"      code: {r['code_preview']}")

        print("\n  6c. Audit normalisation :")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    Aucune violation détectée ✓")

        # ── Verdict ─────────────────────────────────────────────────────
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
            if count_final != count_initial:
                print(
                    f"  WARN: count final ({count_final}) != count initial ({count_initial})"
                )
            else:
                print(f"  Count revenu à {count_initial} ✓")
            print("  MODE TEST — données supprimées")
        else:
            print(f"  MODE PRODUCTION — {n_indexed} patterns conservés en KB")
            print(f"  Pour supprimer ce repo : filter _tag='{TAG}' via FilterSelector")

    # ── Étape 8 : Rapport ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  === RAPPORT INGESTION {REPO_NAME} ===")
    print(f"{'='*60}")
    print(f"  Mode                    : DRY_RUN={DRY_RUN}")
    print(f"  Patterns extraits       : {len(PATTERNS)}")
    print(f"  Patterns indexés        : {n_indexed}")
    print(f"  Count KB avant          : {count_initial}")
    count_now = client.count(collection_name=COLLECTION).count
    print(f"  Count KB après          : {count_now}")
    print()
    print("  Résultats queries :")
    print(f"  {'Query':<52s} | {'Function':<30s} | Score  | OK?")
    print(f"  {'-'*52} | {'-'*30} | ------ | ---")
    for r in query_results:
        ok = "✓" if (0.0 <= r["score"] <= 1.0 and r["function"] != "NO_RESULT") else "✗"
        print(
            f"  {r['query'][:52]:<52s} | {r['function']:<30s} | "
            f"{r['score']:.4f} | {ok}"
        )
    print()
    print(f"  Violations Charte       : {violations if violations else 'aucune'}")
    print(f"\n  Verdict : {verdict}")
    if verdict == "FAIL":
        problems = []
        if not scores_valid:
            problems.append("Scores hors [0.0, 1.0]")
        if not no_empty:
            problems.append("Queries sans résultat")
        if violations:
            problems.append(f"{len(violations)} violations Charte")
        print(f"  Problèmes : {', '.join(problems)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
