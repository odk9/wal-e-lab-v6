# TABLEAU DE BORD — Wal-e Lab V6
> Suivi complet des tâches, problèmes, solutions et impacts.
> Mis à jour en continu à chaque session.

---

## 29 mars 2026

---

### TÂCHE 1 — Analyse V5 + lecture docs V6
**Statut :** ✅ Terminée
**Approche :** Lecture des fichiers `CLAUDE.md`, `WAL-E_V6_KB_ARCHITECTURE.md`, `WAL-E_CHARTE_PYTHON_FASTAPI.md` présents dans `Document/`.

**Ce qu'on a appris :**
- V5 atteignait 99/100 sur un CRUD simple mais les patterns étaient hardcodés dans le SYSTEM_PROMPT — non généralisable à d'autres projets
- V6 corrige ça avec une KB feature-level (Qdrant), des agents KB (Scanner + Extracteur + Normaliseur), la Charte Wal-e, et deux nouveaux agents pipeline (Family Classifier + Delta Analyzer)
- Le modèle d'embedding préconisé dans le doc : `all-MiniLM-L6-v2` ONNX (384 dims)
- Stockage KB : Qdrant embedded local (même API que le mode serveur V7+)

**Problèmes :** Aucun.
**Impact :** Base de compréhension solide avant toute action.

---

### TÂCHE 2 — Préparation environnement GitHub
**Statut :** ✅ Terminée
**Approche :** Création du repo `odk9/wal-e-lab-v6` via GitHub API (curl + token), initialisation git dans un dossier staging `/sessions/v6_staging/`.

**Problème P1 — Filesystem monté en lecture seule pour `rm`**
- **Cause :** Les fichiers créés dans `/mnt/Wal-e Lab V6/` sont propriété d'un autre utilisateur système. `rm` retourne `Operation not permitted`.
- **Solution :** Utilisation de l'outil `allow_cowork_file_delete` pour obtenir les permissions, puis `rm` fonctionne.
- **Impact :** Toutes les suppressions futures dans le dossier V6 nécessitent cette étape préalable.

**Problème P2 — `git add` bloqué par `index.lock`**
- **Cause :** Le dossier `.git` initialisé directement dans `/mnt/Wal-e Lab V6/` hérite des restrictions du filesystem monté. Le fichier `index.lock` ne peut pas être supprimé.
- **Lié à :** P1 (même cause racine — filesystem monté avec restrictions).
- **Solution :** Travailler dans un dossier staging temporaire (`/sessions/sweet-practical-fermi/v6_staging/`), `rsync` vers le staging, commit et push depuis là.
- **Impact :** Workflow établi pour tous les commits futurs : modifications dans `/mnt/Wal-e Lab V6/` → `cp` ou `rsync` vers `v6_staging/` → commit → push.

---

### TÂCHE 3 — Première tentative : création de la structure V6 complète
**Statut :** ❌ Annulée sur demande
**Approche :** Création de tous les fichiers V6 en une seule fois (pipeline, KB, nodes...).

**Problème P3 — Travail trop anticipé**
- **Cause :** Anticipation de l'architecture complète sans validation étape par étape.
- **Solution :** Tout supprimer, repartir à zéro, avancer une étape à la fois.
- **Impact :** Méthode de travail redéfinie — une tâche à la fois, validation avant de passer à la suivante. Repo GitHub remis à zéro (README minimal).

---

### TÂCHE 4 — Installation Qdrant
**Statut :** ✅ Terminée
**Approche :** Création d'un venv Python 3.10 avec `uv`, installation de `qdrant-client` via `uv pip install qdrant-client`.

**Résultat :** `qdrant-client 1.17.1` installé. Test de validation : création collection → insert `PointStruct` → count → nettoyage. ✅

**Problème P4 — Syntaxe `PointStruct` incorrecte au premier test**
- **Cause :** Test initial utilisait un `dict` nu au lieu de `PointStruct(id=..., vector=...)`.
- **Solution :** Correction immédiate vers la syntaxe `PointStruct`.
- **Impact :** Aucun impact durable — erreur de test corrigée avant toute utilisation réelle.

**Commit :** —
**Impact :** Qdrant embedded local opérationnel, aucun Docker requis.

---

### TÂCHE 5 — Création des collections Qdrant
**Statut :** ✅ Terminée (avec modification en cours de route — voir T7)
**Approche :** Écriture de `setup_collections.py` définissant les 2 collections :
- `patterns` : HNSW m=16/ef_construct=100, 4 index payload (feature_type, framework, language, file_role)
- `architectures` : simple, 1 index payload (family)

**Premier run :** Collections créées en **384 dims** (modèle préconisé dans le doc V6).
**Commit initial :** `feat: add setup_collections.py — collections Qdrant patterns + architectures`

