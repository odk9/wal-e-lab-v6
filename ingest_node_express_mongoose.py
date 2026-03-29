"""
ingest_node_express_mongoose.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de madhums/node-express-mongoose-demo dans la KB Qdrant V6.

Premier repo JavaScript dans la KB.

Usage:
    .venv/bin/python3 ingest_node_express_mongoose.py
"""

from __future__ import annotations

import os
import subprocess

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import (
    audit_report,
    build_payload,
    check_charte_violations,
    make_uuid,
)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/madhums/node-express-mongoose-demo.git"
REPO_NAME = "madhums/node-express-mongoose-demo"
REPO_LOCAL = "/tmp/node_express_mongoose"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose+passport"
CHARTE_VERSION = "1.0"
TAG = "madhums/node-express-mongoose-demo"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/madhums/node-express-mongoose-demo"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# Source: node-express-mongoose-demo (blog app → concrete patterns)
# Normalization applied:
#   U-5:  Article→Xxx, User→Xxx, Comment→XxxComment, Tag→XxxLabel
#   U-7/J-3: console.log removed
#   J-1:  var → const/let
#   J-2:  generator callbacks (co wrap) → async/await
#   U-1:  imports ordered (built-in → npm → local)

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS (Mongoose)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Mongoose schema — basic entity with refs + embedded subdocs ───────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  title: { type: String, default: '', trim: true, maxlength: 400 },
  body: { type: String, default: '', trim: true, maxlength: 1000 },
  xxx_ref: { type: Schema.ObjectId, ref: 'Xxx' },
  sub_xxxs: [
    {
      body: { type: String, default: '', maxlength: 1000 },
      xxx_ref: { type: Schema.ObjectId, ref: 'Xxx' },
      createdAt: { type: Date, default: Date.now },
    },
  ],
  createdAt: { type: Date, default: Date.now },
});

