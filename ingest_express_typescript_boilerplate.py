"""
ingest_express_typescript_boilerplate.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de w3tecch/express-typescript-boilerplate dans la KB Qdrant V6.

TypeScript A — Express + TypeORM + TypeDI + routing-controllers + type-graphql.
3-layer architecture with DI.

Usage:
    .venv/bin/python3 ingest_express_typescript_boilerplate.py
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
REPO_URL = "https://github.com/w3tecch/express-typescript-boilerplate.git"
REPO_NAME = "w3tecch/express-typescript-boilerplate"
REPO_LOCAL = "/tmp/express_typescript_boilerplate"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+typeorm+typedi+routing-controllers+typescript"
CHARTE_VERSION = "1.0"
TAG = "w3tecch/express-typescript-boilerplate"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/w3tecch/express-typescript-boilerplate"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: User→Xxx, user→xxx, users→xxxs, userId→xxxId, UserService→XxxService
# Pet stays as Pet (not in FORBIDDEN_ENTITIES).
# T-1: no :any. T-2: no var. T-3: no console.log.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # ENTITIES (TypeORM)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Main entity with bcrypt + validation + relations ─────────────────
    {
        "normalized_code": """\
import bcrypt from 'bcrypt';
import { Exclude } from 'class-transformer';
import { IsNotEmpty } from 'class-validator';
import {
  BeforeInsert,
  Column,
  Entity,
  OneToMany,
  PrimaryColumn,
} from 'typeorm';

import { Pet } from './Pet';

@Entity()
export class Xxx {
  @PrimaryColumn('uuid')
  public id: string;

  @IsNotEmpty()
  @Column()
  public firstName: string;

  @IsNotEmpty()
  @Column()
  public lastName: string;

  @IsNotEmpty()
  @Column()
  @Exclude()
  public password: string;

  @IsNotEmpty()
  @Column()
  public email: string;

  @OneToMany(() => Pet, (pet) => pet.xxx)
  public pets: Pet[];

  public static hashPassword(password: string): Promise<string> {
    return new Promise((resolve, reject) => {
      bcrypt.hash(password, 10, (err: Error, hash: string) => {
        if (err) reject(err);
        resolve(hash);
      });
    });
  }

  public static comparePassword(
    xxx: Xxx,
    password: string,
  ): Promise<boolean> {
    return new Promise((resolve, reject) => {
      bcrypt.compare(
        password,
        xxx.password,
        (err: Error, result: boolean) => {
          if (err) reject(err);
          resolve(result);
        },
      );
    });
  }

  @BeforeInsert()
  public async hashPassword(): Promise<void> {
    this.password = await Xxx.hashPassword(this.password);
  }

  public toString(): string {
    return `${this.firstName} ${this.lastName} (${this.email})`;
  }
}\
""",
        "function": "typeorm_entity_main_with_bcrypt_validation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/api/models/Xxx.ts",
    },

    # ── 2. Relation entity with ManyToOne + JoinColumn ──────────────────────
    {
        "normalized_code": """\
import { IsNotEmpty } from 'class-validator';
import {
  Column,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryColumn,
} from 'typeorm';

import { Xxx } from './Xxx';

@Entity()
export class Pet {
  @PrimaryColumn('uuid')
  public id: string;

  @IsNotEmpty()
  @Column()
  public name: string;

  @IsNotEmpty()
  @Column()
  public age: number;

  @Column({ nullable: true })
  public xxxId: string;

  @ManyToOne(() => Xxx, (xxx) => xxx.pets)
  @JoinColumn()
  public xxx: Xxx;
}\
""",
        "function": "typeorm_entity_relation_many_to_one",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/api/models/Pet.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # REPOSITORIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 3. Base repository extending Repository<T> ──────────────────────────
    {
        "normalized_code": """\
import { EntityRepository, Repository } from 'typeorm';

import { Xxx } from '../models/Xxx';

@EntityRepository(Xxx)
export class XxxRepository extends Repository<Xxx> {}\
""",
        "function": "typeorm_repository_base_entity",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/api/repositories/XxxRepository.ts",
    },

    # ── 4. Custom repository with QueryBuilder for DataLoader ───────────────
    {
        "normalized_code": """\
import { EntityRepository, Repository } from 'typeorm';

