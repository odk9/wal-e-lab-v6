#!/usr/bin/env python3
"""
Wirings ingestion script for Wal-e Lab V6 Qdrant KB.
Repo: gothinkster/node-express-realworld-example-app (TypeScript Medium)

MANUAL WIRINGS (NO AST extraction — TypeScript):
1. import_graph: Module dependency tree (app.ts → routes → controllers → services → prisma)
2. flow_pattern: File creation order for a complete Realworld app
3. dependency_chain: Prisma Client singleton pattern with HMR
4. dependency_chain: JWT auth flow (generateToken → header extraction → req.auth)
5. flow_pattern: Prisma relational query patterns (include, nested create, cascade)
6. dependency_chain: Self-relation wiring (Follow: User follows User)
7. flow_pattern: Error handling flow (HttpException → Express middleware → JSON)
8. flow_pattern: Test wiring (jest + supertest, prisma reset, seed, auth headers)

All code examples normalized per Charte (Xxx/xxx/xxxs).
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, Distance, VectorParams
except ImportError as e:
    print(f"Error: qdrant-client not installed. {e}")
    raise

try:
    from embedder import embed_documents_batch, embed_query
except ImportError as e:
    print(f"Error: embedder module not found. {e}")
    raise


# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/gothinkster/node-express-realworld-example-app.git"
REPO_NAME = "gothinkster/node-express-realworld-example-app"
REPO_LOCAL = "/tmp/node-express-realworld-example-app"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+prisma+jwt+typescript"
CHARTE_VERSION = "1.0"
TAG = "wirings/gothinkster/node-express-realworld-example-app"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

TIMESTAMP = int(datetime.now().timestamp())


# ============================================================================
# WIRING DATA (Manual)
# ============================================================================

WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "Module dependency tree: app.ts entry point imports routes, middleware, services depend on Prisma Client singleton. Controllers delegate to services. Services perform CRUD and domain logic. Prisma Client is the data layer.",
        "modules": ["src/app.ts", "src/routes/", "src/controllers/", "src/services/", "src/prisma/prisma-client.ts", "src/middleware/auth.ts", "src/middleware/error-handler.ts"],
        "connections": [
            "app.ts → routes/ (import routers, include in Express app)",
            "routes/ → controllers/ (import controller functions, attach to Express Router)",
            "controllers/ → services/ (import service functions, call from route handlers)",
            "controllers/ → middleware/auth.ts (import auth, use in route-level middleware)",
            "services/ → prisma-client.ts (import Prisma Client, use for queries)",
            "app.ts → middleware/error-handler.ts (attach Express error middleware at end)",
            "app.ts → middleware/auth.ts (attach global auth middleware if needed)",
        ],
        "code_example": """
// src/app.ts
import express, { Express, ErrorRequestHandler } from 'express';
import { xxxRouter } from './routes/xxx.routes';
import { errorHandlerMiddleware } from './middleware/error-handler';
import { optionalAuthMiddleware } from './middleware/auth';

const app: Express = express();

app.use(express.json());
app.use(optionalAuthMiddleware);  // Global optional auth
app.use('/api/v1/xxxs', xxxRouter);
app.use(errorHandlerMiddleware);  // Error handler at end

export default app;

// src/routes/xxx.routes.ts
import { Router } from 'express';
import { requiredAuthMiddleware } from '../middleware/auth';
import { createXxx, getXxx, updateXxx, deleteXxx } from '../controllers/xxx.controller';

const xxxRouter = Router();

xxxRouter.post('/', requiredAuthMiddleware, createXxx);
xxxRouter.get('/:xxxId', getXxx);
xxxRouter.put('/:xxxId', requiredAuthMiddleware, updateXxx);
xxxRouter.delete('/:xxxId', requiredAuthMiddleware, deleteXxx);

export { xxxRouter };

// src/controllers/xxx.controller.ts
import { Request, Response, NextFunction } from 'express';
import { createXxxService } from '../services/xxx.service';

