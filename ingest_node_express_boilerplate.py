"""
ingest_node_express_boilerplate.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de hagopj13/node-express-boilerplate dans la KB Qdrant V6.

Second JS repo — architecture 3-layer (Controller → Service → Model).

Usage:
    .venv/bin/python3 ingest_node_express_boilerplate.py
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
    query_kb,
)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/hagopj13/node-express-boilerplate.git"
REPO_NAME = "hagopj13/node-express-boilerplate"
REPO_LOCAL = "/tmp/node_express_boilerplate"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose+passport_jwt+joi"
CHARTE_VERSION = "1.0"
TAG = "hagopj13/node-express-boilerplate"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/hagopj13/node-express-boilerplate"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: User→Xxx, user→xxx, users→xxxs, Token→XxxToken, token→xxxToken,
#       userId→xxxId. Kept: email, password, name, role (generic fields).
# J-1: no var. J-3: no console.log.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1a. Mongoose schema — entity definition + plugins + validation ───────
    {
        "normalized_code": """\
const mongoose = require('mongoose');
const validator = require('validator');

const { toJSON, paginate } = require('./plugins');
const { roles } = require('../config/roles');

const xxxSchema = mongoose.Schema(
  {
    name: { type: String, required: true, trim: true },
    email: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      lowercase: true,
      validate(value) {
        if (!validator.isEmail(value)) throw new Error('Invalid email');
      },
    },
    password: {
      type: String,
      required: true,
      trim: true,
      minlength: 8,
      validate(value) {
        if (!value.match(/\\d/) || !value.match(/[a-zA-Z]/))
          throw new Error(
            'Password must contain at least one letter and one number'
          );
      },
      private: true,
    },
    role: { type: String, enum: roles, default: 'xxx' },
    isEmailVerified: { type: Boolean, default: false },
  },
  { timestamps: true }
);

xxxSchema.plugin(toJSON);
xxxSchema.plugin(paginate);

const Xxx = mongoose.model('Xxx', xxxSchema);
module.exports = Xxx;
""",
        "function": "mongoose_schema_validation_plugins_rbac",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/models/xxx.model.js",
    },

    # ── 1b. Mongoose static — isEmailTaken ──────────────────────────────────
    {
        "normalized_code": """\
xxxSchema.statics.isEmailTaken = async function (email, excludeXxxId) {
  const xxx = await this.findOne({ email, _id: { $ne: excludeXxxId } });
  return !!xxx;
};
""",
        "function": "mongoose_static_is_email_taken",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/models/xxx.model.js",
    },

    # ── 1c. Mongoose method + pre-save bcrypt ────────────────────────────────
    {
        "normalized_code": """\
const bcrypt = require('bcryptjs');

xxxSchema.methods.isPasswordMatch = async function (password) {
  return bcrypt.compare(password, this.password);
};

xxxSchema.pre('save', async function (next) {
  if (this.isModified('password')) {
    this.password = await bcrypt.hash(this.password, 8);
  }
  next();
});
""",
        "function": "mongoose_method_password_match_presave_bcrypt",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/models/xxx.model.js",
    },

    # ── 2. Mongoose token model with enum type ───────────────────────────────
    {
        "normalized_code": """\
const mongoose = require('mongoose');

const { toJSON } = require('./plugins');
const { xxxTokenTypes } = require('../config/xxxTokens');

const xxxTokenSchema = mongoose.Schema(
  {
    xxxToken: { type: String, required: true, index: true },
    xxx: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Xxx',
      required: true,
    },
    type: {
      type: String,
      enum: [
        xxxTokenTypes.REFRESH,
        xxxTokenTypes.RESET_PASSWORD,
        xxxTokenTypes.VERIFY_EMAIL,
      ],
      required: true,
    },
    expires: { type: Date, required: true },
    blacklisted: { type: Boolean, default: false },
  },
  { timestamps: true }
);

xxxTokenSchema.plugin(toJSON);

const XxxToken = mongoose.model('XxxToken', xxxTokenSchema);
module.exports = XxxToken;
""",
        "function": "mongoose_token_model_enum_type",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/models/xxxToken.model.js",
    },

    # ── 3. toJSON plugin — sanitize private fields + _id→id ──────────────────
    {
        "normalized_code": """\