import { Pet } from '../models/Pet';

@EntityRepository(Pet)
export class PetRepository extends Repository<Pet> {
  public findByXxxIds(ids: string[]): Promise<Pet[]> {
    return this.createQueryBuilder('pet')
      .where('pet.xxxId IN (:...ids)', { ids })
      .getMany();
  }
}\
""",
        "function": "typeorm_repository_custom_querybuilder_dataloader",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/api/repositories/PetRepository.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SERVICES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 5. Service with full DI + CRUD + event dispatch ─────────────────────
    {
        "normalized_code": """\
import { Service } from 'typedi';
import { OrmRepository } from 'typeorm-typedi-extensions';

import { EventDispatcher, EventDispatcherInterface } from '../../decorators/EventDispatcher';
import { Logger, LoggerInterface } from '../../decorators/Logger';
import { Xxx } from '../models/Xxx';
import { XxxRepository } from '../repositories/XxxRepository';
import { entityHooks } from '../subscribers/entityHooks';

@Service()
export class XxxService {
  constructor(
    @OrmRepository() private xxxRepository: XxxRepository,
    @EventDispatcher() private eventDispatcher: EventDispatcherInterface,
    @Logger(__filename) private log: LoggerInterface,
  ) {}

  public find(): Promise<Xxx[]> {
    this.log.info('Find all xxxs');
    return this.xxxRepository.find({ relations: ['pets'] });
  }

  public findOne(id: string): Promise<Xxx | undefined> {
    this.log.info('Find one xxx');
    return this.xxxRepository.findOne({ where: { id } });
  }

  public async create(xxx: Xxx): Promise<Xxx> {
    this.log.info('Create a new xxx => ', xxx.toString());
    xxx.id = require('uuid').v1();
    const newXxx = await this.xxxRepository.save(xxx);
    this.eventDispatcher.dispatch(entityHooks.xxx.created, newXxx);
    return newXxx;
  }

  public update(id: string, xxx: Xxx): Promise<Xxx> {
    this.log.info('Update a xxx');
    xxx.id = id;
    return this.xxxRepository.save(xxx);
  }

  public async delete(id: string): Promise<void> {
    this.log.info('Delete a xxx');
    await this.xxxRepository.delete(id);
  }
}\
""",
        "function": "service_crud_with_di_event_dispatch_logging",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/api/services/XxxService.ts",
    },

    # ── 6. Service with relational query method ─────────────────────────────
    {
        "normalized_code": """\
import { Service } from 'typedi';
import { OrmRepository } from 'typeorm-typedi-extensions';

import { Logger, LoggerInterface } from '../../decorators/Logger';
import { Pet } from '../models/Pet';
import { Xxx } from '../models/Xxx';
import { PetRepository } from '../repositories/PetRepository';

@Service()
export class PetService {
  constructor(
    @OrmRepository() private petRepository: PetRepository,
    @Logger(__filename) private log: LoggerInterface,
  ) {}

  public find(): Promise<Pet[]> {
    this.log.info('Find all pets');
    return this.petRepository.find();
  }

  public findByXxx(xxx: Xxx): Promise<Pet[]> {
    this.log.info('Find all pets of xxx');
    return this.petRepository.find({
      where: { xxxId: xxx.id },
    });
  }

  public findOne(id: string): Promise<Pet | undefined> {
    return this.petRepository.findOne({ where: { id } });
  }

  public async create(pet: Pet): Promise<Pet> {
    this.log.info('Create a new pet');
    pet.id = require('uuid').v1();
    return this.petRepository.save(pet);
  }

  public async delete(id: string): Promise<void> {
    await this.petRepository.delete(id);
  }
}\
""",
        "function": "service_relational_query",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "src/api/services/PetService.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTROLLERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 7. CRUD controller with routing-controllers + auth ──────────────────
    {
        "normalized_code": """\
import { Authorized, Body, Delete, Get, JsonController, OnUndefined, Param, Post, Put, Req } from 'routing-controllers';
import { OpenAPI, ResponseSchema } from 'routing-controllers-openapi';

import { XxxNotFoundError } from '../errors/XxxNotFoundError';
import { Xxx } from '../models/Xxx';
import { XxxService } from '../services/XxxService';
import { XxxResponse } from './XxxResponse';

