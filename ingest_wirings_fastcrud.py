"""
ingest_wirings_fastcrud.py — Extrait et indexe les wirings (flux inter-modules)
de igorbenav/fastcrud dans la KB Qdrant V6 (collection `wirings`).

Premier test de la pipeline wirings. Utilise extract_wirings.py pour l'extraction
AST, puis complète avec des wirings manuels pour les patterns que l'AST ne capture
pas (flow patterns complexes, conventions d'assemblage).

Usage:
    .venv/bin/python3 ingest_wirings_fastcrud.py
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
REPO_URL = "https://github.com/igorbenav/fastcrud.git"
REPO_NAME = "igorbenav/fastcrud"
REPO_LOCAL = "/tmp/fastcrud"
LANGUAGE = "python"
FRAMEWORK = "fastapi"
STACK = "fastapi+sqlalchemy+pydantic_v2"
CHARTE_VERSION = "1.0"
TAG = "wirings/igorbenav/fastcrud"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"


# ─── Wirings manuels (complètent l'extraction AST) ──────────────────────────
# Ces wirings capturent les conventions d'assemblage que l'AST ne voit pas
# (ex: conventions de nommage, ordre des opérations dans un CRUD complet).

MANUAL_WIRINGS: list[dict] = [
    # ── Convention d'assemblage CRUD FastAPI simple ──────────────────────
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete CRUD assembly convention for FastAPI simple project. "
            "Shows the file creation order and how each file references the others. "
            "This is the standard Wal-e assembly sequence for any CRUD API."
        ),
        "modules": [
            "models.py", "database.py", "schemas.py",
            "crud.py", "routes.py", "main.py", "conftest.py",
        ],
        "connections": [
            "1. database.py — create engine + AsyncSessionLocal + get_db()",
            "2. models.py — from database import Base → class Xxx(Base)",
            "3. schemas.py — standalone Pydantic V2 (no DB import needed)",
            "4. crud.py — from models import Xxx + from database import AsyncSession",
            "5. routes.py — from crud import * + from schemas import * + from database import get_db",
            "6. main.py — from routes import router → app.include_router(router, prefix='/api/v1')",
            "7. conftest.py — from database import Base, engine + from main import app → TestClient",
        ],
        "code_example": """\
# === File creation order for CRUD FastAPI project ===

# 1. database.py (foundation — no local imports)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# 2. models.py (depends on: database.py)
from database import Base
class Xxx(Base):
    __tablename__ = "xxxs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

# 3. schemas.py (standalone — no local imports)
class XxxCreate(BaseModel):
    title: str
class XxxResponse(XxxCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

# 4. crud.py (depends on: models.py, database.py)
from models import Xxx
async def create_xxx(db: AsyncSession, xxx_in: XxxCreate) -> Xxx:
    xxx = Xxx(**xxx_in.model_dump())
    db.add(xxx)
    await db.commit()
    await db.refresh(xxx)
    return xxx

# 5. routes.py (depends on: crud.py, schemas.py, database.py)
from crud import create_xxx, get_xxxs, get_xxx, update_xxx, delete_xxx
from schemas import XxxCreate, XxxUpdate, XxxResponse
from database import get_db
router = APIRouter(prefix="/xxxs", tags=["xxxs"])

# 6. main.py (depends on: routes.py, database.py)
from routes import router
app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Dependency injection graph ──────────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Standard FastAPI dependency injection graph for CRUD API. "
            "get_db() is the root dependency, injected into every route. "
            "For auth projects, get_current_user() chains on top of get_db()."
        ),
        "modules": ["database.py", "routes.py"],
        "connections": [
            "get_db() → AsyncSession → yield → auto-close at request end",
            "route(db: AsyncSession = Depends(get_db)) → every CRUD route",
            "route(xxx_id: int = Path(..., ge=1, le=2147483647)) → path validation",
            "route(request: Request) → for unknown query param rejection on GET list",
        ],
        "code_example": """\
# === Dependency Injection Graph — CRUD Simple ===

# Root dependency (database.py)
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# Injected into every route (routes.py)
@router.post("/", response_model=XxxResponse, status_code=201)
async def create_xxx(
    xxx_in: XxxCreate,
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    return await crud.create_xxx(db, xxx_in)

@router.get("/", response_model=list[XxxResponse])
async def list_xxxs(
    request: Request,                    # for unknown param rejection
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[Xxx]:
    unknown = set(request.query_params.keys()) - {"skip", "limit"}
    if unknown:
        raise HTTPException(422, detail=f"Unknown query params: {unknown}")
    return await crud.get_xxxs(db, skip=skip, limit=limit)

@router.get("/{xxx_id}", response_model=XxxResponse)
async def get_xxx(
    xxx_id: int = Path(..., ge=1, le=2147483647),
    db: AsyncSession = Depends(get_db),
) -> Xxx:
    return await crud.get_xxx(db, xxx_id)
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Test wiring convention ──────────────────────────────────────────
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Test fixture wiring for FastAPI CRUD project. "
            "Shows how conftest.py overrides get_db() with SQLite in-memory, "
            "creates tables via Base.metadata, and provides a sync TestClient."
        ),
        "modules": ["conftest.py", "main.py", "database.py", "models.py"],
        "connections": [
            "conftest.py → from database import Base (for metadata.create_all)",
            "conftest.py → from main import app (for TestClient)",
            "conftest.py → app.dependency_overrides[get_db] = override_get_db",
            "conftest.py → TestClient(app) → sync client fixture",
            "TEST_DATABASE_URL = 'sqlite://' → in-memory, fresh per test",
        ],
        "code_example": """\
