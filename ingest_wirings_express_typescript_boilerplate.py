#!/usr/bin/env python3
"""
Wirings ingestion script for Wal-e Lab V6 Qdrant KB.
Repo: w3tecch/express-typescript-boilerplate (TypeScript Simple)

TypeScript — pas d'extracteur AST, wirings 100% manuels.
8 manual wirings covering: import graph, flow patterns, dependency chains, event dispatch, DataLoader, tests.
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


# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/w3tecch/express-typescript-boilerplate.git"
REPO_NAME = "w3tecch/express-typescript-boilerplate"
REPO_LOCAL = "/tmp/express-typescript-boilerplate"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+typeorm+typedi+routing-controllers+typescript"
CHARTE_VERSION = "1.0"
TAG = "wirings/w3tecch/express-typescript-boilerplate"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"


# ============================================================================
# MANUAL WIRINGS (8)
# ============================================================================

MANUAL_WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "Module import tree: app.ts → loaders/ → controllers/ → services/ → repositories/ → models/. DI container wires services to controllers automatically.",
        "modules": [
            "src/app.ts",
            "src/loaders/index.ts",
            "src/loaders/express.ts",
            "src/loaders/typeorm.ts",
            "src/loaders/typedi.ts",
            "src/controllers/index.ts",
            "src/controllers/XxxController.ts",
            "src/services/XxxService.ts",
            "src/repositories/XxxRepository.ts",
            "src/models/Xxx.ts",
        ],
        "connections": [
            "app.ts → loaders/index.ts (imports, initializes all loaders)",
            "loaders/express.ts → controllers/ (registers routing-controllers decorators)",
            "loaders/typeorm.ts → models/ (creates database connection, syncs entities)",
            "loaders/typedi.ts → DI container (registers services, repositories)",
            "XxxController → @Inject XxxService (TypeDI resolves at request time)",
            "XxxService → @OrmRepository XxxRepository (repository injection)",
            "XxxRepository extends Repository<Xxx> (TypeORM base)",
        ],
        "code_example": """
// src/app.ts
import { loadExpressServer } from './loaders/express';
import { loadTypeormConnection } from './loaders/typeorm';
import { loadTypedi } from './loaders/typedi';

