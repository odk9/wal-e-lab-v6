"""
ingest_node_express_realworld.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns architecturaux de gothinkster/node-express-realworld-example-app
dans la KB Qdrant V6.

SCOPE: TypeScript Express API — RealWorld (Conduit) spec avec Prisma ORM + JWT.

Usage:
    .venv/bin/python3 ingest_node_express_realworld.py
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
REPO_URL = "https://github.com/gothinkster/node-express-realworld-example-app.git"
REPO_NAME = "gothinkster/node-express-realworld-example-app"
REPO_LOCAL = "/tmp/node_express_realworld"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+prisma+jwt+typescript"
CHARTE_VERSION = "1.0"
TAG = "gothinkster/node-express-realworld-example-app"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/gothinkster/node-express-realworld-example-app"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Article→XxxContent, User→Xxx, Comment→XxxComment, Tag→XxxLabel
# T-1: no :any. T-2: no var. T-3: no console.log/console.info.
# Callback params: item→el

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS (Prisma)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Prisma schema — relational model ─────────────────────────────────
    {
        "normalized_code": """\
model Xxx {
  id       Int      @id @default(autoincrement())
  email    String   @unique
  password String
  bio      String?
  image    String?

  xxxs          XxxContent[]
  favorites     XxxContent[]  @relation("XxxFavorites")
  followedBy    Xxx[]         @relation("XxxFollows")
  following     Xxx[]         @relation("XxxFollows")
  xxxComments   XxxComment[]
}

model XxxContent {
  id          Int      @id @default(autoincrement())
  slug        String   @unique
  title       String
  description String
  body        String
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  author      Xxx       @relation(fields: [authorId], references: [id])
  authorId    Int
  xxxLabels   XxxLabel[]
  favoritedBy Xxx[]     @relation("XxxFavorites")
  xxxComments XxxComment[]
}

model XxxComment {
  id        Int      @id @default(autoincrement())
  body      String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  author    Xxx        @relation(fields: [authorId], references: [id])
  authorId  Int
  content   XxxContent @relation(fields: [contentId], references: [id], onDelete: Cascade)
  contentId Int
}

model XxxLabel {
  id       Int          @id @default(autoincrement())
  name     String       @unique
  xxxs     XxxContent[]
}
""",
        "function": "prisma_schema_relational_model",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/prisma/schema.prisma",
    },

    # ── 2. Prisma client singleton — global dev guard ───────────────────────
    {
        "normalized_code": """\
import { PrismaClient } from '@prisma/client';

declare const global: { prisma?: PrismaClient } & typeof globalThis;

const prisma = global.prisma || new PrismaClient();

if (process.env.NODE_ENV === 'development') {
  global.prisma = prisma;
}

export default prisma;
""",
        "function": "prisma_client_singleton_global",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/prisma/prisma-client.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE / AUTH
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 3. JWT auth middleware — required + optional ─────────────────────────
    {
        "normalized_code": """\
import { Request } from 'express';
import { expressjwt } from 'express-jwt';

const getTokenFromHeaders = (req: Request): string | null => {
  if (
    req.headers.authorization &&
    (req.headers.authorization.split(' ')[0] === 'Token' ||
     req.headers.authorization.split(' ')[0] === 'Bearer')
  ) {
    return req.headers.authorization.split(' ')[1];
  }
  return null;
};

const auth = {
  required: expressjwt({
    secret: process.env.JWT_SECRET || 'superSecret',
    getToken: getTokenFromHeaders,
    algorithms: ['HS256'],
  }),
  optional: expressjwt({
    secret: process.env.JWT_SECRET || 'superSecret',
    credentialsRequired: false,
    getToken: getTokenFromHeaders,
    algorithms: ['HS256'],
  }),
};

export default auth;
""",
        "function": "jwt_auth_middleware_required_optional",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/app/routes/auth/auth.ts",
    },

    # ── 4. JWT token generation ─────────────────────────────────────────────
    {
        "normalized_code": """\
import jwt from 'jsonwebtoken';

const generateToken = (id: number): string =>
  jwt.sign({ sub: id }, process.env.JWT_SECRET || 'superSecret', {
    expiresIn: '60d',
  });

export default generateToken;
""",
        "function": "jwt_token_generation",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/app/routes/auth/token.utils.ts",
    },

    # ── 5. Custom HTTP exception class ──────────────────────────────────────
    {
        "normalized_code": """\
