# WAL-E LAB V6 — CLAUDE.md

> Mémoire persistante du projet. Lu automatiquement à chaque session Claude Code.
> Dernière mise à jour : 29 mars 2026

---

## Vision

Wal-e Lab V6 est une **usine de génération de code autonome** — PRD → projet complet, testé, déployé sur GitHub.

**Ce qui change par rapport à V5 :**
- V5 : patterns hardcodés dans le SYSTEM_PROMPT → 99/100 sur un CRUD simple, mais non généralisable
- V6 : KB feature-level (Qdrant) — patterns extraits de vrais repos, normalisés via Charte Wal-e, indexés par feature. Le générateur assemble des patterns éprouvés au lieu de générer from scratch.

**Principe fondamental :** Le LLM devient de la colle. 80-90% du code = recombination de patterns KB. 10-20% = logique métier spécifique au PRD.

---

## Architecture V6

```
PRD
 ↓
analyst (Python) — parse PRD, détecte langage + features
 ↓
family_classifier (LLM) — classe le projet dans une famille (bot, RAG, marketplace...)
 ↓
strategist (Python) — sélectionne plan modules/waves
 ↓
delta_analyzer (LLM) — identifie le delta vs architecture de référence
 ↓
retriever (Python) — query KB Qdrant par feature
 ↓
generator (LLM) — assemble patterns + logique métier
 ↓
evaluator (Python) — ruff + pyright + pytest + schemathesis
 ↓
should_continue → fixer (loop) ou deployer
 ↓
deployer (Python) — git push GitHub
```

**KB building pipeline (offline) :**
```
GitHub repos → kb_scanner → kb_extracteur (AST + LLM) → kb_normaliseur (Charte) → Qdrant
```

---

## Stack KB

| Composant | Valeur |
|---|---|
| Vector DB | Qdrant embedded local (`./kb_qdrant/`) |
| Modèle embedding | `nomic-ai/nomic-embed-text-v1.5-Q` (fastembed) |
| Dimensions | 768 |
| Tokens max | 8192 (pas de troncature) |
| Normalisation vecteurs | L2 manuelle dans `embedder.py` |
| API Qdrant search | `client.query_points()` — PAS `client.search()` (retiré en 1.17+) |
| Cleanup tests | `FilterSelector` par champ `_tag` |
| Python venv | `.venv/` — Python 3.13 (reconstruit le 29 mars 2026, python3.10 absent de la machine) |

---

## Structure du projet

```
Wal-e Lab V6/
├── CLAUDE.md                  ← ce fichier (lu automatiquement)
├── embedder.py                ← wrapper fastembed : embed_document / embed_query / embed_documents_batch
├── setup_collections.py       ← crée collections Qdrant (patterns + architectures)
├── kb_qdrant/                 ← données Qdrant (gitignored)
├── .venv/                     ← Python 3.10, qdrant-client 1.17.1, fastembed
├── Document/
│   ├── WAL-E_V6_KB_ARCHITECTURE.md   ← architecture complète V6
│   └── WAL-E_CHARTE_PYTHON_FASTAPI.md ← Charte de normalisation (référence complète)
└── ingest_*.py                ← scripts d'ingestion par repo (à créer)
```

**Commandes utiles :**
```bash
# Vérifier les collections Qdrant
.venv/bin/python3 -c "
import qdrant_client
c = qdrant_client.QdrantClient(path='./kb_qdrant')
for col in ['patterns', 'architectures']:
    print(col, c.get_collection(col).points_count)
"

# Recréer les collections (DESTRUCTIF)
.venv/bin/python3 setup_collections.py

# Lancer un script d'ingestion
.venv/bin/python3 ingest_fastcrud.py

# Git
git add <fichiers> && git commit -m "feat: ..." && git push
```

---

## Payload Qdrant — Collection `patterns`

Champ obligatoire sur chaque point inséré :

