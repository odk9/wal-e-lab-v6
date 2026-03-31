# Prompt Batch — 13 repos restants (full autonomie)

> Copier-coller ce prompt en entier dans Claude Code.

---

Tu es le KB Builder autonome de Wal-e Lab V6. Tu vas exécuter l'ingestion des **13 repos restants** de la matrice de test KB, un par un, en toute autonomie.

**AVANT TOUTE CHOSE :** Lis `CLAUDE.md` et `kb_utils.py` pour comprendre le projet, les règles Charte, et les utilitaires disponibles.

---

## WORKFLOW PAR REPO

Pour CHAQUE repo dans la liste ci-dessous, exécute ces étapes **dans l'ordre** :

### Étape 1 — Créer le script d'ingestion
Crée `ingest_<repo_slug>.py` en suivant **exactement** la structure des scripts existants (`ingest_node_express_boilerplate.py` ou `ingest_fastcrud.py`).

Le script DOIT contenir :
- Constantes en haut (REPO_URL, REPO_NAME, LANGUAGE, FRAMEWORK, STACK, TAG, etc.)
- `PATTERNS: list[dict]` — TOUS les patterns architecturaux réutilisables extraits du repo, normalisés Charte Wal-e
- `AUDIT_QUERIES: list[str]` — 5-10 queries sémantiques pertinentes pour le repo
- Fonctions : `clone_repo()`, `build_payloads()`, `index_patterns()`, `run_audit_queries()`, `audit_normalization()`, `cleanup()`, `main()`
- Import et utilisation de `kb_utils.py` : `build_payload()`, `check_charte_violations()`, `make_uuid()`, `query_kb()`, `audit_report()`
- `DRY_RUN = False` (production)

### Étape 2 — Extraction des patterns
**Clone le repo** (`git clone --depth=1`) et **lis les fichiers source** pour extraire les patterns.

Règles d'extraction :
- Extraire TOUS les patterns **par fonction** (pas de sampling arbitraire)
- Uniquement les patterns **architecturaux réutilisables** (modèles, routes, auth, middleware, services, tests, config)
- **PAS** d'intégrations API one-off (Stripe, Twilio, etc.) → les noter dans `api_patterns/API_INTEGRATIONS_CATALOG.md` à la place
- Normaliser selon la Charte Wal-e (U-5 entités → Xxx/xxx/xxxs, plus les règles spécifiques au langage)
- Supprimer tous les print/log de debug (U-7 / J-3 / G-2 / R-2)

### Étape 3 — Exécuter
```bash
.venv/bin/python3 ingest_<repo_slug>.py
```

### Étape 4 — Itérer si violations
Si le script retourne des violations ou FAIL :
1. Analyser la cause (faux positif TECHNICAL_TERMS ? entité non normalisée ? callback J-2 ?)
2. Corriger le script OU ajouter des termes dans `kb_utils.py` TECHNICAL_TERMS
3. Purger les points du repo (`FilterSelector` + `_tag`)
4. Relancer le script
5. Répéter jusqu'à **PASS avec 0 violations**
6. **LOGGER CHAQUE FIX** dans `FIX_LOG.md` (voir format ci-dessous)

### Étape 5 — Commit + push
```bash
git add ingest_<repo_slug>.py
# + kb_utils.py si modifié
# + api_patterns/API_INTEGRATIONS_CATALOG.md si complété
git commit -m "feat: ingest <repo_name> — <N> <LANG> <LEVEL> KB patterns"
git push
```

### Étape 6 — Passer au repo suivant

---

## FIX_LOG.md — Format obligatoire

Crée le fichier `FIX_LOG.md` à la racine du projet **avant de commencer**. Pour chaque fix, ajoute une entrée :

```markdown
## [REPO] owner/repo-name (LANG LEVEL)

### Fix N — [TITRE COURT]
- **Violation** : [message exact de la violation]
- **Cause** : [explication : faux positif / entité non normalisée / règle trop stricte / etc.]
- **Fichier modifié** : [ingest_xxx.py / kb_utils.py]
- **Action** : [ce qui a été changé]
- **Itération** : [numéro de la tentative où le fix a été appliqué]
- **Résultat** : PASS / encore des violations → itération suivante
```

