"""
Wirings ingestion for sahat/hackathon-starter (JavaScript Hard).

Complex multi-auth patterns:
- Local + OAuth (6 providers) + WebAuthn + 2FA (TOTP + email)
- Mongoose schema with password reset, email verification, login tokens
- Passport strategies in separate files, configured dynamically
- Nodemailer transactional emails
- Middleware stack: session + flash + CSRF + Lusca + helmet
- Complete auth flows: registration, email verification, password reset, 2FA, WebAuthn

Wirings captured (8-10):
1. import_graph: app.js → controllers + config/passport + models
2. bootstrap_sequence: dotenv → express → mongoose → passport → middleware → routes
3. oauth_multi_provider: passport.use(GoogleStrategy, etc.) → serialize/deserialize → routes → callback flow
4. password_reset_flow: /forgot → token → email → /reset/:token → verify → save new password
5. 2fa_authentication_chain: login → check 2FA → TOTP or email code → verify → session
6. webauthn_flow: register challenge → navigator.credentials.create/get → verify → store credential
7. middleware_security_stack: lusca + helmet + session + flash + CSRF
8. email_verification_flow: register → token → send email → /verify/:token → verified flag
9. file_creation_order: models → config/passport → strategies → controllers → views → app.js assembly

No AST extraction (JavaScript). Manual patterns from architecture.
All patterns normalized: Xxx/xxx/xxxs placeholders, Charte v1.0.
"""

from __future__ import annotations
import subprocess
import os
import time
import uuid
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query

# ===== CONSTANTS =====

REPO_URL = "https://github.com/sahat/hackathon-starter.git"
REPO_NAME = "sahat/hackathon-starter"
REPO_LOCAL = "/tmp/hackathon-starter"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "express+mongoose+passport_multi+nodemailer+webauthn"
CHARTE_VERSION = "1.0"
TAG = "wirings/sahat/hackathon-starter"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# ===== WIRINGS DATA =====