@Authorized()
@JsonController('/xxxs')
@OpenAPI({ security: [{ basicAuth: [] }] })
export class XxxController {
  constructor(private xxxService: XxxService) {}

  @Get()
  @ResponseSchema(XxxResponse, { isArray: true })
  public find(): Promise<Xxx[]> {
    return this.xxxService.find();
  }

  @Get('/me')
  public findMe(@Req() req: Express.Request): Promise<Xxx[]> {
    return req['xxx'];
  }

  @Get('/:id')
  @OnUndefined(XxxNotFoundError)
  @ResponseSchema(XxxResponse)
  public one(@Param('id') id: string): Promise<Xxx | undefined> {
    return this.xxxService.findOne(id);
  }

  @Post()
  public create(@Body() body: Xxx): Promise<Xxx> {
    return this.xxxService.create(body);
  }

  @Put('/:id')
  public update(
    @Param('id') id: string,
    @Body() body: Xxx,
  ): Promise<Xxx> {
    return this.xxxService.update(id, body);
  }

  @Delete('/:id')
  public delete(@Param('id') id: string): Promise<void> {
    return this.xxxService.delete(id);
  }
}\
""",
        "function": "controller_crud_routing_controllers_authorized",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/api/controllers/XxxController.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 8. Before middleware — logging with morgan ──────────────────────────
    {
        "normalized_code": """\
import express from 'express';
import morgan from 'morgan';
import { ExpressMiddlewareInterface, Middleware } from 'routing-controllers';

import { Logger } from '../../lib/logger';
import { env } from '../../env';

@Middleware({ type: 'before' })
export class LogMiddleware implements ExpressMiddlewareInterface {
  private log = new Logger(__dirname);

  public use(
    req: express.Request,
    res: express.Response,
    next: express.NextFunction,
  ): express.Response | void {
    return morgan(env.log.output, {
      stream: {
        write: this.log.info.bind(this.log),
      },
    })(req, res, next);
  }
}\
""",
        "function": "middleware_before_logging_morgan",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/api/middlewares/LogMiddleware.ts",
    },

    # ── 9. After middleware — error handler ─────────────────────────────────
    {
        "normalized_code": """\
import express from 'express';
import {
  ExpressErrorMiddlewareInterface,
  HttpError,
  Middleware,
} from 'routing-controllers';

import { Logger, LoggerInterface } from '../../decorators/Logger';
import { env } from '../../env';

@Middleware({ type: 'after' })
export class ErrorHandlerMiddleware
  implements ExpressErrorMiddlewareInterface
{
  public isProduction = env.isProduction;

  constructor(@Logger(__filename) private log: LoggerInterface) {}

  public error(
    error: HttpError,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ): void {
    res.status(error.httpCode || 500);
    res.json({
      name: error.name,
      errors: error['errors'] || [],
    });

    if (this.isProduction) {
      this.log.error(error.name, error.stack);
    } else {
      this.log.error(error.name, error.stack);
    }
  }
}\
""",
        "function": "middleware_after_error_handler",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/api/middlewares/ErrorHandlerMiddleware.ts",
    },

    # ── 10. Security middleware — helmet ────────────────────────────────────
    {
        "normalized_code": """\
import express from 'express';
import helmet from 'helmet';
import { ExpressMiddlewareInterface, Middleware } from 'routing-controllers';

@Middleware({ type: 'before' })
export class SecurityMiddleware implements ExpressMiddlewareInterface {
  public use(
    req: express.Request,
    res: express.Response,
    next: express.NextFunction,
  ): express.Response | void {
    return helmet()(req, res, next);
  }
}\
""",
        "function": "middleware_security_wrapper_helmet",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/api/middlewares/SecurityMiddleware.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # EVENTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. Event constants ─────────────────────────────────────────────────
    {
        "normalized_code": """\
export const entityHooks = {
  xxx: {
    created: 'onXxxCreate',
  },
  pet: {
    created: 'onPetCreate',
  },
};\
""",
        "function": "event_constants_entity_hooks",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/api/subscribers/entityHooks.ts",
    },

    # ── 12. Event subscriber ───────────────────────────────────────────────
    {
        "normalized_code": """\
import { EventSubscriber, On } from 'event-dispatch';

