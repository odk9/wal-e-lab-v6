# Prompt JS B — hagopj13/node-express-boilerplate

Copier-coller ce prompt dans Claude Code (VS Code terminal).

---

## PROMPT

Tu es le KB Builder de Wal-e Lab V6. Ta mission : créer `ingest_node_express_boilerplate.py` pour extraire, normaliser et indexer TOUS les patterns du repo `hagopj13/node-express-boilerplate` dans la KB Qdrant.

**Lis CLAUDE.md et kb_utils.py avant de commencer.** Utilise `build_payload()`, `check_charte_violations()`, `make_uuid()`, `query_kb()`, et `audit_report()` de kb_utils.py.

---

### REPO : hagopj13/node-express-boilerplate

**Stack :** Express + Mongoose + Passport JWT + Joi + Nodemailer
**Architecture :** Controller → Service → Model (3 couches séparées)
**Ce qui est NOUVEAU vs JS A (node-express-mongoose-demo) :**
- JWT auth (access + refresh tokens), pas session-based
- Role-based access control (RBAC) via roleRights Map
- Joi validation middleware (pas de validation inline)
- Pagination Mongoose plugin (page, limit, sort, populate)
- toJSON Mongoose plugin (private fields, _id→id)
- Service layer pattern (controller → service → model)
- Token model + service (generate, save, verify, blacklist)
- Email service (nodemailer — reset password, verify email)
- catchAsync utility (Promise wrapper)
- ApiError custom class
- Error handling middleware (errorConverter + errorHandler)

---

### CONSTANTES du script

```python
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
```

---

### NORMALISATION Charte Wal-e (U-5 — CRITIQUE)

Remplacements d'entités métier :
- `User` → `Xxx` (classe/modèle)
- `user` → `xxx` (variable/fonction)
- `users` → `xxxs` (pluriel)
- `Token` → `XxxToken` (2ème entité)
- `token` → `xxxToken` (variable)
- `tokens` → `xxxTokens` (pluriel)
- `userId` → `xxxId`

**Garder tel quel (termes techniques) :**
- `email`, `password`, `name`, `role` — champs génériques
- `isEmailVerified`, `isEmailTaken`, `isPasswordMatch` — méthodes
- `req.user` — terme technique Passport (dans TECHNICAL_TERMS)
- `jwt`, `bcrypt`, `passport`, `Joi`, `nodemailer` — noms de lib
- `httpStatus`, `catchAsync`, `ApiError` — utilitaires
- `roleRights`, `roles` — config RBAC
- `blacklisted`, `expires` — champs génériques Token

**Règles JS (J-*) à appliquer :**
- J-1 : `var` → `const`/`let`
- J-2 : pas de callback hell (déjà async/await dans le repo)
- J-3 : supprimer tout `console.log()`

---

### PATTERNS À EXTRAIRE (≈45-50 patterns, TOUS organisés par fonction)

#### MODELS (≈5)

**1. Mongoose schema — main entity with validation + plugins**
Source : `src/models/user.model.js`
- Schema : name, email (unique + validator), password (private + minlength + regex validate), role (enum), isEmailVerified (boolean), timestamps
- Plugins : toJSON, paginate
- Static : `isEmailTaken(email, excludeXxxId)`
- Method : `isPasswordMatch(password)` (bcrypt.compare)
- Pre-save hook : bcrypt hash password if modified
- `Xxx = mongoose.model('Xxx', xxxSchema)`

**2. Mongoose schema — token model with enum type**
Source : `src/models/token.model.js`
- Schema : token (String, index), xxx_ref (ObjectId ref 'Xxx'), type (enum: refresh/resetPassword/verifyEmail), expires (Date), blacklisted (Boolean)
- Plugin : toJSON
- `XxxToken = mongoose.model('XxxToken', xxxTokenSchema)`

**3. toJSON plugin — sanitize JSON output**
Source : `src/models/plugins/toJSON.plugin.js`
- Removes `__v`, `createdAt`, `updatedAt`, and `private: true` fields
- Replaces `_id` with `id`
- Preserves existing transform if present

**4. paginate plugin — cursor-based pagination**
Source : `src/models/plugins/paginate.plugin.js`
- Static method `.paginate(filter, options)`
- Options : sortBy (multi-field), limit (default 10), page (default 1), populate (nested dot notation)
- Returns : `{ results, page, limit, totalPages, totalResults }`