export async function bootstrap(): Promise<void> {
  const connection = await loadTypeormConnection();
  const container = loadTypedi();
  const app = loadExpressServer();
  app.listen(3000, () => {
    console.log('Server running on port 3000');
  });
}
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
        "description": "Complete file creation order: 1) env/ (environment config), 2) models/ (TypeORM entities with decorators), 3) repositories/ (TypeORM Repository<T> extensions), 4) services/ (@Service with injected repos), 5) controllers/ (@Controller with @Service injection), 6) middlewares/ (auth, error, logging), 7) loaders/ (express, typeorm, typedi setup), 8) app.ts (bootstrap all loaders)",
        "modules": [
            "src/env.ts",
            "src/models/Xxx.ts",
            "src/repositories/XxxRepository.ts",
            "src/services/XxxService.ts",
            "src/controllers/XxxController.ts",
            "src/middlewares/auth.ts",
            "src/loaders/typeorm.ts",
            "src/loaders/express.ts",
            "src/loaders/typedi.ts",
            "src/app.ts",
        ],
        "connections": [
            "env.ts → exports config (NODE_ENV, DB_URL, API_PORT)",
            "models/Xxx.ts → @Entity, @Column, @ManyToOne, @OneToMany (defines DB schema)",
            "repositories/XxxRepository.ts → extends Repository<Xxx> (query builders, custom methods)",
            "services/XxxService.ts → @Service, @Inject XxxRepository (business logic)",
            "controllers/XxxController.ts → @Controller, method → XxxService (route handlers)",
            "middlewares/auth.ts → @Middleware (JWT verification, auth guard)",
            "loaders/typeorm.ts → createConnection(env.DB_URL, entities=[Xxx, ...]) (startup)",
            "loaders/express.ts → useExpressServer(app, { controllers: [...], middlewares: [...] }) (registers decorators)",
            "loaders/typedi.ts → setupTypedi() (initializes DI container)",
            "app.ts → calls all loaders, app.listen() (orchestrates bootstrap)",
        ],
        "code_example": """
// 1. env.ts
export const env = {
  NODE_ENV: process.env.NODE_ENV || 'development',
  DB_URL: process.env.DATABASE_URL || 'postgres://user:pass@localhost/xxxdb',
  API_PORT: process.env.API_PORT || 3000,
};

// 2. models/Xxx.ts
import { Entity, PrimaryGeneratedColumn, Column, ManyToOne } from 'typeorm';
import { IsString, IsEmail } from 'class-validator';

@Entity()
export class Xxx {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  @IsString()
  name: string;

  @Column()
  @IsEmail()
  email: string;

  @Column({ default: false })
  active: boolean;

  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP' })
  createdAt: Date;
}

// 3. repositories/XxxRepository.ts
import { Repository } from 'typeorm';
import { Service } from 'typedi';
import { OrmRepository } from 'typeorm-typedi-extensions';
import { Xxx } from '../models/Xxx';

@Service()
export class XxxRepository extends Repository<Xxx> {
  @OrmRepository()
  private repo: Repository<Xxx>;

  async findByEmail(email: string): Promise<Xxx | null> {
    return this.repo.findOne({ where: { email } });
  }

  async findActiveXxxs(skip: number, take: number): Promise<Xxx[]> {
    return this.repo.find({
      where: { active: true },
      skip,
      take,
      order: { createdAt: 'DESC' },
    });
  }
}

// 4. services/XxxService.ts
import { Service, Inject } from 'typedi';
import { XxxRepository } from '../repositories/XxxRepository';

@Service()
export class XxxService {
  constructor(@Inject(() => XxxRepository) private xxxRepo: XxxRepository) {}

  async createXxx(name: string, email: string): Promise<Xxx> {
    const xxx = this.xxxRepo.create({ name, email });
    return this.xxxRepo.save(xxx);
  }

  async getXxxById(id: number): Promise<Xxx | null> {
    return this.xxxRepo.findOne({ where: { id } });
  }

  async listXxxs(skip: number = 0, take: number = 10): Promise<Xxx[]> {
    return this.xxxRepo.findActiveXxxs(skip, take);
  }
}

// 5. controllers/XxxController.ts
import { JsonController, Get, Post, Body, Param, QueryParams } from 'routing-controllers';
import { Service, Inject } from 'typedi';
import { XxxService } from '../services/XxxService';

@JsonController('/xxxs')
@Service()
export class XxxController {
  constructor(@Inject(() => XxxService) private xxxService: XxxService) {}

  @Post('/')
  async createXxx(@Body() data: { name: string; email: string }): Promise<Xxx> {
    return this.xxxService.createXxx(data.name, data.email);
  }

  @Get('/:id')
  async getXxx(@Param('id') id: number): Promise<Xxx | null> {
    return this.xxxService.getXxxById(id);
  }

  @Get('/')
  async listXxxs(@QueryParams() query: { skip?: number; take?: number }): Promise<Xxx[]> {
    const skip = query.skip || 0;
    const take = query.take || 10;
    return this.xxxService.listXxxs(skip, take);
  }
}

// 6. app.ts bootstrap
async function bootstrap(): Promise<void> {
  const connection = await loadTypeormConnection();
  const container = loadTypedi();
  const app = loadExpressServer();
  app.listen(env.API_PORT, () => {
    console.log(`Server running on port ${env.API_PORT}`);
  });
}
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
        "description": "TypeDI injection chain: @OrmRepository(XxxRepository) → XxxService(@Inject) → XxxController(constructor injection). Container resolves all dependencies at startup.",
        "modules": [
            "src/repositories/XxxRepository.ts",
            "src/services/XxxService.ts",
            "src/controllers/XxxController.ts",
            "src/loaders/typedi.ts",
        ],
        "connections": [
            "loaders/typedi.ts → setupTypedi() (initializes Container)",
            "XxxRepository → @Service @OrmRepository (registered in container)",
            "XxxService → @Service @Inject(XxxRepository) (registered, awaits repo injection)",
            "XxxController → @Service @JsonController constructor(XxxService) (registered, awaits service injection)",
            "HTTP request → routing-controllers finds XxxController → Container.get(XxxController) → resolves entire chain",
        ],
        "code_example": """
// loaders/typedi.ts
import { Container } from 'typedi';
import { useContainer } from 'typeorm';

export function loadTypedi(): Container {
  useContainer(Container);  // TypeORM uses TypeDI container for repositories
  return Container;
}