import { Logger } from '../../lib/logger';
import { Xxx } from '../models/Xxx';
import { entityHooks } from './entityHooks';

const log = new Logger(__filename);

@EventSubscriber()
export class XxxEventSubscriber {
  @On(entityHooks.xxx.created)
  public onXxxCreate(xxx: Xxx): void {
    log.info('Xxx ' + xxx.toString() + ' created!');
  }
}\
""",
        "function": "event_subscriber_on_entity_created",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/api/subscribers/XxxEventSubscriber.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CUSTOM DECORATORS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. Logger parameter decorator via Typedi Container ─────────────────
    {
        "normalized_code": """\
import { Container } from 'typedi';

import { Logger as WinstonLogger } from '../lib/logger/Logger';

export function Logger(scope: string): ParameterDecorator {
  return (
    object: Record<string, unknown>,
    propertyKey: string | symbol,
    index: number,
  ): void => {
    const logger = new WinstonLogger(scope);
    Container.registerHandler({
      object: object as Record<string, unknown>,
      propertyName: propertyKey as string,
      index,
      value: () => logger,
    });
  };
}

export interface LoggerInterface {
  debug(msg: string, ...args: unknown[]): void;
  info(msg: string, ...args: unknown[]): void;
  warn(msg: string, ...args: unknown[]): void;
  error(msg: string, ...args: unknown[]): void;
}\
""",
        "function": "decorator_parameter_logger_typedi_container",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/decorators/Logger.ts",
    },

    # ── 14. Event dispatcher parameter decorator via Typedi ─────────────────
    {
        "normalized_code": """\
import { Container } from 'typedi';
import { EventDispatcher as EventDispatcherClass } from 'event-dispatch';

export function EventDispatcher(): ParameterDecorator {
  return (
    object: Record<string, unknown>,
    propertyKey: string | symbol,
    index: number,
  ): void => {
    const eventDispatcher = new EventDispatcherClass();
    Container.registerHandler({
      object: object as Record<string, unknown>,
      propertyName: propertyKey as string,
      index,
      value: () => eventDispatcher,
    });
  };
}

export interface EventDispatcherInterface {
  dispatch(eventName: string, data: unknown): void;
}\
""",
        "function": "decorator_parameter_event_dispatcher_typedi",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/decorators/EventDispatcher.ts",
    },

    # ── 15. Generic DataLoader parameter decorator via Typedi ───────────────
    {
        "normalized_code": """\
import { Container } from 'typedi';
import DataLoader from 'dataloader';

export interface ObjectType<T> {
  new (): T;
}

export interface CreateDataLoaderOptions {
  method?: string;
  key?: string;
  multiple?: boolean;
}

export function DLoader<T>(
  obj: ObjectType<T>,
  options: CreateDataLoaderOptions = {},
): ParameterDecorator {
  return (
    object: Record<string, unknown>,
    propertyKey: string | symbol,
    index: number,
  ): void => {
    const dataLoader = createDataLoader(obj, options);
    Container.registerHandler({
      object: object as Record<string, unknown>,
      propertyName: propertyKey as string,
      index,
      value: () => dataLoader,
    });
  };
}\
""",
        "function": "decorator_parameter_dataloader_typedi_generic",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/decorators/DLoader.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # GRAPHQL
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. GraphQL ObjectType with type-graphql ────────────────────────────
    {
        "normalized_code": """\
import { Field, ID, ObjectType } from 'type-graphql';

import { Pet } from './Pet';

@ObjectType({ description: 'Xxx object.' })
export class Xxx {
  @Field(() => ID)
  public id: string;

  @Field({ description: 'The first name of the xxx.' })
  public firstName: string;

  @Field({ description: 'The last name of the xxx.' })
  public lastName: string;

  @Field({ description: 'The email of the xxx.' })
  public email: string;

  @Field(() => [Pet], {
    description: 'A list of pets which belong to the xxx.',
  })
  public pets: Pet[];
}\
""",
        "function": "graphql_object_type_type_graphql",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/api/types/Xxx.ts",
    },

    # ── 17. GraphQL InputType ───────────────────────────────────────────────
    {
        "normalized_code": """\
import { Field, InputType, Int } from 'type-graphql';

import { Pet } from '../../models/Pet';

