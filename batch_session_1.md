Tu es le KB Builder autonome de Wal-e Lab V6. Tu exécutes l'ingestion de 4 repos (JS C, TS A, TS B, TS C).

**PREMIÈRE CHOSE :** Lis CLAUDE.md et kb_utils.py. Lis aussi un script existant (ingest_node_express_boilerplate.py) comme template de structure.

**DEUXIÈME CHOSE :** Crée le fichier FIX_LOG.md à la racine du projet (s'il n'existe pas) avec ce header :
```
# FIX_LOG — KB Test Matrix
> Toutes les violations rencontrées et fixes appliqués durant les tests.
> Généré automatiquement par le KB Builder.
```

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
   - Imports de kb_utils.py : build_payload, check_charte_violations, make_uuid, query_kb, audit_report
4. **Exécute** : `.venv/bin/python3 ingest_<slug>.py`
5. **Si violations :**
   - Analyse la cause (faux positif TECHNICAL_TERMS ? entité non normalisée ?)
   - Corrige le script OU ajoute des termes dans kb_utils.py
   - Purge les points : `client.delete(collection_name='patterns', points_selector=FilterSelector(filter=Filter(must=[FieldCondition(key='_tag', match=MatchValue(value=TAG))])))`
   - Relance — itère jusqu'à PASS 0 violations
   - **Logge chaque fix** dans FIX_LOG.md au format :
     ```
     ## [REPO] owner/repo (LANG LEVEL)
     ### Fix N — TITRE
     - Violation : message exact
     - Cause : explication
     - Action : ce qui a été changé
     - Résultat : PASS / encore FAIL
     ```
6. **Commit + push** :
   ```bash
   git add ingest_<slug>.py
   # + kb_utils.py si modifié
   # + api_patterns/API_INTEGRATIONS_CATALOG.md si complété
   # + FIX_LOG.md
   git commit -m "feat: ingest <repo> — N <LANG> <LEVEL> KB patterns"
   git push
   ```

**Règles d'extraction :**
- TOUS les patterns par fonction (pas de sampling)
- Uniquement patterns architecturaux réutilisables (modèles, routes, auth, middleware, services, tests, config)
- PAS d'intégrations API one-off → noter dans api_patterns/API_INTEGRATIONS_CATALOG.md
- Supprimer prints/logs (U-7, J-3, T-3, G-2, R-2)
- query_kb() dans les audit queries avec language=LANGUAGE (filtre obligatoire)

---

## REPO 1 : JS C — sahat/hackathon-starter

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/sahat/hackathon-starter.git |
| LANGUAGE | javascript |
| FRAMEWORK | express |
| STACK | express+mongoose+passport_multi+nodemailer+webauthn |
| TAG | sahat/hackathon-starter |

**Architecture :** MVC monolithique. Passport local + 8 OAuth via shared handleAuthLogin().

**Patterns à extraire (~35-40) :**
- models/User.js : Mongoose schema complexe (auth tokens, 2FA email+TOTP, WebAuthn credentials, OAuth providers, profile Map), virtuals (expiration checks), 3 pre-save hooks (bcrypt, token cleanup, gravatar update), methods (comparePassword, verifyTokenAndIp timing-safe, verifyCodeAndIp, gravatar, clearTwoFactorCode), statics (hashIP, generateToken, generateCode)
- config/passport.js : local strategy, shared handleAuthLogin() (pattern OAuth générique multi-provider), serialize/deserialize, isAuthenticated middleware, isAuthorized middleware (token refresh)
- controllers/user.js : login (password + passwordless), signup, passwordless auth (getLoginByEmail), forgot/reset password (token+IP), email verification, 2FA email flow (enable, verify, resend), 2FA TOTP flow (setup QR, verify, remove), OAuth unlink + token revocation, profile update, password change, account delete, logout + logoutEverywhere
- controllers/contact.js : reCAPTCHA Enterprise validation + nodemailer
- controllers/webauthn.js : passkey registration (challenge-response) + passkey login (challenge-response)
- app.js : multi-tier rate limiting (global 200/15min, strict 5/hr, login 10/hr), session MongoStore, CSRF Lusca, helmet security, route registration middleware chains

**U-5 :** User→Xxx, user→xxx, userSchema→xxxSchema. Garder : email, password, profile, passport, bcrypt, crypto, twoFactor, totp, webauthn, session, flash, gravatar, providers (google, github, facebook...).
**J-3 :** Supprimer console.log(err) dans verifyTokenAndIp.
**EXCLURE :** 30+ intégrations API (Stripe, Twilio, Foursquare...) → déjà cataloguées dans api_patterns/API_INTEGRATIONS_CATALOG.md. Ne PAS les indexer.

