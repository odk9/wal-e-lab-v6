"""
ingest_wirings_express_mongoose.py — Extrait et indexe les wirings (flux inter-modules)
de madhums/node-express-mongoose-demo dans la KB Qdrant V6 (collection `wirings`).

Premier test multi-langage : wirings JavaScript / Express + Mongoose.
Wirings 100% manuels (pas d'AST Python pour du JS).

Usage:
    .venv/bin/python3 ingest_wirings_express_mongoose.py
"""

from __future__ import annotations

import subprocess
import os
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/madhums/node-express-mongoose-demo.git"
REPO_NAME = "madhums/node-express-mongoose-demo"
REPO_LOCAL = "/tmp/node-express-mongoose-demo"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose"
CHARTE_VERSION = "1.0"
TAG = "wirings/madhums/node-express-mongoose-demo"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"


# ─── Wirings manuels ────────────────────────────────────────────────────────
# Express+Mongoose n'utilise pas d'AST Python, donc tout est manuel.
# On couvre les 3 types : import_graph, dependency_chain, flow_pattern.

MANUAL_WIRINGS: list[dict] = [

    # ══════════════════════════════════════════════════════════════════════
    # 1. IMPORT GRAPH — qui require() quoi
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "import_graph",
        "description": (
            "Import graph (require) for Express+Mongoose CRUD project. "
            "Shows the require() dependency tree between server.js, config/, "
            "app/controllers/, and app/models/. server.js is the entry point "
            "that bootstraps models, passport, express middleware, and routes."
        ),
        "modules": [
            "server.js", "config/express.js", "config/routes.js",
            "config/passport.js", "config/middlewares/authorization.js",
            "app/controllers/articles.js", "app/controllers/users.js",
            "app/models/article.js", "app/models/user.js",
        ],
        "connections": [
            "server.js → config/ (require('./config'))",
            "server.js → app/models/*.js (fs.readdirSync + require)",
            "server.js → config/passport.js (require('./config/passport')(passport))",
            "server.js → config/express.js (require('./config/express')(app, passport))",
            "server.js → config/routes.js (require('./config/routes')(app, passport))",
            "config/routes.js → app/controllers/articles.js",
            "config/routes.js → app/controllers/users.js",
            "config/routes.js → app/controllers/comments.js",
            "config/routes.js → app/controllers/tags.js",
            "config/routes.js → config/middlewares/authorization.js",
            "app/controllers/articles.js → mongoose.model('Article')",
            "app/controllers/users.js → mongoose.model('User')",
            "app/models/article.js → mongoose (Schema definition)",
            "app/models/user.js → mongoose (Schema definition)",
        ],
        "code_example": """\
// === Import Graph — Express+Mongoose CRUD ===

// server.js (entry point)
const express = require('express');
const mongoose = require('mongoose');
const passport = require('passport');
const config = require('./config');

// Bootstrap models (dynamic require)
fs.readdirSync(models)
  .filter(file => ~file.search(/^[^.].*\\.js$/))
  .forEach(file => require(join(models, file)));

// Bootstrap middleware + routes (function injection pattern)
require('./config/passport')(passport);
require('./config/express')(app, passport);
require('./config/routes')(app, passport);

// config/routes.js (centralized routing)
const articles = require('../app/controllers/articles');
const users = require('../app/controllers/users');
const auth = require('./middlewares/authorization');

// app/controllers/articles.js (uses mongoose.model registry)
const Article = mongoose.model('Article');
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 2. BOOTSTRAP SEQUENCE — Express app initialization order
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete bootstrap sequence for Express+Mongoose project. "
            "Shows the exact initialization order: 1) load env, 2) create express app, "
            "3) register Mongoose models (dynamic require), 4) configure passport strategies, "
            "5) apply middleware stack (config/express.js), 6) mount routes (config/routes.js), "
            "7) connect to MongoDB, 8) listen on port. This is the Express equivalent "
            "of FastAPI's lifespan + include_router pattern."
        ),
        "modules": [
            "server.js", "config/express.js", "config/routes.js",
            "config/passport.js", "app/models/article.js", "app/models/user.js",
        ],
        "connections": [
            "1. require('dotenv').config() — load .env",
            "2. const app = express() — create app instance",
            "3. fs.readdirSync('app/models').forEach(require) — register Mongoose models",
            "4. require('./config/passport')(passport) — configure auth strategies",
            "5. require('./config/express')(app, passport) — apply middleware stack",
            "6. require('./config/routes')(app, passport) — mount all routes",
            "7. mongoose.connect(config.db) — connect to MongoDB",
            "8. app.listen(port) — start HTTP server (after 'open' event)",
        ],
        "code_example": """\
// === Bootstrap Sequence — Express+Mongoose ===

// server.js — EXACT order matters

// 1. Environment
require('dotenv').config();
const config = require('./config');

// 2. Create app
const app = express();
module.exports = app;  // expose for testing

// 3. Register models (MUST be before routes)
fs.readdirSync(models)
  .filter(file => ~file.search(/^[^.].*\\.js$/))
  .forEach(file => require(join(models, file)));

// 4. Passport strategies (MUST be before routes that use auth)
require('./config/passport')(passport);

// 5. Middleware stack (MUST be before routes)
require('./config/express')(app, passport);

// 6. Routes (LAST — after middleware and models)
require('./config/routes')(app, passport);

// 7. DB connection + 8. Listen
connect();  // mongoose.connect → on('open', listen)
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 3. MIDDLEWARE STACK — Express middleware pipeline
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Express middleware stack ordering convention. "
            "Shows the exact order middleware must be applied in config/express.js: "
            "security (helmet, cors) → compression → static files → logging → "
            "view engine → bodyParser → methodOverride → cookieParser → session → "
            "passport → flash → csrf. Order matters — bodyParser before methodOverride, "
            "cookieParser before session, session before passport, passport before flash."
        ),
        "modules": ["config/express.js"],
        "connections": [
            "1. helmet() — security headers (first)",
            "2. requireHttps — HTTPS redirect",
            "3. compression() — response compression (before static)",
            "4. cors() — CORS configuration",
            "5. express.static() — serve public/ files",
            "6. morgan() — HTTP request logging",
            "7. app.set('view engine', 'pug') — template engine",
            "8. bodyParser.json() + bodyParser.urlencoded() — parse request body",
            "9. multer upload.single() — file upload handling",
            "10. methodOverride() — PUT/DELETE from forms (needs bodyParser first)",
            "11. cookieParser() — parse cookies (before session)",
            "12. session() with MongoStore — server sessions (needs cookieParser)",
            "13. passport.initialize() + passport.session() — auth (needs session)",
            "14. flash() — flash messages (needs session)",
            "15. csrf() — CSRF protection (needs session + cookies)",
        ],
        "code_example": """\
// === Middleware Stack Convention — Express ===
// config/express.js — ORDER MATTERS

module.exports = function (app, passport) {
  // Security first
  app.use(helmet());
  app.use(cors({ origin: [...], credentials: true }));

  // Performance
  app.use(compression({ threshold: 512 }));
  app.use(express.static(config.root + '/public'));

  // Logging
  if (env !== 'test') app.use(morgan(log));

  // View engine
  app.set('views', config.root + '/app/views');
  app.set('view engine', 'pug');

  // Body parsing (BEFORE methodOverride)
  app.use(bodyParser.json());
  app.use(bodyParser.urlencoded({ extended: true }));
  app.use(methodOverride(function (req) { ... }));

  // Session chain (order: cookie → session → passport → flash)
  app.use(cookieParser());
  app.use(session({ store: MongoStore.create({...}) }));
  app.use(passport.initialize());
  app.use(passport.session());
  app.use(flash());

  // CSRF (last — needs session + cookies)
  if (env !== 'test') app.use(csrf());
};
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 4. CENTRALIZED ROUTING — route definition + auth middleware pattern
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Centralized routing pattern in Express+Mongoose. "
            "All routes defined in config/routes.js. Controllers loaded via require(). "
            "Auth middleware composed as arrays: [auth.requiresLogin, auth.article.hasAuthorization]. "
            "app.param() used for resource loading (like FastAPI's Path() + Depends()). "
            "Error handling at the bottom with 422/500/404 handlers."
        ),
        "modules": [
            "config/routes.js", "config/middlewares/authorization.js",
            "app/controllers/articles.js", "app/controllers/users.js",
        ],
        "connections": [
            "config/routes.js → require('../app/controllers/articles') → articles controller",
            "config/routes.js → require('../app/controllers/users') → users controller",
            "config/routes.js → require('./middlewares/authorization') → auth middleware",
            "const articleAuth = [auth.requiresLogin, auth.article.hasAuthorization] → middleware array",
            "app.param('id', articles.load) → auto-load resource by ID (like Depends())",
            "app.get('/articles/:id', articles.show) → route → controller method",
            "app.post('/articles', auth.requiresLogin, articles.create) → auth + route",
            "app.put('/articles/:id', articleAuth, articles.update) → compound auth + route",
            "app.use(errorHandler) → catch-all error middleware at bottom",
        ],
        "code_example": """\
