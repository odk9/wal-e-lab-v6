# Wal-e Lab — Architecture KB Feature-Level + Charte Wal-e
> Document de référence : cheminement complet, questions, réponses, et architecture validée
> Date : 28 mars 2026

---

## Point de départ — Le problème de généralisation

**Question initiale :** Si on atteint 99/100 sur test-prd.md (Todo API), comment s'assurer que ce score sera le même peu importe le projet ?

**Réponse :** C'est le problème de généralisation. 99/100 sur un CRUD Todo ne garantit rien sur Polaris V6 ou Aria V2. Le SYSTEM_PROMPT actuel contient des exemples spécifiques ("todos", "TodoCreate") — le LLM peut performer sur ce cas parce qu'il a mémorisé le pattern, pas parce qu'il a appris les règles générales.

---

## Problème 1 — La KB Chroma n'est pas la bonne approche

**Observation :** La KB Chroma stocke des chunks arbitraires de 800 tokens coupés n'importe où dans des fichiers. Une seule query générique par projet. Résultat : contexte bruité, chunks coupés en plein milieu d'une fonction, patterns inutilisables.

**Question :** Au lieu de stocker tout un repo, pourquoi ne pas créer un agent qui scanne les repos directement sur GitHub et un agent qui extrait uniquement les lignes de code ou blocs de code par feature, et les enregistre dans une base de données ?

**Réponse validée :** C'est exactement la bonne direction. Ce n'est pas un moteur de recherche de repos, c'est une **bibliothèque de patterns feature-level**.

### Ce que ça implique concrètement :

**Au moment de concevoir un projet, Wal-e :**
1. Lit le PRD
2. Dresse la liste des features nécessaires ("j'ai besoin de : CRUD async, auth JWT, WebSocket, Redis pub/sub...")
3. Va récupérer dans la KB le pattern exact pour chaque feature
4. Le LLM ne génère rien from scratch — il **adapte et assemble** les patterns récupérés

**Le LLM devient de la colle.** Son seul travail : renommer les entités, résoudre les frictions d'assemblage entre patterns, et réaliser ce qu'attend le PRD. 80-90% du code est de la recombinaison de patterns éprouvés. 10-20% seulement est de la logique métier spécifique.

---

## Architecture des 3 agents KB

### Agent 1 — Scanner
Parcourt GitHub, identifie les repos pertinents par stack (FastAPI, Express, Gin, Axum...), les télécharge. Simple, déjà partiellement implémenté avec gitingest.

### Agent 2 — Extracteur (le plus difficile)
- Parse la structure du code avec AST pour identifier les frontières syntaxiques (fonctions, classes)
- Utilise un LLM pour identifier les frontières **sémantiques** (features qui traversent plusieurs fichiers)
- Label chaque pattern : `{type: "crud", framework: "fastapi", db: "sqlalchemy_async", entity: "generic"}`
- **Important :** Une feature traverse souvent plusieurs fichiers. L'auth = `models/user.py` + `schemas/auth.py` + `middleware/jwt.py` + `routes/auth.py`. Identifier ces frontières cross-fichiers nécessite un LLM.

### Agent 3 — Retriever
Au moment de construire un projet :
- Query par feature depuis le PRD (pas une query générique sur le projet entier)
- Retourne les patterns les plus proches pour chaque feature demandée
- Injecte les patterns directement dans le prompt du générateur

---

## Problème 2 — Fuites de contexte dans les patterns

**Observation concrète** dans `_GOLDEN_PATTERNS` du generator.py actuel :
```python
router = APIRouter(prefix="/todos", tags=["todos"])
```
"todos" est hardcodé dans le pattern — pourtant censé être générique. C'est une **fuite de contexte** : le pattern porte la trace du projet source. Un pattern extrait de GitHub brut aura les mêmes problèmes (noms d'entités spécifiques, logique métier hardcodée, constantes du projet source).

---

## Problème 3 — Conflits entre patterns de sources différentes

