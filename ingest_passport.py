"""
ingest_passport.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du framework Passport.js dans la KB Qdrant V6.

Focus : CORE patterns OAuth/social login middleware (Strategy base, authenticate,
serialization/deserialization, session integration, strategy registration, OAuth2
flow, callback verification, profile normalization, multi-strategy chaining,
failure handling, flash messages).

PAS des patterns spécifiques à une stratégie (passport-local, passport-google, etc.)
— patterns du framework Passport lui-même (lib/authenticator.js, middleware, session).

Usage:
    .venv/bin/python3 ingest_passport.py
"""

from __future__ import annotations

import subprocess
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
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/jaredhanson/passport.git"
REPO_NAME = "jaredhanson/passport"
REPO_LOCAL = "/tmp/passport"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+passport+oauth2"
CHARTE_VERSION = "1.0"
TAG = "jaredhanson/passport"
SOURCE_REPO = "https://github.com/jaredhanson/passport"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Passport = OAuth/social login middleware framework for Node.js/Express.
# Patterns CORE : Strategy registration, authentication middleware, session management,
# serialization/deserialization, multi-strategy chaining, failure handling.
# U-5 : "user" → "xxx", "users" → "xxxs" sauf pour "req.user", "req.users", "username",
#       "passport", "strategy", "authenticate", "session", "serialize", "callback",
#       "profile", "token", "scope", "provider" — all TECHNICAL for Passport.