Si aucun fix n'est nécessaire (PASS du premier coup), noter :
```markdown
## [REPO] owner/repo-name (LANG LEVEL)
Aucun fix nécessaire. PASS au premier run.
```

---

## LES 13 REPOS — DANS L'ORDRE

### ═══ 1. JS C — sahat/hackathon-starter ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/sahat/hackathon-starter.git` |
| LANGUAGE | `javascript` |
| FRAMEWORK | `express` |
| STACK | `express+mongoose+passport_multi+nodemailer+webauthn` |
| TAG | `sahat/hackathon-starter` |

**Architecture :** MVC monolithique, controller direct. Passport local + 8 OAuth via shared `handleAuthLogin()`.
**Patterns clés à extraire :** Mongoose schema complexe (auth tokens, 2FA, WebAuthn, OAuth providers, profile), virtuals (expiration), multiple pre-save hooks (bcrypt, token cleanup, gravatar), timing-safe token verification (crypto.timingSafeEqual), IP hashing, Passport local + shared OAuth handler + isAuthenticated + isAuthorized, login (password + passwordless), 2FA (email code + TOTP), WebAuthn passkeys (challenge-response), password reset, email verify, OAuth unlink + token revocation, multi-tier rate limiting, session MongoStore + CSRF Lusca, contact form reCAPTCHA.
**ATTENTION :** `console.log(err)` dans `verifyTokenAndIp` → supprimer (J-3). Nombreux `function()` avec this-binding Mongoose → exemptés par J-2 fix.
**EXCLURE :** 30+ intégrations API one-off (Stripe, Twilio, Foursquare, etc.) → noter dans `api_patterns/API_INTEGRATIONS_CATALOG.md`.

---

### ═══ 2. TS A — w3tecch/express-typescript-boilerplate ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/w3tecch/express-typescript-boilerplate.git` |
| LANGUAGE | `typescript` |
| FRAMEWORK | `express` |
| STACK | `express+typeorm+typedi+typescript` |
| TAG | `w3tecch/express-typescript-boilerplate` |

**Architecture :** Express + TypeORM + TypeDI (dependency injection) + TypeGraphQL. 3 couches : Controller → Service → Repository.
**Patterns clés :** TypeORM entities (decorators @Entity, @Column, @PrimaryGeneratedColumn), repositories, services avec DI (@Service, @Inject), controllers avec decorators, custom decorators (@Logger, @EventDispatch), middleware auth, error handling, factory pattern (DB seeding + Faker), migration patterns, GraphQL resolvers, event dispatching.
**Règles TS :** T-1 (pas de `any`), T-2 (pas de `var`), T-3 (pas de `console.log`).

---

### ═══ 3. TS B — gothinkster/node-express-realworld-example-app ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/gothinkster/node-express-realworld-example-app.git` |
| LANGUAGE | `typescript` |
| FRAMEWORK | `express` |
| STACK | `express+prisma+jwt+typescript` |
| TAG | `gothinkster/node-express-realworld-example-app` |

**Architecture :** Express + Prisma ORM + JWT. RealWorld spec (Conduit).
**Patterns clés :** Prisma schema + client, JWT auth middleware, CRUD articles/comments/users/tags, favoriting, following, feed, error handling, e2e tests.
**ATTENTION :** Ce repo a changé au fil du temps. Cloner et vérifier la structure actuelle avant d'extraire.

---

### ═══ 4. TS C — nestjs/nest ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/nestjs/nest.git` |
| LANGUAGE | `typescript` |
| FRAMEWORK | `nestjs` |
| STACK | `nestjs+typescript+decorators+di` |
| TAG | `nestjs/nest` |