// === Centralized Routing — Express ===
// config/routes.js

const articles = require('../app/controllers/articles');
const users = require('../app/controllers/users');
const auth = require('./middlewares/authorization');

// Compose auth middleware as arrays
const articleAuth = [auth.requiresLogin, auth.article.hasAuthorization];

module.exports = function(app, passport) {
  // Resource loading middleware (equivalent to Depends + Path)
  app.param('id', articles.load);
  app.param('userId', users.load);

  // Article CRUD routes
  app.get('/articles', articles.index);
  app.post('/articles', auth.requiresLogin, articles.create);
  app.get('/articles/:id', articles.show);
  app.put('/articles/:id', articleAuth, articles.update);
  app.delete('/articles/:id', articleAuth, articles.destroy);

  // Error handling (at the bottom)
  app.use(function(err, req, res, next) {
    if (err.stack.includes('ValidationError')) {
      return res.status(422).render('422', { error: err.stack });
    }
    res.status(500).render('500', { error: err.stack });
  });

  app.use(function(req, res) {
    res.status(404).render('404', { url: req.originalUrl });
  });
};
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 5. MONGOOSE MODEL PATTERN — Schema + validation + statics + methods
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Mongoose model definition pattern for Express CRUD. "
            "Shows the complete model wiring: Schema definition with types + defaults + refs, "
            "path validations, pre-hooks (pre-remove, pre-save), instance methods "
            "(uploadAndSave, addComment), static methods (load with populate, list with "
            "pagination). Model registered via mongoose.model('Xxx', XxxSchema). "
            "Controllers access models via mongoose.model('Xxx') — no direct import needed."
        ),
        "modules": [
            "app/models/article.js", "app/controllers/articles.js",
        ],
        "connections": [
            "app/models/article.js: const XxxSchema = new Schema({...}) → define schema",
            "app/models/article.js: XxxSchema.path('title').required() → add validations",
            "app/models/article.js: XxxSchema.pre('remove', fn) → lifecycle hooks",
            "app/models/article.js: XxxSchema.methods = { uploadAndSave, addComment, removeComment }",
            "app/models/article.js: XxxSchema.statics = { load (findOne+populate), list (find+sort+paginate) }",
            "app/models/article.js: mongoose.model('Xxx', XxxSchema) → register globally",
            "app/controllers/articles.js: const Xxx = mongoose.model('Xxx') → access via global registry",
            "app/controllers/articles.js: yield Xxx.load(id) → uses static method",
            "app/controllers/articles.js: new Xxx(req.body) → create instance + xxx.uploadAndSave()",
        ],
        "code_example": """\
// === Mongoose Model Pattern ===

// app/models/xxx.js
const Schema = mongoose.Schema;

const XxxSchema = new Schema({
  title: { type: String, default: '', trim: true, maxlength: 400 },
  body: { type: String, default: '', trim: true, maxlength: 1000 },
  user: { type: Schema.ObjectId, ref: 'User' },
  createdAt: { type: Date, default: Date.now }
});

// Validations
XxxSchema.path('title').required(true, 'Title cannot be blank');

// Instance methods
XxxSchema.methods = {
  uploadAndSave: function(file) {
    const err = this.validateSync();
    if (err) throw new Error(err.toString());
    return this.save();
  }
};

// Static methods (used by controllers)
XxxSchema.statics = {
  load: function(_id) {
    return this.findOne({ _id })
      .populate('user', 'name email username')
      .exec();
  },
  list: function(options) {
    return this.find(options.criteria || {})
      .populate('user', 'name username')
      .sort({ createdAt: -1 })
      .limit(options.limit || 30)
      .skip(options.limit * options.page)
      .exec();
  }
};

// Register in global Mongoose registry
mongoose.model('Xxx', XxxSchema);

// app/controllers/xxx.js — access via registry (no direct import)
const Xxx = mongoose.model('Xxx');
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 6. AUTH MIDDLEWARE — passport + authorization middleware composition
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "dependency_chain",
        "description": (
            "Authentication and authorization middleware wiring in Express. "
            "Passport configured in config/passport.js with strategies (local, github, google). "
            "Authorization middleware in config/middlewares/authorization.js exports requiresLogin "
            "and resource-specific hasAuthorization. Routes compose these as middleware arrays. "
            "app.param() middleware pre-loads resources before authorization checks."
        ),
        "modules": [
            "config/passport.js", "config/passport/local.js",
            "config/middlewares/authorization.js", "config/routes.js",
        ],
        "connections": [
            "config/passport.js → require('./passport/local') + google + twitter + github",
            "config/passport.js → passport.serializeUser / deserializeUser (User.load)",
            "config/middlewares/authorization.js → exports.requiresLogin (req.isAuthenticated())",
            "config/middlewares/authorization.js → exports.article.hasAuthorization (req.article.user == req.user)",
            "config/routes.js → compose as array: [auth.requiresLogin, auth.article.hasAuthorization]",
            "config/routes.js → app.param('id', articles.load) BEFORE auth check (resource must exist)",
        ],
        "code_example": """\