// repositories/XxxRepository.ts
import { Service } from 'typedi';
import { OrmRepository } from 'typeorm-typedi-extensions';
import { Repository } from 'typeorm';
import { Xxx } from '../models/Xxx';

@Service()
export class XxxRepository extends Repository<Xxx> {
  @OrmRepository()
  private repo: Repository<Xxx>;
  // methods...
}

// services/XxxService.ts
import { Service, Inject } from 'typedi';
import { XxxRepository } from '../repositories/XxxRepository';

@Service()
export class XxxService {
  constructor(@Inject(() => XxxRepository) private xxxRepo: XxxRepository) {}
  // methods...
}

// controllers/XxxController.ts
import { JsonController, Get, Post } from 'routing-controllers';
import { Service, Inject } from 'typedi';
import { XxxService } from '../services/XxxService';

@JsonController('/xxxs')
@Service()
export class XxxController {
  constructor(@Inject(() => XxxService) private xxxService: XxxService) {}

  @Post('/')
  async createXxx(@Body() data: { name: string; email: string }): Promise<Xxx> {
    return this.xxxService.createXxx(data.name, data.email);
  }
}

// At startup: Container.get(XxxController) → resolves XxxService → resolves XxxRepository
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
        "description": "TypeORM entity lifecycle: @BeforeInsert → hashPassword(), @Column decorators, @ManyToOne/@OneToMany relations, @Exclude for sensitive fields (password). Repository pattern abstracts queries.",
        "modules": [
            "src/models/Xxx.ts",
            "src/repositories/XxxRepository.ts",
        ],
        "connections": [
            "models/Xxx.ts → @Entity decorators (schema definition)",
            "@Column decorators → column types, constraints (STRING, INTEGER, TIMESTAMP, etc.)",
            "@BeforeInsert hook → hashPassword(), set defaults (lifecycle event)",
            "@ManyToOne, @OneToMany → foreign key relations",
            "@Exclude → sensitive fields (password) excluded from API responses (class-transformer)",
            "repositories/XxxRepository.ts → this.repo.save(xxx) → triggers @BeforeInsert → hashed password stored",
            "repositories/XxxRepository.ts → this.repo.find() → returns entities with @Exclude fields stripped",
        ],
        "code_example": """
// models/Xxx.ts
import { Entity, PrimaryGeneratedColumn, Column, BeforeInsert, ManyToOne, OneToMany } from 'typeorm';
import { Exclude } from 'class-transformer';
import { IsString, IsEmail, MinLength } from 'class-validator';
import bcrypt from 'bcrypt';
import { Yyy } from './Yyy';

@Entity()
export class Xxx {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ type: 'varchar', length: 255 })
  @IsString()
  name: string;

  @Column({ type: 'varchar', length: 255, unique: true })
  @IsEmail()
  email: string;

  @Column({ type: 'varchar', length: 255 })
  @IsString()
  @MinLength(8)
  @Exclude()  // password never serialized to API
  password: string;

  @Column({ type: 'boolean', default: true })
  active: boolean;

  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP' })
  createdAt: Date;

  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP', onUpdate: 'CURRENT_TIMESTAMP' })
  updatedAt: Date;

  @BeforeInsert()
  async hashPassword(): Promise<void> {
    this.password = await bcrypt.hash(this.password, 10);
  }

  @ManyToOne(() => Yyy, (yyy) => yyy.xxxs, { onDelete: 'CASCADE' })
  yyy: Yyy;

  @OneToMany(() => Zzz, (zzz) => zzz.xxx)
  zzzs: Zzz[];
}

// repositories/XxxRepository.ts
import { Service } from 'typedi';
import { Repository } from 'typeorm';
import { Xxx } from '../models/Xxx';

@Service()
export class XxxRepository extends Repository<Xxx> {
  async findByEmail(email: string): Promise<Xxx | null> {
    return this.find({ where: { email } });  // @Exclude applied on serialization
  }

  async createXxx(email: string, password: string, name: string): Promise<Xxx> {
    const xxx = this.create({ email, password, name });
    return this.save(xxx);  // @BeforeInsert hook runs here, hashes password
  }
}
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
        "description": "Request processing flow: HTTP request → routing-controllers route matching → middleware chain (auth, validate) → @Controller method → @Service business logic → @Repository DB query → response serialization",
        "modules": [
            "src/loaders/express.ts",
            "src/middlewares/auth.ts",
            "src/controllers/XxxController.ts",
            "src/services/XxxService.ts",
            "src/repositories/XxxRepository.ts",
            "src/models/Xxx.ts",
        ],
        "connections": [
            "HTTP POST /api/v1/xxxs → routing-controllers router matches",
            "middleware/auth.ts → verifies JWT, sets req.user",
            "middleware/validate.ts → validates @Body against Xxx schema (class-validator)",
            "middleware/error.ts → global error handler",
            "XxxController.createXxx() → @Body() data triggers validation",
            "XxxService.createXxx() → business logic (auth check, duplicate check)",
            "XxxRepository.save(xxx) → TypeORM insert, @BeforeInsert hook runs",
            "Response → class-transformer serializes Xxx, @Exclude fields stripped → JSON",
        ],
        "code_example": """