**Découverte en T7 :** Les 384 dims correspondaient à `all-MiniLM-L6-v2` qui tronque à 256 tokens — insuffisant pour des blocs de code. Collections recréées en 768 dims après choix du nouveau modèle.
**Commit final :** `feat: collections 768 dims — nomic-embed-text-v1.5-Q (8192 tokens, no truncation)`

---

### TÂCHE 6 — Choix du modèle d'embedding
**Statut :** ✅ Terminée
**Approche :** Évaluation de 3 options — `sentence-transformers` (PyTorch, lourd), ONNX from scratch (manuel), `fastembed` (Qdrant, ONNX, léger).

**Décision initiale :** `fastembed` + `all-MiniLM-L6-v2` (384 dims, 90MB).

**Problème P5 — Troncature à 256 tokens**
- **Cause :** `all-MiniLM-L6-v2` tronque à 256 tokens. Un fichier `routes.py` FastAPI dépasse facilement ça.
- **Découvert lors de :** Vérification des specs du modèle via `TextEmbedding.list_supported_models()`.
- **Solution :** Changement de modèle → `nomic-ai/nomic-embed-text-v1.5-Q` (768 dims, 8192 tokens, 130MB ONNX quantizé).
- **Impact :** Collections recréées en 768 dims. Pas de troncature possible sur n'importe quel bloc de code.

**Modèle retenu :** `nomic-ai/nomic-embed-text-v1.5-Q`
- 768 dimensions
- 8192 tokens max (aucune troncature)
- 130MB (ONNX quantizé, pas de PyTorch)
- Prefixes obligatoires : `"search_document: "` pour indexer, `"search_query: "` pour chercher

---

### TÂCHE 7 — Création de embedder.py
**Statut :** ✅ Terminée
**Approche :** Wrapper autour de `fastembed` avec :
- Singleton du modèle (chargé une seule fois)
- Normalisation L2 systématique
- Prefixes gérés en interne (`embed_document` / `embed_query`)
- Fonction batch `embed_documents_batch` pour l'ingesteur

**Problème P6 — Vecteurs non normalisés par fastembed**
- **Cause :** `fastembed` retourne des vecteurs bruts non normalisés (norme = 18.35 dans nos tests). La distance cosine dans Qdrant suppose des vecteurs normalisés.
- **Découvert lors de :** Test de similarité cosine — résultat `260.41` au lieu d'une valeur entre -1 et 1.
- **Solution :** Normalisation L2 manuelle (`vec / np.linalg.norm(vec)`) dans `embedder.py`. Norme post-normalisation = 1.000000 ✅
- **Impact :** Tous les appels à `embed_document()` et `embed_query()` retournent des vecteurs normalisés. La similarité cosine est correcte (0.0 → 1.0).

**Tests de validation :**
- Norme = 1.000000 ✅
- Dimension = 768 ✅
- Similarité CRUD FastAPI vs query CRUD : 0.7208 ✅
- Similarité CRUD FastAPI vs query Discord bot : 0.5120 ✅
- Delta = 0.2088 → bonne discriminabilité ✅
- Batch 3 items, normes OK ✅

**Commit :** `feat: embedder.py — nomic-embed-text-v1.5-Q, normalisation L2, prefixes document/query`

---

### TÂCHE 8 — Test bout en bout : insert → search → cleanup
**Statut :** ✅ Terminée
**Approche :** Script `test_kb.py` avec 4 patterns manuels (crud, database_setup, auth_jwt, websocket), insert, search, cleanup par tag `_TAG_EPHEMERE`.

**Problème P7 — `client.search()` n'existe plus**
- **Cause :** `qdrant-client 1.17.1` a retiré la méthode `search()`. La nouvelle API est `query_points()`.
- **Lié à :** TÂCHE 4 — le choix de `qdrant-client 1.17.1` (dernière version) implique l'API la plus récente.
- **Solution :** Remplacement de `client.search(...)` par `client.query_points(..., with_payload=True).points`.
- **Impact :** À retenir pour `retriever.py` — utiliser systématiquement `query_points()`.

**Problème P8 — Points résiduels après crash**
- **Cause :** Premier run du test a crashé sur P7 avant d'atteindre le cleanup → 4 points orphelins en KB.
- **Lié à :** P7 (crash interrompu avant cleanup).
- **Solution :** Cleanup par filtre sur `_tag` (FilterSelector) plutôt que par liste d'IDs. Robuste même si le process est interrompu.
- **Impact :** Pattern de cleanup par tag adopté pour tous les tests futurs.