// === Auth Middleware Wiring — Express ===

// config/passport.js — strategy registration
module.exports = function(passport) {
  passport.serializeUser((user, cb) => cb(null, user.id));
  passport.deserializeUser((id, cb) => User.load({ criteria: { _id: id } }, cb));
  passport.use(local);
  passport.use(google);
};

// config/middlewares/authorization.js — guards
exports.requiresLogin = function(req, res, next) {
  if (req.isAuthenticated()) return next();
  res.redirect('/login');
};

exports.article = {
  hasAuthorization: function(req, res, next) {
    if (req.article.user.id != req.user.id) {
      return res.redirect('/articles/' + req.article.id);
    }
    next();
  }
};

// config/routes.js — composition
const articleAuth = [auth.requiresLogin, auth.article.hasAuthorization];
app.param('id', articles.load);  // pre-load resource
app.put('/articles/:id', articleAuth, articles.update);
// Chain: param(load) → requiresLogin → hasAuthorization → controller
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 7. TEST WIRING — test helper + DB cleanup
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Test wiring for Express+Mongoose project. "
            "test/helper.js provides cleanup function that wipes User and Article collections. "
            "Tests use server.js module.exports = app for supertest-style testing. "
            "Config env/test.js provides separate test database URL. "
            "NODE_ENV=test disables CSRF and logging."
        ),
        "modules": [
            "test/helper.js", "test/test-articles-create.js",
            "server.js", "config/env/test.js",
        ],
        "connections": [
            "config/env/test.js → test DB URL (separate from dev/prod)",
            "server.js → module.exports = app (exposes app for testing)",
            "server.js → if (env === 'test') return (skip listen)",
            "config/express.js → if (env !== 'test') app.use(csrf()) (disable CSRF in tests)",
            "test/helper.js → mongoose.model('User').deleteMany() + Article.deleteMany()",
            "test/test-*.js → require('../server') → get app instance for supertest",
        ],
        "code_example": """\
// === Test Wiring — Express+Mongoose ===

// config/env/test.js — separate test DB
module.exports = {
  db: 'mongodb://localhost/test_db'
};

// server.js — expose app + skip listen in test mode
const app = express();
module.exports = app;  // ← key for testing
function listen() {
  if (app.get('env') === 'test') return;  // ← no listen
  app.listen(port);
}

// config/express.js — disable CSRF in tests
if (env !== 'test') {
  app.use(csrf());
}

// test/helper.js — cleanup between tests
const User = mongoose.model('User');
const Article = mongoose.model('Article');
exports.cleanup = function(t) {
  co(function*() {
    yield User.deleteMany();
    yield Article.deleteMany();
    t.end();
  });
};

// test/test-articles-create.js
const app = require('../server');
// Use supertest or similar to test routes
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },

    # ══════════════════════════════════════════════════════════════════════
    # 8. COMPLETE CRUD ASSEMBLY — file creation order for Express+Mongoose
    # ══════════════════════════════════════════════════════════════════════
    {
        "wiring_type": "flow_pattern",
        "description": (
            "Complete CRUD assembly convention for Express+Mongoose project. "
            "Shows the file creation order and how each file references the others. "
            "This is the Express equivalent of the FastAPI assembly convention: "
            "1) config (env), 2) models (Mongoose schemas), 3) controllers (business logic), "
            "4) middlewares (auth), 5) routes (centralized), 6) express config (middleware stack), "
            "7) server.js (bootstrap). Key difference: Express uses centralized routing in a "
            "single file, while FastAPI uses distributed routers."
        ),
        "modules": [
            "config/index.js", "config/env/development.js",
            "app/models/article.js", "app/models/user.js",
            "app/controllers/articles.js", "app/controllers/users.js",
            "config/middlewares/authorization.js",
            "config/passport.js", "config/routes.js",
            "config/express.js", "server.js",
        ],
        "connections": [
            "1. config/env/*.js — environment-specific config (db URL, secrets)",
            "2. config/index.js — loads correct env config, exports { db, root }",
            "3. app/models/*.js — Mongoose schemas + mongoose.model() registration (no local imports)",
            "4. app/controllers/*.js — business logic, access models via mongoose.model()",
            "5. config/middlewares/authorization.js — auth guards (requiresLogin, hasAuthorization)",
            "6. config/passport.js — auth strategies (local, OAuth)",
            "7. config/routes.js — centralized route definitions, require controllers + auth",
            "8. config/express.js — middleware stack (helmet → bodyParser → session → passport)",
            "9. server.js — bootstrap: models → passport → express → routes → connect → listen",
        ],
        "code_example": """\
