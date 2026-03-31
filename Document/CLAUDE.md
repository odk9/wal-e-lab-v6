# WAL-E LAB V5 — CLAUDE.md

> Mémoire persistante du projet. Lire au début de chaque session.
> Dernière mise à jour : 27 mars 2026

---

## Vision

Wal-e Lab V5 est une **usine de génération de code autonome** — PRD → projet complet, testé, déployé sur GitHub.

**Ce qui change par rapport à V4 :**
- V4 : pipeline Node.js/CJS maison, agents custom, score 53/100 (Type C = 0)
- V5 : LangGraph + LangChain, peu de code maison, polyglot dès le départ (Python + TS + Go + Rust)

---

## Architecture

### Pipeline (LangGraph)

```
PRD.md
  → analyst       — parse PRD, détecte langage + features (regex, pas de LLM)
  → strategist    — sélectionne plan modules/waves (déterministe)
  → researcher    — query KB Chroma (LangChain retriever)
  → generator     — génère code via LLM (OpenRouter)
  → evaluator     — ruff + pyright + pytest + schemathesis
  → fixer         — priorise erreurs pour prochain tour
  → (loop jusqu'à score ≥ target ou max_iterations)
  → deployer      — git init + push GitHub
```

### KB (LangChain + Chroma)

86 repos ingérés via gitingest → Chroma (all-MiniLM-L6-v2 ONNX).
Query via `langchain_chroma.Chroma` **sans** `embedding_function` (utilise le default Chroma = même modèle que l'ingestion).

### LLM

- **Génération** : `qwen/qwen3-coder-plus` via OpenRouter
- **API base** : `https://openrouter.ai/api/v1`

---

## Structure du projet

```
Wal-e Lab V5/
├── CLAUDE.md                        ← ce fichier
├── Documentation/
│   ├── MANIFEST.md                  ← analyse des repos de référence
│   ├── TECH_STACKS_AND_REPOS.md     ← 120+ repos, 15 domaines
│   └── TECH_STACKS_QUICK_REF.md     ← lookup rapide par archetype
├── ingestion/                       ← KB pipeline (Prefect + gitingest)
│   ├── ingest.py                    ← entry point
│   ├── repos.py                     ← 86 repos organisés par domaine
│   └── chroma_db/                   ← collection locale (gitignored)
└── pipeline/                        ← usine de génération
    ├── graph.py                     ← LangGraph entry point
    ├── state.py                     ← TypedDict partagé
    └── nodes/
        ├── analyst.py
        ├── strategist.py            ← plans Python + TS + Go + Rust (SIMPLE/MEDIUM/COMPLEX)
        ├── researcher.py
        ├── generator.py
        ├── evaluator.py             ← Type A (ruff+pyright) + B (pytest) + C (schemathesis)
        ├── fixer.py
        └── deployer.py              ← PyGithub + git push
```

---

## Lancer le pipeline

```bash
cd pipeline/
source .venv/bin/activate

# Sur un PRD
python graph.py chemin/vers/prd.md

# Variables d'environnement requises
OPENROUTER_API_KEY=sk-or-...
GITHUB_TOKEN=ghp_...
```

---

## Scoring

```
SCORE = (Type A × 0.20) + (Type B × 0.30) + (Type C × 0.50)

Type A : ruff + pyright         (qualité code)
Type B : pytest                 (tests fonctionnels)
Type C : schemathesis           (utilisateur réel — API fuzzing)
```

Target par défaut : **80/100**. V4 était bloqué à 53 (Type C = 0).

---

## Langages supportés (strategist)

| Langage | Stack | Plans disponibles |
|---|---|---|
| Python | FastAPI + SQLAlchemy + Pydantic V2 | SIMPLE / MEDIUM / COMPLEX |
| TypeScript | Express + Prisma | SIMPLE / MEDIUM / COMPLEX |
| Go | Gin + GORM | SIMPLE / MEDIUM / COMPLEX |
| Rust | Axum + SQLx | SIMPLE / MEDIUM / COMPLEX |

---

## Variables d'environnement

| Variable | Fichier | Obligatoire |
|---|---|---|
| `OPENROUTER_API_KEY` | `pipeline/.env` | ✅ |
| `GITHUB_TOKEN` | `pipeline/.env` | ✅ (deployer) |
| `STORAGE_BACKEND` | `ingestion/.env` | chroma / ragflow / qdrant |
| `RAGFLOW_API_KEY` | `ingestion/.env` | si ragflow |
| `GITHUB_TOKEN` | `ingestion/.env` | évite rate limit |

---

## Commandes utiles

```bash
# Lancer l'ingestion KB
cd ingestion/ && source .venv/bin/activate
STORAGE_BACKEND=chroma python ingest.py

# Tester le pipeline sur un PRD simple
cd pipeline/ && source .venv/bin/activate
python graph.py test-prd.md

# Vérifier la KB Chroma
python3 -c "
import chromadb
col = chromadb.PersistentClient('./chroma_db').get_collection('wale_v5_kb')
print(f'{col.count()} chunks indexés')
"
```

---

## Patterns validés (99/100 — 27 mars 2026)

Ralph Wiggum a atteint 99/100 (A:95, B:100, C:100) sur test-prd.md. Voici les patterns qui fonctionnent :

### models.py — SQLAlchemy 2.0 moderne obligatoire
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase): pass
class Todo(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
```

### schemas.py — StrictBool + field_serializer datetime
```python
completed: StrictBool = False  # empêche "1"/"true" → bool
@field_serializer("created_at") def serialize_dt(cls, v): ...  # UTC aware
```

### routes.py — prefix sans /api/v1 (ajouté dans main.py)
```python
router = APIRouter(prefix="/todos")  # main.py fait include_router(router, prefix="/api/v1")
```

### main.py — lifespan obligatoire
```python
@asynccontextmanager
async def lifespan(_app): await init_db(); yield
app = FastAPI(lifespan=lifespan)
```

### tests — sync uniquement, TestClient sync
```python
def test_create(client):  # JAMAIS async def test_
    response = client.post("/api/v1/todos/", json={"title": "Test"})
```

---

## Erreurs connues

| Erreur | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: chromadb` | pas installé | `uv pip install chromadb` |
| `ModuleNotFoundError: langchain_chroma` | pas installé | `uv pip install langchain-chroma` |
| RAGFlow `embedding_model: ""` | dataset créé sans modèle | infinity service non lancé → utiliser Chroma |
| `zsh: command not found: pip` | uv env | utiliser `uv pip install` |
| Score 0/100 Type C | schemathesis ne démarre pas | lifespan init_db() manquant, ou double prefix |
| Import error `from src.models import Base` | models.py utilise ancien style | utiliser DeclarativeBase, pas `Base = declarative_base()` |

---

## Prochaines étapes

1. ✅ Patterns 99/100 encodés dans generator.py SYSTEM_PROMPT
2. Relancer pipeline fresh (test-prd.md) → vérifier que le LLM génère correct dès l'itération 0
3. Lancer AutoResearch (autoresearch/program_wale_v5.md) pour amélioration autonome
4. Tester sur PRD MEDIUM (Polaris V6 simplifié)
5. Reprendre ingestion KB Chroma (86 repos) quand priorité