```python
{
    "normalized_code": str,       # code normalisé Charte Wal-e (entités = Xxx/xxx)
    "function": str,              # ex: "soft_delete", "paginate_offset_limit", "upsert"
    "feature_type": str,          # "crud" | "schema" | "model" | "route" | "test" | "dependency" | "config"
    "file_role": str,             # "model" | "route" | "schema" | "test" | "dependency" | "utility" | "crud"
    "language": str,              # "python" | "typescript" | "go" | "rust" | "javascript" | "cpp"
    "framework": str,             # "fastapi" | "express" | "gin" | "axum" | "nestjs" | "crow"
    "stack": str,                 # "fastapi+sqlalchemy+pydantic_v2" | "express+mongoose" | ...
    "file_path": str,             # chemin relatif dans le repo source
    "source_repo": str,           # URL GitHub complète
    "charte_version": str,        # "1.0"
    "created_at": int,            # timestamp Unix
    "_tag": str,                  # "owner/repo" — pour cleanup/update par repo
}
```

Champs indexés (filtrables) : `feature_type`, `framework`, `language`, `file_role`

**RÈGLE CRITIQUE — Toujours filtrer par `language` lors des queries KB.**
Sans filtre, une query JS peut retourner un pattern Python (similarité sémantique
entre "create" et "register"). Utiliser `query_kb()` de `kb_utils.py` qui impose
le filtre. Ne JAMAIS faire un `query_points()` sans filtre `language`.

---

## Matrice de test KB (18 repos)

| | A — Simple | B — Medium | C — Hard |
|---|---|---|---|
| Python | `igorbenav/fastcrud` | `fastapi/full-stack-fastapi-template` | `fastapi-users/fastapi-users` |
| JavaScript | `madhums/node-express-mongoose-demo` | `hagopj13/node-express-boilerplate` | `sahat/hackathon-starter` |
| TypeScript | `w3tecch/express-typescript-boilerplate` | `gothinkster/node-express-realworld-example-app` | `nestjs/nest` |
| Go | `eddycjy/go-gin-example` | `ThreeDotsLabs/wild-workouts-go-ddd-example` | `bxcodec/go-clean-arch` |
| Rust | `tokio-rs/axum` (examples/) | `maxcountryman/axum-login` | `shuttle-hq/shuttle` |
| C++ (KB only) | `crowcpp/Crow` | `drogonframework/drogon` | `uNetworking/uWebSockets` |

**Ordre d'ingestion :** Python A → B → C → JavaScript A → B → C → TypeScript → Go → Rust → C++

---

## Charte Wal-e — Règles de normalisation (obligatoires avant tout stockage KB)

> Référence complète : `./Document/WAL-E_CHARTE_PYTHON_FASTAPI.md`
> Ces règles s'appliquent à TOUT pattern avant insertion en KB. Un pattern non normalisé est interdit.

### Niveau 1 — Règles universelles

**U-1 — Ordre imports :** stdlib → third-party → local. Ligne vide entre groupes. Alphabétique dans chaque groupe.

**U-2 — Zéro import inutilisé :** Supprimer tout import non référencé.

**U-3 — Types explicites partout :** Tout paramètre + valeur de retour typé. Pas d'`Any` implicite.

**U-4 — Zéro variable inutilisée :** Utiliser `_` pour les valeurs intentionnellement ignorées.

**U-5 — Noms d'entités → placeholders :**
- Classe : `Xxx` (ex: `Todo` → `Xxx`, `User` → `Xxx`)
- Variable/fonction : `xxx` (ex: `todo` → `xxx`, `create_todo` → `create_xxx`)
- Pluriel : `xxxs` (ex: `todos` → `xxxs`)
- Champs métier spécifiques : garder si génériques (`title`, `name`, `status`), remplacer si trop spécifiques

**U-6 — Fonctions courtes :** > 40 lignes → décomposer. Une fonction = une responsabilité.

**U-7 — Zéro print() :** Supprimer tous les `print()` de debug. Utiliser `logging` si nécessaire.

**U-8 — Guard clauses :** Retourner tôt en cas d'erreur. Imbrication max 2 niveaux.

### Niveau 2 — Règles Python / FastAPI (stack Wal-e)

**F-1 — SQLAlchemy 2.0 OBLIGATOIRE :**
```python
# INTERDIT
Base = declarative_base()
id = Column(Integer, primary_key=True)

# OBLIGATOIRE
class Base(DeclarativeBase): pass
id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
```

