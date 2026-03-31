"""
Wirings ingestion script for hagopj13/node-express-boilerplate (JavaScript Medium)
Wal-e Lab V6 — Qdrant KB wirings collection

REPO: https://github.com/hagopj13/node-express-boilerplate.git
ARCH: 3-layer (Controller → Service → Model) + Mongoose plugins + Passport JWT + Joi validation + RBAC

NO AST extraction (JavaScript) — 100% manual wirings extracted from architecture analysis.
"""

from __future__ import annotations

import subprocess
import os
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/hagopj13/node-express-boilerplate.git"
REPO_NAME = "hagopj13/node-express-boilerplate"
REPO_LOCAL = "/tmp/node-express-boilerplate"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose+passport_jwt+joi"
CHARTE_VERSION = "1.0"
TAG = "wirings/hagopj13/node-express-boilerplate"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# ============================================================================
# MANUAL WIRINGS (9 wirings total)
# ============================================================================

MANUAL_WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "3-layer require chain: app.js loads config, middleware (passport, helmet, cors, morgan, error handler), routes. Routes import controllers. Controllers import services. Services import models.",
        "modules": [
            "src/app.js",
            "src/config/index.js",
            "src/routes/v1/index.js",
            "src/controllers/xxx.controller.js",
            "src/services/xxx.service.js",
            "src/models/xxx.model.js",
        ],
        "connections": [
            "app.js → config/index.js (require config)",
            "app.js → middleware/* (express.use)",
            "app.js → routes/v1/index.js (app.use('/v1', ...))",
            "routes/v1/xxx.route.js → controllers/xxx.controller.js (require)",
            "controllers/xxx.controller.js → services/xxx.service.js (require)",
            "services/xxx.service.js → models/xxx.model.js (require)",
        ],
        "code_example": """// src/app.js
const express = require('express');
const passport = require('passport');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');
const config = require('./config');
const routes = require('./routes/v1');
const { errorConverter, errorHandler } = require('./middlewares/error');

const app = express();

// === Middleware ===
app.use(helmet());
app.use(cors());
app.use(morgan('tiny'));
app.use(express.json());
app.use(passport.initialize());

// === Routes ===
app.use('/v1', routes);

// === Error handling ===
app.use(errorConverter);
app.use(errorHandler);

module.exports = app;

// src/controllers/xxx.controller.js
const xxxService = require('../services/xxx.service');
const catchAsync = require('../utils/catchAsync');

const createXxx = catchAsync(async (req, res) => {
  const result = await xxxService.createXxx(req.body);
  res.status(201).send(result);
});

module.exports = { createXxx };

// src/services/xxx.service.js
const { Xxx } = require('../models');

const createXxx = async (body) => {
  const xxx = await Xxx.create(body);
  return xxx;
};

module.exports = { createXxx };
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Complete file creation order for a feature: 1) config/ (roles, env), 2) models/ (xxx.model.js with Mongoose schema + plugins), 3) services/ (xxx.service.js CRUD + business logic), 4) validations/ (xxx.validation.js Joi schemas), 5) controllers/ (xxx.controller.js), 6) middlewares/ (auth, validate), 7) routes/v1/ (xxx.route.js), 8) app.js wired up",
        "modules": [
            "src/config/roles.js",
            "src/models/xxx.model.js",
            "src/services/xxx.service.js",
            "src/validations/xxx.validation.js",
            "src/controllers/xxx.controller.js",
            "src/middlewares/auth.js",
            "src/routes/v1/xxx.route.js",
            "src/app.js",
        ],
        "connections": [
            "models/xxx.model.js uses Mongoose schema + toJSON + paginate plugins",
            "services/xxx.service.js imports Xxx model, implements CRUD",
            "validations/xxx.validation.js exports Joi schemas (body, params, query)",
            "controllers/xxx.controller.js imports xxxService, wraps with catchAsync",
            "middlewares/auth.js exports auth(requiredRights) for role-based checks",
            "routes/v1/xxx.route.js: router.post('/', validate(xxxValidation.createXxx), auth(requiredRights), xxxController.createXxx)",
            "app.js: app.use('/v1', routes)",
        ],
        "code_example": """// Step 1: config/roles.js
const roles = ['user', 'admin'];
const roleRights = {
  user: [],
  admin: ['manageXxxs'],
};