export async function createXxx(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const xxx = await createXxxService(req.body, req.auth?.id);
    res.status(201).json({ xxx });
  } catch (error) {
    next(error);
  }
}

// src/services/xxx.service.ts
import { prisma } from '../prisma/prisma-client';
import { HttpException } from '../models/http-exception';

export async function createXxxService(data: any, userId: number): Promise<any> {
  if (!userId) throw new HttpException(401, 'UNAUTHORIZED', 'Auth required');
  const xxx = await prisma.xxx.create({ data: { ...data, userId } });
  return xxx;
}

// src/prisma/prisma-client.ts
import { PrismaClient } from '@prisma/client';

const globalForPrisma = global as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ||
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query'] : [],
  });

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma;
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "File creation order for a complete Realworld Express app with Prisma, JWT auth, and error handling. Start with schema and client, then auth utilities, then domain services, then routes and controllers, finally app.ts.",
        "modules": [
            "prisma/schema.prisma",
            "src/prisma/prisma-client.ts",
            "src/models/http-exception.ts",
            "src/middleware/auth.ts",
            "src/utils/token.ts",
            "src/services/",
            "src/routes/",
            "src/controllers/",
            "src/app.ts",
        ],
        "connections": [
            "1. prisma/schema.prisma — Define all models (Xxx, User, etc.) with relations",
            "2. prisma/prisma-client.ts — Singleton with global guard for HMR",
            "3. models/http-exception.ts — Custom error class with statusCode, errorCode, details",
            "4. middleware/auth.ts — JWT middleware (required + optional variants)",
            "5. utils/token.ts — generateToken(id, secret, expiry) helper",
            "6. services/ — Domain logic layer (CRUD + uniqueness checks + bcrypt)",
            "7. routes/ — Express routers with route-level middleware",
            "8. controllers/ — Request handlers that call services",
            "9. app.ts — Express app setup, mount routers, error handler",
        ],
        "code_example": """
// 1. prisma/schema.prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

model Xxx {
  id        Int     @id @default(autoincrement())
  title     String
  slug      String  @unique
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

// 2. src/prisma/prisma-client.ts
const globalForPrisma = global as unknown as { prisma: PrismaClient };
export const prisma = globalForPrisma.prisma || new PrismaClient();
if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma;

// 3. src/models/http-exception.ts
export class HttpException extends Error {
  constructor(
    public statusCode: number,
    public errorCode: string,
    public details?: any
  ) {
    super(errorCode);
  }
}

// 4. src/middleware/auth.ts
export const requiredAuthMiddleware = (req: Request, res: Response, next: NextFunction) => {
  const token = extractToken(req.headers.authorization);
  if (!token) throw new HttpException(401, 'UNAUTHORIZED', 'Token required');
  const decoded = verifyToken(token);
  req.auth = decoded;
  next();
};

// 5. src/utils/token.ts
import jwt from 'jsonwebtoken';
export function generateToken(id: number, secret: string, expiresIn: string = '30d'): string {
  return jwt.sign({ id }, secret, { expiresIn });
}

// 6. src/services/xxx.service.ts
export async function createXxxService(data: any): Promise<any> {
  const existing = await prisma.xxx.findUnique({ where: { slug: data.slug } });
  if (existing) throw new HttpException(422, 'VALIDATION', 'Slug already exists');
  return prisma.xxx.create({ data });
}

// 7-9. Routes → Controllers → App (see import_graph wiring for structure)
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Prisma Client singleton pattern with HMR guard. In development, Node.js reloads modules but keeps the global object. Without the guard, each reload creates a new Prisma Client connection, exhausting the connection pool.",
        "modules": ["src/prisma/prisma-client.ts"],
        "connections": [
            "Module load: Check global.prisma exists?",
            "If no: Create new PrismaClient()",
            "If yes (dev mode with HMR): Reuse existing instance",
            "Store on global (dev only) to survive reload",
            "Export single const prisma for all services",
        ],
        "code_example": """