**Architecture :** Framework complet (monorepo Lerna). Angular-inspired : Modules, Controllers, Services, Pipes, Guards, Interceptors, Middleware.
**Patterns clés :** C'est un FRAMEWORK, pas une app. Extraire les patterns du dossier `sample/` ou `integration/` — les exemples d'utilisation. Patterns : Module decorator, Controller decorator + route handlers, Injectable services, Guards (auth), Pipes (validation), Interceptors (logging, transform), Exception filters, Middleware, DTOs.
**ATTENTION :** Monorepo complexe. Se concentrer sur `packages/common/`, `packages/core/`, et surtout les `sample/` pour les patterns d'utilisation.

---

### ═══ 5. Go A — eddycjy/go-gin-example ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/eddycjy/go-gin-example.git` |
| LANGUAGE | `go` |
| FRAMEWORK | `gin` |
| STACK | `gin+gorm+jwt+redis` |
| TAG | `eddycjy/go-gin-example` |

**Architecture :** Gin + GORM + JWT + Redis. Blog API (articles + tags + auth).
**Patterns clés :** GORM models (Article, Tag, Auth) avec soft delete, Gin route handlers, JWT middleware, Redis caching, pagination, file upload, error codes, config (go-ini), service layer.
**Règles Go :** G-1 (pas de `panic` sauf init), G-2 (pas de `fmt.Println/Printf`).
**Normalisation U-5 Go :** `Article` → `Xxx`, `Tag` → `XxxLabel`, `Auth` → `XxxAuth`. Garder `gin`, `gorm`, `jwt`, `redis` comme termes techniques.

---

### ═══ 6. Go B — ThreeDotsLabs/wild-workouts-go-ddd-example ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example.git` |
| LANGUAGE | `go` |
| FRAMEWORK | `gin` |
| STACK | `go+ddd+cqrs+grpc+firestore` |
| TAG | `ThreeDotsLabs/wild-workouts-go-ddd-example` |

**Architecture :** DDD + Clean Architecture + CQRS. Microservices (trainer, trainings, users). gRPC + REST. Firestore.
**Patterns clés :** Domain entities, value objects, repositories (interface + impl), CQRS commands/queries, application services, ports & adapters, gRPC service definitions, HTTP handlers, Firebase auth middleware, decorator pattern (logging, metrics), tests avec mocks.
**ATTENTION :** Monorepo multi-services. Extraire les patterns DDD/CQRS qui sont réutilisables, pas la logique métier spécifique (workouts, trainings).

---

### ═══ 7. Go C — bxcodec/go-clean-arch ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/bxcodec/go-clean-arch.git` |
| LANGUAGE | `go` |
| FRAMEWORK | `echo` |
| STACK | `go+clean_arch+mysql` |
| TAG | `bxcodec/go-clean-arch` |

**Architecture :** Clean Architecture (Uncle Bob). 4 couches : Domain, Repository, Usecase, Delivery.
**Patterns clés :** Domain interfaces (Repository, Usecase), MySQL repository impl, HTTP delivery (handlers), usecase impl, middleware (CORS, logging), context propagation, error handling, mock generation (mockery), tests unitaires.
**NOTE :** Le framework HTTP peut être Echo ou net/http standard — vérifier en clonant.

---

### ═══ 8. Rust A — tokio-rs/axum (examples/) ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/tokio-rs/axum.git` |
| LANGUAGE | `rust` |
| FRAMEWORK | `axum` |
| STACK | `axum+tokio+tower+sqlx` |
| TAG | `tokio-rs/axum` |

**Architecture :** Framework Axum — extraire les patterns depuis le dossier `examples/`.
**Patterns clés :** Route handlers (GET/POST/PUT/DELETE), extractors (Path, Query, Json, State), middleware Tower, error handling (IntoResponse), shared state (Arc<AppState>), graceful shutdown, static files, WebSocket, CORS, tracing/logging, SQLx database, auth (JWT ou sessions), tests.
**ATTENTION :** C'est un framework, pas une app. Se concentrer sur `examples/` pour les patterns d'utilisation concrets.
**Règles Rust :** R-1 (pas de `.unwrap()` sauf tests), R-2 (pas de `println!`).

---