**5. models/index.js — barrel export**
Exporte Xxx et XxxToken

#### CONTROLLERS (≈2, mais 13 fonctions)

**6. Entity CRUD controller (5 fonctions)**
Source : `src/controllers/user.controller.js`
- `createXxx` — catchAsync, appelle xxxService.createXxx(req.body), 201
- `getXxxs` — catchAsync, pick(req.query, ['name','role']), pick options, xxxService.queryXxxs
- `getXxx` — catchAsync, xxxService.getXxxById, 404 si null
- `updateXxx` — catchAsync, xxxService.updateXxxById
- `deleteXxx` — catchAsync, xxxService.deleteXxxById, 204

**7. Auth controller (8 fonctions)**
Source : `src/controllers/auth.controller.js`
- `register` — createXxx + generateAuthXxxTokens → 201 {xxx, xxxTokens}
- `login` — loginWithEmailAndPassword + generateAuthXxxTokens → {xxx, xxxTokens}
- `logout` — authService.logout(refreshXxxToken) → 204
- `refreshXxxTokens` — authService.refreshAuth(refreshXxxToken)
- `forgotPassword` — generateResetPasswordXxxToken + sendResetPasswordEmail → 204
- `resetPassword` — authService.resetPassword(token, password) → 204
- `sendVerificationEmail` — generateVerifyEmailXxxToken + sendVerificationEmail → 204
- `verifyEmail` — authService.verifyEmail(token) → 204

#### SERVICES (≈4, mais 18 fonctions)

**8. Entity CRUD service (6 fonctions)**
Source : `src/services/user.service.js`
- `createXxx(body)` — email taken check → Xxx.create
- `queryXxxs(filter, options)` — Xxx.paginate
- `getXxxById(id)` — Xxx.findById
- `getXxxByEmail(email)` — Xxx.findOne({email})
- `updateXxxById(xxxId, body)` — get + email taken check + Object.assign + save
- `deleteXxxById(xxxId)` — get + remove

**9. Auth service (5 fonctions)**
Source : `src/services/auth.service.js`
- `loginWithEmailAndPassword(email, password)` — getUserByEmail + isPasswordMatch → UNAUTHORIZED
- `logout(refreshXxxToken)` — find token + remove
- `refreshAuth(refreshXxxToken)` — verifyToken + getUser + remove old + generateAuth
- `resetPassword(token, password)` — verifyToken + updateXxxById + deleteMany tokens
- `verifyEmail(token)` — verifyToken + getUser + deleteMany + updateXxxById({isEmailVerified: true})

**10. Token service (6 fonctions)**
Source : `src/services/token.service.js`
- `generateXxxToken(xxxId, expires, type, secret)` — jwt.sign({sub, iat, exp, type})
- `saveXxxToken(token, xxxId, expires, type, blacklisted)` — XxxToken.create
- `verifyXxxToken(token, type)` — jwt.verify + findOne({token, type, xxx_ref, blacklisted: false})
- `generateAuthXxxTokens(xxx)` — access (30min) + refresh (30d) + saveToken
- `generateResetPasswordXxxToken(email)` — getUserByEmail + generate + save
- `generateVerifyEmailXxxToken(xxx)` — generate + save

**11. Email service (3 fonctions)**
Source : `src/services/email.service.js`
- `sendEmail(to, subject, text)` — nodemailer transport.sendMail
- `sendResetPasswordEmail(to, token)` — template reset URL + sendEmail
- `sendVerificationEmail(to, token)` — template verify URL + sendEmail

#### MIDDLEWARES (≈3)

**12. Auth middleware — Passport JWT + RBAC**
Source : `src/middlewares/auth.js`
- HOF : `auth(...requiredRights)` returns async middleware
- `verifyCallback` : passport.authenticate('jwt', {session: false}), checks requiredRights via roleRights Map
- Self-ownership bypass : `req.params.xxxId !== xxx.id`

**13. Validate middleware — Joi**
Source : `src/middlewares/validate.js`
- HOF : `validate(schema)` returns middleware
- pick(schema, ['params', 'query', 'body'])
- Joi.compile + prefs({abortEarly: false})
- Error → ApiError(BAD_REQUEST, joined message)

