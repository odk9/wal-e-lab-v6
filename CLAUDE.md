# WAL-E LAB V6 — CLAUDE.md

> Mémoire persistante du projet. Lire au début de chaque session.
> Dernière mise à jour : 28 mars 2026

---

## Vision

Wal-e Lab V6 est une **usine de génération de code autonome** — PRD → projet complet, testé, déployé sur GitHub.

**Ce qui change par rapport à V5 :**
- V5 : KB Chroma (chunks arbitraires 800 tokens), patterns hardcodés dans SYSTEM_PROMPT, score 99/100 sur CRUD simple uniquement
- V6 : KB feature-level (Qdrant), agents KB (Scanner + Extracteur + Normaliseur), Charte Wal-e, Family Classifier + Delta Analyzer

---

## Architecture

### Pipeline LangGraph V6

```
PRD.md
  → analyst           — parse PRD, détecte langage + features (Python, pas de LLM)
  → family_classifier — classe le PRD dans une famille applicative (LLM)
  → strategist        — sélectionne plan modules/waves (déterministe)
  → delta_analyzer    — identifie delta vs architecture de référence (LLM)
  → retriever         — query KB Qdrant par feature (Python)
  → generator         — génère code via LLM (OpenRouter)
  → setup             — crée venv, installe deps
  → evaluator         — ruff + pyright + pytest + schemathesis
  → fixer             — priorise erreurs pour prochain tour (Python + LLM)
  → (loop jusqu'à score ≥ target ou max_iterations)
  → deployer          — git init + push GitHub
```

### KB Building Pipeline (offline)

```
GitHub repos
  → kb_scanner    — identifie repos pertinents par stack (Python + GitHub API)
  → kb_extracteur — AST parsing + LLM labellisation features cross-fichiers
  → kb_normaliseur — applique Charte Wal-e (LLM)
  → Qdrant embedded — patterns normalisés indexés par feature
```

### KB (Qdrant)

2 collections :
- `patterns` — patterns de features normalisés (feature_type, framework, file_role, normalized_code)
- `architectures` — familles applicatives (famille, services, communication, base_patterns)

Embedding : `all-MiniLM-L6-v2` ONNX local (384 dims).

### LLM par agent

| Agent | Modèle | Justification |
|---|---|---|
| Generator | `qwen/qwen3-coder` 480B A35B | Génération de code — qualité prioritaire |
| Fixer | `qwen/qwen3-coder` 480B A35B | Même profil |
| KB Normaliseur | `qwen/qwen3-coder` 480B A35B | Réécriture code selon Charte |
| KB Extracteur | `mimo-vl/mimo-v2-flash` | Labellisation répétitive — volume |
| Delta Analyzer | `google/gemini-2.5-flash` | Compréhension structurelle multi-fichiers |
| Family Classifier | `google/gemini-2.5-flash-lite` | Classification courte |

---

## Structure du projet

```
Wal-e Lab V6/
├── CLAUDE.md                            ← ce fichier
├── .gitignore
├── Documentation/
│   ├── WAL-E_V6_KB_ARCHITECTURE.md      ← architecture complète KB + pipeline
│   └── WAL-E_CHARTE_PYTHON_FASTAPI.md   ← charte de normalisation Python/FastAPI
├── kb/                                  ← KB feature-level (Qdrant)
│   ├── kb_qdrant/                       ← données Qdrant (gitignored)
│   ├── embedder.py                      ← wrapper SentenceTransformer
│   ├── retriever.py                     ← interface QdrantRetriever
│   ├── ingestor.py                      ← pipeline scanner → extracteur → normaliseur → upsert
│   ├── scanner.py                       ← GitHub API — identifie repos par stack
│   ├── extractor.py                     ← AST + LLM — extrait patterns par feature
│   ├── normalizer.py                    ← LLM — applique Charte Wal-e
│   ├── setup_collections.py             ← crée collections Qdrant au premier lancement
│   └── repos.py                         ← liste des repos sources par domaine
├── pipeline/                            ← usine de génération
│   ├── graph.py                         ← LangGraph entry point
│   ├── state.py                         ← TypedDict partagé
│   ├── .env.example
│   └── nodes/
│       ├── analyst.py                   ← ✅ V5 (repris)
│       ├── family_classifier.py         ← 🔲 NOUVEAU — LLM
│       ├── strategist.py                ← ✅ V5 (repris, enrichi)
│       ├── delta_analyzer.py            ← 🔲 NOUVEAU — LLM
│       ├── researcher.py                ← 🔄 amélioré — query par feature
│       ├── generator.py                 ← ✅ V5 (repris)
│       ├── setup.py                     ← ✅ V5 (repris)
│       ├── evaluator.py                 ← ✅ V5 (repris)
│       ├── fixer.py                     ← ✅ V5 (repris)
│       └── deployer.py                  ← ✅ V5 (repris)
└── autoresearch/                        ← amélioration autonome (V5 → V6)
```