@InputType()
export class PetInput implements Partial<Pet> {
  @Field()
  public name: string;

  @Field(() => Int, { description: 'The age of the pet in years.' })
  public age: number;
}\
""",
        "function": "graphql_input_type",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/api/types/input/PetInput.ts",
    },

    # ── 18. GraphQL resolver with @Query + @FieldResolver ──────────────────
    {
        "normalized_code": """\
import {
  FieldResolver,
  Query,
  Resolver,
  Root,
} from 'type-graphql';
import { Service } from 'typedi';

import { Pet } from '../models/Pet';
import { Xxx as XxxModel } from '../models/Xxx';
import { PetService } from '../services/PetService';
import { XxxService } from '../services/XxxService';
import { Xxx } from '../types/Xxx';

@Service()
@Resolver(() => Xxx)
export class XxxResolver {
  constructor(
    private xxxService: XxxService,
    private petService: PetService,
  ) {}

  @Query(() => [Xxx])
  public xxxs(): Promise<XxxModel[]> {
    return this.xxxService.find();
  }

  @FieldResolver()
  public async pets(@Root() xxx: XxxModel): Promise<Pet[]> {
    return this.petService.findByXxx(xxx);
  }
}\
""",
        "function": "graphql_resolver_query_fieldresolver",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/api/resolvers/XxxResolver.ts",
    },

    # ── 19. GraphQL resolver with @Mutation + DataLoader ───────────────────
    {
        "normalized_code": """\
import DataLoader from 'dataloader';
import {
  Arg,
  Ctx,
  FieldResolver,
  Mutation,
  Query,
  Resolver,
  Root,
} from 'type-graphql';
import { Service } from 'typedi';

import { DLoader } from '../../decorators/DLoader';
import { Logger, LoggerInterface } from '../../decorators/Logger';
import { Xxx as XxxModel } from '../models/Xxx';
import { Pet as PetModel } from '../models/Pet';
import { PetService } from '../services/PetService';
import { Pet } from '../types/Pet';
import { PetInput } from '../types/input/PetInput';

interface GqlContext {
  requestId: number;
}

@Service()
@Resolver(() => Pet)
export class PetResolver {
  constructor(
    private petService: PetService,
    @Logger(__filename) private log: LoggerInterface,
    @DLoader(XxxModel) private xxxLoader: DataLoader<string, XxxModel>,
  ) {}

  @Query(() => [Pet])
  public pets(@Ctx() { requestId }: GqlContext): Promise<PetModel[]> {
    this.log.info(`PetResolver: requestId=${requestId}`);
    return this.petService.find();
  }

  @Mutation(() => Pet)
  public async addPet(@Arg('pet') pet: PetInput): Promise<PetModel> {
    const newPet = new PetModel();
    newPet.name = pet.name;
    newPet.age = pet.age;
    return this.petService.create(newPet);
  }

  @FieldResolver()
  public async owner(@Root() pet: PetModel): Promise<XxxModel | undefined> {
    if (pet.xxxId) {
      return this.xxxLoader.load(pet.xxxId);
    }
    return undefined;
  }
}\
""",
        "function": "graphql_resolver_mutation_dataloader_context",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/api/resolvers/PetResolver.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 20. Authorization checker HOF ──────────────────────────────────────
    {
        "normalized_code": """\
import { Action } from 'routing-controllers';
import { Container } from 'typedi';
import { Connection } from 'typeorm';

import { Logger } from '../lib/logger';
import { AuthService } from './AuthService';

export function authorizationChecker(
  connection: Connection,
): (action: Action, roles: string[]) => Promise<boolean> | boolean {
  const log = new Logger(__filename);
  const authService = Container.get<AuthService>(AuthService);

  return async function innerAuthorizationChecker(
    action: Action,
    roles: string[],
  ): Promise<boolean> {
    const credentials = authService.parseBasicAuthFromRequest(
      action.request,
    );
    if (credentials === undefined) {
      log.warn('No credentials given');
      return false;
    }
    action.request.xxx = await authService.validateXxx(
      credentials.name,
      credentials.password,
    );
    if (action.request.xxx === undefined) {
      log.warn('Invalid credentials given');
      return false;
    }
    log.info('Successfully checked credentials');
    return true;
  };
}\
""",
        "function": "auth_authorization_checker_hof",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/auth/authorizationChecker.ts",
    },

    # ── 21. Auth service — Basic Auth parse + validate ─────────────────────
    {
        "normalized_code": """\