**14. Error middleware — errorConverter + errorHandler**
Source : `src/middlewares/error.js`
- `errorConverter` : non-ApiError → ApiError (mongoose.Error → BAD_REQUEST)
- `errorHandler` : production (hide non-operational), dev (include stack), send JSON

#### UTILS (≈2)

**15. catchAsync — async middleware wrapper**
Source : `src/utils/catchAsync.js`
- `(fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next)`

**16. ApiError — custom error class**
Source : `src/utils/ApiError.js`
- Extends Error, adds statusCode, isOperational, stack

#### VALIDATIONS (≈2)

**17. Entity CRUD validation — Joi schemas**
Source : `src/validations/user.validation.js`
- createXxx : body(email.required, password.custom, name.required, role.valid)
- getXxxs : query(name, role, sortBy, limit, page)
- getXxx : params(xxxId.custom(objectId))
- updateXxx : params(xxxId) + body(email, password, name).min(1)
- deleteXxx : params(xxxId)

**18. Auth validation — Joi schemas**
Source : `src/validations/auth.validation.js`
- register : body(email, password, name)
- login : body(email, password)
- logout : body(refreshXxxToken)
- refreshXxxTokens : body(refreshXxxToken)
- forgotPassword : body(email)
- resetPassword : query(xxxToken) + body(password)
- verifyEmail : query(xxxToken)

#### CONFIG (≈2)

**19. Roles config — RBAC mapping**
Source : `src/config/roles.js`
- allRoles : { xxx: [], admin: ['getXxxs', 'manageXxxs'] }
- roles : Object.keys
- roleRights : new Map(Object.entries)

**20. Passport JWT strategy config**
Source : `src/config/passport.js`
- JwtStrategy with Bearer token extraction
- secretOrKey from config
- Verify callback : find xxx by sub claim

#### ROUTES (≈2)

**21. Entity CRUD routes — auth + validate middleware chain**
Source : `src/routes/v1/user.route.js`
- POST / → auth('manageXxxs'), validate(createXxx), createXxx
- GET / → auth('getXxxs'), validate(getXxxs), getXxxs
- GET /:xxxId → auth('getXxxs'), validate(getXxx), getXxx
- PATCH /:xxxId → auth('manageXxxs'), validate(updateXxx), updateXxx
- DELETE /:xxxId → auth('manageXxxs'), validate(deleteXxx), deleteXxx

**22. Auth routes**
Source : `src/routes/v1/auth.route.js`
- POST /register, /login, /logout, /refresh-xxxTokens, /forgot-password, /reset-password, /send-verification-email, /verify-email

---

### AUDIT QUERIES (avec filtre language obligatoire)

```python
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
```

**IMPORTANT — Dans `run_audit_queries()` utilise `query_kb()` de kb_utils.py :**
```python
from kb_utils import query_kb

def run_audit_queries(client):
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(
            client=client,
            collection=COLLECTION,
            query_vector=vec,
            language=LANGUAGE,   # ← FILTRE OBLIGATOIRE
            limit=1,
        )
        # ... même logique que JS A pour le reste
```

Ce fix empêche la contamination cross-langage (un pattern Python qui remonte sur une query JS). C'est le fix du commit `c810d71`.

---

### STRUCTURE SCRIPT

Copie exacte de `ingest_node_express_mongoose.py` :
1. Constantes en haut
2. `PATTERNS: list[dict]` avec tout le code normalisé (clés : normalized_code, function, feature_type, file_role, file_path)
3. `AUDIT_QUERIES`
4. `clone_repo()` → `build_payloads()` → `index_patterns()` → `run_audit_queries()` (avec `query_kb()`) → `audit_normalization()` → `cleanup()` → `main()`
5. `check_charte_violations()` avec `language="javascript"`

---

### EXÉCUTION

```bash
cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
.venv/bin/python3 ingest_node_express_boilerplate.py
```

**Si PASS :** commit + push
```bash
git add ingest_node_express_boilerplate.py
git commit -m "feat: ingest node-express-boilerplate — JS B KB patterns"
git push
```

**Si violations :** corrige et relance. Itère jusqu'à PASS.

---

### CHECKLIST AVANT VALIDATION