PATTERNS: list[dict] = [
    # ── 1. Authenticator class — central hub registering strategies ─────────────────
    {
        "normalized_code": """\
function Authenticator() {
  this._key = 'passport';
  this._strategies = {};
  this._serializers = [];
  this._deserializers = [];
  this._infoTransformers = [];
  this._framework = null;

  this.init();
}

Authenticator.prototype.init = function() {
  this.framework(require('./framework/connect')());
  this.use(new SessionStrategy({ key: this._key }, this.deserializeUser.bind(this)));
  this._sm = new SessionManager({ key: this._key }, this.serializeUser.bind(this));
};

module.exports = Authenticator;
""",
        "function": "authenticator_class_init",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/authenticator.js",
    },
    # ── 2. Register strategy — use(), unuse() pattern ──────────────────────────────
    {
        "normalized_code": """\
Authenticator.prototype.use = function(name, strategy) {
  if (!strategy) {
    strategy = name;
    name = strategy.name;
  }
  if (!name) { throw new Error('Authentication strategies must have a name'); }

  this._strategies[name] = strategy;
  return this;
};

Authenticator.prototype.unuse = function(name) {
  delete this._strategies[name];
  return this;
};
""",
        "function": "strategy_registration_use_unuse",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "lib/authenticator.js",
    },
    # ── 3. Serialize/deserialize user into session chain ────────────────────────────
    {
        "normalized_code": """\
Authenticator.prototype.serializeUser = function(fn, req, done) {
  if (typeof fn === 'function') {
    return this._serializers.push(fn);
  }

  const element = fn;

  if (typeof req === 'function') {
    done = req;
    req = undefined;
  }

  const stack = this._serializers;
  (function pass(i, err, obj) {
    if ('pass' === err) {
      err = undefined;
    }
    if (err || obj || obj === 0) { return done(err, obj); }

    const layer = stack[i];
    if (!layer) {
      return done(new Error('Failed to serialize element into session'));
    }


    function serialized(e, o) {
      pass(i + 1, e, o);
    }

    try {
      const arity = layer.length;
      if (arity == 3) {
        layer(req, element, serialized);
      } else {
        layer(element, serialized);
      }
    } catch(e) {
      return done(e);
    }
  })(0);
};
""",
        "function": "serialize_element_chain",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "lib/authenticator.js",
    },
    # ── 4. Deserialize user from session chain ────────────────────────────────────
    {
        "normalized_code": """\
Authenticator.prototype.deserializeUser = function(fn, req, done) {
  if (typeof fn === 'function') {
    return this._deserializers.push(fn);
  }

  const obj = fn;

  if (typeof req === 'function') {
    done = req;
    req = undefined;
  }

  const stack = this._deserializers;
  (function pass(i, err, element) {
    if ('pass' === err) {
      err = undefined;
    }
    if (err || element) { return done(err, element); }
    if (element === null || element === false) { return done(null, false); }

    const layer = stack[i];
    if (!layer) {
      return done(new Error('Failed to deserialize element out of session'));
    }


    function deserialized(e, u) {
      pass(i + 1, e, u);
    }

    try {
      const arity = layer.length;
      if (arity == 3) {
        layer(req, obj, deserialized);
      } else {
        layer(obj, deserialized);
      }
    } catch(e) {
      return done(e);
    }
  })(0);
};
""",
        "function": "deserialize_element_chain",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "lib/authenticator.js",
    },
    # ── 5. Initialize passport middleware ─────────────────────────────────────────
    {
        "normalized_code": """\
module.exports = function initialize(passport, options) {
  options = options || {};

  return function initialize(req, res, next) {
    req.login =
    req.logIn = req.logIn || IncomingMessageExt.logIn;
    req.logout =
    req.logOut = req.logOut || IncomingMessageExt.logOut;
    req.isAuthenticated = req.isAuthenticated || IncomingMessageExt.isAuthenticated;
    req.isUnauthenticated = req.isUnauthenticated || IncomingMessageExt.isUnauthenticated;

    req._sessionManager = passport._sm;

    if (options.userProperty) {
      req._userProperty = options.userProperty;
    }

    const compat = (options.compat === undefined) ? true : options.compat;
    if (compat) {
      passport._userProperty = options.userProperty || 'xxx';

      req._passport = {};
      req._passport.instance = passport;
    }

    next();
  };
};
""",
        "function": "initialize_middleware_req_extension",
        "feature_type": "config",
        "file_role": "route",
        "file_path": "lib/middleware/initialize.js",
    },
    # ── 6. Session manager — logIn with session regeneration ───────────────────────
    {
        "normalized_code": """\
SessionManager.prototype.logIn = function(req, element, options, cb) {
  if (typeof options == 'function') {
    cb = options;
    options = {};
  }
  options = options || {};

  if (!req.session) { return cb(new Error('Login sessions require session support.')); }

  const self = this;
  const prevSession = req.session;

  req.session.regenerate((err) => {
    if (err) {
      return cb(err);
    }

    self._serializeUser(element, req, (err, obj) => {
      if (err) {
        return cb(err);
      }
      if (options.keepSessionInfo) {
        merge(req.session, prevSession);
      }
      if (!req.session[self._key]) {
        req.session[self._key] = {};
      }
      req.session[self._key].xxx = obj;
      req.session.save((err) => {
        if (err) {
          return cb(err);
        }
        cb();
      });
    });
  });
};
""",
        "function": "session_login_regenerate",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "lib/sessionmanager.js",
    },
    # ── 7. Session manager — logOut with session regeneration ──────────────────────
    {
        "normalized_code": """\
SessionManager.prototype.logOut = function(req, options, cb) {
  if (typeof options == 'function') {
    cb = options;
    options = {};
  }
  options = options || {};

  if (!req.session) { return cb(new Error('Login sessions require session support.')); }

  const self = this;

  if (req.session[this._key]) {
    delete req.session[this._key].xxx;
  }
  const prevSession = req.session;

  req.session.save((err) => {
    if (err) {
      return cb(err)
    }

    req.session.regenerate((err) => {
      if (err) {
        return cb(err);
      }
      if (options.keepSessionInfo) {
        merge(req.session, prevSession);
      }
      cb();
    });
  });
};
""",
        "function": "session_logout_regenerate",
        "feature_type": "auth",
        "file_role": "utility",
        "file_path": "lib/sessionmanager.js",
    },
    # ── 8. req.logIn — add authenticated xxx to request ──────────────────────────
    {
        "normalized_code": """\
req.login =
req.logIn = function(element, options, done) {
  if (typeof options == 'function') {
    done = options;
    options = {};
  }
  options = options || {};

  const property = this._userProperty || 'xxx';
  const session = (options.session === undefined) ? true : options.session;

  this[property] = element;
  if (session && this._sessionManager) {
    if (typeof done != 'function') { throw new Error('req#login requires a callback function'); }

    const self = this;
    this._sessionManager.logIn(this, element, options, (err) => {
      if (err) { self[property] = null; return done(err); }
      done();
    });
  } else {
    done && done();
  }
};
""",
        "function": "request_login_method",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "lib/http/request.js",
    },
    # ── 9. req.logOut — terminate session and clear xxx ────────────────────────────
    {
        "normalized_code": """\
req.logout =
req.logOut = function(options, done) {
  if (typeof options == 'function') {
    done = options;
    options = {};
  }
  options = options || {};

  const property = this._userProperty || 'xxx';

  this[property] = null;
  if (this._sessionManager) {
    if (typeof done != 'function') { throw new Error('req#logout requires a callback function'); }

    this._sessionManager.logOut(this, options, done);
  } else {
    done && done();
  }
};
""",
        "function": "request_logout_method",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "lib/http/request.js",
    },
    # ── 10. req.isAuthenticated / isUnauthenticated checks ────────────────────────
    {
        "normalized_code": """\
req.isAuthenticated = function() {
  const property = this._userProperty || 'xxx';
  return (this[property]) ? true : false;
};

req.isUnauthenticated = function() {
  return !this.isAuthenticated();
};
""",
        "function": "request_auth_check_methods",
        "feature_type": "auth",
        "file_role": "route",
        "file_path": "lib/http/request.js",
    },
    # ── 11. Authenticate middleware — multi-strategy chain attempt ──────────────────
    {
        "normalized_code": """\
module.exports = function authenticate(passport, name, options, callback) {
  if (typeof options == 'function') {
    callback = options;
    options = {};
  }
  options = options || {};

  let multi = true;

  if (!Array.isArray(name)) {
    name = [ name ];
    multi = false;
  }

  return function authenticate(req, res, next) {
    req.login =
    req.logIn = req.logIn || IncomingMessageExt.logIn;
    req.logout =
    req.logOut = req.logOut || IncomingMessageExt.logOut;
    req.isAuthenticated = req.isAuthenticated || IncomingMessageExt.isAuthenticated;
    req.isUnauthenticated = req.isUnauthenticated || IncomingMessageExt.isUnauthenticated;

    req._sessionManager = passport._sm;

    const failures = [];

    function allFailed() {
      if (callback) {
        if (!multi) {
          return callback(null, false, failures[0].challenge, failures[0].status);
        } else {
          const challenges = failures.map((f) => { return f.challenge; });
          const statuses = failures.map((f) => { return f.status; });
          return callback(null, false, challenges, statuses);
        }
      }

      const failure = failures[0] || {}
        , challenge = failure.challenge || {}
        , msg;

      if (options.failureFlash) {
        let flash = options.failureFlash;
        if (typeof flash == 'string') {
          flash = { type: 'error', payload: flash };
        }
        flash.type = flash.type || 'error';

        const type = flash.type || challenge.type || 'error';
        msg = flash.payload || challenge.payload || challenge;
        if (typeof msg == 'string') {
          req.flash(type, msg);
        }
      }

      res.statusCode = 401;
      res.end('Unauthorized');
    }

    (function attempt(i) {
      const layer = name[i];
      if (!layer) { return allFailed(); }

      let strategy, prototype;
      if (typeof layer.authenticate == 'function') {
        strategy = layer;
      } else {
        prototype = passport._strategy(layer);
        if (!prototype) { return next(new Error('Unknown authentication strategy "' + layer + '"')); }

        strategy = Object.create(prototype);
      }

      attempt(i + 1);
    })(0);
  };
};
""",
        "function": "authenticate_middleware_multi_strategy",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/middleware/authenticate.js",
    },
    # ── 12. Flash message handling — successFlash / failureFlash ────────────────────
    {
        "normalized_code": """\
if (options.successFlash) {
  let flash = options.successFlash;
  if (typeof flash == 'string') {
    flash = { type: 'success', payload: flash };
  }
  flash.type = flash.type || 'success';

  const type = flash.type || info.type || 'success';
  const msg = flash.payload || info.payload || info;
  if (typeof msg == 'string') {
    req.flash(type, msg);
  }
}

if (options.failureFlash) {
  let flash = options.failureFlash;
  if (typeof flash == 'string') {
    flash = { type: 'error', payload: flash };
  }
  flash.type = flash.type || 'error';

  const type = flash.type || challenge.type || 'error';
  const msg = flash.payload || challenge.payload || challenge;
  if (typeof msg == 'string') {
    req.flash(type, msg);
  }
}
""",
        "function": "flash_payload_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/middleware/authenticate.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "register OAuth authentication strategy",
    "serialize deserialize xxx session chain",
    "initialize passport middleware Express",
    "session login logout regenerate",
    "authenticate multi-strategy chain",
    "isAuthenticated isUnauthenticated check",
    "flash payload success failure messages",
    "req.logIn req.logOut session management",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