// Step 2: src/models/xxx.model.js
const mongoose = require('mongoose');
const { toJSON, paginate } = require('./plugins');

const xxxSchema = new mongoose.Schema({
  name: { type: String, required: true },
  description: String,
  createdAt: { type: Date, default: () => new Date() },
}, { timestamps: true });

xxxSchema.plugin(toJSON);
xxxSchema.plugin(paginate);

const Xxx = mongoose.model('Xxx', xxxSchema);

// Step 3: src/services/xxx.service.js
const { Xxx } = require('../models');

const createXxx = async (body) => {
  return Xxx.create(body);
};

const getXxxById = async (id) => {
  return Xxx.findById(id);
};

const updateXxx = async (id, body) => {
  return Xxx.findByIdAndUpdate(id, body, { new: true });
};

const deleteXxx = async (id) => {
  return Xxx.findByIdAndDelete(id);
};

const queryXxxs = async (filter, options) => {
  return Xxx.paginate(filter, options);
};

module.exports = { createXxx, getXxxById, updateXxx, deleteXxx, queryXxxs };

// Step 4: src/validations/xxx.validation.js
const Joi = require('joi');

const createXxx = {
  body: Joi.object().keys({
    name: Joi.string().required(),
    description: Joi.string(),
  }),
};

const getXxx = {
  params: Joi.object().keys({
    id: Joi.string().required(),
  }),
};

module.exports = { createXxx, getXxx };

// Step 5: src/controllers/xxx.controller.js
const { xxxService } = require('../services');
const catchAsync = require('../utils/catchAsync');

const createXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.createXxx(req.body);
  res.status(201).send(xxx);
});

const getXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.getXxxById(req.params.id);
  res.send(xxx);
});

module.exports = { createXxx, getXxx };

// Step 6: src/middlewares/auth.js + validate.js already defined
// Step 7: src/routes/v1/xxx.route.js
const express = require('express');
const { validate } = require('../../middlewares');
const { auth } = require('../../middlewares');
const { xxxController } = require('../../controllers');
const { xxxValidation } = require('../../validations');

const router = express.Router();

router
  .route('/')
  .post(validate(xxxValidation.createXxx), auth('manageXxxs'), xxxController.createXxx);

router
  .route('/:id')
  .get(validate(xxxValidation.getXxx), xxxController.getXxx);

module.exports = router;