WIRINGS = [
    # ========== WIRING 1: IMPORT GRAPH ==========
    {
        "wiring_type": "import_graph",
        "description": "Express app requires controllers (home, user, api, contact), passport config, and Mongoose models. Passport config dynamically loads individual strategy files.",
        "modules": [
            "app.js",
            "controllers/home.js",
            "controllers/user.js",
            "controllers/api.js",
            "controllers/contact.js",
            "config/passport.js",
            "config/passport/index.js",
            "models/Xxx.js",
        ],
        "connections": [
            "app.js → require('./controllers/home')",
            "app.js → require('./controllers/user')",
            "app.js → require('./controllers/api')",
            "app.js → require('./controllers/contact')",
            "app.js → require('./config/passport')",
            "config/passport.js → require('./strategies/local')",
            "config/passport.js → require('./strategies/google')",
            "config/passport.js → require('./strategies/github')",
            "config/passport.js → require('./strategies/facebook')",
            "config/passport.js → require('./strategies/discord')",
            "config/passport.js → require('./strategies/linkedin')",
            "config/passport.js → require('./strategies/microsoft')",
            "app.js → require('./models/Xxx')",
            "controllers/user.js → require('../models/Xxx')",
        ],
        "code_example": """// app.js
const home = require('./controllers/home');
const userController = require('./controllers/user');
const apiController = require('./controllers/api');
const contactController = require('./controllers/contact');
const passportConfig = require('./config/passport');
const Xxx = require('./models/Xxx');

// Passport strategies loaded dynamically
require('./config/passport')(passport);

app.use(passport.initialize());
app.use(passport.session());

// Routes using controllers
app.get('/', home.index);
app.post('/login', userController.postLogin);
app.post('/signup', userController.postSignup);
app.get('/auth/google', userController.authGoogle);

// config/passport.js
module.exports = (passport) => {
  passport.use(new LocalStrategy({...}, (...) => {...}));
  passport.use(new GoogleStrategy({...}, (...) => {...}));
  // ... more strategies
};
""",
        "pattern_scope": "import_graph",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 2: BOOTSTRAP SEQUENCE ==========
    {
        "wiring_type": "flow_pattern",
        "description": "Express app bootstrap: load dotenv, create express instance, connect Mongoose, load passport config, apply middleware stack (session, flash, CSRF, lusca, helmet, static, views), setup routes, error handler, listen.",
        "modules": [
            "app.js",
            ".env",
            "models/Xxx.js",
            "config/passport.js",
            "views/",
        ],
        "connections": [
            "app.js: 1) dotenv.config()",
            "app.js: 2) express()",
            "app.js: 3) mongoose.connect(process.env.MONGODB_URI)",
            "app.js: 4) require('./config/passport')(passport)",
            "app.js: 5) app.use(expressSession({...}))",
            "app.js: 6) app.use(passport.initialize/session)",
            "app.js: 7) app.use(flash())",
            "app.js: 8) app.use(lusca.csrf/xframe/xssProtection)",
            "app.js: 9) app.use(helmet())",
            "app.js: 10) app.use(express.static('public'))",
            "app.js: 11) app.set('view engine', 'pug')",
            "app.js: 12) routes setup",
            "app.js: 13) app.use(errorHandler)",
            "app.js: 14) app.listen(PORT)",
        ],
        "code_example": """// app.js
require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const passport = require('passport');
const session = require('express-session');
const MongoStore = require('connect-mongo');
const flash = require('express-flash');
const lusca = require('lusca');
const helmet = require('helmet');

const app = express();

// 1. Connect DB
mongoose.connect(process.env.MONGODB_URI, {...});

// 2. Load passport config
require('./config/passport')(passport);

// 3. Middleware stack
app.use(session({
  secret: process.env.SESSION_SECRET,
  store: MongoStore.create({mongoUrl: process.env.MONGODB_URI}),
  resave: false,
  saveUninitialized: false,
}));
app.use(passport.initialize());
app.use(passport.session());
app.use(flash());
app.use(lusca.csrf());
app.use(lusca.xframe('SAMEORIGIN'));
app.use(lusca.xssProtection(true));
app.use(helmet());
app.use(express.static('public'));
app.set('view engine', 'pug');

// 4. Routes
app.get('/', home.index);
app.post('/login', userController.postLogin);

// 5. Error handler
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).send('Server error');
});

// 6. Listen
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`App running on port ${PORT}`));
""",
        "pattern_scope": "bootstrap",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 3: OAUTH MULTI-PROVIDER FLOW ==========
    {
        "wiring_type": "dependency_chain",
        "description": "Multi-provider OAuth wiring: passport.use(GoogleStrategy/GitHubStrategy/etc.) with callbackURL, clientID, clientSecret. User serialization/deserialization. Routes: /auth/provider, /auth/provider/callback. Callback finds or creates user, links provider ID to user model, establishes session.",
        "modules": [
            "config/passport.js",
            "config/passport/google.js",
            "config/passport/github.js",
            "config/passport/facebook.js",
            "controllers/user.js",
            "models/Xxx.js",
        ],
        "connections": [
            "config/passport.js → passport.serializeUser()",
            "config/passport.js → passport.deserializeUser()",
            "config/passport.js → passport.use(new GoogleStrategy(...))",
            "GoogleStrategy callback → find user by googleId",
            "GoogleStrategy callback → create user if not exists",
            "GoogleStrategy callback → return user",
            "controllers/user.js → GET /auth/google: passport.authenticate('google', {scope: [...]}, ...)",
            "controllers/user.js → GET /auth/google/callback: passport.authenticate('google', {failureRedirect: '/login'}, ...)",
            "callback handler → find user by googleId → req.logIn(user, ...) → redirect /dashboard",
        ],
        "code_example": """// config/passport.js
module.exports = (passport) => {
  passport.serializeUser((xxx, done) => {
    done(null, xxx.id);
  });

  passport.deserializeUser((id, done) => {
    Xxx.findById(id, (err, xxx) => {
      done(err, xxx);
    });
  });

  // Google
  passport.use(new GoogleStrategy(
    {
      clientID: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      callbackURL: '/auth/google/callback',
    },
    async (accessToken, refreshToken, profile, done) => {
      try {
        let xxx = await Xxx.findOne({googleId: profile.id});
        if (xxx) {
          return done(null, xxx);
        }
        xxx = new Xxx({
          googleId: profile.id,
          email: profile.emails[0].value,
          name: profile.displayName,
        });
        await xxx.save();
        done(null, xxx);
      } catch (err) {
        done(err);
      }
    }
  ));

  // Similar for GitHub, Facebook, etc.
};

// controllers/user.js
exports.getAuthGoogle = passport.authenticate('google', {
  scope: ['profile', 'email'],
});

exports.getAuthGoogleCallback = (req, res, next) => {
  passport.authenticate('google', {failureRedirect: '/login'}, (err, xxx) => {
    if (err) return next(err);
    req.logIn(xxx, (err) => {
      if (err) return next(err);
      res.redirect('/dashboard');
    });
  })(req, res, next);
};

// app.js routes
app.get('/auth/google', userController.getAuthGoogle);
app.get('/auth/google/callback', userController.getAuthGoogleCallback);
""",
        "pattern_scope": "oauth_flow",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 4: PASSWORD RESET FLOW ==========
    {
        "wiring_type": "flow_pattern",
        "description": "Password reset multi-step flow: 1) POST /forgot → validate email → generate crypto.randomBytes token → save token + expiration (1 hour) to user model → send reset email via Nodemailer. 2) GET /reset/:token → retrieve user by token → verify not expired → render password form. 3) POST /reset/:token → verify token → hash new password → save → clear token → redirect login.",
        "modules": [
            "controllers/user.js",
            "models/Xxx.js",
            "views/forgot.pug",
            "views/reset.pug",
        ],
        "connections": [
            "app.post('/forgot', ...) → user.postForgot()",
            "postForgot: 1) Xxx.findOne({email})",
            "postForgot: 2) crypto.randomBytes(32).toString('hex') → token",
            "postForgot: 3) xxx.resetPasswordToken = token, xxx.resetPasswordExpires = Date.now() + 3600000",
            "postForgot: 4) xxx.save()",
            "postForgot: 5) nodemailer.transporter.sendMail({to, subject, html})",
            "app.get('/reset/:token', ...) → user.getReset()",
            "getReset: 1) Xxx.findOne({resetPasswordToken: token, resetPasswordExpires: {$gt: Date.now()}})",
            "getReset: 2) res.render('reset', {token})",
            "app.post('/reset/:token', ...) → user.postReset()",
            "postReset: 1) Xxx.findOne({resetPasswordToken: token, resetPasswordExpires: {$gt: Date.now()}})",
            "postReset: 2) xxx.password = req.body.password",
            "postReset: 3) xxx.resetPasswordToken = undefined, xxx.resetPasswordExpires = undefined",
            "postReset: 4) xxx.save()",
            "postReset: 5) res.redirect('/login')",
        ],
        "code_example": """// models/Xxx.js
const xxxSchema = new mongoose.Schema({
  email: {type: String, unique: true},
  password: String,
  resetPasswordToken: String,
  resetPasswordExpires: Date,
  // ... other fields
});

// Pre-save hook: clear expired tokens
xxxSchema.pre('save', function(next) {
  if (this.resetPasswordExpires && this.resetPasswordExpires < Date.now()) {
    this.resetPasswordToken = undefined;
    this.resetPasswordExpires = undefined;
  }
  next();
});

// controllers/user.js
const crypto = require('crypto');

exports.postForgot = async (req, res) => {
  try {
    const xxx = await Xxx.findOne({email: req.body.email});
    if (!xxx) {
      return res.redirect('/forgot');
    }

    const token = crypto.randomBytes(32).toString('hex');
    xxx.resetPasswordToken = token;
    xxx.resetPasswordExpires = Date.now() + 3600000; // 1 hour
    await xxx.save();

    await transporter.sendMail({
      to: xxx.email,
      subject: 'Password reset link',
      html: `<a href="http://localhost:3000/reset/${token}">Reset password</a>`,
    });

    res.redirect('/');
  } catch (err) {
    res.redirect('/forgot');
  }
};

exports.getReset = async (req, res) => {
  try {
    const xxx = await Xxx.findOne({
      resetPasswordToken: req.params.token,
      resetPasswordExpires: {$gt: Date.now()},
    });
    if (!xxx) {
      return res.redirect('/forgot');
    }
    res.render('reset', {token: req.params.token});
  } catch (err) {
    res.redirect('/forgot');
  }
};

exports.postReset = async (req, res) => {
  try {
    const xxx = await Xxx.findOne({
      resetPasswordToken: req.params.token,
      resetPasswordExpires: {$gt: Date.now()},
    });
    if (!xxx) {
      return res.redirect('/forgot');
    }

    xxx.password = req.body.password;
    xxx.resetPasswordToken = undefined;
    xxx.resetPasswordExpires = undefined;
    await xxx.save();

    res.redirect('/login');
  } catch (err) {
    res.redirect('/forgot');
  }
};
""",
        "pattern_scope": "password_reset_flow",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 5: 2FA AUTHENTICATION CHAIN ==========
    {
        "wiring_type": "dependency_chain",
        "description": "Two-factor authentication chain: 1) User logs in with email + password → controller checks xxx.twoFactorEnabled. 2) If TOTP enabled: redirect /2fa/totp → user enters TOTP code from authenticator app → verify with speakeasy.totp.verify() → establish session. 3) If email 2FA enabled: generate code → send via Nodemailer → POST /2fa/email → verify code → session. Counter incremented on each use.",
        "modules": [
            "controllers/user.js",
            "models/Xxx.js",
            "views/2fa-totp.pug",
            "views/2fa-email.pug",
        ],
        "connections": [
            "POST /login → user.postLogin()",
            "postLogin: 1) passport.authenticate('local')",
            "postLogin: 2) if xxx.twoFactorEnabled && xxx.twoFactorType === 'totp' → redirect /2fa/totp",
            "postLogin: 3) if xxx.twoFactorEnabled && xxx.twoFactorType === 'email' → generate code → sendMail → redirect /2fa/email",
            "GET /2fa/totp → render form for TOTP code",
            "POST /2fa/totp → user.post2faTotp()",
            "post2faTotp: 1) speakeasy.totp.verify({secret: xxx.totpSecret, code: req.body.code})",
            "post2faTotp: 2) xxx.totpCounter++, xxx.save()",
            "post2faTotp: 3) req.session.twoFactorVerified = true",
            "post2faTotp: 4) res.redirect('/dashboard')",
            "GET /2fa/email → render form for email code",
            "POST /2fa/email → user.post2faEmail()",
            "post2faEmail: 1) verify code matches xxx.emailVerificationCode",
            "post2faEmail: 2) verify not expired (twoFactorCodeExpires)",
            "post2faEmail: 3) req.session.twoFactorVerified = true",
            "post2faEmail: 4) xxx.emailVerificationCode = null, xxx.twoFactorCodeExpires = null",
            "post2faEmail: 5) res.redirect('/dashboard')",
        ],
        "code_example": """// models/Xxx.js
const xxxSchema = new mongoose.Schema({
  email: String,
  password: String,
  twoFactorEnabled: {type: Boolean, default: false},
  twoFactorType: {type: String, enum: ['totp', 'email']},
  totpSecret: String,
  totpCounter: {type: Number, default: 0},
  emailVerificationCode: String,
  twoFactorCodeExpires: Date,
  // ...
});

// controllers/user.js
const speakeasy = require('speakeasy');

exports.postLogin = async (req, res, next) => {
  passport.authenticate('local', async (err, xxx) => {
    if (err || !xxx) {
      return res.redirect('/login');
    }

    if (xxx.twoFactorEnabled) {
      if (xxx.twoFactorType === 'totp') {
        return res.redirect('/2fa/totp');
      }

      if (xxx.twoFactorType === 'email') {
        const code = Math.floor(100000 + Math.random() * 900000).toString();
        xxx.emailVerificationCode = code;
        xxx.twoFactorCodeExpires = Date.now() + 600000; // 10 minutes
        await xxx.save();

        await transporter.sendMail({
          to: xxx.email,
          subject: '2FA Code',
          text: `Your 2FA code: ${code}`,
        });

        return res.redirect('/2fa/email');
      }
    }

    req.logIn(xxx, (err) => {
      if (err) return next(err);
      res.redirect('/dashboard');
    });
  })(req, res, next);
};

exports.post2faTotp = async (req, res) => {
  try {
    const xxx = await Xxx.findById(req.user.id);
    const verified = speakeasy.totp.verify({
      secret: xxx.totpSecret,
      encoding: 'base32',
      token: req.body.token,
    });

    if (!verified) {
      return res.redirect('/2fa/totp');
    }

    xxx.totpCounter++;
    await xxx.save();

    req.session.twoFactorVerified = true;
    res.redirect('/dashboard');
  } catch (err) {
    res.redirect('/2fa/totp');
  }
};

exports.post2faEmail = async (req, res) => {
  try {
    const xxx = await Xxx.findById(req.user.id);

    if (xxx.emailVerificationCode !== req.body.code) {
      return res.redirect('/2fa/email');
    }

    if (xxx.twoFactorCodeExpires < Date.now()) {
      return res.redirect('/2fa/email');
    }

    xxx.emailVerificationCode = null;
    xxx.twoFactorCodeExpires = null;
    await xxx.save();

    req.session.twoFactorVerified = true;
    res.redirect('/dashboard');
  } catch (err) {
    res.redirect('/2fa/email');
  }
};
""",
        "pattern_scope": "2fa_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 6: WEBAUTHN FLOW ==========
    {
        "wiring_type": "flow_pattern",
        "description": "WebAuthn (FIDO2) registration + authentication: Registration: server generates challenge → send to client → navigator.credentials.create() → client returns attestation → server verifies attestation with fido2-lib → store credential public key + ID in user model. Authentication: server generates challenge → navigator.credentials.get() → client returns assertion → server verifies assertion with fido2-lib → increment counter → establish session.",
        "modules": [
            "controllers/user.js",
            "models/Xxx.js",
            "public/webauthn-register.js",
            "public/webauthn-login.js",
        ],
        "connections": [
            "GET /webauthn/register/options → generate challenge via fido2-lib",
            "GET /webauthn/register/options → save challenge in session",
            "POST /webauthn/register → client sends attestation",
            "POST /webauthn/register → server verifies attestation with fido2-lib",
            "POST /webauthn/register → store credential in xxx.webauthnCredentials",
            "GET /webauthn/login/options → generate challenge via fido2-lib",
            "GET /webauthn/login/options → save challenge in session",
            "POST /webauthn/login → client sends assertion",
            "POST /webauthn/login → server verifies assertion with fido2-lib",
            "POST /webauthn/login → find credential by ID in xxx.webauthnCredentials",
            "POST /webauthn/login → verify counter > previous counter",
            "POST /webauthn/login → increment counter, save to model",
            "POST /webauthn/login → req.logIn(xxx) → redirect /dashboard",
        ],
        "code_example": """// models/Xxx.js
const xxxSchema = new mongoose.Schema({
  email: String,
  webauthnCredentials: [{
    credentialID: Buffer,
    publicKey: Buffer,
    counter: Number,
    transports: [String],
  }],
  // ...
});

// controllers/user.js
const Fido2Lib = require('fido2-lib');
const fido2 = new Fido2Lib({
  timeout: 60000,
  rpId: 'localhost',
  rpName: 'Xxx App',
  rpIcon: 'https://xxx.com/icon.png',
  attestation: 'direct',
});

exports.getWebauthnRegisterOptions = async (req, res) => {
  const challenge = await fido2.attestationOptions();
  req.session.webauthnChallenge = challenge.challenge;
  res.json(challenge);
};

exports.postWebauthnRegister = async (req, res) => {
  try {
    const verified = await fido2.attestationResult(
      req.body,
      req.session.webauthnChallenge
    );

    const xxx = await Xxx.findById(req.user.id);
    xxx.webauthnCredentials.push({
      credentialID: verified.id,
      publicKey: verified.publicKey,
      counter: verified.counter,
      transports: req.body.response.transports,
    });
    await xxx.save();

    res.json({success: true});
  } catch (err) {
    res.json({success: false, error: err.message});
  }
};

exports.getWebauthnLoginOptions = async (req, res) => {
  const challenge = await fido2.assertionOptions();
  req.session.webauthnChallenge = challenge.challenge;
  res.json(challenge);
};

exports.postWebauthnLogin = async (req, res) => {
  try {
    const verified = await fido2.assertionResult(
      req.body,
      req.session.webauthnChallenge
    );

    const xxx = await Xxx.findOne({
      'webauthnCredentials.credentialID': verified.id,
    });
    if (!xxx) {
      return res.json({success: false, error: 'Credential not found'});
    }

    const credential = xxx.webauthnCredentials.find(
      (c) => c.credentialID.toString() === verified.id.toString()
    );
    if (verified.counter <= credential.counter) {
      return res.json({success: false, error: 'Counter check failed'});
    }

    credential.counter = verified.counter;
    await xxx.save();

    req.logIn(xxx, (err) => {
      if (err) return res.json({success: false, error: err.message});
      res.json({success: true});
    });
  } catch (err) {
    res.json({success: false, error: err.message});
  }
};

// public/webauthn-register.js
async function registerWebauthn() {
  const resp = await fetch('/webauthn/register/options');
  const options = await resp.json();

  const attestation = await navigator.credentials.create({
    publicKey: {
      challenge: new Uint8Array(options.challenge),
      rp: {name: 'Xxx App', id: 'localhost'},
      user: {
        id: new Uint8Array(16),
        name: 'xxx@example.com',
        displayName: 'Xxx User',
      },
      pubKeyCredParams: [{alg: -7, type: 'public-key'}],
      timeout: 60000,
      attestation: 'direct',
    },
  });

  const resp2 = await fetch('/webauthn/register', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(attestation),
  });
  const result = await resp2.json();
  console.log(result.success ? 'Registered' : 'Failed');
}
""",
        "pattern_scope": "webauthn_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 7: MIDDLEWARE SECURITY STACK ==========
    {
        "wiring_type": "dependency_chain",
        "description": "Security middleware stack: 1) helmet() → sets security headers (Content-Security-Policy, X-Frame-Options, etc.). 2) lusca.csrf() → CSRF token generation and validation. 3) lusca.xframe('SAMEORIGIN') → clickjacking prevention. 4) lusca.xssProtection(true) → XSS filter. 5) express-session with MongoStore → session persistence. 6) passport.initialize/session → auth state. 7) flash messages → error/success notifications.",
        "modules": [
            "app.js",
            "package.json",
        ],
        "connections": [
            "app.use(helmet())",
            "helmet() → X-Content-Type-Options: nosniff",
            "helmet() → X-Frame-Options: DENY",
            "helmet() → X-XSS-Protection: 1; mode=block",
            "helmet() → Strict-Transport-Security",
            "app.use(session({...}))",
            "session → express-session + connect-mongo",
            "app.use(passport.initialize())",
            "app.use(passport.session())",
            "app.use(lusca.csrf())",
            "csrf → req.csrfToken() available in templates",
            "app.use(lusca.xframe('SAMEORIGIN'))",
            "app.use(lusca.xssProtection(true))",
            "app.use(flash())",
            "flash → req.flash('error'), res.locals.messages in Pug",
        ],
        "code_example": """// app.js
const helmet = require('helmet');
const lusca = require('lusca');
const session = require('express-session');
const MongoStore = require('connect-mongo');
const passport = require('passport');
const flash = require('express-flash');

app.use(helmet());

app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  store: MongoStore.create({
    mongoUrl: process.env.MONGODB_URI,
  }),
  cookie: {
    maxAge: 1000 * 60 * 60 * 24, // 1 day
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
  },
}));

app.use(passport.initialize());
app.use(passport.session());

app.use(lusca.csrf());
app.use(lusca.xframe('SAMEORIGIN'));
app.use(lusca.xssProtection(true));

app.use(flash());

// Make CSRF token available in all templates
app.use((req, res, next) => {
  res.locals.csrfToken = req.csrfToken();
  res.locals.messages = req.flash();
  next();
});

// Routes
app.post('/login', [
  // CSRF validation automatic via lusca
  userController.postLogin,
]);

// views/login.pug
form(method='POST', action='/login')
  input(type='hidden', name='_csrf', value=csrfToken)
  input(type='email', name='email', required)
  input(type='password', name='password', required)
  button(type='submit') Login
""",
        "pattern_scope": "middleware_security",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 8: EMAIL VERIFICATION FLOW ==========
    {
        "wiring_type": "flow_pattern",
        "description": "Email verification multi-step flow: 1) User registers → generate token via crypto.randomBytes → save token + expiration (24 hours) + IP hash to user model. 2) Send verification email with Nodemailer containing verification link. 3) GET /verify/:token → retrieve user by token → verify not expired → verify IP matches (optional, can be skipped for relocation). 4) Set verified=true → save user → redirect login.",
        "modules": [
            "controllers/user.js",
            "models/Xxx.js",
            "views/verify-email.pug",
        ],
        "connections": [
            "POST /signup → user.postSignup()",
            "postSignup: 1) check if email exists",
            "postSignup: 2) hash password (bcrypt)",
            "postSignup: 3) create new xxx with verified=false",
            "postSignup: 4) generate token: crypto.randomBytes(64).toString('hex')",
            "postSignup: 5) xxx.emailVerificationToken = token",
            "postSignup: 6) xxx.emailVerificationExpires = Date.now() + 86400000 (24h)",
            "postSignup: 7) xxx.emailVerificationIp = req.ip",
            "postSignup: 8) xxx.save()",
            "postSignup: 9) sendMail({to, subject, html: verification link})",
            "GET /verify/:token → user.getVerify()",
            "getVerify: 1) Xxx.findOne({emailVerificationToken: token, emailVerificationExpires: {$gt: Date.now()}})",
            "getVerify: 2) verify token is still valid",
            "getVerify: 3) xxx.verified = true",
            "getVerify: 4) xxx.emailVerificationToken = null, xxx.emailVerificationExpires = null",
            "getVerify: 5) xxx.save()",
            "getVerify: 6) res.render('verify-email', {success: true})",
        ],
        "code_example": """// models/Xxx.js
const xxxSchema = new mongoose.Schema({
  email: {type: String, unique: true},
  password: String,
  verified: {type: Boolean, default: false},
  emailVerificationToken: String,
  emailVerificationExpires: Date,
  emailVerificationIp: String,
  // ...
});

// Pre-save: clear expired verification tokens
xxxSchema.pre('save', function(next) {
  if (this.emailVerificationExpires && this.emailVerificationExpires < Date.now()) {
    this.emailVerificationToken = null;
    this.emailVerificationExpires = null;
  }
  next();
});

// controllers/user.js
const crypto = require('crypto');
const bcrypt = require('bcrypt');

exports.postSignup = async (req, res) => {
  try {
    const existing = await Xxx.findOne({email: req.body.email});
    if (existing) {
      return res.status(400).send('Email already in use');
    }

    const hashedPassword = await bcrypt.hash(req.body.password, 10);
    const token = crypto.randomBytes(64).toString('hex');

    const xxx = new Xxx({
      email: req.body.email,
      password: hashedPassword,
      verified: false,
      emailVerificationToken: token,
      emailVerificationExpires: Date.now() + 86400000, // 24 hours
      emailVerificationIp: req.ip,
    });

    await xxx.save();

    await transporter.sendMail({
      to: xxx.email,
      subject: 'Verify your email',
      html: `<a href="http://localhost:3000/verify/${token}">Verify email</a>`,
    });

    res.status(201).send('Verification email sent');
  } catch (err) {
    res.status(500).send('Signup failed');
  }
};

exports.getVerify = async (req, res) => {
  try {
    const xxx = await Xxx.findOne({
      emailVerificationToken: req.params.token,
      emailVerificationExpires: {$gt: Date.now()},
    });

    if (!xxx) {
      return res.status(400).render('verify-email', {
        success: false,
        message: 'Token invalid or expired',
      });
    }

    xxx.verified = true;
    xxx.emailVerificationToken = null;
    xxx.emailVerificationExpires = null;
    await xxx.save();

    res.render('verify-email', {
      success: true,
      message: 'Email verified! You can now log in.',
    });
  } catch (err) {
    res.status(500).render('verify-email', {
      success: false,
      message: 'Verification failed',
    });
  }
};

// app.js
app.get('/verify/:token', userController.getVerify);
""",
        "pattern_scope": "email_verification",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
    # ========== WIRING 9: FILE CREATION ORDER ==========
    {
        "wiring_type": "flow_pattern",
        "description": "Optimal file creation order for complex multi-auth Express app: 1) models/Xxx.js → define schema with all auth-related fields (password, tokens, TOTP, WebAuthn, 2FA, providers), pre-save hooks. 2) config/passport.js → main Passport config with serialize/deserialize. 3) config/passport/*.js → individual strategy files (LocalStrategy, GoogleStrategy, etc.). 4) controllers/user.js → all auth routes and handlers (login, signup, reset, 2FA, WebAuthn, email verify, OAuth callbacks). 5) controllers/api.js → API integrations if needed. 6) public/*.js → client-side WebAuthn, form validation. 7) views/*.pug → auth templates. 8) app.js → assembly: imports, DB connection, middleware stack, routes, error handler, listen.",
        "modules": [
            "models/Xxx.js",
            "config/passport.js",
            "config/passport/local.js",
            "config/passport/google.js",
            "config/passport/github.js",
            "config/passport/facebook.js",
            "config/passport/discord.js",
            "config/passport/linkedin.js",
            "config/passport/microsoft.js",
            "controllers/user.js",
            "controllers/api.js",
            "controllers/home.js",
            "controllers/contact.js",
            "public/webauthn-register.js",
            "public/webauthn-login.js",
            "views/login.pug",
            "views/signup.pug",
            "views/verify-email.pug",
            "views/forgot.pug",
            "views/reset.pug",
            "views/2fa-totp.pug",
            "views/2fa-email.pug",
            "views/account.pug",
            "views/dashboard.pug",
            "app.js",
        ],
        "connections": [
            "Step 1: models/Xxx.js — all auth fields, pre-save hooks, bcrypt hashing",
            "Step 2: config/passport.js — serializeUser, deserializeUser, passport.use(...)",
            "Step 3: config/passport/local.js — LocalStrategy(findOne + compare password)",
            "Step 3: config/passport/google.js — GoogleStrategy(findOne or create by googleId)",
            "Step 3: config/passport/github.js — GitHubStrategy(...)",
            "Step 3: config/passport/facebook.js — FacebookStrategy(...)",
            "Step 3: config/passport/discord.js — DiscordStrategy(...)",
            "Step 3: config/passport/linkedin.js — LinkedInStrategy(...)",
            "Step 3: config/passport/microsoft.js — MicrosoftStrategy(...)",
            "Step 4: controllers/user.js — postSignup, postLogin, postForgot, postReset, post2faTotp, post2faEmail, postWebauthnRegister, postWebauthnLogin, getVerify",
            "Step 5: controllers/api.js — API endpoints for integrations (optional)",
            "Step 6: public/webauthn-register.js — navigator.credentials.create()",
            "Step 6: public/webauthn-login.js — navigator.credentials.get()",
            "Step 7: views/login.pug — form, CSRF token, OAuth buttons",
            "Step 7: views/signup.pug — form, password confirmation, terms",
            "Step 7: views/verify-email.pug — success/failure message",
            "Step 7: views/forgot.pug — email input",
            "Step 7: views/reset.pug — new password form",
            "Step 7: views/2fa-totp.pug — TOTP code input",
            "Step 7: views/2fa-email.pug — email code input",
            "Step 8: app.js — require all, middleware stack, routes, error handler",
        ],
        "code_example": """// File creation order execution example

// 1. models/Xxx.js — define schema
const xxxSchema = new Schema({
  email: String,
  password: String,
  verified: Boolean,
  emailVerificationToken: String,
  emailVerificationExpires: Date,
  resetPasswordToken: String,
  resetPasswordExpires: Date,
  twoFactorEnabled: Boolean,
  twoFactorType: String,
  totpSecret: String,
  emailVerificationCode: String,
  twoFactorCodeExpires: Date,
  googleId: String,
  githubId: String,
  facebookId: String,
  discordId: String,
  linkedinId: String,
  microsoftId: String,
  webauthnCredentials: [{credentialID, publicKey, counter}],
});

// 2. config/passport.js — main config
module.exports = (passport) => {
  passport.serializeUser((xxx, done) => done(null, xxx.id));
  passport.deserializeUser((id, done) => {
    Xxx.findById(id, (err, xxx) => done(err, xxx));
  });
  // All passport.use(...) calls follow
};

// 3. config/passport/local.js, google.js, etc.
passport.use(new LocalStrategy({...}, (...) => {...}));
passport.use(new GoogleStrategy({...}, (...) => {...}));

// 4. controllers/user.js — all handlers
exports.postSignup = async (req, res) => {...};
exports.postLogin = async (req, res) => {...};
exports.post2faTotp = async (req, res) => {...};
exports.postWebauthnLogin = async (req, res) => {...};

// 5. controllers/api.js
exports.getProfile = async (req, res) => {...};

// 6. public/webauthn-register.js, webauthn-login.js
async function registerWebauthn() {...}

// 7. views/*.pug — templates

// 8. app.js — assembly
require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const passport = require('passport');
const app = express();

mongoose.connect(process.env.MONGODB_URI);
require('./config/passport')(passport);

app.use(session({...}));
app.use(passport.initialize());
app.use(passport.session());
app.use(flash());
app.use(lusca.csrf());
app.use(helmet());

app.post('/signup', userController.postSignup);
app.post('/login', userController.postLogin);
app.get('/auth/google', userController.authGoogle);
app.post('/2fa/totp', userController.post2faTotp);
app.post('/webauthn/login', userController.postWebauthnLogin);

app.listen(PORT);
""",
        "pattern_scope": "file_creation_order",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "_tag": TAG,
    },
]


# ===== FUNCTIONS =====


def cleanup_old_wirings():
    """Remove old wirings for this repo from Qdrant."""
    client = QdrantClient(path=KB_PATH)
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="_tag",
                            match=MatchValue(value=TAG),
                        )
                    ]
                )
            ),
        )
        print(f"Cleaned up old wirings: {TAG}")
    except Exception as e:
        print(f"Cleanup error: {e}")


def embed_and_insert_wirings():
    """Embed wiring descriptions and insert into Qdrant."""
    client = QdrantClient(path=KB_PATH)

    # Prepare descriptions for embedding
    descriptions = [w["description"] for w in WIRINGS]

    # Embed in batch
    print(f"Embedding {len(descriptions)} wiring descriptions...")
    embeddings = embed_documents_batch(descriptions)

    # Insert points
    points = []
    for i, (wiring, embedding) in enumerate(zip(WIRINGS, embeddings)):
        point = PointStruct(
            id=int(time.time() * 1000) + i,
            vector=embedding,
            payload=wiring,
        )
        points.append(point)

    print(f"Inserting {len(points)} points into {COLLECTION}...")
    client.upsert(
        collection_name=COLLECTION,
        points=points,
    )
    print(f"Inserted {len(points)} wirings for {REPO_NAME}")


def main():
    """Main entry point."""
    print(f"Starting wirings ingestion for {REPO_NAME}...")
    print(f"Repo: {REPO_URL}")
    print(f"Language: {LANGUAGE}")
    print(f"Framework: {FRAMEWORK}")
    print(f"Stack: {STACK}")
    print(f"Collection: {COLLECTION}")
    print(f"KB path: {KB_PATH}")
    print(f"DRY_RUN: {DRY_RUN}")
    print()

    if DRY_RUN:
        print("DRY_RUN: Would insert:")
        for i, w in enumerate(WIRINGS):
            print(
                f"  {i+1}. {w['wiring_type']}: {w['pattern_scope']} "
                f"({len(w['modules'])} modules)"
            )
        return

    # Cleanup old wirings
    cleanup_old_wirings()

    # Embed and insert
    embed_and_insert_wirings()

    # Verify
    client = QdrantClient(path=KB_PATH)
    col = client.get_collection(COLLECTION)
    print(f"\nVerification: {col.points_count} total points in {COLLECTION}")


if __name__ == "__main__":
    main()