### ═══ 9. Rust B — maxcountryman/axum-login ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/maxcountryman/axum-login.git` |
| LANGUAGE | `rust` |
| FRAMEWORK | `axum` |
| STACK | `axum+tower_sessions+sqlx` |
| TAG | `maxcountryman/axum-login` |

**Architecture :** Auth library pour Axum. Tower middleware.
**Patterns clés :** AuthUser trait, AuthnBackend trait (authenticate + get_user), AuthzBackend trait (permissions), AuthSession extractor, login_required macro, permission_required macro, session management (tower-sessions), SQLite/Postgres backends, protected routes, role-based access.
**Se concentrer sur** les `examples/` et les traits publics qui définissent le contrat d'auth.

---

### ═══ 10. Rust C — shuttle-hq/shuttle ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/shuttle-hq/shuttle.git` |
| LANGUAGE | `rust` |
| FRAMEWORK | `axum` |
| STACK | `axum+shuttle+sqlx+tokio` |
| TAG | `shuttle-hq/shuttle` |

**Architecture :** Platform de déploiement Rust. Monorepo.
**Patterns clés :** Attribute macros (`#[shuttle_runtime::main]`), resource injection (`#[shuttle_shared_db::Postgres]`), async service trait, error handling (Result + ? operator), SQLx migrations, Axum route setup, config management, integration patterns.
**ATTENTION :** Monorepo très large. Se concentrer sur `examples/` et `resources/` pour les patterns réutilisables, pas l'infra de déploiement.

---

### ═══ 11. C++ A — crowcpp/Crow ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/CrowCpp/Crow.git` |
| LANGUAGE | `cpp` |
| FRAMEWORK | `crow` |
| STACK | `crow+cpp17` |
| TAG | `crowcpp/Crow` |

**Architecture :** Header-only C++ microframework, Flask-like.
**Patterns clés :** Route macros (CROW_ROUTE), lambda handlers, JSON read/write (crow::json), Mustache templating, middleware pattern, WebSocket handlers, multipart parsing, static file serving, Blueprint (modular routing), HTTPS/SSL setup.
**NOTE :** Pas de Charte C++ spécifique encore → appliquer uniquement U-* (universelles). Pas de règles C-* dans kb_utils.py.

---

### ═══ 12. C++ B — drogonframework/drogon ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/drogonframework/drogon.git` |
| LANGUAGE | `cpp` |
| FRAMEWORK | `drogon` |
| STACK | `drogon+orm+cpp17` |
| TAG | `drogonframework/drogon` |

**Architecture :** Framework C++17 async. ORM intégré, non-blocking IO.
**Patterns clés :** HttpController (macro-based routing), HttpSimpleController, WebSocketController, Filter chains (auth, validation), ORM mapper (auto-generated), async callbacks/coroutines, JSON handling, file upload, session management, middleware, drogon_ctl scaffolding, config (JSON).
**Se concentrer sur** les `examples/` et `lib/tests/` pour les patterns d'utilisation.

---

### ═══ 13. C++ C — uNetworking/uWebSockets ═══

| Clé | Valeur |
|---|---|
| REPO_URL | `https://github.com/uNetworking/uWebSockets.git` |
| LANGUAGE | `cpp` |
| FRAMEWORK | `uwebsockets` |
| STACK | `uwebsockets+libuv+openssl` |
| TAG | `uNetworking/uWebSockets` |

**Architecture :** HTTP + WebSocket ultra-performant. Low-level.
**Patterns clés :** App setup (listen + route), HTTP handlers (GET/POST), WebSocket handlers (open/message/close/drain), pub/sub, streaming responses, SSL/TLS config, URL routing (wildcards, params), per-socket data, backpressure handling.
**NOTE :** Très bas niveau. Moins de patterns "architecturaux" au sens classique mais des patterns réseau/WebSocket uniques.

---

## RÈGLES PAR LANGAGE — Rappel