- [ ] Tous les patterns extraits par FONCTION (pas de sampling arbitraire)
- [ ] U-5 : User→Xxx, Token→XxxToken, userId→xxxId partout dans le code normalisé
- [ ] J-1 : aucun `var`, que des `const`/`let`
- [ ] J-3 : aucun `console.log()`
- [ ] `query_kb()` utilisé dans les audit queries (pas `client.query_points()` direct)
- [ ] `language="javascript"` passé partout (check_charte_violations + query_kb)
- [ ] Scores audit entre 0.0 et 1.0
- [ ] Aucune violation Charte dans l'audit post-indexation
- [ ] Pas de contamination cross-langage dans les résultats

---

### SOURCE CODE DU REPO (pour référence)

#### src/models/user.model.js
```javascript
const mongoose = require('mongoose');
const validator = require('validator');
const bcrypt = require('bcryptjs');
const { toJSON, paginate } = require('./plugins');
const { roles } = require('../config/roles');

const userSchema = mongoose.Schema(
  {
    name: { type: String, required: true, trim: true },
    email: {
      type: String, required: true, unique: true, trim: true, lowercase: true,
      validate(value) {
        if (!validator.isEmail(value)) throw new Error('Invalid email');
      },
    },
    password: {
      type: String, required: true, trim: true, minlength: 8,
      validate(value) {
        if (!value.match(/\d/) || !value.match(/[a-zA-Z]/))
          throw new Error('Password must contain at least one letter and one number');
      },
      private: true,
    },
    role: { type: String, enum: roles, default: 'user' },
    isEmailVerified: { type: Boolean, default: false },
  },
  { timestamps: true }
);

userSchema.plugin(toJSON);
userSchema.plugin(paginate);

userSchema.statics.isEmailTaken = async function (email, excludeUserId) {
  const user = await this.findOne({ email, _id: { $ne: excludeUserId } });
  return !!user;
};

userSchema.methods.isPasswordMatch = async function (password) {
  const user = this;
  return bcrypt.compare(password, user.password);
};

userSchema.pre('save', async function (next) {
  const user = this;
  if (user.isModified('password')) {
    user.password = await bcrypt.hash(user.password, 8);
  }
  next();
});

const User = mongoose.model('User', userSchema);
module.exports = User;
```

#### src/models/token.model.js
```javascript
const mongoose = require('mongoose');
const { toJSON } = require('./plugins');
const { tokenTypes } = require('../config/tokens');

const tokenSchema = mongoose.Schema(
  {
    token: { type: String, required: true, index: true },
    user: { type: mongoose.SchemaTypes.ObjectId, ref: 'User', required: true },
    type: { type: String, enum: [tokenTypes.REFRESH, tokenTypes.RESET_PASSWORD, tokenTypes.VERIFY_EMAIL], required: true },
    expires: { type: Date, required: true },
    blacklisted: { type: Boolean, default: false },
  },
  { timestamps: true }
);

tokenSchema.plugin(toJSON);
const Token = mongoose.model('Token', tokenSchema);
module.exports = Token;
```

#### src/models/plugins/toJSON.plugin.js
```javascript
const deleteAtPath = (obj, path, index) => {
  if (index === path.length - 1) { delete obj[path[index]]; return; }
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
        if (schema.paths[path].options && schema.paths[path].options.private) {
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
```

#### src/models/plugins/paginate.plugin.js
```javascript
const paginate = (schema) => {
  schema.statics.paginate = async function (filter, options) {
    let sort = '';
    if (options.sortBy) {
      const sortingCriteria = [];
      options.sortBy.split(',').forEach((sortOption) => {
        const [key, order] = sortOption.split(':');
        sortingCriteria.push((order === 'desc' ? '-' : '') + key);
      });
      sort = sortingCriteria.join(' ');
    } else {
      sort = 'createdAt';
    }

    const limit = options.limit && parseInt(options.limit, 10) > 0 ? parseInt(options.limit, 10) : 10;
    const page = options.page && parseInt(options.page, 10) > 0 ? parseInt(options.page, 10) : 1;
    const skip = (page - 1) * limit;

    const countPromise = this.countDocuments(filter).exec();
    let docsPromise = this.find(filter).sort(sort).skip(skip).limit(limit);

    if (options.populate) {
      options.populate.split(',').forEach((populateOption) => {
        docsPromise = docsPromise.populate(
          populateOption.split('.').reverse().reduce((a, b) => ({ path: b, populate: a }))
        );
      });
    }

    docsPromise = docsPromise.exec();

    return Promise.all([countPromise, docsPromise]).then((values) => {
      const [totalResults, results] = values;
      const totalPages = Math.ceil(totalResults / limit);
      return Promise.resolve({ results, page, limit, totalPages, totalResults });
    });
  };
};

module.exports = paginate;
```

