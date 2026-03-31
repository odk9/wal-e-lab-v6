Tu es le KB Builder autonome de Wal-e Lab V6. Tu exécutes l'ingestion de 6 repos (Rust A/B/C + C++ A/B/C).

**PREMIÈRE CHOSE :** Lis CLAUDE.md et kb_utils.py. Lis un script existant comme template. Lis FIX_LOG.md pour voir l'état des sessions précédentes.

---

## WORKFLOW PAR REPO

Pour CHAQUE repo :

1. **Clone** le repo (`git clone --depth=1 <URL> /tmp/<slug>`)
2. **Lis les fichiers source** pour identifier les patterns architecturaux réutilisables
3. **Crée** `ingest_<slug>.py` avec la même structure que les scripts existants
4. **Exécute** : `.venv/bin/python3 ingest_<slug>.py`
5. **Si violations :** corrige → purge tag → relance → itère jusqu'à PASS. Logge chaque fix dans FIX_LOG.md
6. **Commit + push** chaque repo individuellement

**Règles Rust (R-\*) :**
- R-1 : pas de `.unwrap()` sauf dans `#[test]`
- R-2 : pas de `println!()` — utiliser `tracing` ou `log`

**Règles C++ :** Pas de règles C-\* spécifiques dans kb_utils.py. Appliquer uniquement U-\* (universelles).

**TECHNICAL_TERMS à anticiper :**
- Rust : `impl`, `pub fn`, `async fn`, `-> Result<`, `.await`, `axum::Router`, `tower::Service`, `#[derive(`, `#[tokio::main]`, `Arc<`, `State<`, `Json<`, `Path<`, `Query<`
- C++ : `CROW_ROUTE`, `std::`, `::json`, `::request`, `::response`, `#include`, `namespace`, `auto`, `const&`, `void`, `->`, `std::string`, `crow::App`, `drogon::HttpController`

Ajoute au TECHNICAL_TERMS de kb_utils.py si faux positifs.

---

## REPO 1 : Rust A — tokio-rs/axum (examples/)

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/tokio-rs/axum.git |
| LANGUAGE | rust |
| FRAMEWORK | axum |
| STACK | axum+tokio+tower+serde |
| TAG | tokio-rs/axum |

**Architecture :** Framework Axum. EXTRAIRE DEPUIS le dossier `examples/` uniquement.

**Patterns à extraire (~20-25) :**
- Route setup : Router::new().route("/path", get(handler).post(handler))
- Handlers : async fn avec extractors (Path, Query, Json, State)
- Shared state : Arc<AppState> ou State<AppState>
- JSON request/response (serde Serialize/Deserialize)
- Error handling : impl IntoResponse pour custom errors
- Middleware Tower : from_fn, ServiceBuilder
- CORS configuration
- Tracing/logging setup
- Static file serving
- WebSocket handler (si dans examples)
- Graceful shutdown
- Form handling
- Database patterns (SQLx, si dans examples)
- Tests (si dans examples)

**U-5 :** Adapter selon les entités dans les examples. Garder : axum, tokio, tower, serde, hyper, tous les types Rust standard.

---

## REPO 2 : Rust B — maxcountryman/axum-login

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/maxcountryman/axum-login.git |
| LANGUAGE | rust |
| FRAMEWORK | axum |
| STACK | axum+tower_sessions+sqlx |
| TAG | maxcountryman/axum-login |

**Architecture :** Auth library pour Axum. Tower middleware. Trait-based.

**Patterns à extraire (~15-20) :**
- AuthUser trait implementation (get_id, get_password_hash)
- AuthnBackend trait (authenticate, get_user — async)
- AuthzBackend trait (get_permissions, get_group_permissions)
- AuthSession extractor usage
- login_required! macro usage
- permission_required! macro usage
- Session configuration (tower-sessions + SQLx store)
- Protected route patterns
- Login/logout handlers
- Credential struct (username + password)
- Permission/role enum
- SQLx user queries
- App setup avec AuthManagerLayerBuilder

**Se concentrer sur** les `examples/` et les traits publics dans `axum-login/src/`.
**U-5 :** User→Xxx, adapte selon les exemples.

---

## REPO 3 : Rust C — shuttle-hq/shuttle

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/shuttle-hq/shuttle.git |
| LANGUAGE | rust |
| FRAMEWORK | axum |
| STACK | axum+shuttle+sqlx+tokio |
| TAG | shuttle-hq/shuttle |

**Architecture :** Plateforme de déploiement Rust. Monorepo large.

**IMPORTANT :** Se concentrer sur `examples/` uniquement. Ne PAS extraire le code d'infrastructure de la plateforme.

**Patterns à extraire (~15-20) :**
- Attribute macro : `#[shuttle_runtime::main]` entry point
- Resource injection : `#[shuttle_shared_db::Postgres]` dans la signature main
- Axum Router setup dans contexte Shuttle
- SQLx migrations + queries
- Shared state pattern
- Error handling (Result + ? + custom errors)
- Config via Shuttle Secrets
- Static file serving
- WebSocket (si dans examples)
- Tests

**U-5 :** Adapter selon les exemples. Ce sera probablement des entités très simples.
**ATTENTION :** Monorepo large. Clone --depth=1 et IGNORE tout sauf `examples/`.

---

## REPO 4 : C++ A — crowcpp/Crow

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/CrowCpp/Crow.git |
| LANGUAGE | cpp |
| FRAMEWORK | crow |
| STACK | crow+cpp17 |
| TAG | crowcpp/Crow |

**Architecture :** Header-only C++ microframework, Flask-like.

**Se concentrer sur** `examples/` et `tests/` pour les patterns d'utilisation.