const deleteAtPath = (obj, path, index) => {
  if (index === path.length - 1) {
    delete obj[path[index]];
    return;
  }
  deleteAtPath(obj[path[index]], path, index + 1);
};

const toJSON = (schema) => {
  let transform;
  if (schema.options.toJSON && schema.options.toJSON.transform) {
    transform = schema.options.toJSON.transform;
  }
  schema.options.toJSON = Object.assign(schema.options.toJSON || {}, {
    transform(doc, ret, options) {
      Object.keys(schema.paths).forEach((path) => {
        if (
          schema.paths[path].options &&
          schema.paths[path].options.private
        ) {
          deleteAtPath(ret, path.split('.'), 0);
        }
      });
      ret.id = ret._id.toString();
      delete ret._id;
      delete ret.__v;
      delete ret.createdAt;
      delete ret.updatedAt;
      if (transform) return transform(doc, ret, options);
    },
  });
};

module.exports = toJSON;
""",
        "function": "mongoose_tojson_plugin_sanitize",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/models/plugins/toJSON.plugin.js",
    },

    # ── 4. paginate plugin — sort, limit, page, populate ─────────────────────
    {
        "normalized_code": """\
const paginate = (schema) => {
  schema.statics.paginate = async function (filter, options) {
    let sort = '';
    if (options.sortBy) {
      const sortingCriteria = [];
      options.sortBy.split(',').forEach((sortOption) => {
        const [key, direction] = sortOption.split(':');
        sortingCriteria.push((direction === 'desc' ? '-' : '') + key);
      });
      sort = sortingCriteria.join(' ');
    } else {
      sort = 'createdAt';
    }

    const limit =
      options.limit && parseInt(options.limit, 10) > 0
        ? parseInt(options.limit, 10)
        : 10;
    const page =
      options.page && parseInt(options.page, 10) > 0
        ? parseInt(options.page, 10)
        : 1;
    const skip = (page - 1) * limit;

    const countPromise = this.countDocuments(filter).exec();
    let docsPromise = this.find(filter).sort(sort).skip(skip).limit(limit);

    if (options.populate) {
      options.populate.split(',').forEach((populateOption) => {
        docsPromise = docsPromise.populate(
          populateOption
            .split('.')
            .reverse()
            .reduce((a, b) => ({ path: b, populate: a }))
        );
      });
    }

    docsPromise = docsPromise.exec();

    return Promise.all([countPromise, docsPromise]).then((values) => {
      const [totalResults, results] = values;
      const totalPages = Math.ceil(totalResults / limit);
      return { results, page, limit, totalPages, totalResults };
    });
  };
};

module.exports = paginate;
""",
        "function": "mongoose_paginate_plugin",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/models/plugins/paginate.plugin.js",
    },

    # ── 5. models barrel export ──────────────────────────────────────────────
    {
        "normalized_code": """\
module.exports.Xxx = require('./xxx.model');
module.exports.XxxToken = require('./xxxToken.model');
""",
        "function": "models_barrel_export",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/models/index.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 6. Entity CRUD controller — 5 functions ──────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const ApiError = require('../utils/ApiError');
const catchAsync = require('../utils/catchAsync');
const pick = require('../utils/pick');
const { xxxService } = require('../services');

const createXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.createXxx(req.body);
  res.status(httpStatus.CREATED).send(xxx);
});

const getXxxs = catchAsync(async (req, res) => {
  const filter = pick(req.query, ['name', 'role']);
  const options = pick(req.query, ['sortBy', 'limit', 'page']);
  const result = await xxxService.queryXxxs(filter, options);
  res.send(result);
});

const getXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.getXxxById(req.params.xxxId);
  if (!xxx) throw new ApiError(httpStatus.NOT_FOUND, 'Xxx not found');
  res.send(xxx);
});

const updateXxx = catchAsync(async (req, res) => {
  const xxx = await xxxService.updateXxxById(req.params.xxxId, req.body);
  res.send(xxx);
});

const deleteXxx = catchAsync(async (req, res) => {
  await xxxService.deleteXxxById(req.params.xxxId);
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = { createXxx, getXxxs, getXxx, updateXxx, deleteXxx };
""",
        "function": "controller_crud_catch_async",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/controllers/xxx.controller.js",
    },

    # ── 7. Auth controller — register ────────────────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const catchAsync = require('../utils/catchAsync');