#### src/controllers/user.controller.js
```javascript
const httpStatus = require('http-status');
const pick = require('../utils/pick');
const ApiError = require('../utils/ApiError');
const catchAsync = require('../utils/catchAsync');
const { userService } = require('../services');

const createUser = catchAsync(async (req, res) => {
  const user = await userService.createUser(req.body);
  res.status(httpStatus.CREATED).send(user);
});

const getUsers = catchAsync(async (req, res) => {
  const filter = pick(req.query, ['name', 'role']);
  const options = pick(req.query, ['sortBy', 'limit', 'page']);
  const result = await userService.queryUsers(filter, options);
  res.send(result);
});

const getUser = catchAsync(async (req, res) => {
  const user = await userService.getUserById(req.params.userId);
  if (!user) throw new ApiError(httpStatus.NOT_FOUND, 'User not found');
  res.send(user);
});

const updateUser = catchAsync(async (req, res) => {
  const user = await userService.updateUserById(req.params.userId, req.body);
  res.send(user);
});

const deleteUser = catchAsync(async (req, res) => {
  await userService.deleteUserById(req.params.userId);
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = { createUser, getUsers, getUser, updateUser, deleteUser };
```

#### src/controllers/auth.controller.js
```javascript
const httpStatus = require('http-status');
const catchAsync = require('../utils/catchAsync');
const { authService, userService, tokenService, emailService } = require('../services');

const register = catchAsync(async (req, res) => {
  const user = await userService.createUser(req.body);
  const tokens = await tokenService.generateAuthTokens(user);
  res.status(httpStatus.CREATED).send({ user, tokens });
});

const login = catchAsync(async (req, res) => {
  const { email, password } = req.body;
  const user = await authService.loginUserWithEmailAndPassword(email, password);
  const tokens = await tokenService.generateAuthTokens(user);
  res.send({ user, tokens });
});

const logout = catchAsync(async (req, res) => {
  await authService.logout(req.body.refreshToken);
  res.status(httpStatus.NO_CONTENT).send();
});

const refreshTokens = catchAsync(async (req, res) => {
  const tokens = await authService.refreshAuth(req.body.refreshToken);
  res.send({ ...tokens });
});

const forgotPassword = catchAsync(async (req, res) => {
  const resetPasswordToken = await tokenService.generateResetPasswordToken(req.body.email);
  await emailService.sendResetPasswordEmail(req.body.email, resetPasswordToken);
  res.status(httpStatus.NO_CONTENT).send();
});

const resetPassword = catchAsync(async (req, res) => {
  await authService.resetPassword(req.query.token, req.body.password);
  res.status(httpStatus.NO_CONTENT).send();
});

const sendVerificationEmail = catchAsync(async (req, res) => {
  const verifyEmailToken = await tokenService.generateVerifyEmailToken(req.user);
  await emailService.sendVerificationEmail(req.user.email, verifyEmailToken);
  res.status(httpStatus.NO_CONTENT).send();
});

const verifyEmail = catchAsync(async (req, res) => {
  await authService.verifyEmail(req.query.token);
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = { register, login, logout, refreshTokens, forgotPassword, resetPassword, sendVerificationEmail, verifyEmail };
```

#### src/services/user.service.js
```javascript
const httpStatus = require('http-status');
const { User } = require('../models');
const ApiError = require('../utils/ApiError');

const createUser = async (userBody) => {
  if (await User.isEmailTaken(userBody.email))
    throw new ApiError(httpStatus.BAD_REQUEST, 'Email already taken');
  return User.create(userBody);
};

const queryUsers = async (filter, options) => {
  const users = await User.paginate(filter, options);
  return users;
};

const getUserById = async (id) => User.findById(id);

const getUserByEmail = async (email) => User.findOne({ email });

const updateUserById = async (userId, updateBody) => {
  const user = await getUserById(userId);
  if (!user) throw new ApiError(httpStatus.NOT_FOUND, 'User not found');
  if (updateBody.email && (await User.isEmailTaken(updateBody.email, userId)))
    throw new ApiError(httpStatus.BAD_REQUEST, 'Email already taken');
  Object.assign(user, updateBody);
  await user.save();
  return user;
};

const deleteUserById = async (userId) => {
  const user = await getUserById(userId);
  if (!user) throw new ApiError(httpStatus.NOT_FOUND, 'User not found');
  await user.remove();
  return user;
};

module.exports = { createUser, queryUsers, getUserById, getUserByEmail, updateUserById, deleteUserById };
```