import express from 'express';
import { Service } from 'typedi';
import { OrmRepository } from 'typeorm-typedi-extensions';

import { Logger, LoggerInterface } from '../decorators/Logger';
import { Xxx } from '../api/models/Xxx';
import { XxxRepository } from '../api/repositories/XxxRepository';

@Service()
export class AuthService {
  constructor(
    @Logger(__filename) private log: LoggerInterface,
    @OrmRepository() private xxxRepository: XxxRepository,
  ) {}

  public parseBasicAuthFromRequest(
    req: express.Request,
  ): { name: string; password: string } | undefined {
    const authorization = req.header('authorization');
    if (
      authorization &&
      authorization.split(' ')[0] === 'Basic'
    ) {
      const decodedBase64 = Buffer.from(
        authorization.split(' ')[1],
        'base64',
      ).toString('ascii');
      const name = decodedBase64.split(':')[0];
      const password = decodedBase64.split(':')[1];
      if (name && password) {
        return { name, password };
      }
    }
    return undefined;
  }

  public async validateXxx(
    name: string,
    password: string,
  ): Promise<Xxx | undefined> {
    const xxx = await this.xxxRepository.findOne({
      where: { email: name },
    });
    if (xxx && (await Xxx.comparePassword(xxx, password))) {
      return xxx;
    }
    return undefined;
  }
}\
""",
        "function": "auth_service_basic_auth_parse_validate",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/auth/AuthService.ts",
    },

    # ── 22. Current entity checker from request ────────────────────────────
    {
        "normalized_code": """\
import { Action } from 'routing-controllers';
import { Connection } from 'typeorm';

import { Xxx } from '../api/models/Xxx';

export function currentXxxChecker(
  connection: Connection,
): (action: Action) => Promise<Xxx | undefined> {
  return async function innerCurrentXxxChecker(
    action: Action,
  ): Promise<Xxx | undefined> {
    return action.request.xxx;
  };
}\
""",
        "function": "auth_current_checker_from_request",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "src/auth/currentXxxChecker.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DATABASE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 23. TypeORM migration — create table ───────────────────────────────
    {
        "normalized_code": """\
import { MigrationInterface, QueryRunner, Table } from 'typeorm';

export class CreateXxxTable implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    const table = new Table({
      name: 'xxx',
      columns: [
        {
          name: 'id',
          type: 'varchar',
          length: '255',
          isPrimary: true,
        },
        {
          name: 'first_name',
          type: 'varchar',
          length: '255',
        },
        {
          name: 'last_name',
          type: 'varchar',
          length: '255',
        },
        {
          name: 'email',
          type: 'varchar',
          length: '255',
        },
        {
          name: 'password',
          type: 'varchar',
          length: '255',
        },
      ],
    });
    await queryRunner.createTable(table);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.dropTable('xxx');
  }
}\
""",
        "function": "typeorm_migration_create_table",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/database/migrations/CreateXxxTable.ts",
    },

    # ── 24. Database seed with factory pattern ─────────────────────────────
    {
        "normalized_code": """\
import { Factory, Seed } from 'typeorm-seeding';
import { Connection } from 'typeorm';

import { Xxx } from '../../api/models/Xxx';

export class CreateXxxs implements Seed {
  public async seed(
    factory: Factory,
    connection: Connection,
  ): Promise<void> {
    await factory(Xxx)().seedMany(10);
  }
}\
""",
        "function": "database_seed_factory_faker",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "src/database/seeds/CreateXxxs.ts",
    },

    # ── 25. Entity factory with Faker ──────────────────────────────────────
    {
        "normalized_code": """\
import * as uuid from 'uuid';
import { define } from 'typeorm-seeding';
import Faker from 'faker';

import { Xxx } from '../../api/models/Xxx';