const { authService, xxxService, xxxTokenService, emailService } = require('../services');

const register = catchAsync(async (req, res) => {
  const xxx = await xxxService.createXxx(req.body);
  const xxxTokens = await xxxTokenService.generateAuthXxxTokens(xxx);
  res.status(httpStatus.CREATED).send({ xxx, xxxTokens });
});

module.exports = { register };
""",
        "function": "controller_auth_register",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/controllers/auth.controller.js",
    },

    # ── 8. Auth controller — login + logout ──────────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const catchAsync = require('../utils/catchAsync');
const { authService, xxxTokenService } = require('../services');

const login = catchAsync(async (req, res) => {
  const { email, password } = req.body;
  const xxx = await authService.loginWithEmailAndPassword(email, password);
  const xxxTokens = await xxxTokenService.generateAuthXxxTokens(xxx);
  res.send({ xxx, xxxTokens });
});

const logout = catchAsync(async (req, res) => {
  await authService.logout(req.body.refreshXxxToken);
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = { login, logout };
""",
        "function": "controller_auth_login_logout",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/controllers/auth.controller.js",
    },

    # ── 9. Auth controller — refresh + forgot + reset + verify ───────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const catchAsync = require('../utils/catchAsync');
const { authService, xxxTokenService, emailService } = require('../services');

const refreshXxxTokens = catchAsync(async (req, res) => {
  const xxxTokens = await authService.refreshAuth(req.body.refreshXxxToken);
  res.send({ ...xxxTokens });
});

const forgotPassword = catchAsync(async (req, res) => {
  const resetPasswordXxxToken =
    await xxxTokenService.generateResetPasswordXxxToken(req.body.email);
  await emailService.sendResetPasswordEmail(
    req.body.email,
    resetPasswordXxxToken
  );
  res.status(httpStatus.NO_CONTENT).send();
});

const resetPassword = catchAsync(async (req, res) => {
  await authService.resetPassword(req.query.xxxToken, req.body.password);
  res.status(httpStatus.NO_CONTENT).send();
});

const sendVerificationEmail = catchAsync(async (req, res) => {
  const verifyEmailXxxToken =
    await xxxTokenService.generateVerifyEmailXxxToken(req.user);
  await emailService.sendVerificationEmail(
    req.user.email,
    verifyEmailXxxToken
  );
  res.status(httpStatus.NO_CONTENT).send();
});