// Step 8: app.js includes all routes (see wiring 1)
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Request flow through 3-layer architecture: Route handler → validate() middleware (Joi) → auth() middleware (JWT + role check) → catchAsync(controller) → service → model → response or error",
        "modules": [
            "src/routes/v1/xxx.route.js",
            "src/middlewares/validate.js",
            "src/middlewares/auth.js",
            "src/utils/catchAsync.js",
            "src/controllers/xxx.controller.js",
            "src/services/xxx.service.js",
            "src/models/xxx.model.js",
        ],
        "connections": [
            "Route defines: router.post('/', validate(schema), auth(rights), controller)",
            "validate middleware: extracts schema, checks req.body/params/query, strips unknown, passes to next()",
            "auth middleware: calls passport.authenticate('jwt'), extracts req.user, checks roleRights, passes to next()",
            "catchAsync wrapper: executes controller promise, catches errors → next(error)",
            "controller: calls service method, res.send(data) or delegates error",
            "service: business logic, queries model, throws ApiError on failure",
            "model: Mongoose operations (create, find, update, delete)",
            "error middleware: catches ApiError, converts to JSON response",
        ],
        "code_example": """// src/routes/v1/xxx.route.js
const router = express.Router();

router.post(
  '/',
  validate(xxxValidation.createXxx),    // === Step 1: Joi validation ===
  auth('manageXxxs'),                    // === Step 2: JWT auth + role check ===
  xxxController.createXxx                // === Step 3: catchAsync(controller) ===
);

// src/middlewares/validate.js
const validate = (schema) => (req, res, next) => {
  const validSchema = pick(schema, Object.keys(req));
  const object = pick(req, Object.keys(validSchema));
  const { value, error } = Joi.compile(validSchema)
    .prefs({ errors: { label: 'key' } })
    .validate(object);

  if (error) {
    const errorMessage = error.details
      .map((details) => `\${details.message}`)
      .join(', ');
    return res.status(400).json({ code: 400, message: errorMessage });
  }
  Object.assign(req, value);
  return next();
};

// src/middlewares/auth.js
const auth = (requiredRights) => async (req, res, next) => {
  return passport.authenticate('jwt', { session: false }, (err, user) => {
    if (!user) return res.status(401).json({ code: 401, message: 'Unauthorized' });

    const userRights = config.roleRights[user.role];
    const hasRequiredRights = !requiredRights || requiredRights.every(
      (requiredRight) => userRights.includes(requiredRight)
    );

    if (!hasRequiredRights) {
      return res.status(403).json({ code: 403, message: 'Forbidden' });
    }

    req.user = user;
    next();
  })(req, res, next);
};

// src/utils/catchAsync.js
const catchAsync = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch((err) => next(err));
};

// src/controllers/xxx.controller.js — wrapped with catchAsync
const createXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.createXxx(req.body);
  res.status(201).send(xxx);
});

// src/services/xxx.service.js
const createXxx = async (body) => {
  const xxx = await Xxx.create(body);
  return xxx;
};

// Error handler in app.js
app.use((err, req, res, next) => {
  if (err instanceof ApiError) {
    res.status(err.statusCode).send({ code: err.statusCode, message: err.message });
  } else {
    res.status(500).send({ code: 500, message: 'Internal Server Error' });
  }
});
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "JWT authentication middleware chain: passport.authenticate('jwt') with local strategy config → extract user from token → attach req.user → route-level roleRights check via auth(requiredRights) middleware → grant/deny access",
        "modules": [
            "src/config/passport.js",
            "src/middlewares/auth.js",
            "src/routes/v1/*.route.js",
            "src/models/user.model.js",
            "src/services/token.service.js",
        ],
        "connections": [
            "passport.js: JwtStrategy configured with secretOrKey = config.jwt.secret, extract user from payload",
            "auth.js: wraps passport.authenticate('jwt', { session: false }), checks user.role against requiredRights",
            "routes: define auth(requiredRights) middleware on protected endpoints",
            "token.service.js: generates JWT on login with user._id + role in payload",
            "user.model.js: findById(userId) called by JwtStrategy to populate req.user",
        ],
        "code_example": """// src/config/passport.js
const { Strategy: JwtStrategy, ExtractJwt } = require('passport-jwt');
const config = require('./config');
const { User } = require('../models');

const jwtOptions = {
  secretOrKey: config.jwt.secret,
  jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
};

passport.use(
  'jwt',
  new JwtStrategy(jwtOptions, async (payload, done) => {
    try {
      const user = await User.findById(payload.sub);
      if (!user) return done(null, false);
      done(null, user);
    } catch (error) {
      done(error);
    }
  })
);

// src/middlewares/auth.js
const auth = (requiredRights) => async (req, res, next) => {
  return passport.authenticate('jwt', { session: false }, (err, user) => {
    if (!user) {
      return res.status(401).json({ code: 401, message: 'Unauthorized' });
    }

    if (requiredRights) {
      const userRights = config.roleRights[user.role] || [];
      const hasRights = requiredRights.every((r) => userRights.includes(r));
      if (!hasRights) {
        return res.status(403).json({ code: 403, message: 'Forbidden' });
      }
    }

    req.user = user;
    next();
  })(req, res, next);
};

// src/routes/v1/user.route.js
const router = express.Router();
router.get('/:id', validate(userValidation.getUser), auth(), userController.getUser);
// === Only authenticated users can GET /users/:id ===
router.delete('/:id', validate(userValidation.deleteUser), auth('manageUsers'), userController.deleteUser);
// === Only admin with 'manageUsers' right can DELETE ===