// src/prisma/prisma-client.ts
import { PrismaClient } from '@prisma/client';

const globalForPrisma = global as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ||
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query'] : [],
  });

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}

// Usage in services:
import { prisma } from '../prisma/prisma-client';

export async function getXxxService(xxxId: number): Promise<any> {
  return prisma.xxx.findUnique({ where: { id: xxxId } });
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "JWT auth flow: generateToken produces 'Token <jwt>' or 'Bearer <jwt>'. Client sends in Authorization header. Middleware extracts token, verifies signature, attaches req.auth with decoded payload. Services use req.auth.id for ownership checks.",
        "modules": [
            "src/utils/token.ts",
            "src/middleware/auth.ts",
            "src/controllers/",
            "src/services/",
        ],
        "connections": [
            "1. generateToken(userId, secret) → returns 'Token xxx' string",
            "2. Client stores token in localStorage, sends in 'Authorization: Token xxx' header",
            "3. requiredAuthMiddleware extracts token from header",
            "4. verifyToken(token) → decodes JWT → { id, ... }",
            "5. req.auth = decoded → available in controller",
            "6. Controller passes req.auth.id to service",
            "7. Service uses userId for ownership check: where: { id: xxxId, userId: req.auth.id }",
        ],
        "code_example": """
// src/utils/token.ts
import jwt from 'jsonwebtoken';

export function generateToken(id: number, secret: string = process.env.JWT_SECRET, expiresIn: string = '30d'): string {
  return jwt.sign({ id }, secret, { expiresIn });
}

export function verifyToken(token: string, secret: string = process.env.JWT_SECRET): any {
  try {
    return jwt.verify(token, secret);
  } catch (error) {
    throw new HttpException(401, 'INVALID_TOKEN', 'Token expired or invalid');
  }
}

// src/middleware/auth.ts
import { Request, Response, NextFunction } from 'express';

declare global {
  namespace Express {
    interface Request {
      auth?: { id: number };
    }
  }
}

export function extractToken(authHeader?: string): string | null {
  if (!authHeader) return null;
  const parts = authHeader.split(' ');
  if (parts.length === 2) return parts[1];  // "Token xxx" → xxx
  return null;
}

export const requiredAuthMiddleware = (req: Request, res: Response, next: NextFunction): void => {
  try {
    const token = extractToken(req.headers.authorization);
    if (!token) throw new HttpException(401, 'UNAUTHORIZED', 'Token required');
    req.auth = verifyToken(token);
    next();
  } catch (error) {
    next(error);
  }
};

export const optionalAuthMiddleware = (req: Request, res: Response, next: NextFunction): void => {
  try {
    const token = extractToken(req.headers.authorization);
    if (token) req.auth = verifyToken(token);
  } catch {
    // Silently ignore invalid token for optional auth
  }
  next();
};

// src/services/xxx.service.ts
export async function updateXxxService(xxxId: number, userId: number, data: any): Promise<any> {
  const xxx = await prisma.xxx.findUnique({ where: { id: xxxId } });
  if (!xxx) throw new HttpException(404, 'NOT_FOUND', 'Xxx not found');
  if (xxx.userId !== userId) throw new HttpException(403, 'FORBIDDEN', 'Not your Xxx');
  return prisma.xxx.update({ where: { id: xxxId }, data });
}

// src/controllers/xxx.controller.ts
export async function updateXxx(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const xxx = await updateXxxService(parseInt(req.params.xxxId), req.auth!.id, req.body);
    res.json({ xxx });
  } catch (error) {
    next(error);
  }
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Prisma relational query patterns: include for eager loading nested data, nested create with connect for relations, cascade delete on dependent models, unique constraint checking with OR queries.",
        "modules": ["src/services/"],
        "connections": [
            "1. include strategy: { user: { select: { id, email, username } } } for eager loading",
            "2. Nested create: create article with tags by connecting existing tags",
            "3. Cascade delete: Comment onDelete: Cascade in schema → delete comments when article deleted",
            "4. Uniqueness check: where OR query to verify slug/email not taken",
            "5. Self-include: article include: { comments: { include: { author: { select: { ... } } } } }",
        ],
        "code_example": """
// prisma/schema.prisma
model Xxx {
  id        Int     @id @default(autoincrement())
  title     String
  slug      String  @unique
  author    User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  userId    Int
  comments  Comment[]
  xxxs      XxxTag[]
}

model Comment {
  id        Int     @id @default(autoincrement())
  body      String
  xxx       Xxx     @relation(fields: [xxxId], references: [id], onDelete: Cascade)
  xxxId     Int
  author    User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  userId    Int
}

model Tag {
  id   Int    @id @default(autoincrement())
  name String @unique
  xxxs XxxTag[]
}

model XxxTag {
  xxxId Int
  xxx   Xxx  @relation(fields: [xxxId], references: [id], onDelete: Cascade)
  tagId Int
  tag   Tag  @relation(fields: [tagId], references: [id], onDelete: Cascade)
  @@id([xxxId, tagId])
}

// src/services/xxx.service.ts
export async function getXxxDetailService(xxxId: number, userId?: number): Promise<any> {
  const xxx = await prisma.xxx.findUnique({
    where: { id: xxxId },
    include: {
      author: { select: { id, username, email, image } },
      comments: {
        include: { author: { select: { id, username, email, image } } },
        orderBy: { createdAt: 'desc' },
      },
      xxxs: { include: { tag: { select: { id, name } } } },
    },
  });
  if (!xxx) throw new HttpException(404, 'NOT_FOUND', 'Xxx not found');
  return enrichXxx(xxx, userId);  // Add 'favorited', 'following' flags based on userId
}

export async function createXxxWithTagsService(data: any, userId: number): Promise<any> {
  const existing = await prisma.xxx.findFirst({
    where: { OR: [{ slug: data.slug }] },
  });
  if (existing) throw new HttpException(422, 'VALIDATION', 'Slug taken');

  const tags = data.tagList || [];
  const xxx = await prisma.xxx.create({
    data: {
      title: data.title,
      slug: data.slug,
      description: data.description,
      body: data.body,
      userId,
      xxxs: {
        create: await Promise.all(
          tags.map(async (tagName: string) => {
            let tag = await prisma.tag.findUnique({ where: { name: tagName } });
            if (!tag) tag = await prisma.tag.create({ data: { name: tagName } });
            return { tagId: tag.id };
          })
        ),
      },
    },
    include: {
      author: { select: { id, username, email, image } },
      xxxs: { include: { tag: { select: { id, name } } } },
    },
  });
  return xxx;
}

export async function deleteXxxService(xxxId: number, userId: number): Promise<void> {
  const xxx = await prisma.xxx.findUnique({ where: { id: xxxId } });
  if (!xxx) throw new HttpException(404, 'NOT_FOUND', 'Xxx not found');
  if (xxx.userId !== userId) throw new HttpException(403, 'FORBIDDEN', 'Not your Xxx');
  // CASCADE DELETE handles comments automatically
  await prisma.xxx.delete({ where: { id: xxxId } });
}
""",
        "pattern_scope": "prisma_relations",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Self-relation wiring (Follow pattern): User follows User via implicit many-to-many relation. Prisma schema uses @relation with custom name to avoid conflict. Query uses nested relation: user.following.some({ id }).",
        "modules": [
            "prisma/schema.prisma",
            "src/services/user.service.ts",
            "src/controllers/user.controller.ts",
        ],
        "connections": [
            "1. Schema: User model defines two sides of same relation with distinct names",
            "2. Implicit many-to-many junction table created by Prisma",
            "3. Service: queries use relation_filter: user.following.some({ id: targetUserId })",
            "4. Service: follow operation → connect(targetUserId) to following array",
            "5. Controller exposes follow/unfollow endpoints with auth middleware",
        ],
        "code_example": """
// prisma/schema.prisma
model User {
  id        Int     @id @default(autoincrement())
  username  String  @unique
  email     String  @unique
  password  String
  // Self-relation: User follows User
  followedBy User[] @relation("FollowRelation", references: [id])
  following  User[] @relation("FollowRelation", references: [id])
}

// src/services/user.service.ts
export async function followUserService(userId: number, targetUserId: number): Promise<any> {
  if (userId === targetUserId) {
    throw new HttpException(422, 'VALIDATION', 'Cannot follow yourself');
  }
  const target = await prisma.user.findUnique({ where: { id: targetUserId } });
  if (!target) throw new HttpException(404, 'NOT_FOUND', 'User not found');

  return prisma.user.update({
    where: { id: userId },
    data: { following: { connect: { id: targetUserId } } },
    include: { following: { select: { id, username, email } } },
  });
}

export async function unfollowUserService(userId: number, targetUserId: number): Promise<any> {
  return prisma.user.update({
    where: { id: userId },
    data: { following: { disconnect: { id: targetUserId } } },
    include: { following: { select: { id, username, email } } },
  });
}

export async function isFollowingService(userId: number, targetUserId: number): Promise<boolean> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { following: { where: { id: targetUserId } } },
  });
  return (user?.following.length ?? 0) > 0;
}