#### src/services/auth.service.js
```javascript
const httpStatus = require('http-status');
const tokenService = require('./token.service');
const userService = require('./user.service');
const Token = require('../models/token.model');
const ApiError = require('../utils/ApiError');
const { tokenTypes } = require('../config/tokens');

const loginUserWithEmailAndPassword = async (email, password) => {
  const user = await userService.getUserByEmail(email);
  if (!user || !(await user.isPasswordMatch(password)))
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Incorrect email or password');
  return user;
};

const logout = async (refreshToken) => {
  const refreshTokenDoc = await Token.findOne({ token: refreshToken, type: tokenTypes.REFRESH, blacklisted: false });
  if (!refreshTokenDoc) throw new ApiError(httpStatus.NOT_FOUND, 'Not found');
  await refreshTokenDoc.remove();
};

const refreshAuth = async (refreshToken) => {
  try {
    const refreshTokenDoc = await tokenService.verifyToken(refreshToken, tokenTypes.REFRESH);
    const user = await userService.getUserById(refreshTokenDoc.user);
    if (!user) throw new Error();
    await refreshTokenDoc.remove();
    return tokenService.generateAuthTokens(user);
  } catch (error) {
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Please authenticate');
  }
};

const resetPassword = async (resetPasswordToken, newPassword) => {
  try {
    const resetPasswordTokenDoc = await tokenService.verifyToken(resetPasswordToken, tokenTypes.RESET_PASSWORD);
    const user = await userService.getUserById(resetPasswordTokenDoc.user);
    if (!user) throw new Error();
    await userService.updateUserById(user.id, { password: newPassword });
    await Token.deleteMany({ user: user.id, type: tokenTypes.RESET_PASSWORD });
  } catch (error) {
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Password reset failed');
  }
};

const verifyEmail = async (verifyEmailToken) => {
  try {
    const verifyEmailTokenDoc = await tokenService.verifyToken(verifyEmailToken, tokenTypes.VERIFY_EMAIL);
    const user = await userService.getUserById(verifyEmailTokenDoc.user);
    if (!user) throw new Error();
    await Token.deleteMany({ user: user.id, type: tokenTypes.VERIFY_EMAIL });
    await userService.updateUserById(user.id, { isEmailVerified: true });
  } catch (error) {
    throw new ApiError(httpStatus.UNAUTHORIZED, 'Email verification failed');
  }
};

module.exports = { loginUserWithEmailAndPassword, logout, refreshAuth, resetPassword, verifyEmail };
```

#### src/services/token.service.js
```javascript
const jwt = require('jsonwebtoken');
const moment = require('moment');
const httpStatus = require('http-status');
const config = require('../config/config');
const userService = require('./user.service');
const { Token } = require('../models');
const ApiError = require('../utils/ApiError');
const { tokenTypes } = require('../config/tokens');

const generateToken = (userId, expires, type, secret = config.jwt.secret) => {
  const payload = { sub: userId, iat: moment().unix(), exp: expires.unix(), type };
  return jwt.sign(payload, secret);
};

const saveToken = async (token, userId, expires, type, blacklisted = false) => {
  const tokenDoc = await Token.create({ token, user: userId, expires: expires.toDate(), type, blacklisted });
  return tokenDoc;
};

const verifyToken = async (token, type) => {
  const payload = jwt.verify(token, config.jwt.secret);
  const tokenDoc = await Token.findOne({ token, type, user: payload.sub, blacklisted: false });
  if (!tokenDoc) throw new Error('Token not found');
  return tokenDoc;
};

const generateAuthTokens = async (user) => {
  const accessTokenExpires = moment().add(config.jwt.accessExpirationMinutes, 'minutes');
  const accessToken = generateToken(user.id, accessTokenExpires, tokenTypes.ACCESS);
  const refreshTokenExpires = moment().add(config.jwt.refreshExpirationDays, 'days');
  const refreshToken = generateToken(user.id, refreshTokenExpires, tokenTypes.REFRESH);
  await saveToken(refreshToken, user.id, refreshTokenExpires, tokenTypes.REFRESH);
  return {
    access: { token: accessToken, expires: accessTokenExpires.toDate() },
    refresh: { token: refreshToken, expires: refreshTokenExpires.toDate() },
  };
};

const generateResetPasswordToken = async (email) => {
  const user = await userService.getUserByEmail(email);
  if (!user) throw new ApiError(httpStatus.NOT_FOUND, 'No users found with this email');
  const expires = moment().add(config.jwt.resetPasswordExpirationMinutes, 'minutes');
  const resetPasswordToken = generateToken(user.id, expires, tokenTypes.RESET_PASSWORD);
  await saveToken(resetPasswordToken, user.id, expires, tokenTypes.RESET_PASSWORD);
  return resetPasswordToken;
};

const generateVerifyEmailToken = async (user) => {
  const expires = moment().add(config.jwt.verifyEmailExpirationMinutes, 'minutes');
  const verifyEmailToken = generateToken(user.id, expires, tokenTypes.VERIFY_EMAIL);
  await saveToken(verifyEmailToken, user.id, expires, tokenTypes.VERIFY_EMAIL);
  return verifyEmailToken;
};

module.exports = { generateToken, saveToken, verifyToken, generateAuthTokens, generateResetPasswordToken, generateVerifyEmailToken };
```