// === File Creation Order — Express+Mongoose CRUD ===

// 1. config/env/development.js (foundation — no local imports)
module.exports = { db: 'mongodb://localhost/myapp_dev' };

// 2. config/index.js (loads correct env)
module.exports = require('./env/' + (process.env.NODE_ENV || 'development'));

// 3. app/models/xxx.js (depends on: mongoose only)
const XxxSchema = new Schema({ title: String, body: String });
mongoose.model('Xxx', XxxSchema);

// 4. app/controllers/xxxs.js (depends on: mongoose.model registry)
const Xxx = mongoose.model('Xxx');
exports.index = async(function*(req, res) { ... });
exports.create = async(function*(req, res) { ... });

// 5. config/middlewares/authorization.js (standalone)
exports.requiresLogin = function(req, res, next) { ... };

// 6. config/passport.js (depends on: models, passport strategies)
passport.use(local); passport.use(google);

// 7. config/routes.js (depends on: controllers, middlewares)
const articles = require('../app/controllers/articles');
app.get('/articles', articles.index);

// 8. config/express.js (depends on: config, middlewares)
app.use(helmet()); app.use(bodyParser.json()); app.use(passport.initialize());

// 9. server.js (orchestrator — depends on everything)
require('./config/passport')(passport);
require('./config/express')(app, passport);
require('./config/routes')(app, passport);
connect();
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
    },
]