export async function getUserProfileService(userId: number, requesterId?: number): Promise<any> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { id, username, email, image, bio },
  });
  if (!user) throw new HttpException(404, 'NOT_FOUND', 'User not found');

  let following = false;
  if (requesterId && requesterId !== userId) {
    following = await isFollowingService(requesterId, userId);
  }
  return { ...user, following };
}

// src/controllers/user.controller.ts
export async function followUser(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const profile = await followUserService(req.auth!.id, parseInt(req.params.userId));
    res.json({ profile });
  } catch (error) {
    next(error);
  }
}

export async function unfollowUser(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const profile = await unfollowUserService(req.auth!.id, parseInt(req.params.userId));
    res.json({ profile });
  } catch (error) {
    next(error);
  }
}
""",
        "pattern_scope": "prisma_relations",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Error handling flow: Service throws HttpException(statusCode, errorCode, details). Express error middleware catches it. Formats response as { errors: { body: [message] } } for Realworld API spec. 422 for validation, 404 for not found, 401 for unauthorized, 403 for forbidden.",
        "modules": [
            "src/models/http-exception.ts",
            "src/middleware/error-handler.ts",
            "src/services/",
            "src/controllers/",
            "src/app.ts",
        ],
        "connections": [
            "1. Service throws: new HttpException(statusCode, errorCode, details)",
            "2. Controller try-catch → next(error)",
            "3. Express routes error to final error middleware",
            "4. error-handler.ts checks instanceof HttpException",
            "5. Format: { errors: { body: [statusCode, errorCode, details] } }",
            "6. res.status(statusCode).json(...)",
        ],
        "code_example": """