class HttpException extends Error {
  errorCode: number;

  constructor(errorCode: number, details: string | Record<string, string[]>) {
    super(typeof details === 'string' ? details : JSON.stringify(details));
    this.errorCode = errorCode;
  }
}

export default HttpException;
""",
        "function": "http_exception_custom_error_class",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/app/models/http-exception.model.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SERVICES — CRUD
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 6. Create with uniqueness validation + bcrypt ───────────────────────
    {
        "normalized_code": """\
import bcrypt from 'bcryptjs';
import prisma from '../../../prisma/prisma-client';
import HttpException from '../../models/http-exception.model';
import generateToken from './token.utils';

interface RegisterInput {
  email?: string;
  password?: string;
  name?: string;
  image?: string;
  bio?: string;
}

const checkUniqueness = async (
  email: string,
  name: string,
): Promise<void> => {
  const existing = await prisma.xxx.findFirst({
    where: { OR: [{ email }, { name }] },
  });
  if (existing) {
    const errors: Record<string, string[]> = {};
    if (existing.email === email) {
      errors.email = ['has already been taken'];
    }
    if (existing.name === name) {
      errors.name = ['has already been taken'];
    }
    throw new HttpException(422, { errors });
  }
};

const createXxx = async (
  input: RegisterInput,
): Promise<{ name: string; email: string; token: string; bio: string | null; image: string | null }> => {
  const { email, name, password } = input;
  if (!email) throw new HttpException(422, { errors: { email: ["can't be blank"] } });
  if (!name) throw new HttpException(422, { errors: { name: ["can't be blank"] } });
  if (!password) throw new HttpException(422, { errors: { password: ["can't be blank"] } });

  await checkUniqueness(email, name);
  const hashedPassword = await bcrypt.hash(password, 10);

  const xxx = await prisma.xxx.create({
    data: {
      email,
      name,
      password: hashedPassword,
      ...(input.image ? { image: input.image } : {}),
      ...(input.bio ? { bio: input.bio } : {}),
    },
  });

  return {
    name: xxx.name,
    email: xxx.email,
    token: generateToken(xxx.id),
    bio: xxx.bio,
    image: xxx.image,
  };
};

export { createXxx, checkUniqueness };
""",
        "function": "service_create_with_uniqueness_validation",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/auth/auth.service.ts",
    },

    # ── 7. Login — bcrypt compare + JWT token ───────────────────────────────
    {
        "normalized_code": """\
import bcrypt from 'bcryptjs';
import prisma from '../../../prisma/prisma-client';
import HttpException from '../../models/http-exception.model';
import generateToken from './token.utils';

interface LoginPayload {
  email?: string;
  password?: string;
}

const login = async (
  payload: LoginPayload,
): Promise<{ name: string; email: string; token: string; bio: string | null; image: string | null }> => {
  const { email, password } = payload;
  if (!email) throw new HttpException(422, { errors: { email: ["can't be blank"] } });
  if (!password) throw new HttpException(422, { errors: { password: ["can't be blank"] } });

  const xxx = await prisma.xxx.findFirst({ where: { email } });
  if (!xxx) throw new HttpException(403, { errors: { credentials: ['invalid'] } });

  const match = await bcrypt.compare(password, xxx.password);
  if (!match) throw new HttpException(403, { errors: { credentials: ['invalid'] } });

  return {
    name: xxx.name,
    email: xxx.email,
    token: generateToken(xxx.id),
    bio: xxx.bio,
    image: xxx.image,
  };
};