// loaders/express.ts
import { useExpressServer } from 'routing-controllers';
import { useContainer } from 'typeorm';
import { Container } from 'typedi';

export function loadExpressServer(): Express {
  const app = express();
  useContainer(Container);
  useExpressServer(app, {
    controllers: [__dirname + '/controllers/**/*.ts'],
    middlewares: [__dirname + '/middlewares/**/*.ts'],
    defaultErrorHandler: false,  // custom error handler
  });
  return app;
}

// middlewares/auth.ts
import { ExpressMiddlewareInterface, Middleware } from 'routing-controllers';
import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

@Middleware({ type: 'before' })
export class AuthMiddleware implements ExpressMiddlewareInterface {
  use(req: Request, res: Response, next: NextFunction): void {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    try {
      const decoded = jwt.verify(token, process.env.JWT_SECRET!);
      req.user = decoded;
      next();
    } catch (err) {
      res.status(401).json({ error: 'Invalid token' });
    }
  }
}

// controllers/XxxController.ts
import { JsonController, Post, Body, UseAfter, Authorized } from 'routing-controllers';
import { Service, Inject } from 'typedi';
import { XxxService } from '../services/XxxService';

@JsonController('/xxxs')
@UseAfter(ErrorHandler)
@Service()
export class XxxController {
  constructor(@Inject(() => XxxService) private xxxService: XxxService) {}

  @Post('/')
  @Authorized()  // requires AuthMiddleware to run first
  async createXxx(@Body() data: CreateXxxDto): Promise<Xxx> {
    return this.xxxService.createXxx(data.name, data.email);
  }
}

// services/XxxService.ts
@Service()
export class XxxService {
  constructor(@Inject(() => XxxRepository) private xxxRepo: XxxRepository) {}

  async createXxx(name: string, email: string): Promise<Xxx> {
    const existing = await this.xxxRepo.findByEmail(email);
    if (existing) {
      throw new BadRequestException('Email already exists');
    }
    return this.xxxRepo.save(this.xxxRepo.create({ name, email }));
  }
}

// repositories/XxxRepository.ts
@Service()
export class XxxRepository extends Repository<Xxx> {
  async findByEmail(email: string): Promise<Xxx | null> {
    return this.findOne({ where: { email } });
  }
}

// models/Xxx.ts
@Entity()
export class Xxx {
  @PrimaryGeneratedColumn() id: number;
  @Column() name: string;
  @Column() email: string;
  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP' })
  createdAt: Date;
}