Quand on assemble des patterns extraits de repos différents :
- Repo A utilise `datetime.utcnow()` (déprécié), Repo B utilise `datetime.now(UTC)` (correct)
- Repo A : `Base = declarative_base()` (SQLAlchemy 1.x), Repo B : `class Base(DeclarativeBase): pass` (SQLAlchemy 2.0)
- Repo A : imports relatifs (`from .models import`), Repo B : imports absolus (`from src.models import`)
- Styles incompatibles entre patterns → le LLM-colle doit résoudre des conflits qu'il ne devrait pas avoir à gérer

**Solution validée :** Une couche de normalisation avant le stockage en KB.

---

## Solution — La Charte Langage Wal-e

**Question :** Y a-t-il un moyen de mettre des règles qui permettent d'homogénéiser le tout ?

**Réponse validée :** Oui. Une **charte langage Wal-e** — un agent normaliseur qui prend n'importe quel pattern brut extrait de GitHub et le convertit en "langage Wal-e" avant stockage.

Les patterns entrent hétérogènes. Ils sortent tous au même standard.

### Structure de la charte — 3 niveaux

**Niveau 1 — Règles universelles** (valables peu importe le langage ou le pattern)
- Imports groupés et ordonnés (stdlib → third-party → local, une ligne vide entre chaque groupe)
- Zéro code mort (variables inutilisées, imports non utilisés)
- Types explicites partout (paramètres + valeur de retour)
- Pas de valeurs hardcodées qui appartiennent au domaine métier
- Noms d'entités remplacés par des placeholders (`Xxx`, `xxx`, `xxxs`)
- Fonctions courtes avec une seule responsabilité
- Pas de `print()` / `console.log()` en production

**Niveau 2 — Règles par stack** (spécifiques à une combinaison langage + framework)

*Python / FastAPI — déjà validées empiriquement (76.1/100 → 99/100) :*
- SQLAlchemy toujours 2.0 : `class Base(DeclarativeBase): pass`, `Mapped[type]`, `mapped_column()`
- Pydantic toujours V2 : `model_config = ConfigDict(from_attributes=True)`, `StrictBool`, `field_serializer`
- Datetime toujours UTC : `datetime.now(UTC)` jamais `datetime.utcnow()`
- IDs toujours Integer autoincrement, jamais UUID
- Lifespan asynccontextmanager, jamais `@app.on_event`
- Tests toujours sync (`def test_xxx(client):`)
- Prefix split : routes ajoute `/entity`, main ajoute `/api/v1`
- `Path(ge=1, le=2147483647)` sur tous les IDs
- Rejeter les query params inconnus sur GET list

*Go / Gin, TypeScript / Express, Rust / Axum → chartes séparées à construire*

**Niveau 3 — Règles par feature type** (spécifiques à ce que le pattern fait)
- Auth JWT : jamais stocker le mot de passe en clair, toujours bcrypt, JWT avec expiration
- Redis pub/sub : toujours gérer la reconnexion, toujours sérialiser en JSON
- Discord bot : toujours gérer les intents, toujours répondre dans les 3 secondes
- WebSocket : toujours gérer la déconnexion proprement
- ML inference : toujours valider l'input avant l'inférence, timeout sur le modèle

### Implémentation de la normalisation

Un agent LLM simple avec un prompt court :
> "Voici du code Python, réécris-le en respectant ces 6 règles, ne change rien d'autre."

Un appel LLM par pattern. Pas de raisonnement complexe. Le normaliseur est déterministe une fois la charte définie.

**Résultat :** Le générateur ne reçoit jamais de patterns sales. Tous les patterns en KB sont déjà en langage Wal-e. Le LLM-colle n'a plus à résoudre des conflits de style — il n'y en a plus par construction.

---

## Pipeline complet — Architecture cible

### Insight clé — Familles architecturales (28 mars 2026)

**Observation :** Spotify et Deezer ont des interfaces différentes, des features différentes, mais leur architecture backend est sensiblement la même (catalog service, streaming service, user service, recommandation, billing). Pareil pour Netflix et Disney+. Et les 4 ensemble partagent les fondamentaux du streaming — seul le media diffère (audio vs vidéo).

**Ce que ça implique :** Avant même de chercher des patterns de features, on peut identifier la **famille architecturale** du projet. Un PRD de plateforme de streaming ressemble plus à Spotify qu'à une app de rencontre — et l'architecture de référence de Spotify est un meilleur point de départ que de partir de zéro.