XxxSchema.path('title').required(true, 'Title cannot be blank');
XxxSchema.path('body').required(true, 'Body cannot be blank');

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_schema_refs_subdocs",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ── 2. Mongoose schema — auth entity with bcrypt + virtual ───────────────
    {
        "normalized_code": """\
const bcrypt = require('bcrypt');
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  name: { type: String, default: '' },
  email: { type: String, default: '' },
  hashed_password: { type: String, default: '' },
  provider: { type: String, default: '' },
  authToken: { type: String, default: '' },
  github: {},
  google: {},
});

XxxSchema.virtual('password')
  .set(function (password) {
    this._password = password;
    this.hashed_password = this.encryptPassword(password);
  })
  .get(function () {
    return this._password;
  });

XxxSchema.methods = {
  authenticate(password) {
    return bcrypt.compareSync(password, this.hashed_password);
  },

  encryptPassword(password) {
    if (!password) return '';
    return bcrypt.hashSync(password, 10);
  },

  skipValidation() {
    return ~['github', 'google'].indexOf(this.provider);
  },
};

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_auth_schema_bcrypt_virtual",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ── 3. Mongoose pre-save hook — validation ───────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  name: { type: String, default: '' },
  email: { type: String, default: '' },
  hashed_password: { type: String, default: '' },
});

const validatePresenceOf = (value) => value && value.length;

XxxSchema.pre('save', function (next) {
  if (!this.isNew) return next();
  if (!validatePresenceOf(this.password) && !this.skipValidation()) {
    next(new Error('Invalid password'));
  } else {
    next();
  }
});

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_pre_save_hook_validation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ── 4. Mongoose email uniqueness async validation ────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  email: { type: String, default: '' },
});

XxxSchema.path('email').validate(function (email) {
  return new Promise((resolve) => {
    const XxxModel = mongoose.model('Xxx');
    if (this.skipValidation()) return resolve(true);
    if (this.isNew || this.isModified('email')) {
      XxxModel.find({ email })
        .exec()
        .then((results) => resolve(!results.length));
    } else {
      resolve(true);
    }
  });
}, 'Email `{VALUE}` already exists');

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_email_uniqueness_validation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ── 5. Mongoose statics — load by id with populate ───────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  title: { type: String, default: '' },
  xxx_ref: { type: Schema.ObjectId, ref: 'XxxRef' },
});

XxxSchema.statics = {
  load(_id) {
    return this.findOne({ _id })
      .populate('xxx_ref', 'name email')
      .exec();
  },

  list(options) {
    const criteria = options.criteria || {};
    const page = options.page || 0;
    const limit = options.limit || 30;
    return this.find(criteria)
      .populate('xxx_ref', 'name')
      .sort({ createdAt: -1 })
      .limit(limit)
      .skip(limit * page)
      .exec();
  },
};

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_statics_load_list_populate",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ── 6. Mongoose instance methods — add/remove embedded subdoc ────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { Schema } = mongoose;

const XxxSchema = new Schema({
  title: String,
  sub_xxxs: [
    {
      body: { type: String, default: '', maxlength: 1000 },
      xxx_ref: { type: Schema.ObjectId, ref: 'XxxRef' },
      createdAt: { type: Date, default: Date.now },
    },
  ],
});

XxxSchema.methods = {
  addSubXxx(xxxRef, subXxx) {
    this.sub_xxxs.push({
      body: subXxx.body,
      xxx_ref: xxxRef._id,
    });
    return this.save();
  },

  removeSubXxx(subXxxId) {
    const index = this.sub_xxxs
      .map((s) => s.id)
      .indexOf(subXxxId);
    if (~index) this.sub_xxxs.splice(index, 1);
    else throw new Error('Sub-xxx not found');
    return this.save();
  },
};

module.exports = mongoose.model('Xxx', XxxSchema);
""",
        "function": "mongoose_instance_methods_subdoc",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/models/xxx.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS / ROUTES (Express)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 7. Express controller — CRUD create (async/await) ────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const only = require('only');

const Xxx = mongoose.model('Xxx');

exports.create = async function (req, res) {
  const xxx = new Xxx(only(req.body, 'title body'));
  xxx.xxx_ref = req.user;
  try {
    await xxx.save();
    res.redirect(`/xxxs/${xxx._id}`);
  } catch (err) {
    res.status(422).render('xxxs/new', {
      title: 'New Xxx',
      errors: [err.toString()],
      xxx,
    });
  }
};
""",
        "function": "express_controller_create_async",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 8. Express controller — list with pagination ─────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const Xxx = mongoose.model('Xxx');

exports.index = async function (req, res) {
  const page = (req.query.page > 0 ? req.query.page : 1) - 1;
  const limit = 15;
  const options = { limit, page };

  const xxxs = await Xxx.list(options);
  const count = await Xxx.countDocuments();

  res.render('xxxs/index', {
    title: 'Xxxs',
    xxxs,
    page: page + 1,
    pages: Math.ceil(count / limit),
  });
};
""",
        "function": "express_controller_list_paginated",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 9. Express controller — load param middleware ────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const Xxx = mongoose.model('Xxx');

exports.load = async function (req, res, next, id) {
  try {
    req.xxx = await Xxx.load(id);
    if (!req.xxx) return next(new Error('Xxx not found'));
  } catch (err) {
    return next(err);
  }
  next();
};
""",
        "function": "express_param_load_middleware",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 10. Express controller — update ──────────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const only = require('only');

const Xxx = mongoose.model('Xxx');

exports.update = async function (req, res) {
  const xxx = req.xxx;
  Object.assign(xxx, only(req.body, 'title body'));
  try {
    await xxx.save();
    res.redirect(`/xxxs/${xxx._id}`);
  } catch (err) {
    res.status(422).render('xxxs/edit', {
      title: 'Edit Xxx',
      errors: [err.toString()],
      xxx,
    });
  }
};
""",
        "function": "express_controller_update_async",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 11. Express controller — delete ──────────────────────────────────────
    {
        "normalized_code": """\
exports.destroy = async function (req, res) {
  await req.xxx.remove();
  res.redirect('/xxxs');
};
""",
        "function": "express_controller_delete_async",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 12. Express controller — show ────────────────────────────────────────
    {
        "normalized_code": """\
exports.show = function (req, res) {
  res.render('xxxs/show', {
    title: req.xxx.title,
    xxx: req.xxx,
  });
};
""",
        "function": "express_controller_show",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 13. Express controller — create auth entity + login ──────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const Xxx = mongoose.model('Xxx');

exports.create = async function (req, res) {
  const xxx = new Xxx(req.body);
  xxx.provider = 'local';
  try {
    await xxx.save();
    req.logIn(xxx, (err) => {
      if (err) req.flash('info', 'Unable to log in');
      res.redirect('/');
    });
  } catch (err) {
    const errors = Object.keys(err.errors).map(
      (field) => err.errors[field].message
    );
    res.render('xxxs/signup', {
      title: 'Sign up',
      errors,
      xxx,
    });
  }
};
""",
        "function": "express_controller_register_login",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 14. Express logout controller ────────────────────────────────────────
    {
        "normalized_code": """\
exports.logout = function (req, res) {
  req.logout();
  res.redirect('/login');
};
""",
        "function": "express_controller_logout",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 15. Express login redirect (session returnTo) ────────────────────────
    {
        "normalized_code": """\
function loginRedirect(req, res) {
  const redirectTo = req.session.returnTo ? req.session.returnTo : '/';
  delete req.session.returnTo;
  res.redirect(redirectTo);
}
""",
        "function": "express_login_redirect_return_to",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/xxxs.js",
    },

    # ── 16. Express subdoc controller — add embedded ─────────────────────────
    {
        "normalized_code": """\
exports.create = async function (req, res) {
  const xxx = req.xxx;
  await xxx.addSubXxx(req.user, req.body);
  res.redirect(`/xxxs/${xxx._id}`);
};

exports.destroy = async function (req, res) {
  await req.xxx.removeSubXxx(req.params.subXxxId);
  res.redirect(`/xxxs/${req.xxx.id}`);
};
""",
        "function": "express_controller_subdoc_crud",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/controllers/sub_xxxs.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH (Passport.js)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 17. Passport local strategy ──────────────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const LocalStrategy = require('passport-local').Strategy;

const Xxx = mongoose.model('Xxx');

module.exports = new LocalStrategy(
  {
    usernameField: 'email',
    passwordField: 'password',
  },
  async function (email, password, done) {
    try {
      const xxx = await Xxx.findOne({ email })
        .select('name email hashed_password')
        .exec();
      if (!xxx) {
        return done(null, false, { message: 'Unknown account' });
      }
      if (!xxx.authenticate(password)) {
        return done(null, false, { message: 'Invalid password' });
      }
      return done(null, xxx);
    } catch (err) {
      return done(err);
    }
  }
);
""",
        "function": "passport_local_strategy",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport/local.js",
    },

    # ── 18. Passport GitHub OAuth strategy ───────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const GithubStrategy = require('passport-github').Strategy;

const Xxx = mongoose.model('Xxx');

module.exports = new GithubStrategy(
  {
    clientID: process.env.GITHUB_CLIENT_ID,
    clientSecret: process.env.GITHUB_CLIENT_SECRET,
    callbackURL: process.env.GITHUB_CALLBACK_URL,
    scope: ['user:email'],
  },
  async function (accessToken, refreshToken, profile, done) {
    try {
      let xxx = await Xxx.findOne({ 'github.id': parseInt(profile.id) }).exec();
      if (!xxx) {
        xxx = new Xxx({
          name: profile.displayName,
          email: profile.emails[0].value,
          provider: 'github',
          github: profile._json,
        });
        await xxx.save();
      }
      return done(null, xxx);
    } catch (err) {
      return done(err);
    }
  }
);
""",
        "function": "passport_github_oauth_strategy",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport/github.js",
    },

    # ── 19. Passport Google OAuth strategy ───────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const GoogleStrategy = require('passport-google-oauth').OAuth2Strategy;

const Xxx = mongoose.model('Xxx');

module.exports = new GoogleStrategy(
  {
    clientID: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    callbackURL: process.env.GOOGLE_CALLBACK_URL,
  },
  async function (accessToken, refreshToken, profile, done) {
    try {
      let xxx = await Xxx.findOne({ 'google.id': profile.id }).exec();
      if (!xxx) {
        xxx = new Xxx({
          name: profile.displayName,
          email: profile.emails[0].value,
          provider: 'google',
          google: profile._json,
        });
        await xxx.save();
      }
      return done(null, xxx);
    } catch (err) {
      return done(err);
    }
  }
);
""",
        "function": "passport_google_oauth_strategy",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport/google.js",
    },

    # ── 20. Passport serialize/deserialize + registration ────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const Xxx = mongoose.model('Xxx');

module.exports = function (passport) {
  passport.serializeUser((xxx, cb) => cb(null, xxx.id));
  passport.deserializeUser(async (id, cb) => {
    try {
      const xxx = await Xxx.findById(id).exec();
      cb(null, xxx);
    } catch (err) {
      cb(err);
    }
  });

  passport.use(localStrategy);
  passport.use(googleStrategy);
  passport.use(githubStrategy);
};
""",
        "function": "passport_serialize_deserialize",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 21. Requires login middleware ────────────────────────────────────────
    {
        "normalized_code": """\
exports.requiresLogin = function (req, res, next) {
  if (req.isAuthenticated()) return next();
  if (req.method === 'GET') req.session.returnTo = req.originalUrl;
  res.redirect('/login');
};
""",
        "function": "express_requires_login_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/middlewares/authorization.js",
    },

    # ── 22. Resource authorization middleware (owner check) ──────────────────
    {
        "normalized_code": """\
exports.xxx = {
  hasAuthorization(req, res, next) {
    if (req.xxx.xxx_ref.id !== req.user.id) {
      req.flash('info', 'You are not authorized');
      return res.redirect(`/xxxs/${req.xxx.id}`);
    }
    next();
  },
};
""",
        "function": "express_resource_authorization_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/middlewares/authorization.js",
    },

    # ── 23. Subdoc authorization middleware (owner or parent owner) ───────────
    {
        "normalized_code": """\
exports.subXxx = {
  hasAuthorization(req, res, next) {
    if (
      req.user.id === req.subXxx.xxx_ref.id ||
      req.user.id === req.xxx.xxx_ref.id
    ) {
      next();
    } else {
      req.flash('info', 'You are not authorized');
      res.redirect(`/xxxs/${req.xxx.id}`);
    }
  },
};
""",
        "function": "express_subdoc_authorization_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/middlewares/authorization.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 24. Express app setup — middleware chain ─────────────────────────────
    {
        "normalized_code": """\
const bodyParser = require('body-parser');
const compression = require('compression');
const cookieParser = require('cookie-parser');
const cors = require('cors');
const express = require('express');
const flash = require('connect-flash');
const helmet = require('helmet');
const methodOverride = require('method-override');
const morgan = require('morgan');
const session = require('express-session');

const MongoStore = require('connect-mongo');

module.exports = function (app, passport) {
  app.use(helmet());
  app.use(compression({ threshold: 512 }));
  app.use(
    cors({
      origin: [process.env.CORS_ORIGIN || 'http://localhost:3000'],
      credentials: true,
    })
  );
  app.use(express.static('public'));
  app.use(morgan('dev'));
  app.use(bodyParser.json());
  app.use(bodyParser.urlencoded({ extended: true }));
  app.use(methodOverride());
  app.use(cookieParser());
  app.use(
    session({
      resave: false,
      saveUninitialized: true,
      secret: process.env.SESSION_SECRET || 'secret',
      store: MongoStore.create({
        mongoUrl: process.env.MONGODB_URI,
        collection: 'sessions',
      }),
    })
  );
  app.use(passport.initialize());
  app.use(passport.session());
  app.use(flash());
};
""",
        "function": "express_middleware_chain_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "config/express.js",
    },

    # ── 25. Mongoose connection setup ────────────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

function connect(dbUrl) {
  mongoose.connection
    .on('error', (err) => { throw err; })
    .on('disconnected', () => connect(dbUrl))
    .once('open', () => {});
  return mongoose.connect(dbUrl, {
    keepAlive: 1,
    useNewUrlParser: true,
    useUnifiedTopology: true,
  });
}

module.exports = { connect };
""",
        "function": "mongoose_connection_setup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "config/mongoose.js",
    },

    # ── 26. Route registration (Express app.verb pattern) ────────────────────
    {
        "normalized_code": """\
const xxxCtrl = require('../app/controllers/xxxs');
const subXxxCtrl = require('../app/controllers/sub_xxxs');
const auth = require('./middlewares/authorization');

const xxxAuth = [auth.requiresLogin, auth.xxx.hasAuthorization];
const subXxxAuth = [auth.requiresLogin, auth.subXxx.hasAuthorization];

module.exports = function (app, passport) {
  const pauth = passport.authenticate.bind(passport);

  // auth
  app.get('/login', xxxCtrl.login);
  app.get('/signup', xxxCtrl.signup);
  app.get('/logout', xxxCtrl.logout);
  app.post(
    '/xxxs/session',
    pauth('local', { failureRedirect: '/login', failureFlash: true }),
    xxxCtrl.session
  );
  app.get('/auth/github', pauth('github', { failureRedirect: '/login' }));
  app.get('/auth/github/callback', pauth('github', { failureRedirect: '/login' }), xxxCtrl.authCallback);
  app.get('/auth/google', pauth('google', { failureRedirect: '/login', scope: ['profile', 'email'] }));
  app.get('/auth/google/callback', pauth('google', { failureRedirect: '/login' }), xxxCtrl.authCallback);

  // CRUD
  app.param('id', xxxCtrl.load);
  app.get('/xxxs', xxxCtrl.index);
  app.get('/xxxs/new', auth.requiresLogin, xxxCtrl.new);
  app.post('/xxxs', auth.requiresLogin, xxxCtrl.create);
  app.get('/xxxs/:id', xxxCtrl.show);
  app.get('/xxxs/:id/edit', xxxAuth, xxxCtrl.edit);
  app.put('/xxxs/:id', xxxAuth, xxxCtrl.update);
  app.delete('/xxxs/:id', xxxAuth, xxxCtrl.destroy);

  // sub-xxxs
  app.param('subXxxId', subXxxCtrl.load);
  app.post('/xxxs/:id/sub-xxxs', auth.requiresLogin, subXxxCtrl.create);
  app.delete('/xxxs/:id/sub-xxxs/:subXxxId', subXxxAuth, subXxxCtrl.destroy);

  // error handling
  app.use((err, req, res, next) => {
    if (err.message && ~err.message.indexOf('not found')) return next();
    res.status(500).render('500', { error: err.stack });
  });

  app.use((req, res) => {
    if (req.accepts('json')) return res.status(404).json({ error: 'Not found' });
    res.status(404).render('404');
  });
};
""",
        "function": "express_route_registration_full",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "config/routes.js",
    },

    # ── 27. Server entry point — bootstrap + connect ─────────────────────────
    {
        "normalized_code": """\
require('dotenv').config();

const fs = require('fs');
const path = require('path');

const express = require('express');
const mongoose = require('mongoose');
const passport = require('passport');

const config = require('./config');

const modelsPath = path.join(__dirname, 'app/models');
const port = process.env.PORT || 3000;
const app = express();

module.exports = app;

// Bootstrap models
fs.readdirSync(modelsPath)
  .filter((file) => ~file.search(/^[^.].*\\.js$/))
  .forEach((file) => require(path.join(modelsPath, file)));

// Bootstrap config
require('./config/passport')(passport);
require('./config/express')(app, passport);
require('./config/routes')(app, passport);

async function start() {
  await mongoose.connect(config.db);
  if (app.get('env') !== 'test') {
    app.listen(port);
  }
}

start();
""",
        "function": "express_server_entry_bootstrap",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "server.js",
    },

    # ── 28. Config by environment ────────────────────────────────────────────
    {
        "normalized_code": """\
const path = require('path');

const development = require('./env/development');
const test = require('./env/test');
const production = require('./env/production');

const defaults = {
  root: path.join(__dirname, '..'),
};

module.exports = {
  development: Object.assign({}, development, defaults),
  test: Object.assign({}, test, defaults),
  production: Object.assign({}, production, defaults),
}[process.env.NODE_ENV || 'development'];
""",
        "function": "config_by_environment",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "config/index.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 29. Test helper — cleanup DB ─────────────────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const Xxx = mongoose.model('Xxx');

exports.cleanup = async function () {
  await Xxx.deleteMany();
};
""",
        "function": "test_helper_cleanup_db",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "test/helper.js",
    },

    # ── 30. Test — create entity via HTTP ────────────────────────────────────
    {
        "normalized_code": """\
const request = require('supertest');

const app = require('../server');

const agent = request.agent(app);

test('create xxx - when not logged in - should redirect', async () => {
  const res = await request(app).get('/xxxs/new');
  expect(res.status).toBe(302);
  expect(res.headers.location).toBe('/login');
});

test('create xxx - valid form - should succeed', async () => {
  const res = await agent
    .post('/xxxs')
    .field('title', 'foo')
    .field('body', 'bar');
  expect(res.status).toBe(302);
  expect(res.headers.location).toMatch(/\\/xxxs\\//);
});
""",
        "function": "test_create_entity_http",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "test/test-xxxs-create.js",
    },

    # ── 31. Test — login + authenticated request ─────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const request = require('supertest');

const app = require('../server');

const Xxx = mongoose.model('Xxx');
const agent = request.agent(app);

const _xxx = {
  email: 'foo@example.com',
  name: 'Foo Bar',
  password: 'foobar123',
};

test('Create account', async () => {
  const xxx = new Xxx(_xxx);
  await xxx.save();
});

test('Login', async () => {
  await agent
    .post('/xxxs/session')
    .field('email', _xxx.email)
    .field('password', _xxx.password)
    .expect(302);
});
""",
        "function": "test_login_authenticated_request",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "test/test-xxxs-create.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Mongoose schema with pre-save hook password hash",
    "Express CRUD route create with validation",
    "Passport.js local strategy authenticate",
    "Express middleware authorization check logged in",
    "Mongoose connection setup with options",
]


def clone_repo() -> None:
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo already cloned: {REPO_LOCAL}")
        return
    print(f"  Cloning {REPO_URL} → {REPO_LOCAL} ...")
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
    )
    print("  Cloned.")