export default login;
""",
        "function": "service_login_bcrypt_compare_token",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/auth/auth.service.ts",
    },

    # ── 8. List with Prisma filters + pagination ────────────────────────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';

interface QueryParams {
  offset?: string;
  limit?: string;
  author?: string;
  favorited?: string;
  labelName?: string;
}

const buildFindAllQuery = (
  query: QueryParams,
  id?: number,
): Record<string, unknown>[] => {
  const queries: Record<string, unknown>[] = [];
  const orAuthorQuery = [];

  if (id) {
    orAuthorQuery.push({ author: { id } });
  }
  if (orAuthorQuery.length) {
    queries.push({ OR: orAuthorQuery });
  }
  if (query.labelName) {
    queries.push({
      xxxLabels: { some: { name: query.labelName } },
    });
  }
  if (query.favorited) {
    queries.push({
      favoritedBy: { some: { name: query.favorited } },
    });
  }
  if (query.author) {
    queries.push({ author: { name: query.author } });
  }
  return queries;
};

const getXxxs = async (
  query: QueryParams,
  id?: number,
): Promise<{ xxxs: unknown[]; xxxsCount: number }> => {
  const andQueries = buildFindAllQuery(query, id);
  const xxxsCount = await prisma.xxxContent.count({
    where: { AND: andQueries },
  });

  const xxxs = await prisma.xxxContent.findMany({
    where: { AND: andQueries },
    orderBy: { createdAt: 'desc' },
    skip: query.offset ? parseInt(query.offset, 10) : 0,
    take: query.limit ? parseInt(query.limit, 10) : 10,
    include: {
      author: { include: { followedBy: true } },
      xxxLabels: true,
      favoritedBy: true,
    },
  });

  return { xxxs, xxxsCount };
};

export { getXxxs, buildFindAllQuery };
""",
        "function": "service_crud_with_prisma_filters_pagination",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/article/article.service.ts",
    },

    # ── 9. Create with slug + connectOrCreate labels ────────────────────────
    {
        "normalized_code": """\
import slugify from 'slugify';
import prisma from '../../../prisma/prisma-client';
import HttpException from '../../models/http-exception.model';

interface CreateInput {
  title?: string;
  description?: string;
  body?: string;
  labelList?: string[];
}

const createXxx = async (
  input: CreateInput,
  authorId: number,
): Promise<unknown> => {
  const { title, description, body, labelList } = input;
  if (!title) throw new HttpException(422, { errors: { title: ["can't be blank"] } });
  if (!description) throw new HttpException(422, { errors: { description: ["can't be blank"] } });
  if (!body) throw new HttpException(422, { errors: { body: ["can't be blank"] } });

  const slug = `${slugify(title, { lower: true })}-${authorId}`;

  const existingSlug = await prisma.xxxContent.findUnique({
    where: { slug },
  });
  if (existingSlug) {
    throw new HttpException(422, { errors: { title: ['must be unique'] } });
  }

  const xxx = await prisma.xxxContent.create({
    data: {
      title,
      description,
      body,
      slug,
      author: { connect: { id: authorId } },
      xxxLabels: {
        connectOrCreate: (labelList || []).map((name: string) => ({
          where: { name },
          create: { name },
        })),
      },
    },
    include: {
      author: { include: { followedBy: true } },
      xxxLabels: true,
      favoritedBy: true,
    },
  });

  return xxx;
};

export default createXxx;
""",
        "function": "service_create_with_slug_connect_or_create_labels",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/article/article.service.ts",
    },

    # ── 10. Favorite/unfavorite — many-to-many connect/disconnect ───────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';

const favoriteXxx = async (
  slug: string,
  id: number,
): Promise<unknown> => {
  const xxx = await prisma.xxxContent.update({
    where: { slug },
    data: {
      favoritedBy: { connect: { id } },
    },
    include: {
      author: { include: { followedBy: true } },
      xxxLabels: true,
      favoritedBy: true,
    },
  });
  return xxx;
};

const unfavoriteXxx = async (
  slug: string,
  id: number,
): Promise<unknown> => {
  const xxx = await prisma.xxxContent.update({
    where: { slug },
    data: {
      favoritedBy: { disconnect: { id } },
    },
    include: {
      author: { include: { followedBy: true } },
      xxxLabels: true,
      favoritedBy: true,
    },
  });
  return xxx;
};