#### src/services/email.service.js
```javascript
const nodemailer = require('nodemailer');
const config = require('../config/config');
const logger = require('../config/logger');

const transport = nodemailer.createTransport(config.email.smtp);

const sendEmail = async (to, subject, text) => {
  const msg = { from: config.email.from, to, subject, text };
  await transport.sendMail(msg);
};

const sendResetPasswordEmail = async (to, token) => {
  const subject = 'Reset password';
  const resetPasswordUrl = `http://link-to-app/reset-password?token=${token}`;
  const text = `Dear user,\nTo reset your password, click on this link: ${resetPasswordUrl}\nIf you did not request any password resets, then ignore this email.`;
  await sendEmail(to, subject, text);
};

const sendVerificationEmail = async (to, token) => {
  const subject = 'Email Verification';
  const verificationEmailUrl = `http://link-to-app/verify-email?token=${token}`;
  const text = `Dear user,\nTo verify your email, click on this link: ${verificationEmailUrl}\nIf you did not create an account, then ignore this email.`;
  await sendEmail(to, subject, text);
};

module.exports = { transport, sendEmail, sendResetPasswordEmail, sendVerificationEmail };
```

#### src/middlewares/auth.js
```javascript
const passport = require('passport');
const httpStatus = require('http-status');
const ApiError = require('../utils/ApiError');
const { roleRights } = require('../config/roles');

const verifyCallback = (req, resolve, reject, requiredRights) => async (err, user, info) => {
  if (err || info || !user) return reject(new ApiError(httpStatus.UNAUTHORIZED, 'Please authenticate'));
  req.user = user;
  if (requiredRights.length) {
    const userRights = roleRights.get(user.role);
    const hasRequiredRights = requiredRights.every((requiredRight) => userRights.includes(requiredRight));
    if (!hasRequiredRights && req.params.userId !== user.id)
      return reject(new ApiError(httpStatus.FORBIDDEN, 'Forbidden'));
  }
  resolve();
};

const auth = (...requiredRights) => async (req, res, next) => {
  return new Promise((resolve, reject) => {
    passport.authenticate('jwt', { session: false }, verifyCallback(req, resolve, reject, requiredRights))(req, res, next);
  }).then(() => next()).catch((err) => next(err));
};

module.exports = auth;
```

#### src/middlewares/validate.js
```javascript
const Joi = require('joi');
const httpStatus = require('http-status');
const pick = require('../utils/pick');
const ApiError = require('../utils/ApiError');

const validate = (schema) => (req, res, next) => {
  const validSchema = pick(schema, ['params', 'query', 'body']);
  const object = pick(req, Object.keys(validSchema));
  const { value, error } = Joi.compile(validSchema)
    .prefs({ errors: { label: 'key' }, abortEarly: false })
    .validate(object);
  if (error) {
    const errorMessage = error.details.map((details) => details.message).join(', ');
    return next(new ApiError(httpStatus.BAD_REQUEST, errorMessage));
  }
  Object.assign(req, value);
  return next();
};