**Patterns à extraire (~15-20) :**
- App setup : `crow::SimpleApp app;` ou `crow::App<Middleware>` + `app.port(8080).run();`
- Route macros : `CROW_ROUTE(app, "/path").methods("GET"_method, "POST"_method)(handler)`
- Lambda handlers avec req/res params
- JSON read : `crow::json::load(req.body)`, key access
- JSON write : `crow::json::wvalue`, nested objects
- Mustache templating : `crow::mustache::load("template.html").render(ctx)`
- Middleware pattern : custom middleware class avec before_handle/after_handle
- WebSocket : `CROW_WEBSOCKET_ROUTE`, on_open/on_message/on_close
- Multipart parsing : `crow::multipart::message`
- Static file serving : `CROW_ROUTE(app, "/static/<path>")` ou StaticDir
- Blueprint (modular routing) : `crow::Blueprint bp("prefix")`
- HTTPS/SSL : `app.ssl_file("cert.pem", "key.pem")`
- URL params : `<int>`, `<string>`, `<path>`

**U-5 :** Les exemples C++ utilisent rarement des entités métier nommées. Normaliser si trouvé.
**Pas de règles C-\* :** Uniquement U-\* (universelles).

---

## REPO 5 : C++ B — drogonframework/drogon

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/drogonframework/drogon.git |
| LANGUAGE | cpp |
| FRAMEWORK | drogon |
| STACK | drogon+orm+cpp17 |
| TAG | drogonframework/drogon |

**Architecture :** Framework C++17 async. ORM intégré. Non-blocking IO (epoll/kqueue).

**Se concentrer sur** `examples/` et `lib/tests/` (ou `nosql_lib/`, `orm_lib/`).

**Patterns à extraire (~15-25) :**
- HttpController : macro `PATH_ADD`, route handlers, HttpRequest/HttpResponse
- HttpSimpleController : PATH_LIST_BEGIN/END, asyncHandleHttpRequest
- WebSocketController : handleNewMessage, handleNewConnection
- Filter chains : drogon::HttpFilter, doFilter
- ORM mapper : auto-generated models, Mapper<Model>::findByPrimaryKey, insertFuture
- Async callbacks : `[](const HttpResponsePtr &resp) { ... }`
- C++ coroutines (co_await) si disponibles
- JSON handling : Json::Value, req->getJsonObject()
- File upload : MultiPartParser, req->getUploadFiles()
- Session : req->session()->get/set
- Config JSON : `config.json` loading
- App setup : `drogon::app().addListener().run()`
- Middleware : global filters

**U-5 :** Adapter selon les exemples.

---

## REPO 6 : C++ C — uNetworking/uWebSockets

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/uNetworking/uWebSockets.git |
| LANGUAGE | cpp |
| FRAMEWORK | uwebsockets |
| STACK | uwebsockets+libuv+openssl |
| TAG | uNetworking/uWebSockets |

**Architecture :** HTTP + WebSocket ultra-performant. Low-level. Header-only.

**Se concentrer sur** `examples/` et `tests/`.

**Patterns à extraire (~10-15) :**
- App setup : `uWS::App()` ou `uWS::SSLApp()` + `.listen(port, callback)`
- HTTP GET/POST handlers : `.get("/path", handler)`, `.post("/path", handler)`
- WebSocket handlers : `.ws<UserData>("/ws", { .open, .message, .close, .drain })`
- Per-socket user data : template parameter `<UserData>`
- Pub/Sub : `ws->subscribe("topic")`, `ws->publish("topic", data)`
- Streaming responses : `res->onAborted()`, `res->onData()`, chunked write
- URL routing : wildcard `/*`, params (manual parsing)
- SSL/TLS config : `uWS::SSLApp({.key_file_name, .cert_file_name})`
- Backpressure handling : `ws->getBufferedAmount()`
- Request body reading : `res->onData([](std::string_view chunk, bool last) { ... })`

**U-5 :** Très peu d'entités métier dans ce repo. Normaliser si trouvé.
**NOTE :** Repo très bas niveau. Moins de patterns "architecturaux" classiques, plus de patterns réseau/perf.

---

## VÉRIFICATION FINALE (après les 6 repos)

Lance un check global :

```python
from qdrant_client import QdrantClient
c = QdrantClient(path='./kb_qdrant')
print(f'Total patterns: {c.count(collection_name="patterns").count}')

tags = {}
offset = None
while True:
    result = c.scroll(collection_name='patterns', limit=100, offset=offset, with_payload=True)
    points, next_offset = result
    for p in points:
        tag = p.payload.get('_tag', '?')
        tags[tag] = tags.get(tag, 0) + 1
    if next_offset is None:
        break
    offset = next_offset

for tag, count in sorted(tags.items()):
    print(f'  {tag}: {count}')
```

Ajoute le résultat dans FIX_LOG.md section `## RÉSUMÉ FINAL — MATRICE 18 REPOS`.

Commit final :
```bash
git add FIX_LOG.md api_patterns/API_INTEGRATIONS_CATALOG.md
git commit -m "docs: FIX_LOG + API catalog — 18 repos test matrix complete"
git push
```

Affiche :
```
=== SESSION 3 TERMINÉE ===
Rust A — tokio-rs/axum              : N patterns [PASS/FAIL]
Rust B — maxcountryman/axum-login   : N patterns [PASS/FAIL]
Rust C — shuttle-hq/shuttle         : N patterns [PASS/FAIL]
C++ A  — crowcpp/Crow               : N patterns [PASS/FAIL]
C++ B  — drogonframework/drogon     : N patterns [PASS/FAIL]
C++ C  — uNetworking/uWebSockets    : N patterns [PASS/FAIL]
=== MATRICE 18 REPOS COMPLÈTE ===
Total KB : N points
```