**Résultats finaux :**
- crud : score=0.7082, retourné=crud ✅
- auth_jwt : score=0.7289, retourné=auth_jwt ✅
- database_setup : score=0.7612, retourné=database_setup ✅
- websocket : score=0.6349, retourné=websocket ✅
- KB après nettoyage : 0 points ✅

**Fichier `test_kb.py` supprimé après validation** — ne pollue pas la KB ni le repo.

---

### TÂCHE 9 — Définition de la matrice de repos de test
**Statut :** ✅ Terminée
**Approche :** Définir 3 candidats (Simple/Medium/Hard) par langage pour tester la plomberie KB de bout en bout.

**Langages retenus :** Python, JavaScript, TypeScript, Go, Rust, C++ (KB uniquement).
**C++ décision :** KB only pour l'instant — le pipeline complet (génération + évaluation) nécessite des outils spécifiques (clang-tidy, cmake, catch2) qui seront adressés quand Wal-e sera fonctionnel à 100%.

**Problème P9 — 6 repos invalides dans la première proposition**
- `igorbenav/fastcrud` → redirect (repo existe mais déplacé, confirmé via `-L`)
- `tiangolo/full-stack-fastapi-template` → déplacé vers `fastapi/full-stack-fastapi-template`
- `microsoft/TypeScript-Node-Starter` → Not Found (repo supprimé)
- `qiangxue/go-restful-api` → Not Found
- `davidpdrsn/axum-login` → Not Found (déplacé vers `maxcountryman/axum-login`)
- `nicowillis/uWebSockets` → Not Found (bon repo : `uNetworking/uWebSockets`)
- `goldbergyoni/nodebestpractices` → documentation pure, pas de code extractable
- JS B et C → mauvais repos (TypeScript détecté, ou documentation)
- **Solution :** Vérification systématique via GitHub API pour chaque repo, remplacement des invalides.

**Matrice finale validée :**

| | A — Simple | B — Medium | C — Hard |
|---|---|---|---|
| Python | `igorbenav/fastcrud` | `fastapi/full-stack-fastapi-template` | `fastapi-users/fastapi-users` |
| JavaScript | `madhums/node-express-mongoose-demo` | `hagopj13/node-express-boilerplate` | `sahat/hackathon-starter` |
| TypeScript | `w3tecch/express-typescript-boilerplate` | `gothinkster/node-express-realworld-example-app` | `nestjs/nest` |
| Go | `eddycjy/go-gin-example` | `ThreeDotsLabs/wild-workouts-go-ddd-example` | `bxcodec/go-clean-arch` |
| Rust | `tokio-rs/axum` (examples) | `maxcountryman/axum-login` | `shuttle-hq/shuttle` |
| C++ (KB) | `crowcpp/Crow` | `drogonframework/drogon` | `uNetworking/uWebSockets` |

---

## État actuel du projet

### Fichiers en place
```
Wal-e Lab V6/
├── .venv/                  ✅ Python 3.10, qdrant-client 1.17.1, fastembed
├── kb_qdrant/              ✅ Collections patterns + architectures (768 dims, vides)
├── setup_collections.py    ✅ Committé sur GitHub
├── embedder.py             ✅ Committé sur GitHub
└── Document/               📄 Docs de référence V6 (non modifiés)
```

### GitHub
- Repo : https://github.com/odk9/wal-e-lab-v6
- Commits : 4
  1. `chore: reset — repo prêt pour le développement V6`
  2. `feat: add setup_collections.py — collections Qdrant patterns + architectures`
  3. `feat: collections 768 dims — nomic-embed-text-v1.5-Q (8192 tokens, no truncation)`
  4. `feat: embedder.py — nomic-embed-text-v1.5-Q, normalisation L2, prefixes document/query`

### Décisions techniques validées
| Décision | Valeur |
|---|---|
| Vector DB | Qdrant embedded local (`./kb_qdrant/`) |
| Modèle embedding | `nomic-ai/nomic-embed-text-v1.5-Q` |
| Dimensions | 768 |
| Tokens max | 8192 (pas de troncature) |
| Normalisation | L2 manuelle dans `embedder.py` |
| API Qdrant search | `query_points()` (client 1.17+) |
| Cleanup tests | Par tag `FilterSelector` |

### Prochaine étape
Test de la plomberie sur un vrai repo — **Python A : `igorbenav/fastcrud`**.
Ordre complet : Python A → B → C → JavaScript A → B → C → TypeScript → Go → Rust → C++

---

## Légende

| Symbole | Signification |
|---|---|
| ✅ | Terminé et validé |
| 🔲 | À faire |
| ❌ | Annulé ou échoué |
| ⚠️ | Point d'attention |
| P1, P2... | Référence à un problème documenté |