def build_payloads() -> list[dict]:
    payloads = []
    all_violations = []
    for p in PATTERNS:
        v = check_charte_violations(
            p["normalized_code"], p["function"], language=LANGUAGE
        )
        all_violations.extend(v)
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
    if all_violations:
        print("  PRE-INDEX violations:")
        for v in all_violations:
            print(f"    WARN: {v}")
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    print(f"  Embedding {len(codes)} patterns (batch) ...")
    vectors = embed_documents_batch(codes)
    print(f"  {len(vectors)} vectors generated.")

    points = []
    for i, (vec, payload) in enumerate(zip(vectors, payloads)):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
        if (i + 1) % 5 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points prepared")

    print(f"  Upserting {len(points)} points into '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print("  Upsert done.")
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = client.query_points(
            collection_name=COLLECTION, query=vec, limit=1
        ).points
        if hits:
            h = hits[0]
            tag = h.payload.get("_tag", "?")
            lang = h.payload.get("language", "?")
            results.append({
                "query": q,
                "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
                "_tag": tag,
                "language": lang,
            })
        else:
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
                "_tag": "?",
                "language": "?",
            })
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
        ),
        limit=100,
    )
    points = scroll_result[0]
    violations = []
    for point in points:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        violations.extend(check_charte_violations(code, fn, language=LANGUAGE))
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
            )
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN (test)' if DRY_RUN else 'PRODUCTION'}")
    print(f"  Language: {LANGUAGE} (first JS repo in KB)")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)

    # ── Step 1: Prerequisites ────────────────────────────────────────────
    print("── Step 1: Prerequisites")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERROR: collection '{COLLECTION}' not found.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}': {count_initial} points (initial)")

    # ── Step 2: Clone ────────────────────────────────────────────────────
    print("\n── Step 2: Clone")
    clone_repo()

    # ── Step 3-4: Extraction + Normalization ─────────────────────────────
    print(f"\n── Step 3-4: {len(PATTERNS)} patterns extracted and normalized")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads built.")

    # ── Step 5: Indexation ───────────────────────────────────────────────
    print("\n── Step 5: Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []
    verdict = "FAIL"

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count after indexation: {count_after}")

        # ── Step 6: Audit ────────────────────────────────────────────────
        print("\n── Step 6: Audit")
        print("\n  6a. Semantic queries:")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        # 6b. Cross-language discrimination
        print("\n  6b. Cross-language discrimination:")
        cross_lang_warns = 0
        for r in query_results:
            lang = r.get("language", "?")
            if lang != LANGUAGE:
                print(
                    f"    WARN: '{r['query'][:40]}' returned {lang} "
                    f"pattern ({r['function']})"
                )
                cross_lang_warns += 1
        if cross_lang_warns == 0:
            print("    All JS queries returned JS patterns ✓")

        print("\n  6c. Normalization audit:")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    No violations detected ✓")

        scores_valid = all(0.0 <= r["score"] <= 1.0 for r in query_results)
        no_empty = all(r["function"] != "NO_RESULT" for r in query_results)
        verdict = "PASS" if (scores_valid and no_empty and not violations) else "FAIL"

    finally:
        # ── Step 7: Cleanup/conservation ─────────────────────────────────
        print(f"\n── Step 7: {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points deleted. Count final: {count_final}")
            if count_final == count_initial:
                print(f"  Count back to {count_initial} ✓")
            else:
                print(f"  WARN: final ({count_final}) != initial ({count_initial})")
            print("  DRY_RUN — data deleted")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")
            print(f"  To remove: filter _tag='{TAG}' via FilterSelector")

    # ── Step 8: Report ───────────────────────────────────────────────────
    count_now = client.count(collection_name=COLLECTION).count
    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_now,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)
    print(f"  Verdict: {'✅ PASS' if verdict == 'PASS' else '❌ FAIL'}")
    if verdict == "FAIL" and violations:
        print(f"  {len(violations)} blocking violations")


if __name__ == "__main__":
    main()