| Langage | Règles | Détail |
|---|---|---|
| JavaScript | J-1, J-2, J-3 | var→const/let, callbacks (avec exemptions this-binding), console.log |
| TypeScript | T-1, T-2, T-3 | any interdit, var→const/let, console.log |
| Go | G-1, G-2 | panic interdit (sauf init), fmt.Print interdit |
| Rust | R-1, R-2 | .unwrap() interdit (sauf tests), println! interdit |
| C++ | U-* uniquement | Pas de règles C-* spécifiques encore |

---

## NORMALISATION U-5 — Rappel par langage

**Principe :** Remplacer les noms d'entités métier par `Xxx`/`xxx`/`xxxs`. Garder les termes techniques (noms de lib, champs génériques, méthodes standard).

**Entités secondaires :** Si un repo a 2+ entités, utiliser des suffixes :
- Entité principale → `Xxx`
- Entité secondaire → `XxxLabel`, `XxxComment`, `XxxToken`, etc.
- Choisir un suffixe descriptif du rôle

---

## TECHNICAL_TERMS — Anticiper les faux positifs

Les termes techniques déjà dans kb_utils.py couvrent Python et JavaScript. Pour les nouveaux langages, tu devras probablement ajouter :

**Go :** `http.Handler`, `gin.Context`, `gorm.Model`, `gorm.DB`, `.Order(`, `c.JSON(`, `c.Param(`, `c.Query(`
**Rust :** `impl`, `pub fn`, `#[derive(`, `async fn`, `-> Result<`, `.await`, `axum::Router`, `tower::Service`
**TypeScript :** `@Injectable()`, `@Controller()`, `@Module()`, `@Get()`, `@Post(`, `interface `, `type `
**C++ :** `CROW_ROUTE`, `::json`, `::request`, `::response`, `std::`, `#include`, `namespace`

Ajoute au TECHNICAL_TERMS de kb_utils.py **au fur et à mesure** que tu rencontres des faux positifs. Logge chaque ajout dans FIX_LOG.md.

---

## api_patterns/API_INTEGRATIONS_CATALOG.md

Le fichier existe déjà avec les intégrations de `sahat/hackathon-starter`. Si tu trouves d'autres intégrations API one-off dans les repos suivants (peu probable pour Go/Rust/C++ mais possible), ajoute-les au fichier au même format.

---

## VÉRIFICATION FINALE

Après les 13 repos, lance un check global :

```bash
.venv/bin/python3 -c "
from qdrant_client import QdrantClient
c = QdrantClient(path='./kb_qdrant')
print(f'Total patterns: {c.count(collection_name=\"patterns\").count}')

# Count par tag
from qdrant_client.models import FieldCondition, Filter, MatchValue, ScrollRequest
tags = {}
offset = None
while True:
    result = c.scroll(collection_name='patterns', limit=100, offset=offset, with_payload=True)
    points, next_offset = result
    for p in points:
        tag = p.payload.get('_tag', '?')
        lang = p.payload.get('language', '?')
        tags[tag] = tags.get(tag, 0) + 1
    if next_offset is None:
        break
    offset = next_offset

for tag, count in sorted(tags.items()):
    print(f'  {tag}: {count}')
"
```

Note le résultat dans FIX_LOG.md en bas dans une section `## RÉSUMÉ FINAL`.

Puis commit final :
```bash
git add FIX_LOG.md api_patterns/API_INTEGRATIONS_CATALOG.md
git commit -m "docs: FIX_LOG + API catalog — 18 repos test matrix complete"
git push
```

---

## RÉSUMÉ DE L'ÉTAT ACTUEL DE LA KB

```
patterns : 199 points
  ├── Python A  — igorbenav/fastcrud                    35  ✅
  ├── Python B  — fastapi/full-stack-fastapi-template   60  ✅
  ├── Python C  — fastapi-users/fastapi-users           45  ✅
  ├── JS A      — madhums/node-express-mongoose-demo    31  ✅
  └── JS B      — hagopj13/node-express-boilerplate     28  ✅
architectures : 0 points
```

Tu reprends à partir de **JS C — sahat/hackathon-starter**. Bonne chance.