---

## REPO 2 : TS A — w3tecch/express-typescript-boilerplate

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/w3tecch/express-typescript-boilerplate.git |
| LANGUAGE | typescript |
| FRAMEWORK | express |
| STACK | express+typeorm+typedi+routing-controllers+typescript |
| TAG | w3tecch/express-typescript-boilerplate |

**Architecture :** Express + TypeORM + TypeDI (dependency injection) + routing-controllers (decorators). 3 couches.

**Patterns à extraire (~25-30) :**
- Entities TypeORM (@Entity, @Column, @PrimaryGeneratedColumn, relations)
- Repositories (custom + TypeORM)
- Services avec DI (@Service, @Inject)
- Controllers avec decorators (@JsonController, @Get, @Post, @Param, @Body)
- Middleware (auth, error handling, logging)
- Event dispatching pattern
- Database seeding (factory pattern + Faker)
- Migration patterns TypeORM
- GraphQL resolvers (si présents)
- Config (environment, dotenv)
- Tests

**U-5 :** Entités métier → Xxx. Garder : TypeORM decorators, TypeDI decorators, Express terms.
**Règles TS :** T-1 (pas de any), T-2 (pas de var), T-3 (pas de console.log).

---

## REPO 3 : TS B — gothinkster/node-express-realworld-example-app

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/gothinkster/node-express-realworld-example-app.git |
| LANGUAGE | typescript |
| FRAMEWORK | express |
| STACK | express+prisma+jwt+typescript |
| TAG | gothinkster/node-express-realworld-example-app |

**Architecture :** RealWorld spec (Conduit). Express + Prisma ORM + JWT.

**Patterns à extraire (~20-25) :**
- Prisma schema (modèles, relations)
- Prisma client usage (CRUD, filters, includes)
- JWT auth middleware
- Controllers/routes CRUD (articles, comments, users, tags)
- Favoriting pattern (many-to-many)
- Following pattern (self-referencing many-to-many)
- Feed endpoint (filtered query)
- Error handling middleware
- Validation
- Tests (si présents)

**ATTENTION :** Ce repo a évolué. Clone et vérifie la structure actuelle. Si c'est du JS et pas TS, ajuste LANGUAGE en conséquence.
**U-5 :** Article→Xxx, User→XxxAuthor ou Xxx, Comment→XxxComment, Tag→XxxLabel. Adapter selon ce qui est dans le repo.

---

## REPO 4 : TS C — nestjs/nest

| Clé | Valeur |
|---|---|
| REPO_URL | https://github.com/nestjs/nest.git |
| LANGUAGE | typescript |
| FRAMEWORK | nestjs |
| STACK | nestjs+typescript+decorators+di |
| TAG | nestjs/nest |

**Architecture :** Framework NestJS (monorepo Lerna). Angular-inspired. Modules/Controllers/Services/Pipes/Guards/Interceptors.

**IMPORTANT :** C'est un FRAMEWORK, pas une app. Se concentrer sur le dossier `sample/` pour les patterns d'utilisation concrets. Ne PAS extraire le code interne du framework.

**Patterns à extraire (~20-30) :**
- Module decorator pattern (@Module avec imports, controllers, providers)
- Controller decorator pattern (@Controller + @Get/@Post/@Put/@Delete + @Param/@Body/@Query)
- Injectable service pattern (@Injectable + constructor DI)
- Guard pattern (@UseGuards, CanActivate)
- Pipe pattern (@UsePipes, PipeTransform pour validation)
- Interceptor pattern (@UseInterceptors, NestInterceptor)
- Exception filter pattern (@Catch, ExceptionFilter)
- Middleware pattern (NestMiddleware)
- DTO pattern (class-validator + class-transformer)
- Custom decorator pattern (createParamDecorator)
- WebSocket gateway (si dans samples)
- Microservice pattern (si dans samples)
- Testing (Test.createTestingModule)

**U-5 :** Adapter selon les entités dans les samples (Cat→Xxx, etc.).
**ATTENTION :** Monorepo large. Ne clone que --depth=1 et concentre-toi sur `sample/` ou `integration/`.

---

## RÉSUMÉ SESSION 1

Après les 4 repos, affiche :
```
=== SESSION 1 TERMINÉE ===
JS C  — sahat/hackathon-starter        : N patterns [PASS/FAIL]
TS A  — w3tecch/express-typescript-bp   : N patterns [PASS/FAIL]
TS B  — gothinkster/realworld           : N patterns [PASS/FAIL]
TS C  — nestjs/nest                     : N patterns [PASS/FAIL]
Total KB : N points
```

Commit FIX_LOG.md à la fin si pas déjà fait.