// src/services/token.service.js
const generateToken = (userId, type, role) => {
  const payload = {
    sub: userId,
    iat: Math.floor(Date.now() / 1000),
    type: type,
    role: role,
  };
  const secret = config.jwt.secret;
  const expiresIn = config.jwt.accessExpirationMinutes * 60;
  return jwt.sign(payload, secret, { expiresIn });
};
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Token management flow: login endpoint → authService.loginWithEmailAndPassword() → generate access + refresh tokens → store refresh token in Token model → response to client. Client sends refresh token → verifyToken() + check blacklist in Token model → issue new pair → old refresh blacklisted",
        "modules": [
            "src/services/token.service.js",
            "src/services/auth.service.js",
            "src/models/token.model.js",
            "src/controllers/auth.controller.js",
            "src/routes/v1/auth.route.js",
        ],
        "connections": [
            "routes: POST /auth/login → authController.login",
            "controller: calls authService.loginWithEmailAndPassword(email, password)",
            "auth.service: verifies user password, calls tokenService.generateAuthTokens(user._id)",
            "token.service: creates access token + refresh token (JWT), saves refresh in Token model with type='REFRESH'",
            "response: { user: {...}, tokens: { access: {...}, refresh: {...} } }",
            "refresh flow: POST /auth/refresh with refreshToken → tokenService.verifyToken(refreshToken) → check Token record not blacklisted → generate new pair → blacklist old refresh",
        ],
        "code_example": """// src/services/token.service.js
const { Token } = require('../models');
const jwt = require('jsonwebtoken');
const config = require('../config');

const generateAuthTokens = async (userId) => {
  const accessToken = generateToken(userId, 'ACCESS', 'user');
  const refreshToken = generateToken(userId, 'REFRESH', 'user');

  await Token.create({
    token: refreshToken,
    user: userId,
    type: 'REFRESH',
    blacklisted: false,
  });

  return { access: { token: accessToken }, refresh: { token: refreshToken } };
};

const verifyToken = async (token, type) => {
  const payload = jwt.verify(token, config.jwt.secret);
  const tokenDoc = await Token.findOne({ token, type, user: payload.sub });

  if (!tokenDoc || tokenDoc.blacklisted) {
    throw new ApiError(401, 'Token revoked or invalid');
  }

  return payload;
};

const blacklistToken = async (token) => {
  await Token.updateOne({ token }, { blacklisted: true });
};

// src/services/auth.service.js
const loginWithEmailAndPassword = async (email, password) => {
  const user = await User.findOne({ email });
  if (!user || !(await user.isPasswordMatch(password))) {
    throw new ApiError(401, 'Incorrect email or password');
  }
  return user;
};

// src/controllers/auth.controller.js
const login = catchAsync(async (req, res) => {
  const user = await authService.loginWithEmailAndPassword(req.body.email, req.body.password);
  const tokens = await tokenService.generateAuthTokens(user._id);
  res.send({ user: user.toJSON(), tokens });
});

const refreshTokens = catchAsync(async (req, res) => {
  const payload = await tokenService.verifyToken(req.body.refreshToken, 'REFRESH');
  await tokenService.blacklistToken(req.body.refreshToken);
  const newTokens = await tokenService.generateAuthTokens(payload.sub);
  res.send(newTokens);
});

// src/routes/v1/auth.route.js
router.post('/login', validate(authValidation.login), authController.login);
router.post('/refresh-tokens', validate(authValidation.refreshTokens), authController.refreshTokens);
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Joi validation middleware chain: per-route schema definition (body, query, params) → validate middleware picks correct schema from req object keys → runs Joi.compile().validate() → strips unknown fields → if error: 400 JSON response. If pass: value merged back into req",
        "modules": [
            "src/validations/xxx.validation.js",
            "src/middlewares/validate.js",
            "src/routes/v1/xxx.route.js",
            "src/utils/pick.js",
        ],
        "connections": [
            "validation file: exports object with validate(schema) for each endpoint (createXxx, getXxx, updateXxx, deleteXxx, etc.)",
            "schema object: { body: Joi.object(...), params: Joi.object(...), query: Joi.object(...) }",
            "route: router.post('/', validate(xxxValidation.createXxx), controller)",
            "validate middleware: receives schema, picks matching keys from req (body, params, query), validates, strips unknown",
            "error path: return 400 with field-level error messages",
            "success path: Object.assign(req, value) merges validated/typed values back, next()",
        ],
        "code_example": """// src/validations/xxx.validation.js
const Joi = require('joi');

const createXxx = {
  body: Joi.object().keys({
    name: Joi.string().required(),
    description: Joi.string(),
    active: Joi.boolean().default(true),
  }),
};

const getXxx = {
  params: Joi.object().keys({
    id: Joi.string().regex(/^[0-9a-fA-F]{24}\$/).required(),
  }),
};

