Tu es le KB Builder autonome de Wal-e Lab V6. Tu exécutes l'ingestion de 3 repos Go (Go A, Go B, Go C).

**PREMIÈRE CHOSE :** Lis CLAUDE.md et kb_utils.py. Lis aussi un script existant (ingest_node_express_boilerplate.py) comme template de structure. Lis FIX_LOG.md pour voir l'état des sessions précédentes.

---

## WORKFLOW PAR REPO

Pour CHAQUE repo :

1. **Clone** le repo (`git clone --depth=1 <URL> /tmp/<slug>`)
2. **Lis les fichiers source** pour identifier les patterns architecturaux réutilisables
3. **Crée** `ingest_<slug>.py` avec la même structure que les scripts existants :
   - Constantes (REPO_URL, REPO_NAME, LANGUAGE, FRAMEWORK, STACK, TAG, DRY_RUN=False, KB_PATH, COLLECTION, SOURCE_REPO)
   - PATTERNS: list[dict] — code normalisé Charte Wal-e (U-5 : entités→Xxx/xxx, + règles langage)
   - AUDIT_QUERIES: list[str] — 5-10 queries sémantiques
   - Fonctions : clone_repo, build_payloads, index_patterns, run_audit_queries (avec query_kb()), audit_normalization, cleanup, main
   - Imports de kb_utils.py
4. **Exécute** : `.venv/bin/python3 ingest_<slug>.py`
5. **Si violations :** corrige → purge tag → relance → itère jusqu'à PASS. Logge chaque fix dans FIX_LOG.md :
   ```
   ## [REPO] owner/repo (LANG LEVEL)
   ### Fix N — TITRE
   - Violation : message exact
   - Cause : explication
   - Action : ce qui a été changé
   - Résultat : PASS / FAIL
   ```
6. **Commit + push** chaque repo individuellement

**Règles Go (G-\*) :**
- G-1 : pas de `panic()` sauf dans `func init()`
- G-2 : pas de `fmt.Println()` / `fmt.Printf()` — utiliser `log.Logger`
- U-5 : entités métier → Xxx/xxx. Garder : gin, gorm, http, context, error, interface noms de lib.

**TECHNICAL_TERMS Go à anticiper :**
Si des faux positifs apparaissent, ajouter dans kb_utils.py. Exemples probables : `http.Handler`, `gin.Context`, `gorm.Model`, `.Order(`, `c.JSON(`, `c.Param(`, `c.Query(`, `c.PostForm(`, `context.Context`, `error`, `interface{}`, `func (`, `go func(`.

---

## REPO 1 : Go A — eddycjy/go-gin-example

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/eddycjy/go-gin-example.git |
| LANGUAGE | go |
| FRAMEWORK | gin |
| STACK | gin+gorm+jwt+redis |
| TAG | eddycjy/go-gin-example |

**Architecture :** Blog API. Gin + GORM + JWT + Redis. Structure : models/, routers/, pkg/, middleware/, service/, conf/.

**Patterns à extraire (~25-30) :**
- Models GORM : Article (title, desc, content, cover, state, tag_id + foreign key), Tag (name, state, created_by, modified_by), Auth (username, password). Soft delete. Hooks (BeforeCreate, BeforeUpdate).
- Routes Gin : router.Group, middleware chains, route handlers (GET/POST/PUT/DELETE)
- Controllers/handlers : CRUD articles, CRUD tags, auth (get token), file upload
- Service layer : article service, tag service, cache service
- JWT middleware : GenerateToken, ParseToken, middleware handler
- Redis caching : get/set patterns
- Pagination : offset + limit
- Response formatting : code + msg + data pattern (error codes)
- Config : go-ini file parsing
- File upload : image validation + save
- Logging : file-based logger setup
- Validation : gin binding + custom validators

**U-5 Go :** Article→Xxx, Tag→XxxLabel, Auth→XxxAuth. `article_id` → `xxx_id`, `tag_id` → `xxx_label_id`. Garder : gin, gorm, jwt, redis, context, error.

---

## REPO 2 : Go B — ThreeDotsLabs/wild-workouts-go-ddd-example

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example.git |
| LANGUAGE | go |
| FRAMEWORK | chi |
| STACK | go+ddd+cqrs+grpc+firestore |
| TAG | ThreeDotsLabs/wild-workouts-go-ddd-example |

**Architecture :** DDD + Clean Architecture + CQRS. Monorepo multi-services (trainer, trainings, users). gRPC + REST. Firestore.

**ATTENTION :** Clone et vérifie la structure. Le framework HTTP peut être chi, echo, ou net/http — ajuste FRAMEWORK et STACK selon ce que tu trouves.

**Patterns à extraire (~25-35) :**
- Domain entities + value objects (types Go + méthodes)
- Repository interfaces (ports) + implementations (adapters)
- CQRS : Command handlers, Query handlers, Command/Query objects
- Application services (use cases)
- HTTP handlers (delivery layer)
- gRPC service definitions + handlers (si proto files)
- Firebase/Firestore auth middleware
- Decorator pattern (logging, metrics wrapping)
- DI wiring (main.go / wire)
- Error handling patterns (domain errors, HTTP error mapping)
- Tests avec mocks/fakes

**U-5 Go :** Trainer→Xxx, Training→XxxSession, User→XxxUser (ou Xxx selon l'entité principale). Adapter selon ce qui est dans le repo.
**EXCLURE :** La logique métier spécifique (workout scheduling, etc.) — garder les PATTERNS architecturaux (DDD, CQRS, ports/adapters).

---

## REPO 3 : Go C — bxcodec/go-clean-arch

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/bxcodec/go-clean-arch.git |
| LANGUAGE | go |
| FRAMEWORK | echo |
| STACK | go+clean_arch+mysql |
| TAG | bxcodec/go-clean-arch |

**Architecture :** Clean Architecture (Uncle Bob). 4 couches : Domain → Repository → Usecase → Delivery.

**ATTENTION :** Clone et vérifie. Le framework HTTP peut être echo ou net/http standard. Aussi vérifie si c'est v1, v2, v3 ou v4 sur master. Ajuste FRAMEWORK et STACK.

**Patterns à extraire (~15-20) :**
- Domain : interfaces Repository + Usecase (dans domain/ ou models/)
- Repository MySQL implementation (GORM ou database/sql)
- Usecase implementation (business logic layer)
- HTTP delivery handlers (controller/handler)
- Middleware (CORS, logging, request ID)
- Context propagation (context.Context à travers les couches)
- Error handling (domain errors → HTTP status)
- Mocks (mockery generated ou manual)
- Tests unitaires (usecase + handler tests)
- Main.go wiring (DI manual)

**U-5 Go :** Article→Xxx, Author→XxxAuthor. Garder : http, context, error, interface, sql, gorm.

---

## RÉSUMÉ SESSION 2

Après les 3 repos, affiche :
```
=== SESSION 2 TERMINÉE ===
Go A — eddycjy/go-gin-example           : N patterns [PASS/FAIL]
Go B — ThreeDotsLabs/wild-workouts      : N patterns [PASS/FAIL]
Go C — bxcodec/go-clean-arch            : N patterns [PASS/FAIL]
Total KB : N points
```

Commit FIX_LOG.md à la fin si pas déjà fait.