# === Test Fixture Wiring — conftest.py ===

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from database import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite://"  # in-memory

engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture()
def client():
    return TestClient(app)
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Prefix split convention ─────────────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Prefix split convention between routes.py and main.py. "
            "routes.py owns the entity prefix (/xxxs), main.py owns the API version prefix (/api/v1). "
            "This prevents double-prefix bugs that break schemathesis."
        ),
        "modules": ["routes.py", "main.py"],
        "connections": [
            "routes.py: router = APIRouter(prefix='/xxxs', tags=['xxxs'])",
            "main.py: app.include_router(router, prefix='/api/v1')",
            "Final URL: /api/v1/xxxs/ (NOT /api/v1/api/v1/xxxs/)",
        ],
        "code_example": """\
# === Prefix Split Convention ===

# routes.py — entity prefix ONLY
router = APIRouter(prefix="/xxxs", tags=["xxxs"])

@router.get("/")          # → /xxxs/
@router.post("/")         # → /xxxs/
@router.get("/{xxx_id}")  # → /xxxs/{xxx_id}

# main.py — API version prefix
app.include_router(router, prefix="/api/v1")

# Result: /api/v1/xxxs/, /api/v1/xxxs/{xxx_id}
# NEVER: /api/v1/api/v1/xxxs/ (double prefix bug)
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ── Lifespan wiring ─────────────────────────────────────────────────
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Lifespan wiring for FastAPI CRUD project. "
            "init_db() creates tables at startup via Base.metadata.create_all(). "
            "This is REQUIRED for schemathesis to work (no tables = 500 errors)."
        ),
        "modules": ["main.py", "database.py", "models.py"],
        "connections": [
            "main.py: lifespan() → await init_db()",
            "database.py: init_db() → async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)",
            "models.py: Base.metadata contains all table definitions",
            "main.py: app = FastAPI(lifespan=lifespan) → tables exist before first request",
        ],
        "code_example": """\
# === Lifespan Wiring — Required for schemathesis ===

# database.py
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# main.py
from contextlib import asynccontextmanager
from database import init_db

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
# Without lifespan → tables don't exist → schemathesis gets 500 → Type C = 0
""",
        "pattern_scope": "crud_simple",
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
        pattern_scope="crud_simple",
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
        ("how to wire routes in FastAPI CRUD project", "import_graph"),
        ("dependency injection get_db in FastAPI", "dependency_chain"),
        ("test fixture conftest.py TestClient", "flow_pattern"),
        ("prefix split routes main.py /api/v1", "dependency_chain"),
        ("lifespan init_db startup", "dependency_chain"),
        ("file creation order CRUD FastAPI", "flow_pattern"),
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
