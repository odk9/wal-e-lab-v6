# Charte Wal-e — Normalisation KB (Polyglot)

> Standard de normalisation des patterns KB pour Wal-e Lab V6.
> Tout pattern extrait de GitHub doit respecter ces règles avant d'être stocké en KB.
> Tout code généré par le LLM doit respecter ces règles.
> Date : 30 mars 2026 (mise à jour post test matrix 12/18 repos)

---

## Principe

Un pattern brut extrait d'un repo GitHub peut être parfaitement fonctionnel mais inutilisable directement dans Wal-e parce qu'il porte les traces du projet source (noms d'entités, conventions du repo, API dépréciées).

Le Normaliseur applique cette charte à chaque pattern avant stockage. Le Générateur reçoit des patterns propres et peut se concentrer sur l'adaptation au PRD, pas sur la résolution de conflits de style.

**Règle fondamentale :** Si deux patterns venant de deux repos différents passent la charte, ils peuvent être assemblés sans friction.

---

## Niveau 1 — Règles universelles

*Applicables à tout code Python, peu importe le framework.*

---

### U-1 — Ordre des imports

**Règle :** stdlib → third-party → local. Une ligne vide entre chaque groupe. Alphabétique dans chaque groupe.

**Avant :**
```python
from src.database import get_db
import os
from fastapi import APIRouter
from datetime import datetime
from src.models import User
import asyncio
from sqlalchemy.orm import Session
```

**Après :**
```python
import asyncio
import os
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
```

---

### U-2 — Zéro import inutilisé

**Règle :** Supprimer tout import non référencé dans le fichier.

**Avant :**
```python
from typing import Optional, List, Dict, Any  # Dict et Any non utilisés
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks  # BackgroundTasks non utilisé
```

**Après :**
```python
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
```

---

### U-3 — Types explicites partout

**Règle :** Tout paramètre de fonction et toute valeur de retour doit avoir un type annoté. Pas de `Any` implicite.

**Avant :**
```python
def get_user(user_id, db):
    return db.query(User).filter(User.id == user_id).first()

async def create_item(item, db):
    db.add(item)
    db.commit()
```

**Après :**
```python
def get_user(user_id: int, db: Session) -> User | None:
    return db.query(User).filter(User.id == user_id).first()

async def create_item(item: User, db: AsyncSession) -> User:
    db.add(item)
    await db.commit()
    return item
```

---

### U-4 — Zéro variable inutilisée

**Règle :** Supprimer les variables affectées mais non lues. Utiliser `_` pour les valeurs intentionnellement ignorées.

**Avant :**
```python
def process(items: list[str]) -> int:
    result = []  # jamais lu
    count = 0
    for item in items:
        count += 1
    return count
```

**Après :**
```python
def process(items: list[str]) -> int:
    count = 0
    for _ in items:
        count += 1
    return count
```

---

### U-5 — Noms d'entités remplacés par des placeholders

**Règle :** Tout nom d'entité métier spécifique au projet source devient `Xxx` (classe), `xxx` (variable/fonction), `xxxs` (pluriel). Les noms de champs métier deviennent `field_name`.

Cette règle est la plus importante pour la portabilité des patterns.

**Avant :**
```python
class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    completed: bool = False

def create_todo(todo: TodoCreate, db: Session) -> Todo:
    db_todo = Todo(**todo.model_dump())
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo
```

**Après :**
```python
class XxxCreate(BaseModel):
    title: str
    description: str | None = None
    completed: bool = False

def create_xxx(xxx: XxxCreate, db: Session) -> Xxx:
    db_xxx = Xxx(**xxx.model_dump())
    db.add(db_xxx)
    db.commit()
    db.refresh(db_xxx)
    return db_xxx
```

#### U-5 — Implémentation : FORBIDDEN_ENTITIES + TECHNICAL_TERMS

La vérification automatique de U-5 (dans `kb_utils.py`) repose sur deux listes :

**FORBIDDEN_ENTITIES** — mots interdits dans le code normalisé (hors lignes d'import) :
```
todo, todos, task, tasks, post, posts, article, articles, product, products,
user, users, item, items, order, orders, comment, comments, category, categories,
tag, tags, note, notes, event, events, message, messages, blog, blogs
```

**TECHNICAL_TERMS** — termes techniques exemptés qui *contiennent* un mot interdit mais ne sont *pas* des entités métier. Le vérificateur neutralise ces termes avant de chercher les mots interdits.

**Structure contextuelle par langage (v1.1 — 30 mars 2026) :**
Les TECHNICAL_TERMS sont organisés en **dict par langage**. Lors de la vérification, seuls les termes `_universal` + ceux du langage du pattern sont chargés. Ça empêche qu'une exemption Rust (ex: `post(`, `.user`) masque un vrai nom d'entité dans un pattern Python ou JavaScript.

```python
TECHNICAL_TERMS: dict[str, set[str]] = {
    "_universal": { ... },   # termes partagés par tous les langages
    "python":     { ... },   # exemptions spécifiques Python/FastAPI
    "javascript": { ... },   # exemptions spécifiques JS/Express
    "typescript": { ... },   # exemptions spécifiques TS/NestJS
    "go":         { ... },   # exemptions spécifiques Go/Gin
    "rust":       { ... },   # exemptions spécifiques Rust/Axum
    "cpp":        { ... },   # exemptions spécifiques C++
}
```

Exemples de termes qui NE sont PAS universels (et pourquoi) :

| Terme | Langage | Pourquoi pas universel |
|---|---|---|
| `post(` | rust | En Rust, `post(handler)` est un routeur Axum. En Python, `post(data)` serait un vrai nom d'entité. |
| `.user` | rust | En Rust, `auth_session.user` est un field access. En JS, `model.user` serait une entité. |
| `task::` | rust | `tokio::task::spawn_blocking`. Pas pertinent hors Rust. |
| `task<` | cpp | `drogon::Task<>`. Pas pertinent hors C++. |
| `"post"_method` | cpp | Macro Crow. Pas pertinent hors C++. |
| `type ` | typescript | Keyword TS `type Xxx = ...`. En Python, `type` est un builtin différent. |
| `req.user` | javascript, typescript | Express/Passport. Pas pertinent en Python/Go/Rust. |

**Imports multi-lignes :** Le filtre d'import gère les blocs multi-lignes (`use axum::{...};` en Rust, `import (...)` en Go). Toutes les lignes du bloc sont exclues, pas seulement la première.

**Mécanisme :** Avant la détection U-5 :
1. Les lignes d'import sont exclues (y compris blocs multi-lignes)
2. Le texte restant est converti en lowercase
3. Seuls les TECHNICAL_TERMS de `_universal` + du langage courant sont remplacés par `___`
4. La regex `\b{entity}\b` cherche les mots interdits dans le texte sanitized

**Maintenance :** Quand un faux positif U-5 est rencontré sur un nouveau repo, ajouter le terme technique **dans la section du langage concerné** (pas dans `_universal`, sauf si le terme est vraiment commun à tous les langages). Purger les patterns du repo et relancer l'ingestion. La liste référence complète est dans `kb_utils.py`.

---

### U-6 — Fonctions courtes, une responsabilité

**Règle :** Toute fonction de plus de 40 lignes doit être découpée. Une fonction = une action lisible en une phrase.

**Avant :**
```python
async def process_order(order_id: int, db: AsyncSession) -> dict:
    # Récupérer la commande (10 lignes)
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Calculer le total (15 lignes)
    items = await db.execute(select(Item).where(Item.order_id == order_id))
    total = sum(item.price * item.quantity for item in items.scalars())
    tax = total * 0.20
    total_with_tax = total + tax
    # Mettre à jour le stock (15 lignes)
    for item in items.scalars():
        product = await db.get(Product, item.product_id)
        product.stock -= item.quantity
        db.add(product)
    # Envoyer l'email (10 lignes)
    ...
    return {"total": total_with_tax, "status": "processed"}
```

**Après :**
```python
async def process_order(order_id: int, db: AsyncSession) -> dict:
    order = await _get_order_or_404(order_id, db)
    total = await _calculate_order_total(order_id, db)
    await _update_stock(order_id, db)
    await _send_confirmation_email(order)
    return {"total": total, "status": "processed"}
```

---

### U-7 — Pas de print() en production

**Règle :** Zéro `print()` dans le code de production. Utiliser `logging` si le pattern a besoin de logs. Supprimer les prints de debug.

**Avant :**
```python
def calculate(x: int, y: int) -> int:
    print(f"Calculating {x} + {y}")  # debug
    result = x + y
    print(f"Result: {result}")  # debug
    return result
```

**Après :**
```python
def calculate(x: int, y: int) -> int:
    return x + y
```

---

### U-8 — Guard clauses plutôt que if/else imbriqués

**Règle :** Retourner tôt en cas d'erreur. Éviter l'imbrication > 2 niveaux.

**Avant :**
```python
def process(item: dict) -> str:
    if item:
        if "name" in item:
            if len(item["name"]) > 0:
                return item["name"].upper()
            else:
                return ""
        else:
            return ""
    else:
        return ""
```

**Après :**
```python
def process(item: dict) -> str:
    if not item:
        return ""
    if "name" not in item:
        return ""
    if len(item["name"]) == 0:
        return ""
    return item["name"].upper()
```

---

## Niveau 2 — Règles Python / FastAPI

*Spécifiques au stack Wal-e Python : FastAPI + SQLAlchemy 2.0 async + Pydantic V2 + SQLite/PostgreSQL.*

*Ces règles sont validées empiriquement (passage de 7.8/100 à 99/100 sur le pipeline Wal-e V5).*

---

### F-1 — SQLAlchemy 2.0 obligatoire

**Règle :** `DeclarativeBase` + `Mapped` + `mapped_column`. Jamais l'ancien style.

**Avant (SQLAlchemy 1.x — interdit) :**
```python
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    completed = Column(Boolean, default=False)
```

**Après (SQLAlchemy 2.0 — obligatoire) :**
```python
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Xxx(Base):
    __tablename__ = "xxxs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
```

---

### F-2 — Datetime toujours UTC

**Règle :** `datetime.now(UTC)` uniquement. `datetime.utcnow()` est déprécié depuis Python 3.12.

**Avant :**
```python
from datetime import datetime

created_at = Column(DateTime, default=datetime.utcnow)
```

**Après :**
```python
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC)
)
```

---

### F-3 — Pydantic V2 obligatoire

**Règle :** `model_config = ConfigDict(from_attributes=True)`. Jamais `class Config`. `StrictBool` pour les booléens. `field_serializer` pour la sérialisation datetime.

**Avant (Pydantic V1 — interdit) :**
```python
from pydantic import BaseModel

class TodoResponse(BaseModel):
    id: int
    title: str
    completed: bool
    created_at: datetime

    class Config:
        orm_mode = True
```

**Après (Pydantic V2 — obligatoire) :**
```python
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, StrictBool, field_serializer

class XxxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    completed: StrictBool
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.astimezone(UTC).isoformat()
```

---

### F-4 — Lifespan asynccontextmanager obligatoire

**Règle :** `@asynccontextmanager` pour initialiser la DB au démarrage. `@app.on_event("startup")` est déprécié.

**Avant (déprécié) :**
```python
@app.on_event("startup")
async def startup():
    await init_db()
```

**Après (obligatoire) :**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
```

---

### F-5 — Prefix split routes / main

**Règle :** Le router définit le prefix de l'entité (`/xxxs`). Le main ajoute le prefix global (`/api/v1`). Jamais `/api/v1` dans le router, jamais l'entité dans le main.

**Avant (tout dans le router — interdit) :**
```python
# routes/xxx.py
router = APIRouter(prefix="/api/v1/todos", tags=["todos"])
```

**Avant (tout dans le main — interdit) :**
```python
# main.py
app.include_router(router, prefix="/api/v1/todos")
```

**Après (split obligatoire) :**
```python
# routes/xxx.py
router = APIRouter(prefix="/xxxs", tags=["xxxs"])

# main.py
app.include_router(router, prefix="/api/v1")
```

---

### F-6 — Validation des IDs avec Path

**Règle :** Tout paramètre ID dans les routes doit utiliser `Path(ge=1, le=2147483647)` pour rejeter les valeurs invalides avant d'appeler la DB.

**Avant :**
```python
@router.get("/{xxx_id}")
async def get_xxx(xxx_id: int, db: AsyncSession = Depends(get_db)) -> XxxResponse:
    ...
```

**Après :**
```python
from fastapi import Path

@router.get("/{xxx_id}")
async def get_xxx(
    xxx_id: int = Path(..., ge=1, le=2147483647),
    db: AsyncSession = Depends(get_db),
) -> XxxResponse:
    ...
```

---

### F-7 — Rejet des query params inconnus sur GET list

**Règle :** Les endpoints GET list doivent rejeter les paramètres de query inconnus avec une 422. Évite les faux positifs schemathesis.

**Avant :**
```python
@router.get("/")
async def list_xxxs(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[XxxResponse]:
    ...
```

**Après :**
```python
from fastapi import Query, Request

@router.get("/")
async def list_xxxs(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[XxxResponse]:
    known_params = {"skip", "limit"}
    unknown = set(request.query_params.keys()) - known_params
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown query params: {unknown}")
    ...
```

---

### F-8 — Tests sync uniquement avec TestClient

**Règle :** Les tests FastAPI utilisent `TestClient` synchrone. `async def test_xxx()` avec `AsyncClient` cause des conflits d'event loop avec SQLite et pytest-asyncio.

**Avant (interdit) :**
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_xxx(client: AsyncClient) -> None:
    response = await client.post("/api/v1/xxxs/", json={"title": "Test"})
    assert response.status_code == 201
```

**Après (obligatoire) :**
```python
from fastapi.testclient import TestClient

def test_create_xxx(client: TestClient) -> None:
    response = client.post("/api/v1/xxxs/", json={"title": "Test"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test"
    assert "id" in data
```

---

### F-9 — Fixture client avec DB en mémoire

**Règle :** Le conftest.py doit créer une DB SQLite en mémoire propre pour chaque test. Jamais de DB persistante dans les tests.

**Standard :**
```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.main import app
from src.models import Base

TEST_DATABASE_URL = "sqlite://"  # in-memory

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
```

---

### F-10 — Session async dans les routes, sync dans les tests

**Règle :** Routes = `AsyncSession` + `async def`. Tests = `Session` sync (voir F-9). Pas de mélange.

**Route (async) :**
```python
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

@router.post("/", status_code=201)
async def create_xxx(
    xxx_in: XxxCreate,
    db: AsyncSession = Depends(get_db),
) -> XxxResponse:
    db_xxx = Xxx(**xxx_in.model_dump())
    db.add(db_xxx)
    await db.commit()
    await db.refresh(db_xxx)
    return db_xxx
```

**Test (sync) :**
```python
def test_create_xxx(client: TestClient) -> None:
    response = client.post("/api/v1/xxxs/", json={"title": "Test"})
    assert response.status_code == 201
```

---

### F-11 — Database setup standard

**Règle :** `get_db` comme async generator. `init_db()` appelé dans le lifespan.

**Standard :**
```python
# src/database.py
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
```

---

### F-12 — pyproject.toml standard

**Règle :** Toujours inclure `pytest-asyncio`, `ruff`, `pyright` en dev deps. Toujours configurer `isort` avec `known-first-party`.

**Standard :**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.ruff.lint.isort]
known-first-party = ["src", "tests"]

[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "basic"
```

---

### F-13 — main.py standard

**Règle :** Un handler d'exception générique. CORS si nécessaire. Pas de logique métier dans main.py.

**Standard :**
```python
# src/main.py
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
```

---

## Niveau 2b — Règles JavaScript / Express

*Spécifiques au stack JS : Express + Mongoose / Passport / Nodemailer.*

---

### J-1 — `var` interdit

**Règle :** Tout `var` doit être remplacé par `const` (valeur immuable) ou `let` (réassignation nécessaire). `var` a un scoping de fonction qui cause des bugs subtils.

**Avant :**
```javascript
var express = require('express');
var router = express.Router();
var items = [];
```

**Après :**
```javascript
const express = require('express');
const router = express.Router();
let items = [];
```

---

### J-2 — Callback hell → async/await

**Règle :** Si 3+ occurrences de `function()` / `function ()` non exemptées sont détectées, le pattern utilise des callbacks imbriqués et doit être refactoré en async/await.

**Exemptions (ne comptent PAS comme callbacks) :**
Les fonctions qui ont besoin du binding `this` en JS sont légitimes et exemptées :

| Pattern sur la ligne | Raison |
|---|---|
| `= function` | Assignation de méthode/propriété |
| `= async function` | Idem, async |
| `.pre(` | Hook Mongoose (pre-save, pre-validate) |
| `.post(` | Hook Mongoose (post-save, post-remove) |
| `.get(function` | Virtual getter Mongoose |
| `exports = function` | module.exports = function(app) |

**Mécanisme :** Chaque ligne est inspectée individuellement. Si la ligne contient `function(` ou `function (` ET qu'aucun pattern d'exemption n'est présent sur cette même ligne, elle est comptée. Seuil = 3 occurrences non exemptées.

---

### J-3 — `console.log()` interdit

**Règle :** Zéro `console.log()` dans le code normalisé. Équivalent de U-7 pour JavaScript. Utiliser un logger (winston, pino) si nécessaire.

---

## Niveau 2c — Règles TypeScript

*Spécifiques au stack TS : Express + TypeORM/Prisma, ou NestJS.*

---

### T-1 — Type `any` interdit

**Règle :** Jamais `: any` dans le code normalisé. Utiliser un type explicite, un generic, ou `unknown` si le type est vraiment inconnu.

**Avant :**
```typescript
function process(data: any): any {
    return data.value;
}
```

**Après :**
```typescript
function process<T extends { value: string }>(data: T): string {
    return data.value;
}
```

---

### T-2 — `var` interdit

**Règle :** Identique à J-1. `var` → `const` ou `let`.

---

### T-3 — `console.log()` interdit

**Règle :** Identique à J-3. Zéro `console.log()`.

---

## Niveau 2d — Règles Go / Gin

*Spécifiques au stack Go : Gin + GORM.*

---

### G-1 — `panic()` interdit (sauf `init`)

**Règle :** `panic()` ne doit jamais apparaître dans le code de production. Retourner une erreur à la place. Exception : `func init()` où un panic est acceptable pour signaler une configuration invalide au démarrage.

**Avant :**
```go
func GetXxx(id int) *Xxx {
    xxx, err := db.First(&Xxx{}, id)
    if err != nil {
        panic(err)
    }
    return xxx
}
```

**Après :**
```go
func GetXxx(id int) (*Xxx, error) {
    var xxx Xxx
    if err := db.First(&xxx, id).Error; err != nil {
        return nil, err
    }
    return &xxx, nil
}
```

---

### G-2 — `fmt.Println` / `fmt.Printf` interdit

**Règle :** Équivalent de U-7 pour Go. Zéro print de debug. Utiliser `log.Logger` ou un logger structuré (zap, zerolog).

---

## Niveau 2e — Règles Rust / Axum

*Spécifiques au stack Rust : Axum + SQLx + Tokio.*

---

### R-1 — `.unwrap()` interdit (sauf tests)

**Règle :** `.unwrap()` ne doit jamais apparaître dans le code de production. Utiliser `?` (propagation d'erreur) ou `match` / `unwrap_or_else`. Exception : dans les fonctions de test (`#[test]`), `.unwrap()` est acceptable.

**Avant :**
```rust
let xxx = db.fetch_one(query).await.unwrap();
```

**Après :**
```rust
let xxx = db.fetch_one(query).await?;
```

---

### R-2 — `println!()` interdit

**Règle :** Équivalent de U-7 pour Rust. Utiliser `tracing` ou le crate `log`.

---

## Niveau 2f — Règles C++ (Crow / Drogon / uWebSockets)

*Spécifiques au stack C++ : Crow, Drogon, uWebSockets.*

C++ n'a pas de règles spécifiques au-delà des règles universelles (U-1 à U-8). Cependant, les frameworks C++ utilisent des macros et conventions qui génèrent beaucoup de faux positifs U-5. Les TECHNICAL_TERMS suivants sont importants :

- `"post"_method` — Crow HTTP method literal (`"POST"_method`)
- `", post)"`, `", post,"` — Drogon macros `ADD_METHOD_TO(...)` et `PATH_ADD(...)`
- `on_message`, `onmessage`, `handlenewmessage` — WebSocket handler names (pas l'entité "message")
- `task<` — `drogon::Task<HttpResponsePtr>` (coroutine return type, pas l'entité "task")

Pour les variables C++ qui portent des noms d'entités (`item`, `message`, `user`, `tag`), la stratégie est le renommage direct dans le pattern normalisé : `item`→`element`, `message`→`payload`/`detail`/`status_text`, `user`→`account`, `tag`→`label`.

---

## Niveau 3 — Règles par type de feature

*Spécifiques à ce que le pattern fait fonctionnellement. S'ajoutent aux Niveaux 1 et 2.*

---

### Auth JWT

**Règles obligatoires :**
- Jamais stocker le mot de passe en clair — toujours `bcrypt` (passlib)
- Token JWT avec expiration explicite (`exp` claim)
- Séparer le token d'accès (15 min) du token de refresh (7 jours)
- `get_current_user` comme dependency FastAPI, pas comme helper appelé manuellement
- Rejeter avec 401 si token expiré, 403 si token valide mais permissions insuffisantes

```python
from datetime import UTC, datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "..."  # depuis env var, jamais hardcodé
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

def create_access_token(data: dict) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)
```

---

### Redis pub/sub

**Règles obligatoires :**
- Toujours sérialiser les messages en JSON (pas de pickle)
- Gérer la reconnexion (try/except sur `pubsub.listen()`)
- Consumer en background task, pas dans une route synchrone
- Channel name depuis constante, jamais hardcodé inline

```python
import json
import asyncio
import redis.asyncio as aioredis

CHANNEL_NAME = "xxx_events"

async def publish_event(redis: aioredis.Redis, event: dict) -> None:
    await redis.publish(CHANNEL_NAME, json.dumps(event))

async def consume_events(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL_NAME)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                event = json.loads(message["data"])
                await handle_event(event)
    except Exception:
        await pubsub.unsubscribe(CHANNEL_NAME)
```

---

### WebSocket

**Règles obligatoires :**
- Toujours gérer la déconnexion propre (`WebSocketDisconnect`)
- Manager de connexions pour broadcast (pas de global state direct)
- Heartbeat ou timeout explicite pour les connexions inactives

```python
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"{client_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

---

### Discord bot

**Règles obligatoires :**
- Toujours déclarer les intents explicitement
- Répondre dans les 3 secondes (sinon utiliser `defer()`)
- Séparer les cogs par domaine fonctionnel
- Pas de token dans le code — depuis env var

```python
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class XxxCog(commands.Cog):
    @discord.app_commands.command(name="xxx")
    async def xxx_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()  # si traitement > 3 secondes
        result = await long_running_task()
        await interaction.followup.send(result)
```

---

### ML inference

**Règles obligatoires :**
- Valider l'input avant toute inférence (taille, format, valeurs)
- Timeout explicite sur le modèle
- Réponse d'erreur structurée si le modèle échoue
- Modèle chargé une seule fois au démarrage (dans lifespan), pas à chaque requête

```python
import asyncio
from fastapi import HTTPException

_model = None  # chargé dans lifespan

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _model
    _model = load_model()  # une seule fois
    yield

async def run_inference(input_data: list[float]) -> list[float]:
    if len(input_data) > 1024:
        raise HTTPException(status_code=422, detail="Input too large (max 1024)")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_model.predict, input_data),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Model timeout")
    return result
```

---

## Checklist de validation

Avant de stocker un pattern en KB ou de valider du code généré, vérifier :

**Niveau 1 — Universel (tous langages)**
- [ ] U-1 : Imports ordonnés (stdlib → third-party → local)
- [ ] U-2 : Zéro import inutilisé
- [ ] U-3 : Types explicites sur paramètres et retours
- [ ] U-4 : Zéro variable inutilisée
- [ ] U-5 : Noms d'entités = `Xxx`/`xxx`/`xxxs` (vérifier TECHNICAL_TERMS si faux positif)
- [ ] U-6 : Fonctions < 40 lignes
- [ ] U-7 : Zéro `print()` (ou équivalent selon le langage — voir J-3, T-3, G-2, R-2)
- [ ] U-8 : Guard clauses, pas d'imbrication > 2

**Niveau 2a — Python/FastAPI**
- [ ] F-1 : SQLAlchemy 2.0 (`DeclarativeBase`, `Mapped`, `mapped_column`)
- [ ] F-2 : `datetime.now(UTC)`, jamais `utcnow()`
- [ ] F-3 : Pydantic V2 (`ConfigDict`, `StrictBool`, `field_serializer`)
- [ ] F-4 : Lifespan `asynccontextmanager`, jamais `@app.on_event`
- [ ] F-5 : Prefix split (router = `/xxxs`, main = `/api/v1`)
- [ ] F-6 : `Path(ge=1, le=2147483647)` sur tous les IDs
- [ ] F-7 : Rejet des query params inconnus sur GET list
- [ ] F-8 : Tests sync (`def test_xxx`, `TestClient`)
- [ ] F-9 : Fixture client avec SQLite in-memory
- [ ] F-10 : Routes async / tests sync — pas de mélange
- [ ] F-11 : `get_db` async generator standard
- [ ] F-12 : `pyproject.toml` avec `known-first-party`
- [ ] F-13 : `main.py` avec handler d'exception générique

**Niveau 2b — JavaScript/Express**
- [ ] J-1 : `var` → `const` ou `let`
- [ ] J-2 : Pas de callback hell (< 3 `function()` non exemptées)
- [ ] J-3 : Zéro `console.log()`

**Niveau 2c — TypeScript**
- [ ] T-1 : Pas de type `any`
- [ ] T-2 : `var` → `const` ou `let`
- [ ] T-3 : Zéro `console.log()`

**Niveau 2d — Go/Gin**
- [ ] G-1 : Pas de `panic()` (sauf `func init()`)
- [ ] G-2 : Zéro `fmt.Println` / `fmt.Printf`

**Niveau 2e — Rust/Axum**
- [ ] R-1 : Pas de `.unwrap()` (sauf `#[test]`)
- [ ] R-2 : Zéro `println!()`

**Niveau 2f — C++ (Crow/Drogon/uWebSockets)**
- [ ] Variables `item/message/user/tag` renommées (→ `element/payload/account/label`)
- [ ] Macros framework exemptées dans TECHNICAL_TERMS

**Niveau 3 — Par feature (si applicable)**
- [ ] Auth JWT : bcrypt + expiration + dependency
- [ ] Redis : JSON + reconnexion + background task
- [ ] WebSocket : `WebSocketDisconnect` + ConnectionManager
- [ ] Discord bot : intents + defer + cogs
- [ ] ML inference : validation input + timeout + modèle en lifespan

---

## Usage dans le Normaliseur

Le KB Normaliseur reçoit un pattern brut, un label de feature, et le langage. Il applique :
1. Toutes les règles Niveau 1 (U-1 à U-8)
2. Les règles Niveau 2 du langage détecté (F-* pour Python, J-* pour JS, T-* pour TS, G-* pour Go, R-* pour Rust)
3. Les règles Niveau 3 correspondant au label de feature (si applicable)

La vérification automatique est effectuée par `check_charte_violations()` dans `kb_utils.py`, qui reçoit le code et le langage et retourne la liste des violations. Le normaliseur LLM doit produire du code qui passe cette vérification à zéro violation.

Prompt type du Normaliseur :
```
Tu es le Normaliseur Wal-e. Réécris ce code {langage} en appliquant exactement ces règles.
Ne change rien d'autre — pas la logique, pas les algorithmes.
Règles à appliquer : [liste des règles applicables au langage]
Termes techniques exemptés U-5 : [TECHNICAL_TERMS pertinents pour ce langage]
Code à normaliser : [pattern brut]
Sortie : code normalisé uniquement, sans commentaire.
```