const verifyEmail = catchAsync(async (req, res) => {
  await authService.verifyEmail(req.query.xxxToken);
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = {
  refreshXxxTokens,
  forgotPassword,
  resetPassword,
  sendVerificationEmail,
  verifyEmail,
};
""",
        "function": "controller_auth_refresh_reset_verify",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/controllers/auth.controller.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SERVICES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 10. Entity CRUD service — 6 functions ────────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const { Xxx } = require('../models');
const ApiError = require('../utils/ApiError');

const createXxx = async (body) => {
  if (await Xxx.isEmailTaken(body.email))
    throw new ApiError(httpStatus.BAD_REQUEST, 'Email already taken');
  return Xxx.create(body);
};

const queryXxxs = async (filter, options) => {
  return Xxx.paginate(filter, options);
};

const getXxxById = async (id) => Xxx.findById(id);

const getXxxByEmail = async (email) => Xxx.findOne({ email });

const updateXxxById = async (xxxId, updateBody) => {
  const xxx = await getXxxById(xxxId);
  if (!xxx) throw new ApiError(httpStatus.NOT_FOUND, 'Xxx not found');
  if (
    updateBody.email &&
    (await Xxx.isEmailTaken(updateBody.email, xxxId))
  )
    throw new ApiError(httpStatus.BAD_REQUEST, 'Email already taken');
  Object.assign(xxx, updateBody);
  await xxx.save();
  return xxx;
};

const deleteXxxById = async (xxxId) => {
  const xxx = await getXxxById(xxxId);
  if (!xxx) throw new ApiError(httpStatus.NOT_FOUND, 'Xxx not found');
  await xxx.remove();
  return xxx;
};

module.exports = {
  createXxx,
  queryXxxs,
  getXxxById,
  getXxxByEmail,
  updateXxxById,
  deleteXxxById,
};
""",
        "function": "service_crud_full",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/services/xxx.service.js",
    },

    # ── 11. Auth service — login, logout, refreshAuth ────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const { XxxToken } = require('../models');
const ApiError = require('../utils/ApiError');
const { xxxTokenTypes } = require('../config/xxxTokens');
const xxxTokenService = require('./xxxToken.service');
const xxxService = require('./xxx.service');

const loginWithEmailAndPassword = async (email, password) => {
  const xxx = await xxxService.getXxxByEmail(email);
  if (!xxx || !(await xxx.isPasswordMatch(password)))
    throw new ApiError(
      httpStatus.UNAUTHORIZED,
      'Incorrect email or password'
    );
  return xxx;
};

const logout = async (refreshXxxToken) => {
  const doc = await XxxToken.findOne({
    xxxToken: refreshXxxToken,
    type: xxxTokenTypes.REFRESH,
    blacklisted: false,
  });
  if (!doc) throw new ApiError(httpStatus.NOT_FOUND, 'Not found');
  await doc.remove();
};

const refreshAuth = async (refreshXxxToken) => {
  try {
    const doc = await xxxTokenService.verifyXxxToken(
      refreshXxxToken,
      xxxTokenTypes.REFRESH
    );
    const xxx = await xxxService.getXxxById(doc.xxx);
    if (!xxx) throw new Error();
    await doc.remove();
    return xxxTokenService.generateAuthXxxTokens(xxx);
  } catch (error) {
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Please authenticate');
  }
};

module.exports = { loginWithEmailAndPassword, logout, refreshAuth };
""",
        "function": "service_auth_login_logout_refresh",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/services/auth.service.js",
    },

    # ── 12. Auth service — resetPassword + verifyEmail ───────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');

const { XxxToken } = require('../models');
const ApiError = require('../utils/ApiError');
const { xxxTokenTypes } = require('../config/xxxTokens');
const xxxTokenService = require('./xxxToken.service');
const xxxService = require('./xxx.service');

const resetPassword = async (resetPasswordXxxToken, newPassword) => {
  try {
    const doc = await xxxTokenService.verifyXxxToken(
      resetPasswordXxxToken,
      xxxTokenTypes.RESET_PASSWORD
    );
    const xxx = await xxxService.getXxxById(doc.xxx);
    if (!xxx) throw new Error();
    await xxxService.updateXxxById(xxx.id, { password: newPassword });
    await XxxToken.deleteMany({
      xxx: xxx.id,
      type: xxxTokenTypes.RESET_PASSWORD,
    });
  } catch (error) {
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Password reset failed');
  }
};

const verifyEmail = async (verifyEmailXxxToken) => {
  try {
    const doc = await xxxTokenService.verifyXxxToken(
      verifyEmailXxxToken,
      xxxTokenTypes.VERIFY_EMAIL
    );
    const xxx = await xxxService.getXxxById(doc.xxx);
    if (!xxx) throw new Error();
    await XxxToken.deleteMany({
      xxx: xxx.id,
      type: xxxTokenTypes.VERIFY_EMAIL,
    });
    await xxxService.updateXxxById(xxx.id, { isEmailVerified: true });
  } catch (error) {
    throw new ApiError(
      httpStatus.UNAUTHORIZED,
      'Email verification failed'
    );
  }
};

module.exports = { resetPassword, verifyEmail };
""",
        "function": "service_auth_reset_verify",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/services/auth.service.js",
    },

    # ── 13. Token service — generate, save, verify ──────────────────────────
    {
        "normalized_code": """\
const jwt = require('jsonwebtoken');
const moment = require('moment');

const config = require('../config/config');
const { XxxToken } = require('../models');
const { xxxTokenTypes } = require('../config/xxxTokens');

const generateXxxToken = (xxxId, expires, type, secret = config.jwt.secret) => {
  const payload = {
    sub: xxxId,
    iat: moment().unix(),
    exp: expires.unix(),
    type,
  };
  return jwt.sign(payload, secret);
};

const saveXxxToken = async (
  xxxToken,
  xxxId,
  expires,
  type,
  blacklisted = false
) => {
  return XxxToken.create({
    xxxToken,
    xxx: xxxId,
    expires: expires.toDate(),
    type,
    blacklisted,
  });
};

const verifyXxxToken = async (xxxToken, type) => {
  const payload = jwt.verify(xxxToken, config.jwt.secret);
  const doc = await XxxToken.findOne({
    xxxToken,
    type,
    xxx: payload.sub,
    blacklisted: false,
  });
  if (!doc) throw new Error('XxxToken not found');
  return doc;
};

module.exports = { generateXxxToken, saveXxxToken, verifyXxxToken };
""",
        "function": "service_token_generate_save_verify",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/services/xxxToken.service.js",
    },

    # ── 14. Token service — generateAuthTokens ──────────────────────────────
    {
        "normalized_code": """\
const moment = require('moment');

const config = require('../config/config');
const { xxxTokenTypes } = require('../config/xxxTokens');

const generateAuthXxxTokens = async (xxx) => {
  const accessExpires = moment().add(
    config.jwt.accessExpirationMinutes,
    'minutes'
  );
  const accessXxxToken = generateXxxToken(
    xxx.id,
    accessExpires,
    xxxTokenTypes.ACCESS
  );

  const refreshExpires = moment().add(
    config.jwt.refreshExpirationDays,
    'days'
  );
  const refreshXxxToken = generateXxxToken(
    xxx.id,
    refreshExpires,
    xxxTokenTypes.REFRESH
  );
  await saveXxxToken(
    refreshXxxToken,
    xxx.id,
    refreshExpires,
    xxxTokenTypes.REFRESH
  );

  return {
    access: { xxxToken: accessXxxToken, expires: accessExpires.toDate() },
    refresh: {
      xxxToken: refreshXxxToken,
      expires: refreshExpires.toDate(),
    },
  };
};

module.exports = { generateAuthXxxTokens };
""",
        "function": "service_token_generate_auth_pair",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/services/xxxToken.service.js",
    },

    # ── 15. Token service — generateResetPassword + generateVerifyEmail ──────
    {
        "normalized_code": """\
const httpStatus = require('http-status');
const moment = require('moment');

const config = require('../config/config');
const ApiError = require('../utils/ApiError');
const { xxxTokenTypes } = require('../config/xxxTokens');
const xxxService = require('./xxx.service');

const generateResetPasswordXxxToken = async (email) => {
  const xxx = await xxxService.getXxxByEmail(email);
  if (!xxx)
    throw new ApiError(
      httpStatus.NOT_FOUND,
      'No account found with this email'
    );
  const expires = moment().add(
    config.jwt.resetPasswordExpirationMinutes,
    'minutes'
  );
  const resetXxxToken = generateXxxToken(
    xxx.id,
    expires,
    xxxTokenTypes.RESET_PASSWORD
  );
  await saveXxxToken(
    resetXxxToken,
    xxx.id,
    expires,
    xxxTokenTypes.RESET_PASSWORD
  );
  return resetXxxToken;
};

const generateVerifyEmailXxxToken = async (xxx) => {
  const expires = moment().add(
    config.jwt.verifyEmailExpirationMinutes,
    'minutes'
  );
  const verifyXxxToken = generateXxxToken(
    xxx.id,
    expires,
    xxxTokenTypes.VERIFY_EMAIL
  );
  await saveXxxToken(
    verifyXxxToken,
    xxx.id,
    expires,
    xxxTokenTypes.VERIFY_EMAIL
  );
  return verifyXxxToken;
};

module.exports = {
  generateResetPasswordXxxToken,
  generateVerifyEmailXxxToken,
};
""",
        "function": "service_token_reset_verify_generation",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/services/xxxToken.service.js",
    },

    # ── 16. Email service — nodemailer ───────────────────────────────────────
    {
        "normalized_code": """\
const nodemailer = require('nodemailer');

const config = require('../config/config');

const transport = nodemailer.createTransport(config.email.smtp);

const sendEmail = async (to, subject, text) => {
  const msg = { from: config.email.from, to, subject, text };
  await transport.sendMail(msg);
};

const sendResetPasswordEmail = async (to, xxxToken) => {
  const subject = 'Reset password';
  const resetPasswordUrl = `${config.frontendUrl}/reset-password?token=${xxxToken}`;
  const text = `To reset your password, click: ${resetPasswordUrl}`;
  await sendEmail(to, subject, text);
};

const sendVerificationEmail = async (to, xxxToken) => {
  const subject = 'Email Verification';
  const verificationUrl = `${config.frontendUrl}/verify-email?token=${xxxToken}`;
  const text = `To verify your email, click: ${verificationUrl}`;
  await sendEmail(to, subject, text);
};

module.exports = {
  transport,
  sendEmail,
  sendResetPasswordEmail,
  sendVerificationEmail,
};
""",
        "function": "service_email_nodemailer",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/services/email.service.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 17. Auth middleware — Passport JWT + RBAC ────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');
const passport = require('passport');

const ApiError = require('../utils/ApiError');
const { roleRights } = require('../config/roles');

const verifyCallback =
  (req, resolve, reject, requiredRights) => async (err, xxx, info) => {
    if (err || info || !xxx)
      return reject(
        new ApiError(httpStatus.UNAUTHORIZED, 'Please authenticate')
      );
    req.user = xxx;
    if (requiredRights.length) {
      const xxxRights = roleRights.get(xxx.role);
      const hasRequired = requiredRights.every((r) =>
        xxxRights.includes(r)
      );
      if (!hasRequired && req.params.xxxId !== xxx.id)
        return reject(
          new ApiError(httpStatus.FORBIDDEN, 'Forbidden')
        );
    }
    resolve();
  };

const auth =
  (...requiredRights) =>
  async (req, res, next) => {
    return new Promise((resolve, reject) => {
      passport.authenticate(
        'jwt',
        { session: false },
        verifyCallback(req, resolve, reject, requiredRights)
      )(req, res, next);
    })
      .then(() => next())
      .catch((err) => next(err));
  };

module.exports = auth;
""",
        "function": "middleware_auth_passport_jwt_rbac",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/middlewares/auth.js",
    },

    # ── 18. Validate middleware — Joi ────────────────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');
const Joi = require('joi');

const ApiError = require('../utils/ApiError');
const pick = require('../utils/pick');

const validate = (schema) => (req, res, next) => {
  const validSchema = pick(schema, ['params', 'query', 'body']);
  const object = pick(req, Object.keys(validSchema));
  const { value, error } = Joi.compile(validSchema)
    .prefs({ errors: { label: 'key' }, abortEarly: false })
    .validate(object);
  if (error) {
    const errorDetails = error.details
      .map((d) => d.message)
      .join(', ');
    return next(new ApiError(httpStatus.BAD_REQUEST, errorDetails));
  }
  Object.assign(req, value);
  return next();
};

module.exports = validate;
""",
        "function": "middleware_validate_joi",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/middlewares/validate.js",
    },

    # ── 19. Error middleware — converter + handler ────────────────────────────
    {
        "normalized_code": """\
const httpStatus = require('http-status');
const mongoose = require('mongoose');

const config = require('../config/config');
const ApiError = require('../utils/ApiError');

const errorConverter = (err, req, res, next) => {
  let error = err;
  if (!(error instanceof ApiError)) {
    const statusCode =
      error.statusCode || error instanceof mongoose.Error
        ? httpStatus.BAD_REQUEST
        : httpStatus.INTERNAL_SERVER_ERROR;
    error = new ApiError(statusCode, error.message, false, err.stack);
  }
  next(error);
};

const errorHandler = (err, req, res, next) => {
  let { statusCode } = err;
  let { message } = err;
  if (config.env === 'production' && !err.isOperational) {
    statusCode = httpStatus.INTERNAL_SERVER_ERROR;
    message = httpStatus[httpStatus.INTERNAL_SERVER_ERROR];
  }
  res.locals.errorMessage = err.message;
  const response = {
    code: statusCode,
    message,
    ...(config.env === 'development' && { stack: err.stack }),
  };
  res.status(statusCode).send(response);
};

module.exports = { errorConverter, errorHandler };
""",
        "function": "middleware_error_converter_handler",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/middlewares/error.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 20. catchAsync — async middleware wrapper ────────────────────────────
    {
        "normalized_code": """\
const catchAsync = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch((err) => next(err));
};

module.exports = catchAsync;
""",
        "function": "util_catch_async_wrapper",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/utils/catchAsync.js",
    },

    # ── 21. ApiError — custom error class ────────────────────────────────────
    {
        "normalized_code": """\
class ApiError extends Error {
  constructor(statusCode, message, isOperational = true, stack = '') {
    super(message);
    this.statusCode = statusCode;
    this.isOperational = isOperational;
    if (stack) this.stack = stack;
    else Error.captureStackTrace(this, this.constructor);
  }
}

module.exports = ApiError;
""",
        "function": "util_api_error_class",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/utils/ApiError.js",
    },

    # ── 22. pick utility ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
const pick = (object, keys) =>
  keys.reduce((obj, key) => {
    if (object && Object.prototype.hasOwnProperty.call(object, key)) {
      obj[key] = object[key];
    }
    return obj;
  }, {});

module.exports = pick;
""",
        "function": "util_pick_object_keys",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/utils/pick.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDATIONS (Joi)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 23. Entity CRUD validation — Joi schemas ─────────────────────────────
    {
        "normalized_code": """\
const Joi = require('joi');

const { password, objectId } = require('./custom.validation');

const createXxx = {
  body: Joi.object().keys({
    email: Joi.string().required().email(),
    password: Joi.string().required().custom(password),
    name: Joi.string().required(),
    role: Joi.string().required().valid('xxx', 'admin'),
  }),
};

const getXxxs = {
  query: Joi.object().keys({
    name: Joi.string(),
    role: Joi.string(),
    sortBy: Joi.string(),
    limit: Joi.number().integer(),
    page: Joi.number().integer(),
  }),
};

const getXxx = {
  params: Joi.object().keys({
    xxxId: Joi.string().custom(objectId),
  }),
};

const updateXxx = {
  params: Joi.object().keys({
    xxxId: Joi.required().custom(objectId),
  }),
  body: Joi.object()
    .keys({
      email: Joi.string().email(),
      password: Joi.string().custom(password),
      name: Joi.string(),
    })
    .min(1),
};

const deleteXxx = {
  params: Joi.object().keys({
    xxxId: Joi.string().custom(objectId),
  }),
};

module.exports = { createXxx, getXxxs, getXxx, updateXxx, deleteXxx };
""",
        "function": "validation_crud_joi_schemas",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/validations/xxx.validation.js",
    },

    # ── 24. Auth validation — Joi schemas ────────────────────────────────────
    {
        "normalized_code": """\
const Joi = require('joi');

const { password } = require('./custom.validation');

const register = {
  body: Joi.object().keys({
    email: Joi.string().required().email(),
    password: Joi.string().required().custom(password),
    name: Joi.string().required(),
  }),
};

const login = {
  body: Joi.object().keys({
    email: Joi.string().required(),
    password: Joi.string().required(),
  }),
};

const logout = {
  body: Joi.object().keys({
    refreshXxxToken: Joi.string().required(),
  }),
};

const refreshXxxTokens = {
  body: Joi.object().keys({
    refreshXxxToken: Joi.string().required(),
  }),
};

const forgotPassword = {
  body: Joi.object().keys({
    email: Joi.string().email().required(),
  }),
};

const resetPassword = {
  query: Joi.object().keys({
    xxxToken: Joi.string().required(),
  }),
  body: Joi.object().keys({
    password: Joi.string().required().custom(password),
  }),
};

const verifyEmail = {
  query: Joi.object().keys({
    xxxToken: Joi.string().required(),
  }),
};

module.exports = {
  register,
  login,
  logout,
  refreshXxxTokens,
  forgotPassword,
  resetPassword,
  verifyEmail,
};
""",
        "function": "validation_auth_joi_schemas",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/validations/auth.validation.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 25. Roles config — RBAC ──────────────────────────────────────────────
    {
        "normalized_code": """\
const allRoles = {
  xxx: [],
  admin: ['getXxxs', 'manageXxxs'],
};

const roles = Object.keys(allRoles);
const roleRights = new Map(Object.entries(allRoles));

module.exports = { roles, roleRights };
""",
        "function": "config_roles_rbac",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/config/roles.js",
    },

    # ── 26. Passport JWT strategy config ─────────────────────────────────────
    {
        "normalized_code": """\
const { ExtractJwt, Strategy: JwtStrategy } = require('passport-jwt');

const config = require('./config');
const { xxxTokenTypes } = require('./xxxTokens');
const { Xxx } = require('../models');

const jwtOptions = {
  secretOrKey: config.jwt.secret,
  jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
};

const jwtVerify = async (payload, done) => {
  try {
    if (payload.type !== xxxTokenTypes.ACCESS) {
      throw new Error('Invalid xxxToken type');
    }
    const xxx = await Xxx.findById(payload.sub);
    if (!xxx) return done(null, false);
    done(null, xxx);
  } catch (error) {
    done(error, false);
  }
};

const jwtStrategy = new JwtStrategy(jwtOptions, jwtVerify);

module.exports = { jwtStrategy };
""",
        "function": "config_passport_jwt_strategy",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/config/passport.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 27. Entity CRUD routes — auth + validate chain ───────────────────────
    {
        "normalized_code": """\
const express = require('express');

const auth = require('../../middlewares/auth');
const validate = require('../../middlewares/validate');
const xxxValidation = require('../../validations/xxx.validation');
const xxxController = require('../../controllers/xxx.controller');

const router = express.Router();

router
  .route('/')
  .post(
    auth('manageXxxs'),
    validate(xxxValidation.createXxx),
    xxxController.createXxx
  )
  .get(
    auth('getXxxs'),
    validate(xxxValidation.getXxxs),
    xxxController.getXxxs
  );

router
  .route('/:xxxId')
  .get(
    auth('getXxxs'),
    validate(xxxValidation.getXxx),
    xxxController.getXxx
  )
  .patch(
    auth('manageXxxs'),
    validate(xxxValidation.updateXxx),
    xxxController.updateXxx
  )
  .delete(
    auth('manageXxxs'),
    validate(xxxValidation.deleteXxx),
    xxxController.deleteXxx
  );

module.exports = router;
""",
        "function": "routes_crud_auth_validate_chain",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/v1/xxx.route.js",
    },

    # ── 28. Auth routes ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
const express = require('express');

const auth = require('../../middlewares/auth');
const validate = require('../../middlewares/validate');
const authValidation = require('../../validations/auth.validation');
const authController = require('../../controllers/auth.controller');

const router = express.Router();

router.post(
  '/register',
  validate(authValidation.register),
  authController.register
);
router.post(
  '/login',
  validate(authValidation.login),
  authController.login
);
router.post(
  '/logout',
  validate(authValidation.logout),
  authController.logout
);
router.post(
  '/refresh-xxxTokens',
  validate(authValidation.refreshXxxTokens),
  authController.refreshXxxTokens
);
router.post(
  '/forgot-password',
  validate(authValidation.forgotPassword),
  authController.forgotPassword
);
router.post(
  '/reset-password',
  validate(authValidation.resetPassword),
  authController.resetPassword
);
router.post(
  '/send-verification-email',
  auth(),
  authController.sendVerificationEmail
);
router.post(
  '/verify-email',
  validate(authValidation.verifyEmail),
  authController.verifyEmail
);

module.exports = router;
""",
        "function": "routes_auth_full",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/routes/v1/auth.route.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Mongoose schema with bcrypt password hash pre-save hook",
    "JWT token generation with access and refresh tokens",
    "Express RBAC middleware role-based access control",
    "Joi request validation middleware Express",
    "Mongoose paginate plugin with sort and filter",
    "Auth service login with email password verification",
    "Nodemailer email service send reset password",
    "Express error handling middleware converter handler",
    "catchAsync utility wrapper async middleware",
    "Express CRUD route with auth and validate middleware chain",
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
        hits = query_kb(
            client=client,
            collection=COLLECTION,
            query_vector=vec,
            language=LANGUAGE,
            limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q,
                "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
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
    print(f"  Language: {LANGUAGE} | Stack: {STACK}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)

    print("── Step 1: Prerequisites")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERROR: collection '{COLLECTION}' not found.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}': {count_initial} points (initial)")

    print("\n── Step 2: Clone")
    clone_repo()

    print(f"\n── Step 3-4: {len(PATTERNS)} patterns extracted and normalized")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads built.")

    print("\n── Step 5: Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []
    verdict = "FAIL"

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count after indexation: {count_after}")

        print("\n── Step 6: Audit")
        print("\n  6a. Semantic queries (filtered by language=javascript):")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        print("\n  6b. Normalization audit:")
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