---

## Lancer le pipeline

```bash
cd pipeline/
source .venv/bin/activate

# Sur un PRD
python graph.py chemin/vers/prd.md

# Variables d'environnement requises (pipeline/.env)
OPENROUTER_API_KEY=sk-or-...
GITHUB_TOKEN=ghp_...
```

## Lancer le KB building

```bash
cd kb/
source .venv/bin/activate

# Setup collections Qdrant (first run)
python setup_collections.py

# Ingestion complète
python ingestor.py

# Vérifier la KB
python3 -c "
from qdrant_client import QdrantClient
c = QdrantClient(path='./kb_qdrant')
print(c.get_collection('patterns'))
"
```

---

## Scoring

```
SCORE = (Type A × 0.20) + (Type B × 0.30) + (Type C × 0.50)

Type A : ruff + pyright         (qualité code)
Type B : pytest                 (tests fonctionnels)
Type C : schemathesis           (utilisateur réel — API fuzzing)
```

Target par défaut : **80/100**. Objectif V6 : 90+ sur projets MEDIUM (auth, multi-entités).

---

## Langages supportés

| Langage | Stack | Plans disponibles |
|---|---|---|
| Python | FastAPI + SQLAlchemy 2.0 + Pydantic V2 | SIMPLE / MEDIUM / COMPLEX |
| TypeScript | Express + Prisma | SIMPLE / MEDIUM / COMPLEX |
| Go | Gin + GORM | SIMPLE / MEDIUM / COMPLEX |
| Rust | Axum + SQLx | SIMPLE / MEDIUM / COMPLEX |

---

## Familles applicatives

| Famille | Projets cibles | Architecture de référence |
|---|---|---|
| `bot_platform` | Polaris V6 | Discord bot + REST API + event handlers |
| `rag_platform` | Noesis V4 | Vector DB + Redis cache + Streamlit |
| `ai_chat` | Teacher V2 | Local LLM + session state + Streamlit |
| `media_pipeline` | Aria V2 | Event streaming + ML inference + REST API |
| `crud_api` | PRDs simples | FastAPI + SQLAlchemy + Pydantic |

---

## Variables d'environnement

| Variable | Fichier | Obligatoire |
|---|---|---|
| `OPENROUTER_API_KEY` | `pipeline/.env` | ✅ |
| `GITHUB_TOKEN` | `pipeline/.env` | ✅ (deployer) |
| `GITHUB_TOKEN` | `kb/.env` | ✅ (scanner) |

---

## Patterns validés (hérités V5)

Les patterns FastAPI/SQLAlchemy 2.0/Pydantic V2 validés à 99/100 sont documentés dans :
- `Documentation/WAL-E_CHARTE_PYTHON_FASTAPI.md` — règles complètes avec exemples avant/après
- Ces patterns constituent la base du KB Normaliseur

---

## Statut agents

| Agent | Statut | Notes |
|---|---|---|
| analyst | ✅ À porter depuis V5 | |
| family_classifier | 🔲 À créer | LLM — Gemini Flash Lite |
| strategist | ✅ À porter depuis V5 | |
| delta_analyzer | 🔲 À créer | LLM — Gemini Flash |
| researcher/retriever | 🔄 À améliorer | Query par feature, pas par projet |
| generator | ✅ À porter depuis V5 | |
| setup | ✅ À porter depuis V5 | |
| evaluator | ✅ À porter depuis V5 | |
| fixer | ✅ À porter depuis V5 | |
| deployer | ✅ À porter depuis V5 | |
| kb_scanner | 🔲 À créer | Python + GitHub API |
| kb_extracteur | 🔲 À créer | Python AST + LLM |
| kb_normaliseur | 🔲 À créer | LLM — Qwen3-coder |

---

## Prochaines étapes

1. ✅ Structure projet créée + GitHub repo initialisé
2. ✅ Documentation V6 portée (KB Architecture + Charte)
3. 🔲 Setup collections Qdrant (setup_collections.py)
4. 🔲 Assembler la KB : scanner → extracteur → normaliseur → upsert
5. 🔲 Porter les nodes V5 dans pipeline/nodes/
6. 🔲 Implémenter family_classifier et delta_analyzer
7. 🔲 Tester sur PRD SIMPLE → viser 99/100 dès l'itération 0
8. 🔲 Tester sur PRD MEDIUM (auth + multi-entités) → viser 90+