**Approche validée — Reverse engineering par famille :**
1. Analyser des projets GitHub existants pour identifier leurs architectures
2. Regrouper par famille : streaming, marketplace, dating app, RAG platform, bot platform, SaaS B2B...
3. Pour chaque famille, extraire l'architecture de référence : quels services, comment ils communiquent, quels patterns de base
4. Quand Wal-e reçoit un PRD → classifier la famille → charger l'architecture de référence → identifier le delta (ce qui diffère de la référence) → récupérer uniquement les patterns du delta

**Familles pour les projets Wal-e cibles :**

| Projet | Famille | Architecture de référence |
|---|---|---|
| Polaris V6 | Bot / assistant platform | Discord bot + REST API + event handlers |
| Noesis V4 | RAG / search platform | Vector DB + Redis cache + Streamlit UI |
| Teacher V2 | AI chat platform | Local LLM + session state + Streamlit |
| Aria V2 | Media processing pipeline | Event streaming + ML inference + REST API |

**Hiérarchie complète des patterns :**
```
Niveau 0 → Famille applicative     : "streaming", "marketplace", "RAG platform", "bot"
Niveau 1 → Architecture référence  : quels services, comment ils communiquent
Niveau 2 → Feature patterns         : CRUD, auth, WebSocket, Redis pub/sub, ML inference...
Niveau 3 → Code patterns            : _GOLDEN_PATTERNS (déjà en place pour FastAPI CRUD)
```

V5 actuel couvre uniquement le niveau 3. L'objectif V6/V7 est de couvrir les 4 niveaux.

---

```
GitHub repos (reverse engineering)
    ↓
[Architecture     → identifie la famille de chaque repo
 Classifier]        regroupe par domaine : streaming, marketplace, bot...
    ↓
[KB Architectures → architectures de référence par famille
 de référence]      squelette : services + communication + patterns de base
    ↓
[Scanner]         → identifie les repos pertinents par stack
    ↓
[Extracteur]      → AST parsing (frontières syntaxiques)
                    + LLM (frontières sémantiques cross-fichiers)
                    + labellisation : {type, framework, feature, deps}
    ↓
[Normaliseur]     → applique la Charte Wal-e (3 niveaux)
                    → remplace noms d'entités par Xxx
                    → homogénéise conventions
    ↓
[KB Feature-Level] → patterns normalisés, indexés par feature
    ↓
PRD → [Analyst]      → liste des features nécessaires
    ↓
[Family           → classe le PRD dans une famille applicative
 Classifier]        charge l'architecture de référence correspondante
    ↓
[Delta Analyzer]  → identifie ce qui diffère de l'architecture de référence
                    seul le delta nécessite des patterns spécifiques
    ↓
[Retriever]       → query par feature delta → patterns les plus proches
    ↓
[Générateur LLM]  → reçoit : architecture référence + patterns delta + PRD
                    → renomme Xxx → noms d'entités réels
                    → branche les imports
                    → résout les frictions d'assemblage
                    → réalise la logique métier spécifique
    ↓
Code généré → Tests → Score
```

---

## Taux de réussite attendu — Estimation honnête

| Type de projet | V5 actuel | KB + Charte (sans familles) | KB + Charte + Familles |
|---|---|---|---|
| CRUD REST API simple | 76% | 95-99% | 99%+ |
| API multi-entités + auth | 40-60% | 85-95% | 95-99% |
| Polaris V6 (Discord bot + MCP) | 30-50% | 75-85% | 88-95% |
| Noesis V4 (Qdrant + Redis + Streamlit) | 20-40% | 70-80% | 85-92% |
| Aria V2 (Audio ML + Redis Streams) | 10-20% | 50-70% | 70-85% |

**Pourquoi les familles améliorent le score :** Sans familles, le générateur part de zéro pour chaque projet et doit deviner l'architecture. Avec les familles, il part d'une architecture de référence prouvée pour ce type d'application — le delta à générer est beaucoup plus petit, donc beaucoup plus fiable.

**Conclusion honnête :** KB + Charte + Familles architecturales couvre 90-95% des projets backend. Le dernier 5-10% (Aria V2 level) nécessite des suites de tests spécialisées par type de projet et potentiellement une validation humaine sur les décisions d'architecture les plus complexes.