**F-2 — Datetime UTC :**
```python
# INTERDIT
default=datetime.utcnow

# OBLIGATOIRE
default=lambda: datetime.now(UTC)
```

**F-3 — Pydantic V2 OBLIGATOIRE :**
```python
# INTERDIT
class Config:
    orm_mode = True

# OBLIGATOIRE
model_config = ConfigDict(from_attributes=True)
completed: StrictBool = False  # pas bool simple
@field_serializer("created_at") def serialize_dt(...): ...
```

**F-4 — Lifespan asynccontextmanager :**
```python
# INTERDIT
@app.on_event("startup")

# OBLIGATOIRE
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield
app = FastAPI(lifespan=lifespan)
```

**F-5 — Prefix split :**
```python
# router : prefix entité seulement
router = APIRouter(prefix="/xxxs", tags=["xxxs"])
# main.py : prefix global
app.include_router(router, prefix="/api/v1")
```

**F-6 — Path validation sur IDs :**
```python
xxx_id: int = Path(..., ge=1, le=2147483647)
```

**F-7 — Rejet query params inconnus sur GET list :**
```python
unknown = set(request.query_params.keys()) - known_params
if unknown:
    raise HTTPException(status_code=422, detail=f"Unknown query params: {unknown}")
```

**F-8 — Tests sync UNIQUEMENT :**
```python
# INTERDIT
async def test_create(client: AsyncClient): ...

# OBLIGATOIRE
def test_create(client: TestClient): ...
```

**F-9 — Fixture client SQLite in-memory :**
```python
TEST_DATABASE_URL = "sqlite://"  # in-memory, nouvelle DB par test
```

**F-10 — Routes async / tests sync — jamais mélanger.**

**F-11 — get_db standard :**
```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

**F-12 — pyproject.toml :** asyncio_mode="auto", ruff line-length=88, known-first-party=["src","tests"]

**F-13 — main.py :** handler d'exception générique obligatoire.

### Checklist rapide avant insertion KB

- [ ] U-5 : noms d'entités remplacés par Xxx/xxx/xxxs ?
- [ ] F-1 : SQLAlchemy 2.0 (DeclarativeBase, Mapped, mapped_column) ?
- [ ] F-2 : datetime.now(UTC), pas utcnow() ?
- [ ] F-3 : Pydantic V2 (ConfigDict, StrictBool, field_serializer) ?
- [ ] F-8 : tests sync, jamais async def test_ ?

---

## Erreurs connues

| Erreur | Cause | Fix |
|---|---|---|
| `client.search() not found` | qdrant-client 1.17+ a retiré search() | Utiliser `client.query_points(..., with_payload=True).points` |
| Score cosine > 1.0 | vecteurs fastembed non normalisés | `embedder.py` normalise en L2 — toujours utiliser embed_document/embed_query |
| Points orphelins après crash | cleanup par ID list interrompu | Toujours cleanup par FilterSelector + champ `_tag` |
| `index.lock` sur git | .git dans dossier monté | Git initialisé directement dans le dossier Mac — workflow normal |
| Faux positif normalisation — mot `order` | Variable technique `sort_order` contient "order" | Renommer la variable (`direction`) + liste `TECHNICAL_TERMS` dans le script d'ingestion |
| `.venv/bin/python3` introuvable | python3.10 désinstallé de la machine | Recréer le venv : `python3 -m venv .venv --clear && .venv/bin/pip install qdrant-client fastembed numpy` |

---

## LLMs par agent (OpenRouter)

| Agent | Modèle | Justification |
|---|---|---|
| Generator | `qwen/qwen3-coder` 480B | Génération code — qualité prioritaire |
| Fixer | `qwen/qwen3-coder` 480B | Même profil |
| KB Normaliseur | `qwen/qwen3-coder` 480B | Réécriture code selon Charte |
| KB Extracteur | `mimo-vl/mimo-v2-flash` | Labellisation répétitive — vitesse > profondeur |
| Delta Analyzer | `google/gemini-2.5-flash` | Compréhension structurelle multi-fichiers |
| Family Classifier | `google/gemini-2.5-flash-lite` | Classification courte |