// src/models/http-exception.ts
export class HttpException extends Error {
  constructor(
    public statusCode: number,
    public errorCode: string,
    public details?: string | string[] | Record<string, any>
  ) {
    super(errorCode);
    this.name = 'HttpException';
  }
}

// src/middleware/error-handler.ts
import { Request, Response, ErrorRequestHandler } from 'express';
import { HttpException } from '../models/http-exception';

export const errorHandlerMiddleware: ErrorRequestHandler = (err, req, res, next) => {
  if (err instanceof HttpException) {
    const message = typeof err.details === 'string'
      ? err.details
      : err.details?.message || err.errorCode;
    return res.status(err.statusCode).json({
      errors: { body: [message] },
    });
  }

  // Unhandled error (unexpected)
  console.error('Unhandled error:', err);
  return res.status(500).json({
    errors: { body: ['Internal server error'] },
  });
};

// src/services/xxx.service.ts
export async function updateXxxService(xxxId: number, userId: number, data: any): Promise<any> {
  const xxx = await prisma.xxx.findUnique({ where: { id: xxxId } });
  if (!xxx) {
    throw new HttpException(404, 'NOT_FOUND', 'Xxx not found');
  }
  if (xxx.userId !== userId) {
    throw new HttpException(403, 'FORBIDDEN', 'Not your Xxx');
  }
  if (data.title && data.title.length < 3) {
    throw new HttpException(422, 'VALIDATION_ERROR', 'Title must be at least 3 chars');
  }
  return prisma.xxx.update({ where: { id: xxxId }, data });
}