---

## Couches de validation supplémentaires nécessaires

**1. Validation des contrats avant les tests**
Analyse AST statique : vérifier que tous les imports se résolvent entre fichiers avant de lancer pytest. Si `routes.py` importe `from src.crud import create_todo` mais que `crud.py` expose `create_item`, on le détecte sans lancer le serveur.

**2. Cohérence OpenAPI / schemathesis**
Vérifier que le schéma OpenAPI généré par FastAPI correspond à ce que schemathesis va tester. Si `TodoResponse` déclare `updated_at: datetime` mais que le modèle SQLAlchemy n'a pas ce champ, schemathesis crashe avec une erreur opaque. Cette couche détecte ça avant les 528 test cases.

**3. Validation d'assemblage cross-patterns**
S'assurer que deux patterns de sources différentes partagent les mêmes conventions après normalisation. C'est ce que ferait un senior dev en code review avant de merger.

---

## Preuve de concept — Ce qui valide l'approche

Ralph Wiggum a atteint **99/100 (A:95, B:100, C:100)** sur test-prd.md en appliquant exactement ce principe : des patterns complets et normalisés (les `_GOLDEN_PATTERNS` dans `generator.py`) injectés directement dans le prompt du LLM.

Score progression :
- Run 1 (sans patterns) : **7.8/100**
- Run 2 (patterns SYSTEM_PROMPT v1) : **60/100**
- Run 3 (patterns + schemathesis rules) : **76.1/100**
- Ralph loop (patterns complets + correction manuelle) : **99/100**

La corrélation est directe : plus les patterns injectés sont complets et normalisés, plus le score est élevé. L'approche KB feature-level automatise et généralise ce mécanisme.

---

## Agents — Inventaire complet et décisions d'implémentation

### Règle de décision : Python vs LLM

**Python** quand la tâche est mécanique et déterministe (parsing, fichiers, git, règles codifiables).
**LLM** quand la tâche nécessite une compréhension sémantique qu'on ne peut pas réduire à des règles.

### Tableau des agents

| Agent | Python ou LLM | Statut | Justification |
|---|---|---|---|
| Analyst | Python | ✅ V5 | Regex sur le PRD — pas de sémantique |
| **Family Classifier** | LLM | 🔲 À créer | "Est-ce un streaming, un bot, un marketplace ?" — incompressible |
| Strategist | Python | ✅ V5 | Sélection déterministe de modules/waves |
| **Delta Analyzer** | LLM | 🔲 À créer | Comparer features PRD vs architecture de référence — sémantique |
| Researcher / Retriever | Python | ✅ V5 (à améliorer) | Requête vectorielle Chroma — query par feature, pas par projet |
| Generator | LLM | ✅ V5 | Génération de code |
| Setup | Python | ✅ V5 | venv, pip install |
| Evaluator | Python | ✅ V5 | ruff, pyright, pytest, schemathesis |
| Fixer | Python + LLM | ✅ V5 | Parsing erreurs (Python) + contexte fix (LLM) |
| Deployer | Python | ✅ V5 | git + GitHub API |
| **KB Scanner** | Python | 🔲 À créer | GitHub API — simple HTTP, pas de sémantique |
| **KB Extracteur** | Python (AST) + LLM | 🔲 À créer | AST pour frontières syntaxiques, LLM pour label sémantique |
| **KB Normaliseur** | LLM | 🔲 À créer | Réécriture de code selon la Charte — nécessite compréhension |
| **Superviseur V6** | Python | 🔲 À enrichir | Routing plus riche, toujours déterministe |

### Superviseur actuel (V5) vs Superviseur V6

**Actuel — `should_continue()` dans graph.py (3 conditions) :**
```python
def should_continue(state) -> str:
    if state["converged"]: return "deploy"
    if state["iteration"] >= state["max_iterations"]: return "deploy"
    return "fix"
```

**V6 — routing enrichi (toujours Python, toujours déterministe) :**
```python
def should_continue(state) -> str:
    # Boucle de convergence existante
    if state["converged"]: return "deploy"
    if state["iteration"] >= state["max_iterations"]: return "deploy"

    # Nouveau — routing KB + familles architecturales
    if not state["family_identified"]: return "family_classifier"
    if not state["delta_analyzed"]: return "delta_analyzer"
    if not state["kb_patterns_loaded"]: return "retriever"

    return "fix"
```

