"""
ingest_hackathon_starter.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns architecturaux de sahat/hackathon-starter dans la KB Qdrant V6.

SCOPE: Uniquement patterns architecturaux réutilisables.
       PAS d'intégrations API one-off (Stripe, Twilio, etc.).

Usage:
    .venv/bin/python3 ingest_hackathon_starter.py
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
REPO_URL = "https://github.com/sahat/hackathon-starter.git"
REPO_NAME = "sahat/hackathon-starter"
REPO_LOCAL = "/tmp/hackathon_starter"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose+passport_multi+nodemailer+webauthn"
CHARTE_VERSION = "1.0"
TAG = "sahat/hackathon-starter"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/sahat/hackathon-starter"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: User→Xxx, user→xxx, userSchema→xxxSchema
# J-1: no var. J-3: console.log removed.
# Kept: email, password, profile, tokens (generic fields), provider names,
#       twoFactor, totp, webauthn, gravatar (technical terms)

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS (Mongoose)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Complex auth schema — all fields ──────────────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');
const bcrypt = require('@node-rs/bcrypt');
const mongoose = require('mongoose');

const xxxSchema = new mongoose.Schema(
  {
    email: { type: String, unique: true, required: true },
    password: String,

    passwordResetToken: String,
    passwordResetExpires: Date,
    passwordResetIpHash: String,

    emailVerificationToken: String,
    emailVerificationExpires: Date,
    emailVerificationIpHash: String,
    emailVerified: { type: Boolean, default: false },

    loginToken: String,
    loginExpires: Date,
    loginIpHash: String,

    twoFactorEnabled: { type: Boolean, default: false },
    twoFactorMethods: {
      type: [String],
      enum: ['email', 'totp'],
      default: [],
    },
    twoFactorCode: String,
    twoFactorExpires: Date,
    twoFactorIpHash: String,
    totpSecret: String,

    webauthnUserID: { type: Buffer, minlength: 16, maxlength: 64 },
    webauthnCredentials: [
      {
        credentialId: { type: Buffer, required: true },
        publicKey: { type: Buffer, required: true },
        counter: { type: Number, required: true, default: 0 },
        transports: { type: [String], default: [] },
        deviceType: String,
        backedUp: Boolean,
        deviceName: String,
        createdAt: { type: Date, default: Date.now },
        lastUsedAt: { type: Date, default: Date.now },
      },
    ],

    discord: String,
    facebook: String,
    github: String,
    google: String,
    linkedin: String,
    microsoft: String,

    tokens: Array,

    profile: {
      name: String,
      gender: String,
      location: String,
      website: String,
      picture: String,
      pictureSource: String,
      pictures: { type: Map, of: String },
    },
  },
  { timestamps: true }
);

xxxSchema.index(
  { 'webauthnCredentials.credentialId': 1 },
  { unique: true, sparse: true }
);
xxxSchema.index({ passwordResetToken: 1 });
xxxSchema.index({ emailVerificationToken: 1 });
xxxSchema.index({ loginToken: 1 });

const Xxx = mongoose.model('Xxx', xxxSchema);
module.exports = Xxx;
""",
        "function": "mongoose_schema_complex_auth_webauthn_2fa",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 2. Virtuals — token expiration checks ────────────────────────────────
    {
        "normalized_code": """\
xxxSchema.virtual('isPasswordResetExpired').get(function () {
  return Date.now() > this.passwordResetExpires;
});

xxxSchema.virtual('isEmailVerificationExpired').get(function () {
  return Date.now() > this.emailVerificationExpires;
});

xxxSchema.virtual('isLoginExpired').get(function () {
  return Date.now() > this.loginExpires;
});

xxxSchema.virtual('isTwoFactorExpired').get(function () {
  return Date.now() > this.twoFactorExpires;
});
""",
        "function": "mongoose_virtuals_token_expiration_checks",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 3. Pre-save — clear expired tokens ───────────────────────────────────
    {
        "normalized_code": """\
xxxSchema.pre('save', function clearExpiredTokens() {
  const now = Date.now();
  if (this.passwordResetExpires && this.passwordResetExpires < now) {
    this.passwordResetToken = undefined;
    this.passwordResetExpires = undefined;
    this.passwordResetIpHash = undefined;
  }
  if (this.emailVerificationExpires && this.emailVerificationExpires < now) {
    this.emailVerificationToken = undefined;
    this.emailVerificationExpires = undefined;
    this.emailVerificationIpHash = undefined;
  }
  if (this.loginExpires && this.loginExpires < now) {
    this.loginToken = undefined;
    this.loginExpires = undefined;
    this.loginIpHash = undefined;
  }
  if (this.twoFactorExpires && this.twoFactorExpires < now) {
    this.clearTwoFactorCode();
  }
});
""",
        "function": "mongoose_presave_clear_expired_tokens",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 4. Pre-save — bcrypt password hash ───────────────────────────────────
    {
        "normalized_code": """\
const bcrypt = require('@node-rs/bcrypt');

xxxSchema.pre('save', async function hashPassword() {
  if (!this.isModified('password')) return;
  this.password = await bcrypt.hash(this.password, 10);
});
""",
        "function": "mongoose_presave_bcrypt_password",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 5. Pre-save — update derived field on email change ───────────────────
    {
        "normalized_code": """\
xxxSchema.pre('save', function updateGravatarOnEmailChange() {
  if (!this.isModified('email')) return;
  if (!this.profile.pictures) this.profile.pictures = new Map();
  if (!this.profile.pictureSource) this.profile.pictureSource = 'gravatar';
  const url = this.gravatar();
  this.profile.pictures.set('gravatar', url);
  if (this.profile.pictureSource === 'gravatar') {
    this.profile.picture = url;
  }
});
""",
        "function": "mongoose_presave_derived_field_update",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 6. Method — comparePassword (bcrypt verify) ──────────────────────────
    {
        "normalized_code": """\
const bcrypt = require('@node-rs/bcrypt');

xxxSchema.methods.comparePassword = async function comparePassword(
  candidatePassword,
  cb
) {
  try {
    cb(null, await bcrypt.verify(candidatePassword, this.password));
  } catch (err) {
    cb(err);
  }
};
""",
        "function": "mongoose_method_compare_password_bcrypt",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 7. Method — verifyTokenAndIp (timing-safe comparison) ────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');

xxxSchema.methods.verifyTokenAndIp = function verifyTokenAndIp(
  token,
  ip,
  tokenType
) {
  const hashedIp = this.constructor.hashIP(ip);
  const tokenField = `${tokenType}Token`;
  const ipHashField = `${tokenType}IpHash`;
  const expiresField = `${tokenType}Expires`;
  try {
    if (
      !this[tokenField] ||
      !token ||
      !this[ipHashField] ||
      !hashedIp
    )
      return false;
    const storedToken = Buffer.from(this[tokenField]);
    const inputToken = Buffer.from(token);
    if (storedToken.length !== inputToken.length) return false;
    return (
      crypto.timingSafeEqual(storedToken, inputToken) &&
      this[ipHashField] === hashedIp &&
      this[expiresField] > Date.now()
    );
  } catch (err) {
    return false;
  }
};
""",
        "function": "mongoose_method_verify_token_ip_timing_safe",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 8. Method — verifyCodeAndIp (6-digit codes) ──────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');

xxxSchema.methods.verifyCodeAndIp = function verifyCodeAndIp(
  code,
  ip,
  codeType
) {
  const hashedIp = this.constructor.hashIP(ip);
  const codeField = `${codeType}Code`;
  const ipHashField = `${codeType}IpHash`;
  const expiresField = `${codeType}Expires`;
  try {
    if (
      !this[codeField] ||
      !code ||
      !this[ipHashField] ||
      !hashedIp
    )
      return false;
    const storedCode = Buffer.from(this[codeField]);
    const inputCode = Buffer.from(code);
    if (storedCode.length !== inputCode.length) return false;
    return (
      crypto.timingSafeEqual(storedCode, inputCode) &&
      this[ipHashField] === hashedIp &&
      this[expiresField] > Date.now()
    );
  } catch {
    return false;
  }
};
""",
        "function": "mongoose_method_verify_code_ip_timing_safe",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 9. Statics — hashIP + generateToken + generateCode ──────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');

xxxSchema.statics.hashIP = function hashIP(ip) {
  return crypto.createHash('sha256').update(ip).digest('hex');
};

xxxSchema.statics.generateToken = function generateToken() {
  return crypto.randomBytes(32).toString('hex');
};

xxxSchema.statics.generateCode = function generateCode() {
  return crypto.randomInt(100000, 1000000).toString();
};
""",
        "function": "mongoose_statics_haship_generate_token_code",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ── 10. Method — gravatar URL generation ─────────────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');

xxxSchema.methods.gravatar = function gravatarUrl(size) {
  if (!size) size = 200;
  if (!this.email)
    return `https://gravatar.com/avatar/0?s=${size}&d=retro`;
  const sha256 = crypto
    .createHash('sha256')
    .update(this.email)
    .digest('hex');
  return `https://gravatar.com/avatar/${sha256}?s=${size}&d=retro`;
};
""",
        "function": "mongoose_method_gravatar_url",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/Xxx.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH / PASSPORT CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. Passport serialize/deserialize ───────────────────────────────────
    {
        "normalized_code": """\
const passport = require('passport');

const Xxx = require('../models/Xxx');

passport.serializeUser((xxx, done) => {
  done(null, xxx.id);
});

passport.deserializeUser(async (id, done) => {
  try {
    return done(null, await Xxx.findById(id));
  } catch (error) {
    return done(error);
  }
});
""",
        "function": "passport_serialize_deserialize_async",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport.js",
    },

    # ── 12. Passport local strategy — email/password ─────────────────────────
    {
        "normalized_code": """\
const passport = require('passport');
const { Strategy: LocalStrategy } = require('passport-local');

const Xxx = require('../models/Xxx');

passport.use(
  new LocalStrategy(
    { usernameField: 'email' },
    (email, password, done) => {
      Xxx.findOne({ email: { $eq: email.toLowerCase() } })
        .then((xxx) => {
          if (!xxx) {
            return done(null, false, {
              msg: `Email ${email} not found.`,
            });
          }
          if (!xxx.password) {
            return done(null, false, {
              msg: 'Account was created with a sign-in provider.',
            });
          }
          xxx.comparePassword(password, (err, isMatch) => {
            if (err) return done(err);
            if (isMatch) return done(null, xxx);
            return done(null, false, {
              msg: 'Invalid email or password.',
            });
          });
        })
        .catch((err) => done(err));
    }
  )
);
""",
        "function": "passport_local_strategy_email_password",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport.js",
    },

    # ── 13. Shared OAuth handler — handleAuthLogin() ─────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');

async function handleAuthLogin(
  req,
  accessToken,
  refreshToken,
  providerName,
  params,
  providerProfile,
  sessionAlreadyLoggedIn,
  tokenSecret,
  oauth2provider,
  tokenConfig = {},
  refreshTokenExpiration = null
) {
  if (sessionAlreadyLoggedIn) {
    const existingXxx = await Xxx.findOne({
      [providerName]: { $eq: providerProfile.id },
    });
    if (existingXxx && existingXxx.id !== req.user.id) {
      throw new Error('PROVIDER_COLLISION');
    }
    const xxx = await Xxx.findById(req.user.id);
    xxx[providerName] = providerProfile.id;
    xxx.tokens.push({
      kind: providerName,
      accessToken,
      ...(tokenSecret && { tokenSecret }),
    });
    xxx.profile.name = xxx.profile.name || providerProfile.name;
    if (providerProfile.picture) {
      if (!xxx.profile.pictures) xxx.profile.pictures = new Map();
      xxx.profile.pictures.set(providerName, providerProfile.picture);
      if (xxx.profile.pictureSource === 'gravatar') {
        xxx.profile.picture = providerProfile.picture;
        xxx.profile.pictureSource = providerName;
      }
    }
    xxx.profile.location =
      xxx.profile.location || providerProfile.location;
    await xxx.save();
    return xxx;
  }
  const existingXxx = await Xxx.findOne({
    [providerName]: { $eq: providerProfile.id },
  });
  if (existingXxx) return existingXxx;
  const normalizedEmail = providerProfile.email
    ? validator.normalizeEmail(providerProfile.email, {
        gmail_remove_dots: false,
      })
    : undefined;
  if (!normalizedEmail) throw new Error('EMAIL_REQUIRED');
  const existingEmailXxx = await Xxx.findOne({
    email: { $eq: normalizedEmail },
  });
  if (existingEmailXxx) throw new Error('EMAIL_COLLISION');
  const xxx = new Xxx();
  xxx.email = normalizedEmail;
  xxx[providerName] = providerProfile.id;
  xxx.tokens.push({
    kind: providerName,
    accessToken,
    ...(tokenSecret && { tokenSecret }),
  });
  xxx.profile.name = providerProfile.name;
  if (providerProfile.picture) {
    xxx.profile.pictures = new Map();
    xxx.profile.pictures.set(providerName, providerProfile.picture);
    xxx.profile.picture = providerProfile.picture;
    xxx.profile.pictureSource = providerName;
  }
  xxx.profile.location = providerProfile.location;
  await xxx.save();
  return xxx;
}
""",
        "function": "passport_shared_oauth_handler",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport.js",
    },

    # ── 14. isAuthenticated + isAuthorized middleware ─────────────────────────
    {
        "normalized_code": """\
const refresh = require('passport-oauth2-refresh');

exports.isAuthenticated = (req, res, next) => {
  if (req.isAuthenticated()) return next();
  req.flash('errors', {
    msg: 'You need to be logged in to access that page.',
  });
  res.redirect('/login');
};

exports.isAuthorized = async (req, res, next) => {
  const provider = req.path.split('/')[2];
  const token = req.user.tokens.find((t) => t.kind === provider);
  if (!token) return res.redirect(`/auth/${provider}`);
  if (
    token.accessTokenExpires &&
    new Date(token.accessTokenExpires).getTime() <
      Date.now() - 60 * 1000
  ) {
    if (!token.refreshToken)
      return res.redirect(`/auth/${provider}`);
    if (
      token.refreshTokenExpires &&
      new Date(token.refreshTokenExpires).getTime() <
        Date.now() - 60 * 1000
    )
      return res.redirect(`/auth/${provider}`);
    try {
      const newTokens = await new Promise((resolve, reject) => {
        refresh.requestNewAccessToken(
          provider,
          token.refreshToken,
          (err, accessToken, refreshToken, params) => {
            if (err) reject(err);
            resolve({ accessToken, refreshToken, params });
          }
        );
      });
      req.user.tokens.forEach((t) => {
        if (t.kind === provider) {
          t.accessToken = newTokens.accessToken;
          if (newTokens.params.expires_in)
            t.accessTokenExpires = new Date(
              Date.now() + newTokens.params.expires_in * 1000
            ).toISOString();
        }
      });
      await req.user.save();
      return next();
    } catch (err) {
      return res.redirect(`/auth/${provider}`);
    }
  }
  return next();
};
""",
        "function": "middleware_is_authenticated_is_authorized",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "config/passport.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS — AUTH FLOWS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. Login — password + passwordless dual-mode ────────────────────────
    {
        "normalized_code": """\
const passport = require('passport');
const validator = require('validator');

const Xxx = require('../models/Xxx');
const nodemailerConfig = require('../config/nodemailer');

exports.postLogin = async (req, res, next) => {
  const validationErrors = [];
  if (!validator.isEmail(req.body.email))
    validationErrors.push({ msg: 'Please enter a valid email.' });
  if (validationErrors.length) {
    req.flash('errors', validationErrors);
    return res.redirect('/login');
  }
  req.body.email = validator.normalizeEmail(req.body.email, {
    gmail_remove_dots: false,
  });

  if (req.body.loginByEmailLink === 'on') {
    const xxx = await Xxx.findOne({
      email: { $eq: req.body.email },
    });
    if (!xxx) {
      req.flash('info', { msg: 'Check your email for a login link.' });
      return res.redirect('/login');
    }
    const token = await Xxx.generateToken();
    xxx.loginToken = token;
    xxx.loginExpires = Date.now() + 900000;
    xxx.loginIpHash = Xxx.hashIP(req.ip);
    await xxx.save();
    await nodemailerConfig.sendMail({
      mailOptions: {
        to: xxx.email,
        from: process.env.SITE_CONTACT_EMAIL,
        subject: 'Login Link',
        text: `Click to log in: ${process.env.BASE_URL}/login/verify/${token}`,
      },
      successfulType: 'info',
      successfulMsg: 'Check your email for a login link.',
      loggingError: 'ERROR: Could not send login link.',
      errorType: 'errors',
      errorMsg: 'Error sending login email. Try again later.',
      req,
    });
    return res.redirect('/login');
  }

  if (validator.isEmpty(req.body.password)) {
    req.flash('errors', 'Password cannot be blank.');
    return res.redirect('/login');
  }
  passport.authenticate('local', (err, xxx, info) => {
    if (err) return next(err);
    if (!xxx) {
      req.flash('errors', info);
      return res.redirect('/login');
    }
    if (xxx.twoFactorEnabled && xxx.password) {
      req.session.twoFactorPendingXxxId = xxx.id;
      if (xxx.twoFactorMethods.includes('totp'))
        return res.redirect('/login/2fa/totp');
      return res.redirect('/login/2fa');
    }
    req.logIn(xxx, (err) => {
      if (err) return next(err);
      req.flash('success', { msg: 'Success! You are logged in.' });
      res.redirect(req.session.returnTo || '/');
    });
  })(req, res, next);
};
""",
        "function": "controller_login_password_passwordless_dual",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 16. Signup — with anti-enumeration ───────────────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');
const validator = require('validator');
const mailChecker = require('mailchecker');

const Xxx = require('../models/Xxx');

exports.postSignup = async (req, res, next) => {
  const validationErrors = [];
  if (!validator.isEmail(req.body.email))
    validationErrors.push({ msg: 'Please enter a valid email.' });
  if (!req.body.passwordless) {
    if (!validator.isLength(req.body.password, { min: 8 }))
      validationErrors.push({ msg: 'Password must be 8+ chars.' });
    if (req.body.password !== req.body.confirmPassword)
      validationErrors.push({ msg: 'Passwords do not match.' });
  }
  if (validationErrors.length) {
    req.flash('errors', validationErrors);
    return res.redirect('/signup');
  }
  req.body.email = validator.normalizeEmail(req.body.email, {
    gmail_remove_dots: false,
  });
  if (!mailChecker.isValid(req.body.email)) {
    req.flash('errors', { msg: 'Disposable email not allowed.' });
    return res.redirect('/signup');
  }
  try {
    const existingXxx = await Xxx.findOne({
      email: { $eq: req.body.email },
    });
    if (existingXxx) {
      await sendPasswordlessLoginLinkIfExists(existingXxx, req);
      return res.redirect('/login');
    }
    const password = req.body.passwordless
      ? crypto.randomBytes(16).toString('hex')
      : req.body.password;
    const xxx = new Xxx({ email: req.body.email, password });
    await xxx.save();
    if (req.body.passwordless) {
      await sendPasswordlessSignupLink(xxx, req);
      return res.redirect('/');
    }
    req.logIn(xxx, (err) => {
      if (err) return next(err);
      res.redirect('/');
    });
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_signup_anti_enumeration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 17. Passwordless login — token-based email auth ──────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');

exports.getLoginByEmail = async (req, res, next) => {
  if (req.user) return res.redirect('/');
  if (!validator.isHexadecimal(req.params.token)) {
    req.flash('errors', { msg: 'Invalid or expired login link.' });
    return res.redirect('/login');
  }
  try {
    const xxx = await Xxx.findOne({
      loginToken: { $eq: req.params.token },
    });
    if (
      !xxx ||
      !xxx.verifyTokenAndIp(xxx.loginToken, req.ip, 'login')
    ) {
      req.flash('errors', { msg: 'Invalid or expired login link.' });
      return res.redirect('/login');
    }
    xxx.emailVerified = true;
    await xxx.save();
    req.logIn(xxx, (err) => {
      if (err) return next(err);
      req.flash('success', { msg: 'Success! You are logged in.' });
      res.redirect(req.session.returnTo || '/');
    });
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_passwordless_login_token_email",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 18. Forgot password — anti-enumeration ───────────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');
const nodemailerConfig = require('../config/nodemailer');

exports.postForgot = async (req, res, next) => {
  if (!validator.isEmail(req.body.email)) {
    req.flash('errors', { msg: 'Please enter a valid email.' });
    return res.redirect('/forgot');
  }
  req.body.email = validator.normalizeEmail(req.body.email, {
    gmail_remove_dots: false,
  });
  try {
    const xxx = await Xxx.findOne({
      email: { $eq: req.body.email.toLowerCase() },
    });
    if (!xxx) {
      req.flash('info', {
        msg: 'If an account exists, you will receive reset instructions.',
      });
      return res.redirect('/forgot');
    }
    const token = await Xxx.generateToken();
    xxx.passwordResetToken = token;
    xxx.passwordResetExpires = Date.now() + 900000;
    xxx.passwordResetIpHash = Xxx.hashIP(req.ip);
    await xxx.save();
    await nodemailerConfig.sendMail({
      mailOptions: {
        to: xxx.email,
        from: process.env.SITE_CONTACT_EMAIL,
        subject: 'Reset your password',
        text: `Click to reset: ${process.env.BASE_URL}/reset/${token}`,
      },
      successfulType: 'info',
      successfulMsg:
        'If an account exists, you will receive reset instructions.',
      loggingError: 'ERROR: Could not send password reset email.',
      errorType: 'errors',
      errorMsg: 'Error sending reset email. Try again later.',
      req,
    });
    res.redirect('/forgot');
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_forgot_password_anti_enumeration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 19. Reset password — token verify + update ───────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');
const nodemailerConfig = require('../config/nodemailer');

exports.postReset = async (req, res, next) => {
  const validationErrors = [];
  if (!validator.isLength(req.body.password, { min: 8 }))
    validationErrors.push({ msg: 'Password must be 8+ chars.' });
  if (req.body.password !== req.body.confirm)
    validationErrors.push({ msg: 'Passwords do not match.' });
  if (!validator.isHexadecimal(req.params.token))
    validationErrors.push({ msg: 'Invalid token.' });
  if (validationErrors.length) {
    req.flash('errors', validationErrors);
    return res.redirect(req.get('Referrer') || '/');
  }
  try {
    const xxx = await Xxx.findOne({
      passwordResetToken: { $eq: req.params.token },
    });
    if (
      !xxx ||
      !xxx.verifyTokenAndIp(
        xxx.passwordResetToken,
        req.ip,
        'passwordReset'
      )
    ) {
      req.flash('errors', { msg: 'Reset link is invalid or expired.' });
      return res.redirect('/forgot');
    }
    xxx.password = req.body.password;
    xxx.emailVerified = true;
    await xxx.save();
    await nodemailerConfig.sendMail({
      mailOptions: {
        to: xxx.email,
        from: process.env.SITE_CONTACT_EMAIL,
        subject: 'Your password has been changed',
        text: `Password for ${xxx.email} has been changed.`,
      },
      successfulType: 'success',
      successfulMsg: 'Your password has been changed.',
      loggingError: 'ERROR: Could not send confirmation email.',
      errorType: 'warning',
      errorMsg: 'Password changed but confirmation email failed.',
      req,
    });
    res.redirect('/');
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_reset_password_token_verify",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 20. Email verification — send + verify ───────────────────────────────
    {
        "normalized_code": """\
const Xxx = require('../models/Xxx');
const nodemailerConfig = require('../config/nodemailer');

exports.getVerifyEmail = async (req, res, next) => {
  if (req.user.emailVerified) {
    req.flash('info', { msg: 'Email already verified.' });
    return res.redirect('/account');
  }
  try {
    const token = await Xxx.generateToken();
    req.user.emailVerificationToken = token;
    req.user.emailVerificationExpires = Date.now() + 900000;
    req.user.emailVerificationIpHash = Xxx.hashIP(req.ip);
    await req.user.save();
    await nodemailerConfig.sendMail({
      mailOptions: {
        to: req.user.email,
        from: process.env.SITE_CONTACT_EMAIL,
        subject: 'Verify your email',
        text: `Click to verify: ${process.env.BASE_URL}/account/verify/${token}`,
      },
      successfulType: 'info',
      successfulMsg: `Verification email sent to ${req.user.email}.`,
      loggingError: 'ERROR: Could not send verification email.',
      errorType: 'errors',
      errorMsg: 'Error sending verification email.',
      req,
    });
    return res.redirect('/account');
  } catch (err) {
    next(err);
  }
};

exports.getVerifyEmailToken = async (req, res, next) => {
  if (req.user.emailVerified) return res.redirect('/account');
  try {
    if (
      !req.user.verifyTokenAndIp(
        req.user.emailVerificationToken,
        req.ip,
        'emailVerification'
      )
    ) {
      req.flash('errors', {
        msg: 'Invalid or expired verification link.',
      });
      return res.redirect('/account');
    }
    req.user.emailVerified = true;
    await req.user.save();
    req.flash('success', { msg: 'Email address verified.' });
    return res.redirect('/account');
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_email_verification_send_verify",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 21. OAuth unlink — with token revocation ─────────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');
const {
  revokeProviderTokens,
} = require('../config/token-revocation');

exports.getOauthUnlink = async (req, res, next) => {
  try {
    let { provider } = req.params;
    provider = validator.escape(provider);
    const xxx = await Xxx.findById(req.user.id);
    xxx[provider.toLowerCase()] = undefined;
    const tokenToRevoke = xxx.tokens.find(
      (t) => t.kind === provider.toLowerCase()
    );
    const remaining = xxx.tokens.filter(
      (t) => t.kind !== provider.toLowerCase()
    );
    if (!(xxx.email && xxx.password) && remaining.length === 0) {
      req.flash('errors', {
        msg: `Cannot unlink ${provider} without another login method.`,
      });
      return res.redirect('/account');
    }
    if (xxx.profile.pictures && xxx.profile.pictures.has(provider.toLowerCase())) {
      xxx.profile.pictures.delete(provider.toLowerCase());
      if (xxx.profile.pictureSource === provider.toLowerCase()) {
        const fallback = xxx.profile.pictures.has('gravatar')
          ? 'gravatar'
          : xxx.profile.pictures.keys().next().value || undefined;
        xxx.profile.pictureSource = fallback;
        xxx.profile.picture = fallback
          ? xxx.profile.pictures.get(fallback)
          : undefined;
      }
    }
    await revokeProviderTokens(provider.toLowerCase(), tokenToRevoke);
    xxx.tokens = remaining;
    await xxx.save();
    req.flash('info', { msg: `${provider} account has been unlinked.` });
    res.redirect('/account');
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_oauth_unlink_token_revocation",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 22. Account — profile + password + delete ────────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const Xxx = require('../models/Xxx');
const {
  revokeAllProviderTokens,
} = require('../config/token-revocation');

exports.postUpdateProfile = async (req, res, next) => {
  if (!validator.isEmail(req.body.email)) {
    req.flash('errors', { msg: 'Please enter a valid email.' });
    return res.redirect('/account');
  }
  try {
    const xxx = await Xxx.findById(req.user.id);
    if (xxx.email !== req.body.email) xxx.emailVerified = false;
    xxx.email = req.body.email || '';
    xxx.profile.name = req.body.name || '';
    xxx.profile.gender = req.body.gender || '';
    xxx.profile.location = req.body.location || '';
    xxx.profile.website = req.body.website || '';
    await xxx.save();
    req.flash('success', { msg: 'Profile updated.' });
    res.redirect('/account');
  } catch (err) {
    if (err.code === 11000) {
      req.flash('errors', { msg: 'Email update failed.' });
      return res.redirect('/account');
    }
    next(err);
  }
};

exports.postUpdatePassword = async (req, res, next) => {
  if (!validator.isLength(req.body.password, { min: 8 })) {
    req.flash('errors', { msg: 'Password must be 8+ chars.' });
    return res.redirect('/account');
  }
  try {
    const xxx = await Xxx.findById(req.user.id);
    xxx.password = req.body.password;
    await xxx.save();
    req.flash('success', { msg: 'Password has been changed.' });
    res.redirect('/account');
  } catch (err) {
    next(err);
  }
};

exports.postDeleteAccount = async (req, res, next) => {
  try {
    await revokeAllProviderTokens(req.user.tokens);
    await Xxx.deleteOne({ _id: req.user.id });
    req.logout((err) => {
      req.session.destroy(() => {
        req.user = null;
        res.redirect('/');
      });
    });
  } catch (err) {
    next(err);
  }
};
""",
        "function": "controller_account_profile_password_delete",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ── 23. Logout + logoutEverywhere ────────────────────────────────────────
    {
        "normalized_code": """\
exports.logout = (req, res) => {
  req.logout(() => {
    req.session.destroy(() => {
      req.user = null;
      res.redirect('/');
    });
  });
};
""",
        "function": "controller_logout_session_destroy",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/xxx.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS — FEATURES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 24. Contact form — reCAPTCHA Enterprise ──────────────────────────────
    {
        "normalized_code": """\
const validator = require('validator');

const nodemailerConfig = require('../config/nodemailer');

async function validateReCAPTCHA(token) {
  const projectId = process.env.GOOGLE_PROJECT_ID;
  const siteKey = process.env.GOOGLE_RECAPTCHA_SITE_KEY;
  const apiKey = process.env.GOOGLE_API_KEY;
  const url = `https://recaptchaenterprise.googleapis.com/v1/projects/${projectId}/assessments?key=${apiKey}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: { token, siteKey } }),
  });
  const data = await resp.json();
  return {
    valid: data.tokenProperties?.valid === true,
    score: data.riskAnalysis?.score ?? null,
  };
}

exports.postContact = async (req, res, next) => {
  const validationErrors = [];
  if (!req.user) {
    if (validator.isEmpty(req.body.name))
      validationErrors.push({ msg: 'Enter your name.' });
    if (!validator.isEmail(req.body.email))
      validationErrors.push({ msg: 'Enter a valid email.' });
  }
  if (validator.isEmpty(req.body.message))
    validationErrors.push({ msg: 'Enter your message.' });
  if (process.env.GOOGLE_RECAPTCHA_SITE_KEY) {
    if (req.body['g-recaptcha-response']) {
      const result = await validateReCAPTCHA(
        req.body['g-recaptcha-response']
      );
      if (!result.valid)
        validationErrors.push({ msg: 'reCAPTCHA failed.' });
    } else {
      validationErrors.push({ msg: 'reCAPTCHA missing.' });
    }
  }
  if (validationErrors.length) {
    req.flash('errors', validationErrors);
    return res.redirect('/contact');
  }
  const fromName = req.user
    ? req.user.profile.name || ''
    : req.body.name;
  const fromEmail = req.user ? req.user.email : req.body.email;
  await nodemailerConfig.sendMail({
    mailOptions: {
      to: process.env.SITE_CONTACT_EMAIL,
      from: `${fromName} <${fromEmail}>`,
      subject: 'Contact Form',
      text: req.body.message,
    },
    successfulType: 'info',
    successfulMsg: 'Email sent successfully!',
    loggingError: 'ERROR: Could not send contact email.',
    errorType: 'errors',
    errorMsg: 'Error sending message. Try again.',
    req,
  });
  res.redirect('/contact');
};
""",
        "function": "controller_contact_recaptcha_nodemailer",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/contact.js",
    },

    # ── 25. WebAuthn — passkey registration ──────────────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');
const {
  generateRegistrationOptions,
  verifyRegistrationResponse,
} = require('@simplewebauthn/server');

const Xxx = require('../models/Xxx');

const rpName = 'Xxx App';
const rpID = new URL(process.env.BASE_URL).hostname;
const expectedOrigin = new URL(process.env.BASE_URL).origin;

exports.postRegisterStart = async (req, res) => {
  try {
    const { user: xxx } = req;
    if (!xxx.emailVerified) {
      req.flash('errors', { msg: 'Verify your email first.' });
      return res.redirect('/account');
    }
    if (!xxx.webauthnUserID) {
      xxx.webauthnUserID = crypto.randomBytes(32);
      await xxx.save();
    }
    const options = await generateRegistrationOptions({
      rpName,
      rpID,
      userID: xxx.webauthnUserID,
      userName: xxx.email,
      excludeCredentials: (xxx.webauthnCredentials || []).map(
        (c) => ({
          id: c.credentialId,
          type: 'public-key',
          transports: c.transports,
        })
      ),
      authenticatorSelection: {
        residentKey: 'discouraged',
        userVerification: 'preferred',
      },
    });
    req.session.registerChallenge = options.challenge;
    res.render('account/webauthn-register', {
      title: 'Enable Biometric Login',
      publicKey: JSON.stringify(options),
    });
  } catch (err) {
    req.flash('errors', { msg: 'Failed to start passkey registration.' });
    res.redirect('/account');
  }
};

exports.postRegisterVerify = async (req, res) => {
  try {
    const { credential } = req.body;
    const expectedChallenge = req.session.registerChallenge;
    if (!credential || !expectedChallenge) {
      delete req.session.registerChallenge;
      req.flash('errors', { msg: 'Registration failed.' });
      return res.redirect('/account');
    }
    const parsed = JSON.parse(credential);
    const verification = await verifyRegistrationResponse({
      response: parsed,
      expectedChallenge,
      expectedOrigin,
      expectedRPID: rpID,
      requireUserVerification: false,
    });
    delete req.session.registerChallenge;
    if (!verification?.verified) {
      req.flash('errors', { msg: 'Registration failed.' });
      return res.redirect('/account');
    }
    const c = verification.registrationInfo.credential;
    req.user.webauthnCredentials.push({
      credentialId: Buffer.from(c.id, 'base64url'),
      publicKey: Buffer.from(c.publicKey),
      counter: c.counter || 0,
      transports: c.transports || [],
      deviceType: verification.registrationInfo.credentialDeviceType,
      backedUp: Boolean(
        verification.registrationInfo.credentialBackedUp
      ),
      deviceName: 'Biometric Device',
      createdAt: new Date(),
      lastUsedAt: new Date(),
    });
    await req.user.save();
    req.flash('success', { msg: 'Biometric login enabled.' });
    return res.redirect('/account');
  } catch (err) {
    delete req.session.registerChallenge;
    req.flash('errors', { msg: 'Registration failed.' });
    return res.redirect('/account');
  }
};
""",
        "function": "controller_webauthn_passkey_registration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/webauthn.js",
    },

    # ── 26. WebAuthn — passkey authentication ────────────────────────────────
    {
        "normalized_code": """\
const crypto = require('node:crypto');
const {
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
} = require('@simplewebauthn/server');

const Xxx = require('../models/Xxx');

const rpID = new URL(process.env.BASE_URL).hostname;
const expectedOrigin = new URL(process.env.BASE_URL).origin;

exports.postLoginStart = async (req, res) => {
  try {
    const options = await generateAuthenticationOptions({
      rpID,
      userVerification: 'preferred',
    });
    req.session.loginChallenge = options.challenge;
    res.render('account/webauthn-login', {
      title: 'Biometric Login',
      publicKey: JSON.stringify(options),
    });
  } catch (err) {
    req.flash('errors', { msg: 'Passkey auth failed.' });
    res.redirect('/login');
  }
};

exports.postLoginVerify = async (req, res) => {
  try {
    const { credential } = req.body;
    const expectedChallenge = req.session.loginChallenge;
    if (!credential || !expectedChallenge) {
      delete req.session.loginChallenge;
      req.flash('errors', { msg: 'Passkey auth failed.' });
      return res.redirect('/login');
    }
    const parsed = JSON.parse(credential);
    const credentialId = Buffer.from(parsed.id, 'base64url');
    const xxx = await Xxx.findOne({
      'webauthnCredentials.credentialId': credentialId,
    });
    const cred = xxx
      ? xxx.webauthnCredentials.find((c) =>
          c.credentialId.equals(credentialId)
        )
      : null;
    if (!cred) {
      delete req.session.loginChallenge;
      req.flash('errors', { msg: 'Passkey auth failed.' });
      return res.redirect('/login');
    }
    const verification = await verifyAuthenticationResponse({
      response: parsed,
      expectedChallenge,
      expectedOrigin,
      expectedRPID: rpID,
      requireUserVerification: false,
      credential: {
        id: cred.credentialId,
        publicKey: cred.publicKey,
        counter: cred.counter,
        transports: cred.transports,
      },
    });
    delete req.session.loginChallenge;
    if (!verification.verified) {
      req.flash('errors', { msg: 'Passkey auth failed.' });
      return res.redirect('/login');
    }
    cred.counter = verification.authenticationInfo.newCounter;
    cred.lastUsedAt = new Date();
    await xxx.save();
    req.logIn(xxx, (err) => {
      if (err) {
        req.flash('errors', { msg: 'Login failed.' });
        return res.redirect('/login');
      }
      req.flash('success', { msg: 'Success! You are logged in.' });
      res.redirect(req.session.returnTo || '/');
    });
  } catch (err) {
    delete req.session.loginChallenge;
    req.flash('errors', { msg: 'Passkey auth failed.' });
    res.redirect('/login');
  }
};
""",
        "function": "controller_webauthn_passkey_authentication",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/webauthn.js",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # APP CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 27. Express multi-tier rate limiting ──────────────────────────────────
    {
        "normalized_code": """\
const rateLimit = require('express-rate-limit');

const RATE_LIMIT_GLOBAL =
  parseInt(process.env.RATE_LIMIT_GLOBAL, 10) || 200;
const RATE_LIMIT_STRICT =
  parseInt(process.env.RATE_LIMIT_STRICT, 10) || 5;
const RATE_LIMIT_LOGIN =
  parseInt(process.env.RATE_LIMIT_LOGIN, 10) || 10;

const globalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: RATE_LIMIT_GLOBAL,
  standardHeaders: true,
  legacyHeaders: false,
});

const strictLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: RATE_LIMIT_STRICT,
  standardHeaders: true,
  legacyHeaders: false,
});

const loginLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: RATE_LIMIT_LOGIN,
  standardHeaders: true,
  legacyHeaders: false,
});

const login2FALimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: RATE_LIMIT_LOGIN * 5,
  standardHeaders: true,
  legacyHeaders: false,
});
""",
        "function": "express_multi_tier_rate_limiting",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app.js",
    },

    # ── 28. Express session + CSRF + security ────────────────────────────────
    {
        "normalized_code": """\
const express = require('express');
const lusca = require('lusca');
const passport = require('passport');
const session = require('express-session');

const { MongoStore } = require('connect-mongo');

const secureTransfer = process.env.BASE_URL.startsWith('https');

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(globalLimiter);
app.use(
  session({
    resave: false,
    saveUninitialized: false,
    secret: process.env.SESSION_SECRET,
    name: 'startercookie',
    cookie: {
      maxAge: 1209600000,
      secure: secureTransfer,
    },
    store: MongoStore.create({ mongoUrl: process.env.MONGODB_URI }),
  })
);
app.use(passport.initialize());
app.use(passport.session());
app.use((req, res, next) => {
  if (
    req.path === '/api/upload' ||
    req.path === '/ai/llm-camera'
  ) {
    next();
  } else {
    lusca.csrf()(req, res, next);
  }
});
app.use(lusca.xframe('SAMEORIGIN'));
app.use(lusca.xssProtection(true));
app.disable('x-powered-by');
""",
        "function": "express_session_csrf_lusca_security",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app.js",
    },

    # ── 29. Express route registration — middleware chains ───────────────────
    {
        "normalized_code": """\
const passportConfig = require('./config/passport');

app.get('/login', xxxController.getLogin);
app.post('/login', loginLimiter, xxxController.postLogin);
app.get('/logout', xxxController.logout);
app.get('/signup', xxxController.getSignup);
app.post('/signup', strictLimiter, xxxController.postSignup);
app.get(
  '/login/verify/:token',
  strictLimiter,
  xxxController.getLoginByEmail
);
app.get('/forgot', xxxController.getForgot);
app.post('/forgot', strictLimiter, xxxController.postForgot);
app.get('/reset/:token', xxxController.getReset);
app.post('/reset/:token', strictLimiter, xxxController.postReset);
app.get(
  '/account/verify',
  passportConfig.isAuthenticated,
  strictLimiter,
  xxxController.getVerifyEmail
);
app.get(
  '/account/verify/:token',
  passportConfig.isAuthenticated,
  xxxController.getVerifyEmailToken
);
app.post(
  '/account/profile',
  passportConfig.isAuthenticated,
  xxxController.postUpdateProfile
);
app.post(
  '/account/password',
  passportConfig.isAuthenticated,
  xxxController.postUpdatePassword
);
app.post(
  '/account/delete',
  passportConfig.isAuthenticated,
  xxxController.postDeleteAccount
);
app.get(
  '/account/unlink/:provider',
  passportConfig.isAuthenticated,
  xxxController.getOauthUnlink
);
app.post(
  '/login/webauthn-start',
  loginLimiter,
  webauthnController.postLoginStart
);
app.post(
  '/login/webauthn-verify',
  login2FALimiter,
  webauthnController.postLoginVerify
);
app.post(
  '/account/webauthn/register',
  passportConfig.isAuthenticated,
  strictLimiter,
  webauthnController.postRegisterStart
);
app.post(
  '/account/webauthn/verify',
  passportConfig.isAuthenticated,
  strictLimiter,
  webauthnController.postRegisterVerify
);
app.post('/contact', strictLimiter, contactController.postContact);
""",
        "function": "express_route_registration_middleware_chains",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Mongoose schema complex user with auth tokens and OAuth providers",
    "Passport local strategy email password authentication",
    "Passport shared OAuth handler multiple providers account linking",
    "Two-factor authentication email code TOTP verify",
    "WebAuthn passkey registration challenge response credential",
    "Express rate limiting multi-tier global strict login",
    "Password reset token generation IP hash timing-safe verify",
    "Contact form reCAPTCHA validation nodemailer email",
    "Mongoose pre-save hook bcrypt password hash",
    "Express session MongoStore CSRF Lusca security middleware",
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
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:45s} | "
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
            print("  DRY_RUN — data deleted")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")

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
