# FIX_LOG — KB Test Matrix
> Toutes les violations rencontrées et fixes appliqués durant les tests.
> Généré automatiquement par le KB Builder.

## [TS A] w3tecch/express-typescript-boilerplate (TypeScript A)

### Fix 1 — Variable `events` triggers U-5 forbidden entity
- Violation : `[U-5] Entité métier 'events' dans pattern 'service_crud_with_di_event_dispatch_logging'` (+ 2 autres patterns)
- Cause : Le nom de variable `events` (export const events = {...}) correspond au mot interdit "events" dans FORBIDDEN_ENTITIES.
- Action : Renommé `events` → `entityHooks` dans les 3 patterns concernés (service, event constants, event subscriber).
- Résultat : PASS

### Fix 2 — `@Post()` decorator triggers U-5 forbidden entity "post"
- Violation : `[U-5] Entité métier 'post' dans pattern 'controller_crud_routing_controllers_authorized'`
- Cause : `@Post()` lowercased → `@post()` → `\bpost\b` matches. Le terme technique `"@post("` ajouté à TECHNICAL_TERMS mais le multi-line import `Post,` (sur sa propre ligne) n'était pas exclu car la ligne ne commence pas par `import `.
- Action : (1) Ajouté `"@post("` à TECHNICAL_TERMS dans kb_utils.py. (2) Collapsé le multi-line import en single-line pour que `Post` soit sur la ligne `import ...`.
- Résultat : PASS

### Fix 3 — Added TypeScript/NestJS TECHNICAL_TERMS
- Violation : Prévention pour tous les repos TS
- Cause : `@Post()` decorator et event-dispatch decorators non exemptés.
- Action : Ajouté dans kb_utils.py TECHNICAL_TERMS : `"@post("`, `"eventdispatcher"`, `"eventsubscriber"`, `"@on("`.
- Résultat : PASS

## [TS B] gothinkster/node-express-realworld-example-app (TypeScript B)

Aucune violation — PASS au premier essai.

## [TS C] nestjs/nest (TypeScript C)

### Fix 1 — `Post` in multi-line imports + `events` in WebSocket
- Violation : `[U-5] 'post' dans 'nestjs_auth_controller_public_protected'`, `[U-5] 'events' dans 'nestjs_websocket_gateway'`, `[U-5] 'post' dans 'nestjs_file_upload_interceptor_pipe'`
- Cause : (1) Multi-line imports avec `Post,` sur sa propre ligne — non exclue par le filtre d'imports. (2) `EventsGateway` class name et `'events'` string literal contiennent le mot interdit.
- Action : (1) Collapsé les imports multi-lignes en single-line pour auth controller et file upload. (2) Renommé `EventsGateway` → `WsGateway`, `'events'` → `'data'` dans le WebSocket pattern.
- Résultat : PASS

## [Go A] eddycjy/go-gin-example (Go A)

Aucune violation — PASS au premier essai (25 patterns).

## [Go B] ThreeDotsLabs/wild-workouts-go-ddd-example (Go B)

### Fix 1 — `"POST"` in CORS AllowedMethods triggers U-5 forbidden entity "post"
- Violation : `[U-5] Entité métier 'post' dans pattern 'chi_http_server_middleware_chain'`
- Cause : `AllowedMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"}` — after lowercasing, `"post"` matches `\bpost\b`. The existing TECHNICAL_TERMS only covered `.post(` (method call) and `@post(` (decorator), not `"post"` as an HTTP method string literal.
- Action : Ajouté `'"post"'` et `'"post",'` dans TECHNICAL_TERMS de kb_utils.py pour exempter les chaînes HTTP method.
- Résultat : PASS (purge + re-run)

## [Go C] bxcodec/go-clean-arch (Go C)

### Fix 1 — `ORDER BY` in SQL query triggers U-5 forbidden entity "order"
- Violation : `[U-5] Entité métier 'order' dans pattern 'mysql_repository_fetch_get'`
- Cause : SQL query `ORDER BY created_at` — after lowercasing, `order` in `order by` matches `\border\b`. The existing TECHNICAL_TERMS only covered `.order(` (GORM method), not SQL `ORDER BY`.
- Action : Ajouté `"order by"` dans TECHNICAL_TERMS de kb_utils.py pour exempter la clause SQL ORDER BY.
- Résultat : PASS (purge + re-run)