Le superviseur reste Python. Ce qui change : il orchestre plus d'états. Le LLM n'est jamais dans la boucle de routing — seulement dans les nodes qui nécessitent de la compréhension sémantique.

### Graphe V6 complet

```
PRD
 ↓
analyst (Python)
 ↓
family_classifier (LLM) ← nouveau
 ↓
strategist (Python)
 ↓
delta_analyzer (LLM) ← nouveau
 ↓
retriever (Python, query par feature) ← amélioré
 ↓
generator (LLM)
 ↓
setup (Python)
 ↓
evaluator (Python)
 ↓
should_continue (Python) ──→ deployer (Python) → END
 ↓ fix
fixer (Python + LLM) → generator (boucle)
```

**KB building pipeline (séparé, tourne en offline) :**
```
GitHub repos
 ↓
kb_scanner (Python)
 ↓
kb_extracteur (Python AST + LLM)
 ↓
kb_normaliseur (LLM)
 ↓
KB Feature-Level (Qdrant)
```

---

## Prochaines étapes pour implémenter cette architecture

**Phase 1 — Fondations (V5 → V6)**
1. **Formaliser la Charte Wal-e Python/FastAPI** — documenter les règles niveau 1 et 2 de manière exhaustive, avec des exemples avant/après pour chaque règle
2. **Construire l'Extracteur** — agent qui prend un repo GitHub et sort des patterns labellisés par feature (AST + LLM)
3. **Construire le Normaliseur** — agent LLM qui applique la charte à chaque pattern brut avant stockage KB

**Phase 2 — Familles architecturales (V6 → V7)**
4. **Reverse engineering des familles** — analyser des projets GitHub par domaine, identifier les architectures de référence pour chaque famille (streaming, RAG, bot, marketplace...)
5. **Family Classifier** — agent qui classe un PRD dans une famille et charge l'architecture de référence correspondante
6. **Delta Analyzer** — identifie ce qui diffère de l'architecture de référence pour minimiser la génération from scratch

**Phase 3 — Généralisation (V7)**
7. **Étendre aux autres stacks** — Go/Gin, TypeScript/Express, Rust/Axum avec leurs propres chartes
8. **Suites de tests spécialisées** — tester un Discord bot, un serveur MCP, un pipeline ML de manière appropriée (pas juste schemathesis)
9. **Validation d'assemblage automatique** — contrats AST + cohérence OpenAPI avant de lancer les tests

---

## KB — Stockage : Qdrant (décision validée 28 mars 2026)

### Pourquoi Qdrant dès le départ

Qdrant a un mode **embedded local** (aucun Docker, aucun serveur) qui utilise exactement la même API Python que le mode serveur complet. La ligne qui change quand on passe en production :

```python
# V5/V6 — local embedded, zéro infrastructure
client = QdrantClient(path="./kb_qdrant")

# V7+ — server mode, même API, zéro changement de code
client = QdrantClient(url="http://localhost:6333", api_key="...")
```

Démarrer avec Qdrant évite toute migration future. Le code KB (scanner, extracteur, normaliseur, retriever) ne change pas entre les versions.

---

### Collections Qdrant

#### Collection `patterns` — patterns de features normalisés

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PayloadSchemaType,
    CreateCollection, HnswConfigDiff
)

client.create_collection(
    collection_name="patterns",
    vectors_config=VectorParams(
        size=384,           # all-MiniLM-L6-v2
        distance=Distance.COSINE,
    ),
    hnsw_config=HnswConfigDiff(
        m=16,               # qualité de l'index
        ef_construct=100,
    ),
)