module.exports = validate;
```

#### src/middlewares/error.js
```javascript
const mongoose = require('mongoose');
const httpStatus = require('http-status');
const config = require('../config/config');
const logger = require('../config/logger');
const ApiError = require('../utils/ApiError');

const errorConverter = (err, req, res, next) => {
  let error = err;
  if (!(error instanceof ApiError)) {
    const statusCode = error.statusCode || error instanceof mongoose.Error ? httpStatus.BAD_REQUEST : httpStatus.INTERNAL_SERVER_ERROR;
    const message = error.message || httpStatus[statusCode];
    error = new ApiError(statusCode, message, false, err.stack);
  }
  next(error);
};

const errorHandler = (err, req, res, next) => {
  let { statusCode, message } = err;
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
  if (config.env === 'development') logger.error(err);
  res.status(statusCode).send(response);
};

module.exports = { errorConverter, errorHandler };
```

#### src/utils/catchAsync.js
```javascript
const catchAsync = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch((err) => next(err));
};

module.exports = catchAsync;
```

#### src/utils/ApiError.js
```javascript
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
```

#### src/validations/user.validation.js
```javascript
const Joi = require('joi');
const { password, objectId } = require('./custom.validation');

const createUser = {
  body: Joi.object().keys({
    email: Joi.string().required().email(),
    password: Joi.string().required().custom(password),
    name: Joi.string().required(),
    role: Joi.string().required().valid('user', 'admin'),
  }),
};

const getUsers = {
  query: Joi.object().keys({
    name: Joi.string(),
    role: Joi.string(),
    sortBy: Joi.string(),
    limit: Joi.number().integer(),
    page: Joi.number().integer(),
  }),
};

const getUser = {
  params: Joi.object().keys({ userId: Joi.string().custom(objectId) }),
};

const updateUser = {
  params: Joi.object().keys({ userId: Joi.required().custom(objectId) }),
  body: Joi.object().keys({
    email: Joi.string().email(),
    password: Joi.string().custom(password),
    name: Joi.string(),
  }).min(1),
};

const deleteUser = {
  params: Joi.object().keys({ userId: Joi.string().custom(objectId) }),
};

module.exports = { createUser, getUsers, getUser, updateUser, deleteUser };
```

#### src/config/roles.js
```javascript
const allRoles = {
  user: [],
  admin: ['getUsers', 'manageUsers'],
};

const roles = Object.keys(allRoles);
const roleRights = new Map(Object.entries(allRoles));

module.exports = { roles, roleRights };
```

#### src/routes/v1/user.route.js
```javascript
const express = require('express');
const auth = require('../../middlewares/auth');
const validate = require('../../middlewares/validate');
const userValidation = require('../../validations/user.validation');
const userController = require('../../controllers/user.controller');

const router = express.Router();

router.route('/')
  .post(auth('manageUsers'), validate(userValidation.createUser), userController.createUser)
  .get(auth('getUsers'), validate(userValidation.getUsers), userController.getUsers);

router.route('/:userId')
  .get(auth('getUsers'), validate(userValidation.getUser), userController.getUser)
  .patch(auth('manageUsers'), validate(userValidation.updateUser), userController.updateUser)
  .delete(auth('manageUsers'), validate(userValidation.deleteUser), userController.deleteUser);

module.exports = router;
```

#### src/routes/v1/auth.route.js
```javascript
const express = require('express');
const validate = require('../../middlewares/validate');
const authValidation = require('../../validations/auth.validation');
const authController = require('../../controllers/auth.controller');
const auth = require('../../middlewares/auth');

const router = express.Router();

router.post('/register', validate(authValidation.register), authController.register);
router.post('/login', validate(authValidation.login), authController.login);
router.post('/logout', validate(authValidation.logout), authController.logout);
router.post('/refresh-tokens', validate(authValidation.refreshTokens), authController.refreshTokens);
router.post('/forgot-password', validate(authValidation.forgotPassword), authController.forgotPassword);
router.post('/reset-password', validate(authValidation.resetPassword), authController.resetPassword);
router.post('/send-verification-email', auth(), authController.sendVerificationEmail);
router.post('/verify-email', validate(authValidation.verifyEmail), authController.verifyEmail);

module.exports = router;
```