// Response: Xxx entity → class-transformer serializes → @Exclude(password) removed → JSON sent
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
        "description": "Event dispatcher pattern: @EventDispatcher in service → dispatch('onXxxCreated', xxx) → subscriber handles event (logging, notifications, side effects). Decouples cross-cutting concerns.",
        "modules": [
            "src/services/XxxService.ts",
            "src/subscribers/XxxSubscriber.ts",
            "src/events/XxxEvent.ts",
            "src/loaders/typedi.ts",
        ],
        "connections": [
            "services/XxxService.ts → @EventDispatcher inject (event dispatcher from TypeDI)",
            "XxxService.createXxx() → this.dispatcher.dispatch('onXxxCreated', xxx)",
            "subscribers/XxxSubscriber.ts → @EventSubscriber, @On('onXxxCreated') (listens for event)",
            "XxxSubscriber.onXxxCreated() → side effects (send email, log audit, notify webhooks)",
            "loaders/typedi.ts → registerSubscribers() (registers all subscribers at startup)",
        ],
        "code_example": """
// events/XxxEvent.ts
export class XxxEvent {
  constructor(public readonly xxx: Xxx) {}
}

// services/XxxService.ts
import { Service, Inject, EventDispatcher } from 'typedi';
import { XxxRepository } from '../repositories/XxxRepository';

@Service()
export class XxxService {
  constructor(
    @Inject(() => XxxRepository) private xxxRepo: XxxRepository,
    private dispatcher: EventDispatcher,
  ) {}

  async createXxx(name: string, email: string): Promise<Xxx> {
    const xxx = await this.xxxRepo.save(this.xxxRepo.create({ name, email }));
    this.dispatcher.dispatch(new XxxEvent(xxx));  // emit event
    return xxx;
  }
}

// subscribers/XxxSubscriber.ts
import { EventSubscriber, On, Inject } from 'typedi';
import { Logger } from '../utilities/Logger';
import { XxxEvent } from '../events/XxxEvent';
import { EmailService } from '../services/EmailService';

@EventSubscriber()
export class XxxSubscriber {
  constructor(
    @Inject() private logger: Logger,
    @Inject() private emailService: EmailService,
  ) {}

  @On(XxxEvent)
  async onXxxCreated(event: XxxEvent): Promise<void> {
    this.logger.info(`Xxx created: ${event.xxx.id}`);
    await this.emailService.sendWelcomeEmail(event.xxx.email);
  }
}

// loaders/typedi.ts
export function loadTypedi(): Container {
  useContainer(Container);
  useClassTransformer(true);
  useEventDispatcher(true);  // enables event dispatching
  return Container;
}
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
        "description": "DataLoader wiring for N+1: GraphQL or batch endpoint → DataLoader<ID, Xxx> → batches IDs → repository.findByIds(ids) → returns in order. Used in XxxRepository with QueryBuilder.",
        "modules": [
            "src/repositories/XxxRepository.ts",
            "src/utilities/DataLoader.ts",
            "src/controllers/XxxController.ts",
        ],
        "connections": [
            "DataLoader<number, Xxx> constructor → batches IDs (default size 100)",
            "XxxController.getXxxWithRelation() → loads yyy for each xxx via xxx.dataLoader.load(yyyId)",
            "DataLoader.load(id) → queues request, batches after microtask",
            "DataLoader batch function → repository.findByIds([id1, id2, ...]) → single DB query",
            "returns in correct order, caches results per request lifecycle",
        ],
        "code_example": """
// utilities/DataLoader.ts
import DataLoader from 'dataloader';

export function createXxxDataLoader(xxxRepo: XxxRepository): DataLoader<number, Xxx> {
  return new DataLoader(async (ids: readonly number[]) => {
    const xxxs = await xxxRepo.findByIds(Array.from(ids));
    const map = new Map(xxxs.map((x) => [x.id, x]));
    return ids.map((id) => map.get(id) || new Error(`Xxx ${id} not found`));
  });
}

// repositories/XxxRepository.ts
import { Service } from 'typedi';
import { Repository } from 'typeorm';
import { Xxx } from '../models/Xxx';

@Service()
export class XxxRepository extends Repository<Xxx> {
  async findByIds(ids: number[]): Promise<Xxx[]> {
    return this.createQueryBuilder('xxx')
      .where('xxx.id IN (:...ids)', { ids })
      .orderBy('xxx.id', 'ASC')
      .getMany();
  }

  async findXxxWithYyy(id: number, dataLoader: DataLoader<number, Yyy>): Promise<Xxx | null> {
    const xxx = await this.findOne({ where: { id }, relations: ['yyy'] });
    if (xxx && xxx.yyyId) {
      xxx.yyy = await dataLoader.load(xxx.yyyId);  // batched query
    }
    return xxx;
  }
}

// controllers/XxxController.ts
import { JsonController, Get, Param } from 'routing-controllers';
import { Service, Inject } from 'typedi';
import { XxxRepository } from '../repositories/XxxRepository';
import { createXxxDataLoader } from '../utilities/DataLoader';

@JsonController('/xxxs')
@Service()
export class XxxController {
  constructor(@Inject(() => XxxRepository) private xxxRepo: XxxRepository) {}