const listXxxs = {
  query: Joi.object().keys({
    sortBy: Joi.string(),
    limit: Joi.number().integer().min(1).max(100),
    page: Joi.number().integer().min(1),
  }),
};

module.exports = { createXxx, getXxx, listXxxs };

// src/middlewares/validate.js
const Joi = require('joi');
const pick = require('../utils/pick');

const validate = (schema) => (req, res, next) => {
  // === Pick only relevant parts (body, params, query, headers) ===
  const validSchema = pick(schema, Object.keys(req));
  const object = pick(req, Object.keys(validSchema));

  // === Validate ===
  const { value, error } = Joi.compile(validSchema)
    .prefs({ errors: { label: 'key' } })
    .validate(object);

  if (error) {
    const errorMessage = error.details
      .map((details) => \`\${details.context.label}: \${details.message}\`)
      .join(', ');
    return res.status(400).json({
      code: 400,
      message: errorMessage,
    });
  }

  // === Merge validated values back into req ===
  Object.assign(req, value);
  return next();
};

module.exports = validate;

// src/utils/pick.js
const pick = (object, keys) => {
  return keys.reduce((obj, key) => {
    if (object && Object.prototype.hasOwnProperty.call(object, key)) {
      obj[key] = object[key];
    }
    return obj;
  }, {});
};

// src/routes/v1/xxx.route.js
const router = express.Router();

router
  .route('/')
  .post(validate(xxxValidation.createXxx), xxxController.createXxx)  // body validated
  .get(validate(xxxValidation.listXxxs), xxxController.listXxxs);    // query validated

router
  .route('/:id')
  .get(validate(xxxValidation.getXxx), xxxController.getXxx)         // params validated
  .patch(validate(xxxValidation.updateXxx), xxxController.updateXxx)
  .delete(validate(xxxValidation.deleteXxx), xxxController.deleteXxx);
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Mongoose plugin wiring: toJSON plugin (transforms _id to id, removes __v, respects private fields marked `private: true` in schema) + paginate plugin (adds static .paginate(filter, options) returning { results: [...], page, limit, pages, total }). Both registered via schema.plugin()",
        "modules": [
            "src/models/plugins/toJSON.js",
            "src/models/plugins/paginate.js",
            "src/models/xxx.model.js",
            "src/services/xxx.service.js",
        ],
        "connections": [
            "toJSON plugin: schema.plugin(toJSON) → overrides toJSON() method, transforms response",
            "paginate plugin: schema.plugin(paginate) → adds static Xxx.paginate(filter, options) method",
            "service calls Xxx.paginate(filter, options) → returns paginated response",
            "response includes: results[], page, limit, pages (Math.ceil(total/limit)), total",
        ],
        "code_example": """// src/models/plugins/toJSON.js
const toJSON = (schema) => {
  schema.set('toJSON', {
    virtuals: true,
    versionKey: false,
    transform: (doc, ret) => {
      // === _id → id ===
      ret.id = ret._id;
      delete ret._id;

      // === Remove __v ===
      delete ret.__v;

      // === Remove private fields ===
      schema.eachPath((path) => {
        const schemaType = schema.path(path);
        if (schemaType.options.private) {
          delete ret[path];
        }
      });

      return ret;
    },
  });
};

module.exports = toJSON;

// src/models/plugins/paginate.js
const paginate = (schema) => {
  schema.statics.paginate = async function (filter = {}, options = {}) {
    const page = options.page || 1;
    const limit = options.limit || 10;
    const skip = (page - 1) * limit;
    const sort = options.sortBy || { createdAt: -1 };

    const total = await this.countDocuments(filter);
    const results = await this.find(filter).sort(sort).limit(limit).skip(skip);

    return {
      results,
      page,
      limit,
      pages: Math.ceil(total / limit),
      total,
    };
  };
};

module.exports = paginate;

// src/models/xxx.model.js
const mongoose = require('mongoose');
const { toJSON, paginate } = require('./plugins');

const xxxSchema = new mongoose.Schema({
  name: { type: String, required: true },
  email: { type: String, unique: true, private: true },
  password: { type: String, private: true },
  role: { type: String, default: 'user' },
  createdAt: { type: Date, default: () => new Date() },
});

xxxSchema.plugin(toJSON);
xxxSchema.plugin(paginate);

const Xxx = mongoose.model('Xxx', xxxSchema);

// src/services/xxx.service.js
const queryXxxs = async (filter, options) => {
  const result = await Xxx.paginate(filter, options);
  // === { results: [...], page, limit, pages, total } ===
  return result;
};

// src/controllers/xxx.controller.js
const listXxxs = catchAsync(async (req, res) => {
  const options = { page: req.query.page, limit: req.query.limit, sortBy: req.query.sortBy };
  const result = await xxxService.queryXxxs({}, options);
  // === Response: { results: [...], page: 1, limit: 10, pages: 5, total: 42 } ===
  res.send(result);
});
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Error handling chain: catchAsync wraps controller → ApiError thrown in service → error converter middleware (req.json set to default {} if undefined) → error handler middleware catches error → logs with winston logger → converts ApiError to JSON response with statusCode + message. In production: stack trace hidden",
        "modules": [
            "src/utils/catchAsync.js",
            "src/utils/ApiError.js",
            "src/middlewares/error.js",
            "src/config/logger.js",
            "src/services/xxx.service.js",
            "src/controllers/xxx.controller.js",
        ],
        "connections": [
            "service: throws new ApiError(statusCode, message) on failure",
            "catchAsync: wraps controller, catches rejected Promise → next(err)",
            "errorConverter middleware: ensures err is ApiError instance, sets req.json defaults",
            "errorHandler middleware: logs error via winston, responds with err.statusCode + err.message",
            "error.js exports both converter and handler",
        ],
        "code_example": """// src/utils/ApiError.js
class ApiError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.statusCode = statusCode;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

module.exports = ApiError;

// src/utils/catchAsync.js
const catchAsync = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch((err) => next(err));
};

module.exports = catchAsync;

// src/middlewares/error.js
const config = require('../config');
const logger = require('../config/logger');
const ApiError = require('../utils/ApiError');

const errorConverter = (err, req, res, next) => {
  let error = err;

  if (!(error instanceof ApiError)) {
    const statusCode = error.statusCode || 500;
    const message = error.message || 'Internal Server Error';
    error = new ApiError(statusCode, message);
  }

  // === Ensure req.json is set for logging ===
  req.json = req.json || {};

  next(error);
};

const errorHandler = (err, req, res, next) => {
  // === Log error ===
  logger.error({
    message: err.message,
    status: err.statusCode,
    stack: err.stack,
    path: req.originalUrl,
  });

  // === Hide stack trace in production ===
  const response = {
    code: err.statusCode || 500,
    message: err.message,
  };

  if (config.env === 'development') {
    response.stack = err.stack;
  }

  res.status(err.statusCode || 500).send(response);
};

module.exports = { errorConverter, errorHandler };

// src/config/logger.js
const winston = require('winston');

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.json(),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: 'error.log', level: 'error' }),
    new winston.transports.File({ filename: 'combined.log' }),
  ],
});

module.exports = logger;

// src/app.js
const { errorConverter, errorHandler } = require('./middlewares/error');
app.use(errorConverter);
app.use(errorHandler);

// src/services/xxx.service.js
const createXxx = async (body) => {
  const existing = await Xxx.findOne({ name: body.name });
  if (existing) {
    throw new ApiError(409, 'Xxx with this name already exists');
  }
  return Xxx.create(body);
};
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Test wiring: jest + supertest, setupTestDB fixture (mongoose.connect to test MongoDB, clear all collections between tests), generateAuthToken helper, test user fixtures. beforeAll: create test DB, afterAll: close. beforeEach: clear collections. Test structure: arrange (createXxx()), act (client.get()), assert (expect())",
        "modules": [
            "tests/setup.js",
            "tests/fixtures/db.js",
            "tests/fixtures/user.fixture.js",
            "tests/fixtures/auth.fixture.js",
            "tests/unit/xxx.test.js",
            "tests/integration/xxx.integration.test.js",
            "jest.config.js",
        ],
        "connections": [
            "jest.config.js: testEnvironment='node', setupFilesAfterEnv=['tests/setup.js']",
            "setup.js: beforeAll(setupTestDB), afterAll(closeTestDB), beforeEach(clearCollections)",
            "db.fixture: connects to TEST_DATABASE_URL='mongodb://localhost:27017/test-db'",
            "user.fixture: createUserInDb(userData) → returns { user, password }",
            "auth.fixture: generateAuthToken(userId, userRole) → returns JWT string",
            "integration test: createUser() → generateToken() → client.get('/users/:id', { auth header }) → assert 200 + body",
        ],
        "code_example": """// jest.config.js
module.exports = {
  testEnvironment: 'node',
  setupFilesAfterEnv: ['<rootDir>/tests/setup.js'],
  testMatch: ['**/tests/**/*.test.js'],
  collectCoverageFrom: ['src/**/*.js', '!src/**/*.test.js'],
};

// tests/setup.js
const { setupTestDB, closeTestDB, clearCollections } = require('./fixtures/db');

beforeAll(async () => {
  await setupTestDB();
});

afterAll(async () => {
  await closeTestDB();
});

beforeEach(async () => {
  await clearCollections();
});

// tests/fixtures/db.js
const mongoose = require('mongoose');

const setupTestDB = async () => {
  const TEST_DATABASE_URL = process.env.TEST_DATABASE_URL || 'mongodb://localhost:27017/wale-test';
  await mongoose.connect(TEST_DATABASE_URL);
};

const closeTestDB = async () => {
  await mongoose.connection.close();
};

const clearCollections = async () => {
  const collections = mongoose.connection.collections;
  for (const key in collections) {
    await collections[key].deleteMany({});
  }
};

module.exports = { setupTestDB, closeTestDB, clearCollections };

// tests/fixtures/user.fixture.js
const { User } = require('../../src/models');
const bcrypt = require('bcryptjs');

const createUserInDb = async (userOverride = {}) => {
  const userData = {
    email: 'test@example.com',
    password: 'Test@123456',
    name: 'Test User',
    role: 'user',
    ...userOverride,
  };

  const hash = await bcrypt.hash(userData.password, 8);
  const user = await User.create({ ...userData, password: hash });
  return { user, password: userData.password };
};

module.exports = { createUserInDb };

// tests/fixtures/auth.fixture.js
const jwt = require('jsonwebtoken');
const config = require('../../src/config');

const generateAuthToken = (userId, role = 'user') => {
  const payload = {
    sub: userId,
    type: 'ACCESS',
    role: role,
  };
  return jwt.sign(payload, config.jwt.secret, { expiresIn: '7d' });
};

module.exports = { generateAuthToken };

// tests/integration/xxx.integration.test.js
const request = require('supertest');
const app = require('../../src/app');
const { createUserInDb } = require('../fixtures/user.fixture');
const { generateAuthToken } = require('../fixtures/auth.fixture');

describe('Xxx Integration Tests', () => {
  let user;
  let token;

  beforeEach(async () => {
    const { user: createdUser } = await createUserInDb({ role: 'admin' });
    user = createdUser;
    token = generateAuthToken(user._id, 'admin');
  });

  it('should create Xxx when authenticated', async () => {
    const res = await request(app)
      .post('/v1/xxxs')
      .set('Authorization', \`Bearer \${token}\`)
      .send({ name: 'Test Xxx', description: 'Test' });

    expect(res.status).toBe(201);
    expect(res.body).toHaveProperty('id');
    expect(res.body.name).toBe('Test Xxx');
  });

  it('should return 401 when not authenticated', async () => {
    const res = await request(app)
      .post('/v1/xxxs')
      .send({ name: 'Test Xxx' });

    expect(res.status).toBe(401);
  });
});
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
]

# ============================================================================
# MAIN
# ============================================================================


def main():
    print(f"\n{'=' * 80}")
    print(f"Wirings Ingestion: {REPO_NAME} (JavaScript)")
    print(f"Language: {LANGUAGE} | Framework: {FRAMEWORK}")
    print(f"Wirings: {len(MANUAL_WIRINGS)} manual (no AST extraction)")
    print(f"{'=' * 80}\n")

    # =========================================================================
    # 1. Initialize Qdrant client
    # =========================================================================
    kb_path = Path(KB_PATH)
    if not kb_path.exists():
        print(f"ERROR: KB path {KB_PATH} does not exist. Run setup_collections.py first.\n")
        return

    try:
        client = QdrantClient(path=str(kb_path))
        print(f"✓ Qdrant client initialized at {KB_PATH}")
    except Exception as e:
        print(f"ERROR: Failed to initialize Qdrant client: {e}\n")
        return

    # =========================================================================
    # 2. Check collection exists
    # =========================================================================
    try:
        collection = client.get_collection(COLLECTION)
        print(f"✓ Collection '{COLLECTION}' exists ({collection.points_count} points)")
    except Exception as e:
        print(f"ERROR: Collection '{COLLECTION}' not found: {e}\n")
        return

    # =========================================================================
    # 3. Cleanup old wirings for this repo
    # =========================================================================
    print(f"\n→ Cleaning up old wirings (tag={TAG})...")
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="_tag", match=MatchValue(value=TAG))
                    ]
                )
            ),
        )
        print(f"✓ Old wirings cleaned up")
    except Exception as e:
        print(f"WARNING: Cleanup failed: {e}")

    # =========================================================================
    # 4. Embed all wirings
    # =========================================================================
    print(f"\n→ Embedding {len(MANUAL_WIRINGS)} wirings...")
    try:
        descriptions = [w["description"] for w in MANUAL_WIRINGS]
        embeddings = embed_documents_batch(descriptions)
        print(f"✓ Embedded {len(embeddings)} descriptions")
    except Exception as e:
        print(f"ERROR: Embedding failed: {e}\n")
        return

    # =========================================================================
    # 5. Build points
    # =========================================================================
    print(f"\n→ Building Qdrant points...")
    points = []
    for i, wiring in enumerate(MANUAL_WIRINGS):
        point = PointStruct(
            id=uuid.uuid4().int % (2**63 - 1),  # 63-bit positive int
            vector=embeddings[i],
            payload={
                "wiring_type": wiring["wiring_type"],
                "description": wiring["description"],
                "modules": wiring["modules"],
                "connections": wiring["connections"],
                "code_example": wiring["code_example"],
                "pattern_scope": wiring["pattern_scope"],
                "language": wiring["language"],
                "framework": wiring["framework"],
                "stack": wiring["stack"],
                "source_repo": wiring["source_repo"],
                "charte_version": wiring["charte_version"],
                "created_at": wiring["created_at"],
                "_tag": wiring["_tag"],
            },
        )
        points.append(point)

    print(f"✓ Built {len(points)} points")

    # =========================================================================
    # 6. Upsert into Qdrant
    # =========================================================================
    print(f"\n→ Upserting into Qdrant...")
    if DRY_RUN:
        print(f"DRY RUN: Would upsert {len(points)} points")
        return

    try:
        client.upsert(
            collection_name=COLLECTION,
            points=points,
        )
        print(f"✓ Upserted {len(points)} points")
    except Exception as e:
        print(f"ERROR: Upsert failed: {e}\n")
        return

    # =========================================================================
    # 7. Verify with test queries
    # =========================================================================
    print(f"\n→ Verifying with test queries...")
    test_queries = [
        ("request flow 3-layer architecture", "flow_pattern"),
        ("JWT authentication token", "dependency_chain"),
        ("Mongoose plugin toJSON paginate", "flow_pattern"),
        ("error handling ApiError", "dependency_chain"),
        ("Joi validation middleware", "dependency_chain"),
    ]

    for query_text, expected_type in test_queries:
        try:
            query_vector = embed_query(query_text)
            results = client.query_points(
                collection_name=COLLECTION,
                query=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="language", match=MatchValue(value=LANGUAGE)),
                        FieldCondition(
                            key="wiring_type", match=MatchValue(value=expected_type)
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
            )
            if results and len(results.points) > 0:
                point = results.points[0]
                desc = point.payload.get("description", "")[:60]
                print(f"  ✓ Query '{query_text}' → matched (score={results.points[0].score:.3f})")
            else:
                print(f"  ✗ Query '{query_text}' → no match (language={LANGUAGE})")
        except Exception as e:
            print(f"  ✗ Query '{query_text}' → error: {e}")

    # =========================================================================
    # 8. Summary
    # =========================================================================
    print(f"\n{'=' * 80}")
    print(f"✓ SUCCESS: Ingested {len(MANUAL_WIRINGS)} wirings for {REPO_NAME}")
    print(f"  - Collection: {COLLECTION}")
    print(f"  - Language: {LANGUAGE} | Framework: {FRAMEWORK}")
    print(f"  - Tag: {TAG}")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