define(Xxx, (faker: typeof Faker) => {
  const gender = faker.random.number(1);
  const firstName = faker.name.firstName(gender);
  const lastName = faker.name.lastName(gender);
  const xxx = new Xxx();
  xxx.id = uuid.v1();
  xxx.firstName = firstName;
  xxx.lastName = lastName;
  xxx.email = faker.internet.email(firstName, lastName);
  xxx.password = '1234';
  return xxx;
});\
""",
        "function": "database_factory_faker_entity",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "src/database/factories/XxxFactory.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 26. Centralized env config with type-safe getters ──────────────────
    {
        "normalized_code": """\
import * as pkg from '../package.json';

export const env = {
  node: process.env.NODE_ENV || 'development',
  isProduction: process.env.NODE_ENV === 'production',
  isTest: process.env.NODE_ENV === 'test',
  isDevelopment: process.env.NODE_ENV === 'development',
  app: {
    name: getOsEnv('APP_NAME'),
    version: (pkg as Record<string, string>).version,
    port: normalizePort(process.env.PORT || getOsEnv('APP_PORT')),
    routePrefix: getOsEnv('APP_ROUTE_PREFIX'),
    dirs: {
      migrations: getOsPaths('TYPEORM_MIGRATIONS'),
      entities: getOsPaths('TYPEORM_ENTITIES'),
      controllers: getOsPaths('CONTROLLERS'),
      middlewares: getOsPaths('MIDDLEWARES'),
      interceptors: getOsPaths('INTERCEPTORS'),
      subscribers: getOsPaths('SUBSCRIBERS'),
      resolvers: getOsPaths('RESOLVERS'),
    },
  },
  log: {
    level: getOsEnv('LOG_LEVEL'),
    output: getOsEnv('LOG_OUTPUT'),
  },
  db: {
    type: getOsEnv('TYPEORM_CONNECTION'),
    host: getOsEnvOptional('TYPEORM_HOST'),
    port: toNumber(getOsEnvOptional('TYPEORM_PORT') || '3306'),
    database: getOsEnv('TYPEORM_DATABASE'),
  },
  graphql: {
    enabled: toBool(getOsEnv('GRAPHQL_ENABLED')),
    route: getOsEnv('GRAPHQL_ROUTE'),
    editor: toBool(getOsEnv('GRAPHQL_EDITOR')),
  },
  swagger: {
    enabled: toBool(getOsEnv('SWAGGER_ENABLED')),
    route: getOsEnv('SWAGGER_ROUTE'),
  },
};

function getOsEnv(key: string): string {
  if (process.env[key] === undefined) {
    throw new Error(`Environment variable ${key} is not set.`);
  }
  return process.env[key] as string;
}

function getOsEnvOptional(key: string): string | undefined {
  return process.env[key];
}

function getOsPaths(key: string): string[] {
  return (process.env[key] && process.env[key]!.split(',')) || [];
}

function toNumber(value: string): number {
  return parseInt(value, 10);
}

function toBool(value: string): boolean {
  return value === 'true';
}

function normalizePort(port: string): number | string | boolean {
  const parsedPort = parseInt(port, 10);
  if (isNaN(parsedPort)) return port;
  if (parsedPort >= 0) return parsedPort;
  return false;
}\
""",
        "function": "config_centralized_env_typed",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/env.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # LOADERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 27. IoC container loader — Typedi ──────────────────────────────────
    {
        "normalized_code": """\
import { MicroframeworkLoader, MicroframeworkSettings } from 'microframework-w3tec';
import { useContainer as routingUseContainer } from 'routing-controllers';
import { useContainer as ormUseContainer } from 'typeorm';
import { useContainer as classValidatorUseContainer } from 'class-validator';
import { useContainer as typeGraphQLUseContainer } from 'type-graphql';
import { Container } from 'typedi';

export const iocLoader: MicroframeworkLoader = (
  settings: MicroframeworkSettings | undefined,
): void => {
  routingUseContainer(Container);
  ormUseContainer(Container);
  classValidatorUseContainer(Container);
  typeGraphQLUseContainer(Container);
};\
""",
        "function": "loader_ioc_container_typedi",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/loaders/iocLoader.ts",
    },

    # ── 28. Express server loader with routing-controllers ─────────────────
    {
        "normalized_code": """\
import { Application } from 'express';
import {
  MicroframeworkLoader,
  MicroframeworkSettings,
} from 'microframework-w3tec';
import { createExpressServer } from 'routing-controllers';

import { authorizationChecker } from '../auth/authorizationChecker';
import { currentXxxChecker } from '../auth/currentXxxChecker';
import { env } from '../env';