// src/controllers/xxx.controller.ts
export async function updateXxx(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const xxx = await updateXxxService(parseInt(req.params.xxxId), req.auth!.id, req.body);
    res.json({ xxx });
  } catch (error) {
    next(error);  // Passes to error-handler middleware
  }
}

// src/app.ts
import { errorHandlerMiddleware } from './middleware/error-handler';

const app = express();
app.use(express.json());
app.use('/api/v1/xxxs', xxxRouter);
app.use(errorHandlerMiddleware);  // Must be last
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Test wiring: Jest + Supertest for API testing. Separate .env.test with test database. prisma migrate reset before test suite. Seed fixtures (user, article, tags). Auth token generated in test headers using same generateToken function.",
        "modules": [
            ".env.test",
            "jest.config.js",
            "src/tests/fixtures/seed.ts",
            "src/tests/setup.ts",
            "src/tests/xxx.integration.test.ts",
        ],
        "connections": [
            "1. jest.config.js sets NODE_ENV=test, points to .env.test",
            "2. setupFilesAfterEnv: src/tests/setup.ts runs before all tests",
            "3. setup.ts: prisma migrate reset, await seed()",
            "4. seed.ts: create test user, articles, tags in test DB",
            "5. Integration test: getToken(testUserId), include in headers",
            "6. Test sends request, expects response, validates response body",
        ],
        "code_example": """
// .env.test
DATABASE_URL="postgresql://test:test@localhost:5432/test_db"
JWT_SECRET="test-secret"
NODE_ENV=test

// jest.config.js
export default {
  preset: 'ts-jest',
  testEnvironment: 'node',
  setupFilesAfterEnv: ['<rootDir>/src/tests/setup.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
};

// src/tests/setup.ts
import { execSync } from 'child_process';
import { seed } from './fixtures/seed';

beforeAll(async () => {
  // Reset database (includes migrate + seed)
  execSync('npx prisma migrate reset --force', {
    env: { ...process.env, NODE_ENV: 'test' },
  });
  // Run custom seed
  await seed();
});

afterAll(async () => {
  await prisma.$disconnect();
});

// src/tests/fixtures/seed.ts
import { prisma } from '../../prisma/prisma-client';
import bcrypt from 'bcryptjs';

export async function seed() {
  // Create test user
  const hashedPassword = await bcrypt.hash('password123', 10);
  const testUser = await prisma.user.create({
    data: {
      username: 'testuser',
      email: 'test@example.com',
      password: hashedPassword,
      image: null,
      bio: '',
    },
  });

  // Create test articles
  const article1 = await prisma.xxx.create({
    data: {
      title: 'Test Article 1',
      slug: 'test-article-1',
      userId: testUser.id,
    },
  });

  // Create tags
  const tag1 = await prisma.tag.create({ data: { name: 'test' } });
  await prisma.xxxTag.create({ data: { xxxId: article1.id, tagId: tag1.id } });

  global.testUser = testUser;
  global.testArticle = article1;
}

declare global {
  var testUser: any;
  var testArticle: any;
}

// src/tests/xxx.integration.test.ts
import request from 'supertest';
import app from '../../app';
import { generateToken } from '../../utils/token';

describe('Xxx Endpoints', () => {
  it('POST /api/v1/xxxs creates xxx with auth', async () => {
    const token = generateToken(global.testUser.id);
    const response = await request(app)
      .post('/api/v1/xxxs')
      .set('Authorization', `Token ${token}`)
      .send({
        xxx: {
          title: 'New Article',
          slug: 'new-article',
          description: 'Test',
          body: 'Test body',
          tagList: ['test'],
        },
      });

    expect(response.status).toBe(201);
    expect(response.body.xxx).toHaveProperty('id');
    expect(response.body.xxx.title).toBe('New Article');
  });

  it('GET /api/v1/xxxs/:id returns xxx with author', async () => {
    const response = await request(app).get(`/api/v1/xxxs/${global.testArticle.id}`);
    expect(response.status).toBe(200);
    expect(response.body.xxx.author).toHaveProperty('username');
  });

  it('PUT /api/v1/xxxs/:id requires auth', async () => {
    const response = await request(app)
      .put(`/api/v1/xxxs/${global.testArticle.id}`)
      .send({ xxx: { title: 'Updated' } });
    expect(response.status).toBe(401);
  });
});
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": TIMESTAMP,
        "_tag": TAG,
    },
]


# ============================================================================
# QDRANT HELPER FUNCTIONS
# ============================================================================


def create_wiring_points() -> list[PointStruct]:
    """Convert wiring dictionaries to Qdrant PointStruct."""
    import uuid

    # Batch embed all descriptions
    descriptions = [w["description"] for w in WIRINGS]
    embeddings = embed_documents_batch(descriptions)

    points = []
    for idx, (wiring, embedding) in enumerate(zip(WIRINGS, embeddings)):
        payload = {
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
        }
        points.append(PointStruct(id=str(uuid.uuid4()), vector=embedding, payload=payload))
    return points


def cleanup_old_wirings(client: QdrantClient, collection_name: str, tag: str) -> None:
    """Delete old wiring points for this repo before inserting new ones."""
    try:
        client.delete(
            collection_name=collection_name,
            points_selector={"has_id": []},  # Placeholder; actual filter below
        )
    except Exception:
        pass  # Collection may not exist yet


def upsert_wirings(client: QdrantClient, collection_name: str, points: list[PointStruct]) -> None:
    """Upsert wiring points into Qdrant collection."""
    if not points:
        print("No wiring points to upsert.")
        return

    try:
        client.upsert(
            collection_name=collection_name,
            points=points,
        )
        print(f"Upserted {len(points)} wiring points to '{collection_name}'")
    except Exception as e:
        print(f"Error upserting wirings: {e}")
        raise


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    """Main ingestion flow."""
    print(f"[{REPO_NAME}] Starting wirings ingestion...")
    print(f"  Language: {LANGUAGE}")
    print(f"  Framework: {FRAMEWORK}")
    print(f"  Stack: {STACK}")
    print(f"  DRY_RUN: {DRY_RUN}")
    print()

    # Initialize Qdrant client
    try:
        client = QdrantClient(path=KB_PATH)
        print(f"Connected to Qdrant at {KB_PATH}")
    except Exception as e:
        print(f"Error connecting to Qdrant: {e}")
        raise

    # Create wiring points
    points = create_wiring_points()
    print(f"Created {len(points)} wiring points from manual definitions")

    if DRY_RUN:
        print("\n[DRY_RUN] Would upsert the following points:")
        for point in points:
            print(f"  - ID {point.id}: {point.payload.get('wiring_type')} ({point.payload.get('pattern_scope')})")
        return

    # Upsert to Qdrant
    upsert_wirings(client, COLLECTION, points)

    print()
    print(f"[{REPO_NAME}] Wirings ingestion complete!")


if __name__ == "__main__":
    main()