export { favoriteXxx, unfavoriteXxx };
""",
        "function": "service_favorite_many_to_many_connect_disconnect",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/article/article.service.ts",
    },

    # ── 11. Follow/unfollow — self-referencing many-to-many ─────────────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';

const followXxx = async (
  name: string,
  followerId: number,
): Promise<{ name: string; bio: string | null; image: string | null; following: boolean }> => {
  const profile = await prisma.xxx.update({
    where: { name },
    data: {
      followedBy: { connect: { id: followerId } },
    },
    include: { followedBy: true },
  });
  return profileMapper(profile, followerId);
};

const unfollowXxx = async (
  name: string,
  followerId: number,
): Promise<{ name: string; bio: string | null; image: string | null; following: boolean }> => {
  const profile = await prisma.xxx.update({
    where: { name },
    data: {
      followedBy: { disconnect: { id: followerId } },
    },
    include: { followedBy: true },
  });
  return profileMapper(profile, followerId);
};

const profileMapper = (
  profile: { name: string; bio: string | null; image: string | null; followedBy: { id: number }[] },
  currentId: number | undefined,
): { name: string; bio: string | null; image: string | null; following: boolean } => ({
  name: profile.name,
  bio: profile.bio,
  image: profile.image,
  following: currentId
    ? profile.followedBy.some((el: { id: number }) => el.id === currentId)
    : false,
});

export { followXxx, unfollowXxx, profileMapper };
""",
        "function": "service_follow_unfollow_self_referencing",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/profile/profile.service.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MAPPERS / SCHEMAS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 12. Mapper — entity response with computed fields ───────────────────
    {
        "normalized_code": """\
interface AuthorData {
  name: string;
  bio: string | null;
  image: string | null;
  followedBy: { id: number }[];
}

interface ContentData {
  slug: string;
  title: string;
  description: string;
  body: string;
  xxxLabels: { name: string }[];
  createdAt: Date;
  updatedAt: Date;
  favoritedBy: { id: number }[];
  author: AuthorData;
}

const authorMapper = (
  author: AuthorData,
  id?: number,
): { name: string; bio: string | null; image: string | null; following: boolean } => ({
  name: author.name,
  bio: author.bio,
  image: author.image,
  following: id
    ? author.followedBy.some((el: { id: number }) => el.id === id)
    : false,
});

const contentMapper = (
  content: ContentData,
  id?: number,
): Record<string, unknown> => ({
  slug: content.slug,
  title: content.title,
  description: content.description,
  body: content.body,
  labelList: content.xxxLabels.map((label: { name: string }) => label.name),
  createdAt: content.createdAt,
  updatedAt: content.updatedAt,
  favorited: content.favoritedBy.some((el: { id: number }) => el.id === id),
  favoritesCount: content.favoritedBy.length,
  author: authorMapper(content.author, id),
});

export { contentMapper, authorMapper };
""",
        "function": "mapper_entity_response_with_computed_fields",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/app/routes/article/article.mapper.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS (Express Router)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. CRUD controller — auth required/optional ────────────────────────
    {
        "normalized_code": """\
import { Router, Request, Response, NextFunction } from 'express';
import auth from '../auth/auth';

const router = Router();

router.get(
  '/',
  auth.optional,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const query = req.query;
      const id = (req as Record<string, unknown>).auth
        ? ((req as Record<string, unknown>).auth as { sub?: number })?.sub
        : undefined;
      const result = await getXxxs(query, id);
      res.json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.get(
  '/feed',
  auth.required,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { offset, limit } = req.query as { offset?: string; limit?: string };
      const id = ((req as Record<string, unknown>).auth as { sub?: number })?.sub;
      const result = await getFeed(offset, limit, id);
      res.json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.post(
  '/',
  auth.required,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = ((req as Record<string, unknown>).auth as { sub?: number })?.sub;
      const result = await createXxx(req.body, id!);
      res.status(201).json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.delete(
  '/:slug',
  auth.required,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = ((req as Record<string, unknown>).auth as { sub?: number })?.sub;
      await deleteXxx(req.params.slug, id!);
      res.status(204).send();
    } catch (error) {
      next(error);
    }
  },
);

export default router;
""",
        "function": "controller_crud_express_router_auth",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/app/routes/article/article.controller.ts",
    },

    # ── 14. Auth controller — register, login, current, update ──────────────
    {
        "normalized_code": """\
import { Router, Request, Response, NextFunction } from 'express';
import auth from './auth';

const router = Router();

router.post(
  '/register',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const result = await createXxx(req.body);
      res.status(201).json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.post(
  '/login',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const result = await login(req.body);
      res.json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.get(
  '/current',
  auth.required,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = ((req as Record<string, unknown>).auth as { sub?: number })?.sub;
      const result = await getCurrentXxx(id!);
      res.json(result);
    } catch (error) {
      next(error);
    }
  },
);

router.put(
  '/current',
  auth.required,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = ((req as Record<string, unknown>).auth as { sub?: number })?.sub;
      const result = await updateXxx(req.body, id!);
      res.json(result);
    } catch (error) {
      next(error);
    }
  },
);

export default router;
""",
        "function": "controller_auth_register_login_update",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/app/routes/auth/auth.controller.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # APP CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. Router aggregation — namespace prefix ───────────────────────────
    {
        "normalized_code": """\
import { Router } from 'express';
import xxxContentController from './article/article.controller';
import authController from './auth/auth.controller';
import profileController from './profile/profile.controller';
import xxxLabelController from './tag/tag.controller';

const api = Router()
  .use(xxxLabelController)
  .use(xxxContentController)
  .use(authController)
  .use(profileController);

export default Router().use('/api', api);
""",
        "function": "router_aggregation_prefix",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/app/routes/routes.ts",
    },

    # ── 16. Express entry point — error handler ─────────────────────────────
    {
        "normalized_code": """\
import cors from 'cors';
import express, { Request, Response, NextFunction } from 'express';
import bodyParser from 'body-parser';
import routes from './app/routes/routes';

const app = express();

app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(routes);
app.use(express.static(__dirname + '/assets'));

app.get('/', (_req: Request, res: Response) => {
  res.json({ status: 'API is running on /api' });
});

app.use(
  (
    err: { name?: string; errorCode?: number } & Error,
    _req: Request,
    res: Response,
    _next: NextFunction,
  ) => {
    if (err.name === 'UnauthorizedError') {
      return res.status(401).json({
        status: 'error',
      });
    }
    if (err.errorCode) {
      return res.status(err.errorCode).json(
        typeof err.message === 'string'
          ? { errors: { body: [err.message] } }
          : JSON.parse(err.message),
      );
    }
    return res.status(500).json({ errors: { body: [err.message] } });
  },
);

const PORT = process.env.PORT || 3000;
app.listen(PORT);
""",
        "function": "express_entry_point_error_handler",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/main.ts",
    },

    # ── 17. Update with conditional fields — spread operator ────────────────
    {
        "normalized_code": """\
import bcrypt from 'bcryptjs';
import prisma from '../../../prisma/prisma-client';
import generateToken from './token.utils';

interface UpdatePayload {
  email?: string;
  name?: string;
  password?: string;
  image?: string;
  bio?: string;
}

const updateXxx = async (
  payload: UpdatePayload,
  id: number,
): Promise<{ name: string; email: string; token: string; bio: string | null; image: string | null }> => {
  const hashedPassword = payload.password
    ? await bcrypt.hash(payload.password, 10)
    : undefined;

  const xxx = await prisma.xxx.update({
    where: { id },
    data: {
      ...(payload.email ? { email: payload.email } : {}),
      ...(payload.name ? { name: payload.name } : {}),
      ...(hashedPassword ? { password: hashedPassword } : {}),
      ...(payload.image ? { image: payload.image } : {}),
      ...(payload.bio ? { bio: payload.bio } : {}),
    },
  });

  return {
    name: xxx.name,
    email: xxx.email,
    token: generateToken(xxx.id),
    bio: xxx.bio,
    image: xxx.image,
  };
};

export default updateXxx;
""",
        "function": "service_update_conditional_fields",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/auth/auth.service.ts",
    },

    # ── 18. Feed — following filter ─────────────────────────────────────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';

const getFeed = async (
  offset?: string,
  limit?: string,
  currentId?: number,
): Promise<{ xxxs: unknown[]; xxxsCount: number }> => {
  const xxxs = await prisma.xxxContent.findMany({
    where: {
      author: {
        followedBy: { some: { id: currentId } },
      },
    },
    orderBy: { createdAt: 'desc' },
    skip: offset ? parseInt(offset, 10) : 0,
    take: limit ? parseInt(limit, 10) : 10,
    include: {
      author: { include: { followedBy: true } },
      xxxLabels: true,
      favoritedBy: true,
    },
  });

  const xxxsCount = await prisma.xxxContent.count({
    where: {
      author: {
        followedBy: { some: { id: currentId } },
      },
    },
  });

  return { xxxs, xxxsCount };
};

export default getFeed;
""",
        "function": "service_feed_following_filter",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/article/article.service.ts",
    },

    # ── 19. Add/delete nested comment — ownership validation ────────────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';
import HttpException from '../../models/http-exception.model';

const addXxxComment = async (
  body: string,
  slug: string,
  authorId: number,
): Promise<unknown> => {
  if (!body) throw new HttpException(422, { errors: { body: ["can't be blank"] } });

  const content = await prisma.xxxContent.findUnique({ where: { slug } });
  if (!content) throw new HttpException(404, { errors: { content: ['not found'] } });

  const xxxComment = await prisma.xxxComment.create({
    data: {
      body,
      content: { connect: { id: content.id } },
      author: { connect: { id: authorId } },
    },
    include: { author: { include: { followedBy: true } } },
  });

  return xxxComment;
};

const deleteXxxComment = async (
  id: number,
  authorId: number,
): Promise<void> => {
  const xxxComment = await prisma.xxxComment.findUnique({
    where: { id },
  });
  if (!xxxComment || xxxComment.authorId !== authorId) {
    throw new HttpException(403, { errors: { content: ['forbidden'] } });
  }
  await prisma.xxxComment.delete({ where: { id } });
};

export { addXxxComment, deleteXxxComment };
""",
        "function": "service_add_delete_nested_comment",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/article/article.service.ts",
    },

    # ── 20. Get labels ordered by count ─────────────────────────────────────
    {
        "normalized_code": """\
import prisma from '../../../prisma/prisma-client';

const getXxxLabels = async (
  currentId?: number,
): Promise<string[]> => {
  const labels = await prisma.xxxLabel.findMany({
    where: {
      xxxs: {
        some: {
          OR: [
            { author: { id: currentId } },
          ],
        },
      },
    },
    orderBy: { xxxs: { _count: 'desc' } },
    take: 10,
    select: { name: true },
  });

  return labels.map((label: { name: string }) => label.name);
};

export default getXxxLabels;
""",
        "function": "service_get_labels_ordered_by_count",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/app/routes/tag/tag.service.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 21. Jest test setup — deep Prisma mock ──────────────────────────────
    {
        "normalized_code": """\
import { PrismaClient } from '@prisma/client';
import { DeepMockProxy, mockDeep, mockReset } from 'jest-mock-extended';
import prisma from '../prisma/prisma-client';

jest.mock('../prisma/prisma-client', () => ({
  __esModule: true,
  default: mockDeep<PrismaClient>(),
}));

const prismaMock = prisma as unknown as DeepMockProxy<PrismaClient>;

beforeEach(() => {
  mockReset(prismaMock);
});

export { prismaMock };
""",
        "function": "test_prisma_mock_deep_jest",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "src/tests/prisma-mock.ts",
    },

    # ── 22. Unit test — service with Prisma mock ────────────────────────────
    {
        "normalized_code": """\
import { prismaMock } from '../prisma-mock';
import { createXxx } from '../../app/routes/auth/auth.service';

describe('Auth Service', () => {
  test('should create new entity', async () => {
    const input = {
      name: 'TestName',
      email: 'test@example.com',
      password: '12345678',
    };
    const mockedResponse = {
      id: 123,
      name: input.name,
      email: input.email,
      password: 'hashed',
      bio: null,
      image: null,
    };

    prismaMock.xxx.findFirst.mockResolvedValue(null);
    prismaMock.xxx.create.mockResolvedValue(mockedResponse);

    await expect(createXxx(input)).resolves.toHaveProperty('token');
  });

  test('should fail with duplicate email', async () => {
    const input = {
      name: 'TestName',
      email: 'test@example.com',
      password: '12345678',
    };
    const existing = {
      id: 1,
      name: 'Other',
      email: input.email,
      password: 'hashed',
      bio: null,
      image: null,
    };

    prismaMock.xxx.findFirst.mockResolvedValue(existing);

    await expect(createXxx(input)).rejects.toThrow();
  });
});
""",
        "function": "test_service_unit_prisma_mock",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "src/tests/services/auth.service.test.ts",
    },

    # ── 23. Express Request type augmentation ───────────────────────────────
    {
        "normalized_code": """\
declare namespace Express {
  export interface Request {
    auth?: {
      sub?: number;
    };
  }
}
""",
        "function": "express_request_type_augmentation",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/app/routes/auth/xxx-request.d.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Prisma schema with relations many-to-many self-referencing",
    "JWT authentication middleware required optional Express",
    "Service create entity uniqueness validation bcrypt password",
    "Prisma query dynamic filters pagination offset limit",
    "Many-to-many favorite connect disconnect Prisma",
    "Follow unfollow self-referencing relation Prisma",
    "Response mapper computed fields favorited count following",
    "Express router controller CRUD auth middleware",
    "Custom HTTP exception error class with error code",
    "Jest test Prisma mock deep arrange act assert",
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
        print(f"\n  6a. Semantic queries (filtered by language={LANGUAGE}):")
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