# Index sur les champs de filtrage fréquents
client.create_payload_index("patterns", "feature_type",  PayloadSchemaType.KEYWORD)
client.create_payload_index("patterns", "framework",     PayloadSchemaType.KEYWORD)
client.create_payload_index("patterns", "language",      PayloadSchemaType.KEYWORD)
client.create_payload_index("patterns", "file_role",     PayloadSchemaType.KEYWORD)
```

**Payload par point :**

| Champ | Type | Valeurs possibles | Rôle |
|---|---|---|---|
| `feature_type` | keyword | `crud`, `auth_jwt`, `websocket`, `redis_pubsub`, `ml_inference`, `background_task`... | Filtre principal de query |
| `framework` | keyword | `fastapi`, `express`, `gin`, `axum` | Filtre stack |
| `language` | keyword | `python`, `typescript`, `go`, `rust` | Filtre langage |
| `file_role` | keyword | `models`, `routes`, `schemas`, `crud`, `tests`, `config`, `main` | Quel fichier ce pattern représente |
| `stack` | keyword | `fastapi+sqlalchemy+pydantic_v2`, `express+prisma`... | Stack complet |
| `normalized_code` | text | code Python/TS/Go/Rust normalisé | Le pattern lui-même |
| `source_repo` | text | URL GitHub | Traçabilité |
| `charte_version` | keyword | `1.0`, `1.1`... | Quelle version de la Charte a été appliquée |
| `created_at` | integer | timestamp Unix | Date d'ingestion |

---

#### Collection `architectures` — familles architecturales

```python
client.create_collection(
    collection_name="architectures",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

client.create_payload_index("architectures", "family", PayloadSchemaType.KEYWORD)
```

**Payload par point :**

| Champ | Type | Exemple |
|---|---|---|
| `family` | keyword | `rag_platform`, `streaming`, `bot_platform`, `marketplace`, `ai_chat` |
| `description` | text | Description de la famille |
| `reference_repos` | list[text] | URLs GitHub des repos de référence |
| `services` | list[text] | `["catalog_service", "streaming_service", "user_service"]` |
| `communication` | list[text] | `["REST", "Redis pub/sub", "WebSocket"]` |
| `base_patterns` | list[text] | feature_types toujours présents dans cette famille |

---

### Interface retriever — stable à travers les versions

```python
# kb/retriever.py
from dataclasses import dataclass
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

@dataclass
class Pattern:
    feature_type: str
    framework: str
    file_role: str
    normalized_code: str
    score: float

class QdrantRetriever:
    def __init__(self, path: str = "./kb_qdrant") -> None:
        self.client = QdrantClient(path=path)  # local V5/V6
        # self.client = QdrantClient(url="...", api_key="...")  # server V7+

    def search(
        self,
        feature_type: str,
        framework: str,
        embedding: list[float],
        limit: int = 5,
    ) -> list[Pattern]:
        results = self.client.search(
            collection_name="patterns",
            query_vector=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="feature_type", match=MatchValue(value=feature_type)),
                    FieldCondition(key="framework",    match=MatchValue(value=framework)),
                ]
            ),
            limit=limit,
        )
        return [
            Pattern(
                feature_type=r.payload["feature_type"],
                framework=r.payload["framework"],
                file_role=r.payload["file_role"],
                normalized_code=r.payload["normalized_code"],
                score=r.score,
            )
            for r in results
        ]

    def get_architecture(self, family: str) -> dict | None:
        results = self.client.search(
            collection_name="architectures",
            query_vector=[0.0] * 384,  # dummy — filtrage exact
            query_filter=Filter(
                must=[FieldCondition(key="family", match=MatchValue(value=family))]
            ),
            limit=1,
        )
        return results[0].payload if results else None
```

---

### Modèle d'embedding

`all-MiniLM-L6-v2` — local, ONNX, 384 dimensions, rapide, pas d'API externe.

```python
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(text: str) -> list[float]:
    return _model.encode(text, normalize_embeddings=True).tolist()
```

Alternative si qualité insuffisante : `nomic-embed-text` (768 dims, meilleur sur code) — changer `size=768` dans la collection.

---

### Structure fichiers KB

```
Wal-e Lab V5/
└── kb/
    ├── kb_qdrant/           ← données Qdrant (dossier géré par Qdrant, ne pas éditer)
    ├── retriever.py         ← interface stable (QdrantRetriever)
    ├── ingestor.py          ← pipeline scanner → extracteur → normaliseur → upsert
    └── embedder.py          ← wrapper SentenceTransformer