  @Get('/:id/with-yyy')
  async getXxxWithYyy(@Param('id') id: number): Promise<Xxx | null> {
    const dataLoader = createXxxDataLoader(this.xxxRepo);
    return this.xxxRepo.findXxxWithYyy(id, dataLoader);
  }

  @Get('/')
  async listXxxsWithYyy(): Promise<Xxx[]> {
    const dataLoader = createXxxDataLoader(this.xxxRepo);
    const xxxs = await this.xxxRepo.find({ relations: ['yyyId'] });
    // N+1 prevented: batch loads all yyy IDs in single query
    for (const xxx of xxxs) {
      if (xxx.yyyId) {
        xxx.yyy = await dataLoader.load(xxx.yyyId);
      }
    }
    return xxxs;
  }
}
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
        "description": "Test wiring: jest + supertest, TypeDI container reset between tests, in-memory SQLite TypeORM connection, seed test data fixtures, auth token generation",
        "modules": [
            "src/tests/setup.ts",
            "src/tests/fixtures/xxxFixture.ts",
            "src/tests/utils/authToken.ts",
            "src/tests/integration/xxx.controller.test.ts",
        ],
        "connections": [
            "tests/setup.ts → beforeAll: create in-memory TypeORM connection, run migrations",
            "tests/setup.ts → beforeEach: reset TypeDI Container, seed fixtures",
            "tests/setup.ts → afterAll: drop connection",
            "xxxFixture.ts → factory functions to create test Xxx entities",
            "authToken.ts → jwt.sign(payload) to generate test tokens",
            "xxx.controller.test.ts → describe('XxxController') → test('POST /api/v1/xxxs creates xxx')",
            "test sends supertest request → middleware + controller + service → repository uses in-memory DB → response assertion",
        ],
        "code_example": """
// tests/setup.ts
import { DataSource } from 'typeorm';
import { Container } from 'typedi';
import { Xxx } from '../models/Xxx';

let connection: DataSource;

beforeAll(async () => {
  connection = new DataSource({
    type: 'sqlite',
    database: ':memory:',
    entities: [Xxx, Yyy, Zzz],
    synchronize: true,
  });
  await connection.initialize();
});

beforeEach(async () => {
  Container.reset();
  // seed test data
  const xxxRepo = connection.getRepository(Xxx);
  await xxxRepo.clear();
});

afterAll(async () => {
  await connection.destroy();
});

// tests/fixtures/xxxFixture.ts
import { Xxx } from '../../models/Xxx';

export async function createTestXxx(
  repo: Repository<Xxx>,
  overrides?: Partial<Xxx>,
): Promise<Xxx> {
  const defaults = {
    name: 'Test Xxx',
    email: 'test@example.com',
    password: 'password123',
    ...overrides,
  };
  return repo.save(repo.create(defaults));
}

// tests/utils/authToken.ts
import jwt from 'jsonwebtoken';

export function generateAuthToken(userId: number): string {
  return jwt.sign({ sub: userId, role: 'user' }, process.env.JWT_SECRET!, {
    expiresIn: '1h',
  });
}

// tests/integration/xxx.controller.test.ts
import request from 'supertest';
import { createTestXxx, generateAuthToken } from '../fixtures/xxxFixture';

describe('XxxController', () => {
  it('POST /api/v1/xxxs creates xxx', async () => {
    const token = generateAuthToken(1);
    const response = await request(app)
      .post('/api/v1/xxxs')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'New Xxx', email: 'new@example.com' })
      .expect(201);

    expect(response.body).toHaveProperty('id');
    expect(response.body.name).toBe('New Xxx');
  });

  it('GET /api/v1/xxxs lists xxxs', async () => {
    const xxx = await createTestXxx(xxxRepo);
    const response = await request(app)
      .get('/api/v1/xxxs')
      .expect(200);

    expect(response.body).toHaveLength(1);
    expect(response.body[0].id).toBe(xxx.id);
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
# FUNCTIONS
# ============================================================================


def init_qdrant_client(kb_path: str) -> QdrantClient:
    """Initialize Qdrant client."""
    return QdrantClient(path=kb_path)


def cleanup_wirings(client: QdrantClient, tag: str) -> None:
    """Delete all wirings with given tag."""
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="_tag",
                            match=MatchValue(value=tag),
                        )
                    ]
                )
            ),
        )
        print(f"[cleanup] Deleted wirings with tag: {tag}")
    except Exception as e:
        print(f"[cleanup] No wirings found with tag {tag}, or error: {e}")


def clone_repo(repo_url: str, repo_local: str) -> None:
    """Clone repository."""
    if os.path.exists(repo_local):
        print(f"[clone] Repo already exists at {repo_local}, skipping clone.")
        return
    print(f"[clone] Cloning {repo_url} to {repo_local}...")
    subprocess.run(
        ["git", "clone", repo_url, repo_local],
        check=True,
        capture_output=True,
    )
    print(f"[clone] Done.")


def embed_and_upsert_wirings(
    client: QdrantClient,
    wirings: list[dict],
) -> None:
    """Embed descriptions and upsert all wirings."""
    print(f"[embed] Embedding {len(wirings)} wirings...")

    descriptions = [w["description"] for w in wirings]
    embeddings = embed_documents_batch(descriptions)

    points = []
    for idx, (wiring, embedding) in enumerate(zip(wirings, embeddings)):
        point_id = int(uuid.uuid4().int % 2**63)
        point = PointStruct(
            id=point_id,
            vector=embedding,
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

    if not DRY_RUN:
        client.upsert(
            collection_name=COLLECTION,
            points=points,
        )
        print(f"[upsert] Inserted {len(points)} wirings into {COLLECTION}.")
    else:
        print(f"[DRY_RUN] Would insert {len(points)} wirings.")


def verify_queries(client: QdrantClient) -> None:
    """Verify KB queries with language filter."""
    print("[verify] Running KB queries...")

    test_queries = [
        ("TypeDI dependency injection pattern", "dependency_chain"),
        ("routing-controllers decorators setup", "flow_pattern"),
        ("TypeORM entity lifecycle hooks", "dependency_chain"),
    ]

    for query_text, expected_type in test_queries:
        print(f"  Query: {query_text}")
        try:
            embedding = embed_query(query_text)
            results = client.query_points(
                collection_name=COLLECTION,
                query=embedding,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="language",
                            match=MatchValue(value=LANGUAGE),
                        )
                    ]
                ),
                limit=1,
            )
            if results.points:
                point = results.points[0]
                wiring_type = point.payload.get("wiring_type", "unknown")
                score = point.score
                print(
                    f"    ✓ Found: {wiring_type} (score={score:.3f}, "
                    f"tag={point.payload.get('_tag', 'unknown')})"
                )
            else:
                print(f"    ✗ No results")
        except Exception as e:
            print(f"    ✗ Error: {e}")

    print("[verify] Done.")


def main() -> None:
    """Main ingestion pipeline."""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║ Wirings Ingestion — {REPO_NAME}             ║
║ TypeScript — pas d'extracteur AST, wirings 100% manuels       ║
╚═══════════════════════════════════════════════════════════════╝
""")

    # Init Qdrant
    print(f"[init] Connecting to Qdrant at {KB_PATH}...")
    client = init_qdrant_client(KB_PATH)
    print(f"[init] Done.")

    # Cleanup
    print(f"[cleanup] Removing old wirings with tag: {TAG}...")
    cleanup_wirings(client, TAG)
    print(f"[cleanup] Done.")

    # Clone repo (informational only, not used for AST extraction)
    print(f"[clone] Checking repo at {REPO_LOCAL}...")
    clone_repo(REPO_URL, REPO_LOCAL)
    print(f"[clone] Done.")

    # Embed and upsert
    print(f"[embed] Processing {len(MANUAL_WIRINGS)} manual wirings...")
    embed_and_upsert_wirings(client, MANUAL_WIRINGS)
    print(f"[embed] Done.")

    # Verify
    verify_queries(client)

    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║ ✓ Ingestion complete                                          ║
║                                                               ║
║ Summary:                                                      ║
║  - Repo: {REPO_NAME}                    ║
║  - Language: {LANGUAGE}                                         ║
║  - Framework: {FRAMEWORK}                                      ║
║  - Manual wirings: {len(MANUAL_WIRINGS)}                                           ║
║  - Collection: {COLLECTION}                                    ║
║  - Tag: {TAG}                 ║
║                                                               ║
║ Next: Validate wirings in Qdrant:                             ║
║  client = QdrantClient(path='./kb_qdrant')                    ║
║  col = client.get_collection('{COLLECTION}')                  ║
║  print(f'Total points: {{col.points_count}}')                 ║
╚═══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