export const expressLoader: MicroframeworkLoader = (
  settings: MicroframeworkSettings | undefined,
): void => {
  if (settings) {
    const connection = settings.getData('connection');
    const expressApp: Application = createExpressServer({
      cors: true,
      classTransformer: true,
      routePrefix: env.app.routePrefix,
      defaultErrorHandler: false,
      controllers: env.app.dirs.controllers,
      middlewares: env.app.dirs.middlewares,
      interceptors: env.app.dirs.interceptors,
      authorizationChecker: authorizationChecker(connection),
      currentUserChecker: currentXxxChecker(connection),
    });

    if (!env.isTest) {
      const server = expressApp.listen(env.app.port);
      settings.setData('express_server', server);
    }
    settings.setData('express_app', expressApp);
  }
};\
""",
        "function": "loader_express_server_create",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/loaders/expressLoader.ts",
    },

    # ── 29. TypeORM connection loader ──────────────────────────────────────
    {
        "normalized_code": """\
import {
  MicroframeworkLoader,
  MicroframeworkSettings,
} from 'microframework-w3tec';
import {
  createConnection,
  getConnectionOptions,
} from 'typeorm';

import { env } from '../env';

export const typeormLoader: MicroframeworkLoader = async (
  settings: MicroframeworkSettings | undefined,
): Promise<void> => {
  const loadedConnectionOptions = await getConnectionOptions();
  const connectionOptions = Object.assign(
    loadedConnectionOptions,
    {
      type: env.db.type as string,
      host: env.db.host,
      port: env.db.port,
      database: env.db.database,
      entities: env.app.dirs.entities,
      migrations: env.app.dirs.migrations,
    },
  );

  const connection = await createConnection(connectionOptions);

  if (settings) {
    settings.setData('connection', connection);
    settings.onShutdown(() => connection.close());
  }
};\
""",
        "function": "loader_typeorm_connection",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/loaders/typeormLoader.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # BOOT
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 30. Microframework bootstrap with loader chain ─────────────────────
    {
        "normalized_code": """\
import 'reflect-metadata';
import { bootstrapMicroframework } from 'microframework-w3tec';

import { Logger } from './lib/logger';
import { banner } from './lib/banner';
import { eventDispatchLoader } from './loaders/eventDispatchLoader';
import { expressLoader } from './loaders/expressLoader';
import { graphqlLoader } from './loaders/graphqlLoader';
import { homeLoader } from './loaders/homeLoader';
import { iocLoader } from './loaders/iocLoader';
import { monitorLoader } from './loaders/monitorLoader';
import { publicLoader } from './loaders/publicLoader';
import { swaggerLoader } from './loaders/swaggerLoader';
import { typeormLoader } from './loaders/typeormLoader';
import { winstonLoader } from './loaders/winstonLoader';

const log = new Logger(__filename);

bootstrapMicroframework({
  loaders: [
    winstonLoader,
    iocLoader,
    eventDispatchLoader,
    typeormLoader,
    expressLoader,
    swaggerLoader,
    monitorLoader,
    homeLoader,
    publicLoader,
    graphqlLoader,
  ],
})
  .then(() => banner(log))
  .catch((error: Error) =>
    log.error('Application is crashed: ' + error),
  );\
""",
        "function": "microframework_bootstrap_loader_chain",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/app.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 31. Custom HTTP error — not found ──────────────────────────────────
    {
        "normalized_code": """\
import { HttpError } from 'routing-controllers';

export class XxxNotFoundError extends HttpError {
  constructor() {
    super(404, 'Xxx not found!');
  }
}\
""",
        "function": "custom_http_error_not_found",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/api/errors/XxxNotFoundError.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "TypeORM entity with decorators validation bcrypt password hashing",
    "Repository pattern extending base TypeORM Repository",
    "Service with TypeDI dependency injection CRUD operations",
    "Controller with routing-controllers decorators authorized CRUD",
    "Express middleware before logging morgan pattern",
    "Express error handler middleware after",
    "Custom parameter decorator TypeDI Container registerHandler",
    "GraphQL resolver with query mutation type-graphql",
    "Authorization checker higher-order function basic auth",
    "TypeORM migration create table up down",
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