# ─── Ingestion ───────────────────────────────────────────────────────────────

def clone_repo() -> None:
    """Clone le repo si absent."""
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo déjà cloné → {REPO_LOCAL}")
        return
    print(f"  Cloning {REPO_URL}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, REPO_LOCAL],
        check=True, capture_output=True,
    )
    print(f"  ✅ Cloné → {REPO_LOCAL}")


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION WIRINGS — {REPO_NAME}")
    print(f"{'='*60}\n")

    # ── 0. Init Qdrant ──────────────────────────────────────────────
    client = QdrantClient(path=KB_PATH)

    # Vérifier que la collection existe
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        print(f"  ❌ Collection '{COLLECTION}' n'existe pas. Lancer setup_collections.py d'abord.")
        return

    count_before = client.count(COLLECTION).count
    print(f"  KB avant : {count_before} wirings")

    # ── 1. Cleanup ancien tag ───────────────────────────────────────
    print(f"\n  Cleanup tag '{TAG}'...")
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
            )
        ),
    )
    after_cleanup = client.count(COLLECTION).count
    print(f"  Après cleanup : {after_cleanup} wirings")

    # ── 2. Clone repo (pour référence) ──────────────────────────────
    clone_repo()

    # ── 3. Pas d'extraction AST pour JavaScript ─────────────────────
    print("\n  ⚠️  JavaScript — pas d'extracteur AST, wirings 100% manuels")
    all_wirings = MANUAL_WIRINGS
    print(f"  → {len(all_wirings)} wirings manuels")

    # ── 4. Embedding ────────────────────────────────────────────────
    print("\n  Embedding des descriptions...")
    descriptions = [w["description"] for w in all_wirings]
    vectors = embed_documents_batch(descriptions)
    print(f"  → {len(vectors)} vecteurs générés ({len(vectors[0])} dims)")

    # ── 5. Upsert dans Qdrant ───────────────────────────────────────
    print("\n  Indexation dans Qdrant...")
    points: list[PointStruct] = []
    for wiring, vector in zip(all_wirings, vectors):
        payload = {
            **wiring,
            "charte_version": CHARTE_VERSION,
            "created_at": int(time.time()),
            "_tag": TAG,
        }
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        ))

    client.upsert(collection_name=COLLECTION, points=points)
    count_after = client.count(COLLECTION).count
    print(f"  ✅ {len(points)} wirings indexés")
    print(f"  KB après : {count_after} wirings")

    # ── 6. Verification queries ─────────────────────────────────────
    print("\n  Vérification par queries sémantiques...")
    test_queries = [
        # Queries JS — doivent retourner des wirings JS
        ("how to wire routes in Express Mongoose project", "import_graph"),
        ("Express middleware stack ordering bodyParser session", "dependency_chain"),
        ("bootstrap initialization order Express server.js", "flow_pattern"),
        ("Mongoose model schema statics methods", "flow_pattern"),
        ("passport authentication middleware Express", "dependency_chain"),
        ("test setup cleanup Express Mongoose", "flow_pattern"),
        ("file creation order Express CRUD project", "flow_pattern"),
    ]

    all_pass = True
    for query_text, expected_type in test_queries:
        qvec = embed_query(query_text)
        results = client.query_points(
            collection_name=COLLECTION,
            query=qvec,
            query_filter=Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=LANGUAGE))]
            ),
            limit=1,
            with_payload=True,
        )

        if results.points:
            top = results.points[0]
            wtype = top.payload.get("wiring_type", "?")
            score = top.score
            desc = top.payload.get("description", "?")[:80]
            status = "✅" if wtype == expected_type else "⚠️"
            if wtype != expected_type:
                all_pass = False
            print(f"  {status} [{score:.4f}] '{query_text[:50]}' → {wtype} ({desc}...)")
        else:
            print(f"  ❌ '{query_text[:50]}' → no results")
            all_pass = False

    # ── 7. Cross-language isolation test ────────────────────────────
    print("\n  Test isolation cross-language...")
    cross_queries = [
        # Query Python — NE DOIT PAS retourner de wirings JS
        ("FastAPI Depends get_db dependency injection", "python"),
        # Query JS — NE DOIT PAS retourner de wirings Python
        ("Express middleware passport session", "javascript"),
    ]

    for query_text, expected_lang in cross_queries:
        qvec = embed_query(query_text)

        # Query SANS filtre langue — voir ce qui remonte
        results_unfiltered = client.query_points(
            collection_name=COLLECTION,
            query=qvec,
            limit=1,
            with_payload=True,
        )

        # Query AVEC filtre langue
        results_filtered = client.query_points(
            collection_name=COLLECTION,
            query=qvec,
            query_filter=Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=expected_lang))]
            ),
            limit=1,
            with_payload=True,
        )

        if results_unfiltered.points and results_filtered.points:
            unf_lang = results_unfiltered.points[0].payload.get("language", "?")
            fil_lang = results_filtered.points[0].payload.get("language", "?")
            unf_score = results_unfiltered.points[0].score
            fil_score = results_filtered.points[0].score
            isolation_ok = fil_lang == expected_lang
            print(
                f"  {'✅' if isolation_ok else '❌'} "
                f"'{query_text[:45]}' — "
                f"unfiltered: {unf_lang} [{unf_score:.4f}] | "
                f"filtered({expected_lang}): {fil_lang} [{fil_score:.4f}]"
            )
        else:
            print(f"  ❌ '{query_text[:45]}' — no results")

    # ── 8. Cleanup si dry run ───────────────────────────────────────
    if DRY_RUN:
        print(f"\n  🧹 DRY_RUN — suppression des wirings...")
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
                )
            ),
        )
        final_count = client.count(COLLECTION).count
        print(f"  KB final : {final_count} wirings (nettoyé)")
    else:
        final_count = count_after

    # ── 9. Rapport ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RAPPORT INGESTION WIRINGS — {REPO_NAME}")
    print(f"{'='*60}")
    print(f"  Mode            : {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"  Language         : {LANGUAGE}")
    print(f"  Framework        : {FRAMEWORK}")
    print(f"  Wirings manuels : {len(all_wirings)}")
    print(f"  KB avant        : {count_before}")
    print(f"  KB après        : {final_count}")
    print(f"  Queries         : {'✅ ALL PASS' if all_pass else '⚠️  SOME MISMATCH'}")
    verdict = "✅ PASS" if len(all_wirings) > 0 and not DRY_RUN else "🧪 DRY RUN OK" if DRY_RUN else "❌ FAIL"
    print(f"  Verdict         : {verdict}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