```

---

## Choix des LLM par agent

### Règle générale

Les LLMs ne sont pas interchangeables. Chaque type de tâche dans Wal-e a un profil différent : certaines nécessitent du raisonnement profond (génération, delta analysis), d'autres sont mécaniques et rapides (extraction, classification). Le coût doit être proportionnel à la valeur apportée.

### Recommandations par agent (état OpenRouter mars 2026)

| Agent | Modèle recommandé | Fallback | Justification |
|---|---|---|---|
| Generator | `qwen/qwen3-coder` 480B A35B ($0.22/$1.00) | MiMo-V2-Pro ($1/$3) | Génération de code — critère qualité prioritaire |
| Fixer | `qwen/qwen3-coder` 480B A35B ($0.22/$1.00) | — | Même profil que Generator |
| KB Normaliseur | `qwen/qwen3-coder` 480B A35B ($0.22/$1.00) | — | Réécriture de code selon la Charte |
| KB Extracteur | `mimo-vl/mimo-v2-flash` ($0.09/$0.29) | — | Labellisation répétitive — vitesse > profondeur |
| Delta Analyzer | `google/gemini-2.5-flash` ($0.30/$2.50) | — | Compréhension structurelle multi-fichiers |
| Family Classifier | `google/gemini-2.5-flash-lite` ($0.10/$0.40) | — | Classification courte, pas de génération |

**Remarque :** `qwen/qwen3-coder-plus` (utilisé en V5) est le prédécesseur de `qwen3-coder` 480B A35B. La V2 est moins chère et plus puissante — priorité au changement dès validation.

### Profils de tâches

**Tâches qualité-critique** (Generator, Fixer, Normaliseur) : le coût par token est secondaire face à la qualité du code généré. Un mauvais fix coûte plusieurs itérations de loop — bien plus cher qu'un modèle premium.

**Tâches volume-critique** (Extracteur) : tourne sur des dizaines de repos avec des centaines de patterns. Le coût s'accumule vite. Un modèle flash avec un prompt bien cadré suffit.

**Tâches compréhension-critique** (Delta Analyzer, Family Classifier) : nécessitent de comprendre la structure d'un projet entier, pas juste générer du code. Les modèles Gemini Flash ont un excellent rapport coût/contexte long.

---

## Méthodologie de sélection LLM — Tests personnels

Avant de valider les recommandations ci-dessus, tester personnellement 3 modèles en parallèle sur 3 tâches de difficulté croissante.

### Protocole

**3 tâches :**
1. **Tâche simple** — Générer un endpoint FastAPI CRUD minimal (1 entité, 5 routes)
2. **Tâche medium** — Générer un module d'authentification JWT complet (login, register, refresh, middleware)
3. **Tâche complexe** — Générer un pipeline de traitement async avec Redis Streams (producer, consumer, retry, dead-letter queue)

**3 modèles à tester en parallèle :**
- **Meilleur / plus cher** — MiMo-V2-Pro ($1/$3) ou le meilleur disponible au moment du test
- **Bon rapport qualité/prix** — qwen/qwen3-coder 480B A35B ($0.22/$1.00)
- **Low cost** — MiMo-V2-Flash ($0.09/$0.29) ou Gemini 2.5 Flash Lite ($0.10/$0.40)

**Critères d'évaluation :**
- Score Wal-e (Type A + B + C) — objectif : ≥ 80/100
- Nombre d'itérations nécessaires pour atteindre le score
- Coût total par tâche (tokens in + tokens out × tarif)
- Robustesse : le code compile-t-il dès la première génération ?

**Règle de décision personnelle :** Pour les tâches de génération de code et de compréhension (Generator, Fixer, Delta Analyzer), prendre le meilleur modèle même s'il est plus cher — le coût d'un mauvais output dépasse largement le delta de prix entre modèles. Pour les tâches mécaniques (Extracteur, Family Classifier), prendre le low cost si le score ne se dégrade pas.

### À documenter après les tests

- Quel modèle a atteint ≥ 80/100 sur les 3 tâches ?
- Quel modèle a le meilleur ratio score/coût ?
- Y a-t-il des tâches où le low cost suffit ?
- Mettre à jour le tableau "Recommandations par agent" avec les résultats réels
