"""
ingest_nestjs_nest.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns architecturaux de nestjs/nest (sample/ directory) dans la KB Qdrant V6.

SCOPE: Uniquement patterns architecturaux réutilisables du dossier sample/.
       36 sample projects — modules, controllers, services, guards, pipes,
       interceptors, filters, middleware, decorators, gateways, microservices,
       auth JWT, TypeORM, serializer, dynamic modules, file upload, cache.

Usage:
    .venv/bin/python3 ingest_nestjs_nest.py
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
REPO_URL = "https://github.com/nestjs/nest.git"
REPO_NAME = "nestjs/nest"
REPO_LOCAL = "/tmp/nestjs_nest"
LANGUAGE = "typescript"
FRAMEWORK = "nestjs"
STACK = "nestjs+typescript+decorators+di"
CHARTE_VERSION = "1.0"
TAG = "nestjs/nest"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/nestjs/nest"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Cat→Xxx, cat→xxx, cats→xxxs, User→Xxx, user→xxx, users→xxxs
# T-1: no `: any`. T-2: no `var`. T-3: no console.log().
# Kept: NestJS decorator names (@Module, @Controller, @Injectable, etc.),
#       technical terms (email, password, profile, token, role)

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # 01-cats-app — CORE PATTERNS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Module decorator ─────────────────────────────────────────────────
    {
        "normalized_code": """\
import { Module } from '@nestjs/common';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

@Module({
  controllers: [XxxController],
  providers: [XxxService],
})
export class XxxModule {}
""",
        "function": "nestjs_module_decorator",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/cats/cats.module.ts",
    },

    # ── 2. Controller CRUD decorators ───────────────────────────────────────
    {
        "normalized_code": """\
import { Body, Controller, Get, Param, Post, UseGuards } from '@nestjs/common';
import { Roles } from '../common/decorators/roles.decorator';
import { RolesGuard } from '../common/guards/roles.guard';
import { ParseIntPipe } from '../common/pipes/parse-int.pipe';
import { XxxService } from './xxx.service';
import { CreateXxxDto } from './dto/create-xxx.dto';
import { Xxx } from './interfaces/xxx.interface';

@UseGuards(RolesGuard)
@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  @Roles(['admin'])
  async create(@Body() createXxxDto: CreateXxxDto): Promise<void> {
    this.xxxService.create(createXxxDto);
  }

  @Get()
  async findAll(): Promise<Xxx[]> {
    return this.xxxService.findAll();
  }

  @Get(':id')
  findOne(
    @Param('id', new ParseIntPipe())
    id: number,
  ): void {
    // Retrieve instance by ID
  }
}
""",
        "function": "nestjs_controller_crud_decorators",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "sample/01-cats-app/src/cats/cats.controller.ts",
    },

    # ── 3. Injectable service ───────────────────────────────────────────────
    {
        "normalized_code": """\
import { Injectable } from '@nestjs/common';
import { Xxx } from './interfaces/xxx.interface';

@Injectable()
export class XxxService {
  private readonly xxxs: Xxx[] = [];

  create(xxx: Xxx): void {
    this.xxxs.push(xxx);
  }

  findAll(): Promise<Xxx[]> {
    return Promise.resolve(this.xxxs);
  }
}
""",
        "function": "nestjs_injectable_service",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "sample/01-cats-app/src/cats/cats.service.ts",
    },

    # ── 4. DTO class-validator ──────────────────────────────────────────────
    {
        "normalized_code": """\
import { IsInt, IsString } from 'class-validator';

export class CreateXxxDto {
  @IsString()
  readonly name: string;

  @IsInt()
  readonly age: number;

  @IsString()
  readonly breed: string;
}
""",
        "function": "nestjs_dto_class_validator",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "sample/01-cats-app/src/cats/dto/create-xxx.dto.ts",
    },

    # ── 5. Entity interface ─────────────────────────────────────────────────
    {
        "normalized_code": """\
export interface Xxx {
  name: string;
  age: number;
  breed: string;
}
""",
        "function": "nestjs_interface_entity",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "sample/01-cats-app/src/cats/interfaces/xxx.interface.ts",
    },

    # ── 6. Guard roles CanActivate ──────────────────────────────────────────
    {
        "normalized_code": """\
import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Roles } from '../decorators/roles.decorator';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const roles = this.reflector.get(Roles, context.getHandler());
    if (!roles) {
      return true;
    }
    const request = context.switchToHttp().getRequest();
    const xxx = request.xxx;
    const hasRole = (): boolean =>
      xxx.roles.some((role: string) => !!roles.find((r: string) => r === role));

    return xxx && xxx.roles && hasRole();
  }
}
""",
        "function": "nestjs_guard_roles_canactivate",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/guards/roles.guard.ts",
    },

    # ── 7. Custom decorator Reflector ───────────────────────────────────────
    {
        "normalized_code": """\
import { Reflector } from '@nestjs/core';

export const Roles = Reflector.createDecorator<string[]>();
""",
        "function": "nestjs_custom_decorator_reflector",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/decorators/roles.decorator.ts",
    },

    # ── 8. Pipe ParseInt transform ──────────────────────────────────────────
    {
        "normalized_code": """\
import {
  ArgumentMetadata,
  BadRequestException,
  Injectable,
  PipeTransform,
} from '@nestjs/common';

@Injectable()
export class ParseIntPipe implements PipeTransform<string> {
  async transform(value: string, metadata: ArgumentMetadata): Promise<number> {
    const val = parseInt(value, 10);
    if (isNaN(val)) {
      throw new BadRequestException('Validation failed');
    }
    return val;
  }
}
""",
        "function": "nestjs_pipe_parse_int_transform",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/pipes/parse-int.pipe.ts",
    },

    # ── 9. Pipe validation class-validator ──────────────────────────────────
    {
        "normalized_code": """\
import {
  ArgumentMetadata,
  BadRequestException,
  Injectable,
  PipeTransform,
  Type,
} from '@nestjs/common';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';

@Injectable()
export class ValidationPipe implements PipeTransform<unknown> {
  async transform(value: unknown, metadata: ArgumentMetadata): Promise<unknown> {
    const { metatype } = metadata;
    if (!metatype || !this.toValidate(metatype)) {
      return value;
    }
    const object = plainToInstance(metatype, value);
    const errors = await validate(object as object);
    if (errors.length > 0) {
      throw new BadRequestException('Validation failed');
    }
    return value;
  }

  private toValidate(metatype: Type<unknown>): boolean {
    const types: Array<Type<unknown>> = [String, Boolean, Number, Array, Object];
    return !types.find((t) => metatype === t);
  }
}
""",
        "function": "nestjs_pipe_validation_class_validator",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/pipes/validation.pipe.ts",
    },

    # ── 10. Exception filter HttpException ──────────────────────────────────
    {
        "normalized_code": """\
import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
} from '@nestjs/common';

@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter<HttpException> {
  catch(exception: HttpException, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse();
    const request = ctx.getRequest();
    const statusCode = exception.getStatus();

    response.status(statusCode).json({
      statusCode,
      timestamp: new Date().toISOString(),
      path: request.url,
    });
  }
}
""",
        "function": "nestjs_exception_filter_http",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/filters/http-exception.filter.ts",
    },

    # ── 11. Interceptor errors RxJS ─────────────────────────────────────────
    {
        "normalized_code": """\
import {
  CallHandler,
  ExecutionContext,
  HttpException,
  HttpStatus,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

@Injectable()
export class ErrorsInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next
      .handle()
      .pipe(
        catchError(() =>
          throwError(
            () => new HttpException('Gateway error', HttpStatus.BAD_GATEWAY),
          ),
        ),
      );
  }
}
""",
        "function": "nestjs_interceptor_errors_rxjs",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/interceptors/exception.interceptor.ts",
    },

    # ── 12. Interceptor timeout RxJS ────────────────────────────────────────
    {
        "normalized_code": """\
import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { timeout } from 'rxjs/operators';

@Injectable()
export class TimeoutInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(timeout(5000));
  }
}
""",
        "function": "nestjs_interceptor_timeout_rxjs",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/interceptors/timeout.interceptor.ts",
    },

    # ── 13. Interceptor transform response ──────────────────────────────────
    {
        "normalized_code": """\
import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface Response<T> {
  data: T;
}

@Injectable()
export class TransformInterceptor<T>
  implements NestInterceptor<T, Response<T>>
{
  intercept(
    context: ExecutionContext,
    next: CallHandler<T>,
  ): Observable<Response<T>> {
    return next.handle().pipe(map((data) => ({ data })));
  }
}
""",
        "function": "nestjs_interceptor_transform_response",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/core/interceptors/transform.interceptor.ts",
    },

    # ── 14. Middleware class ────────────────────────────────────────────────
    {
        "normalized_code": """\
import { Injectable, NestMiddleware } from '@nestjs/common';

@Injectable()
export class LoggerMiddleware implements NestMiddleware {
  use(req: Record<string, unknown>, res: Record<string, unknown>, next: () => void): void {
    next();
  }
}
""",
        "function": "nestjs_middleware_class",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/common/middleware/logger.middleware.ts",
    },

    # ── 15. Core module global interceptors ─────────────────────────────────
    {
        "normalized_code": """\
import { Module } from '@nestjs/common';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { LoggingInterceptor } from './interceptors/logging.interceptor';
import { TransformInterceptor } from './interceptors/transform.interceptor';

@Module({
  providers: [
    { provide: APP_INTERCEPTOR, useClass: TransformInterceptor },
    { provide: APP_INTERCEPTOR, useClass: LoggingInterceptor },
  ],
})
export class CoreModule {}
""",
        "function": "nestjs_core_module_global_interceptors",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/core/core.module.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 02-gateways — WEBSOCKET
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. WebSocket gateway ───────────────────────────────────────────────
    {
        "normalized_code": """\
import {
  MessageBody,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  WsResponse,
} from '@nestjs/websockets';
import { from, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { Server } from 'socket.io';

@WebSocketGateway({ cors: { origin: '*' } })
export class WsGateway {
  @WebSocketServer()
  server: Server;

  @SubscribeMessage('data')
  findAll(@MessageBody() data: number): Observable<WsResponse<number>> {
    return from([1, 2, 3]).pipe(
      map((el) => ({ event: 'data', data: el })),
    );
  }

  @SubscribeMessage('identity')
  async identity(@MessageBody() data: number): Promise<number> {
    return data;
  }
}
""",
        "function": "nestjs_websocket_gateway",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "sample/02-gateways/src/events/events.gateway.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 03-microservices — TCP/MESSAGE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 17. Microservice message pattern ────────────────────────────────────
    {
        "normalized_code": """\
import { Controller, Get, Inject } from '@nestjs/common';
import { ClientProxy, MessagePattern } from '@nestjs/microservices';
import { Observable } from 'rxjs';

const MATH_SERVICE = 'MATH_SERVICE';

@Controller()
export class MathController {
  constructor(@Inject(MATH_SERVICE) private readonly client: ClientProxy) {}

  @Get()
  execute(): Observable<number> {
    const pattern = { cmd: 'sum' };
    const data = [1, 2, 3, 4, 5];
    return this.client.send<number>(pattern, data);
  }

  @MessagePattern({ cmd: 'sum' })
  sum(data: number[]): number {
    return (data || []).reduce((a, b) => a + b);
  }
}
""",
        "function": "nestjs_microservice_message_pattern",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "sample/03-microservices/src/math/math.controller.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 19-auth-jwt — JWT AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 18. Auth JWT guard bearer ───────────────────────────────────────────
    {
        "normalized_code": """\
import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { JwtService } from '@nestjs/jwt';
import { Request } from 'express';
import { IS_PUBLIC_KEY } from './decorators/public.decorator';

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private jwtService: JwtService,
    private reflector: Reflector,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) {
      return true;
    }

    const request = context.switchToHttp().getRequest<Request>();
    const token = this.extractTokenFromHeader(request);
    if (!token) {
      throw new UnauthorizedException();
    }
    try {
      const payload = await this.jwtService.verifyAsync(token, {
        secret: process.env.JWT_SECRET || 'secret',
      });
      request['xxx'] = payload;
    } catch {
      throw new UnauthorizedException();
    }
    return true;
  }

  private extractTokenFromHeader(request: Request): string | undefined {
    const [authType, token] = request.headers.authorization?.split(' ') ?? [];
    return authType === 'Bearer' ? token : undefined;
  }
}
""",
        "function": "nestjs_auth_jwt_guard_bearer",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/19-auth-jwt/src/auth/auth.guard.ts",
    },

    # ── 19. Auth service JWT signIn ─────────────────────────────────────────
    {
        "normalized_code": """\
import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { XxxService } from '../xxxs/xxx.service';

@Injectable()
export class AuthService {
  constructor(
    private xxxService: XxxService,
    private jwtService: JwtService,
  ) {}

  async signIn(
    name: string,
    pass: string,
  ): Promise<{ access_token: string }> {
    const xxx = await this.xxxService.findOne(name);
    if (xxx?.password !== pass) {
      throw new UnauthorizedException();
    }
    const payload = { name: xxx.name, sub: xxx.id };
    return {
      access_token: await this.jwtService.signAsync(payload),
    };
  }
}
""",
        "function": "nestjs_auth_service_jwt_signin",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/19-auth-jwt/src/auth/auth.service.ts",
    },

    # ── 20. Auth module JWT global guard ────────────────────────────────────
    {
        "normalized_code": """\
import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { JwtModule } from '@nestjs/jwt';
import { XxxModule } from '../xxxs/xxx.module';
import { AuthController } from './auth.controller';
import { AuthGuard } from './auth.guard';
import { AuthService } from './auth.service';

@Module({
  imports: [
    XxxModule,
    JwtModule.register({
      global: true,
      secret: process.env.JWT_SECRET || 'secret',
      signOptions: { expiresIn: '60s' },
    }),
  ],
  providers: [
    AuthService,
    { provide: APP_GUARD, useClass: AuthGuard },
  ],
  controllers: [AuthController],
  exports: [AuthService],
})
export class AuthModule {}
""",
        "function": "nestjs_auth_module_jwt_global_guard",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/19-auth-jwt/src/auth/auth.module.ts",
    },

    # ── 21. Public decorator SetMetadata ────────────────────────────────────
    {
        "normalized_code": """\
import { SetMetadata } from '@nestjs/common';

export const IS_PUBLIC_KEY = 'isPublic';
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);
""",
        "function": "nestjs_public_decorator_setmetadata",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/19-auth-jwt/src/auth/decorators/public.decorator.ts",
    },

    # ── 22. Auth controller public + protected ──────────────────────────────
    {
        "normalized_code": """\
import { Body, Controller, Get, HttpCode, HttpStatus, Post, Request } from '@nestjs/common';
import { AuthService } from './auth.service';
import { Public } from './decorators/public.decorator';

@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @Public()
  @HttpCode(HttpStatus.OK)
  @Post('login')
  signIn(
    @Body() signInDto: Record<string, string>,
  ): Promise<{ access_token: string }> {
    return this.authService.signIn(signInDto.name, signInDto.password);
  }

  @Get('profile')
  getProfile(
    @Request() req: { xxx: Record<string, unknown> },
  ): Record<string, unknown> {
    return req.xxx;
  }
}
""",
        "function": "nestjs_auth_controller_public_protected",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "sample/19-auth-jwt/src/auth/auth.controller.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 05-sql-typeorm — TYPEORM INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 23. TypeORM entity decorators ───────────────────────────────────────
    {
        "normalized_code": """\
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';

@Entity()
export class Xxx {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  firstName: string;

  @Column()
  lastName: string;

  @Column({ default: true })
  isActive: boolean;
}
""",
        "function": "nestjs_typeorm_entity_decorators",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "sample/05-sql-typeorm/src/users/user.entity.ts",
    },

    # ── 24. TypeORM service repository inject ───────────────────────────────
    {
        "normalized_code": """\
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CreateXxxDto } from './dto/create-xxx.dto';
import { Xxx } from './xxx.entity';

@Injectable()
export class XxxService {
  constructor(
    @InjectRepository(Xxx)
    private readonly xxxRepository: Repository<Xxx>,
  ) {}

  create(createXxxDto: CreateXxxDto): Promise<Xxx> {
    const xxx = new Xxx();
    xxx.firstName = createXxxDto.firstName;
    xxx.lastName = createXxxDto.lastName;
    return this.xxxRepository.save(xxx);
  }

  async findAll(): Promise<Xxx[]> {
    return this.xxxRepository.find();
  }

  findOne(id: number): Promise<Xxx> {
    return this.xxxRepository.findOneBy({ id });
  }

  async remove(id: string): Promise<void> {
    await this.xxxRepository.delete(id);
  }
}
""",
        "function": "nestjs_typeorm_service_repository_inject",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "sample/05-sql-typeorm/src/users/users.service.ts",
    },

    # ── 25. TypeORM module forFeature ───────────────────────────────────────
    {
        "normalized_code": """\
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Xxx } from './xxx.entity';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

@Module({
  imports: [TypeOrmModule.forFeature([Xxx])],
  providers: [XxxService],
  controllers: [XxxController],
})
export class XxxModule {}
""",
        "function": "nestjs_typeorm_module_for_feature",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/05-sql-typeorm/src/users/users.module.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 21-serializer — CLASS-TRANSFORMER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 26. Serializer exclude expose transform ─────────────────────────────
    {
        "normalized_code": """\
import { Exclude, Expose, Transform } from 'class-transformer';

export class RoleEntity {
  id: number;
  name: string;

  constructor(partial: Partial<RoleEntity>) {
    Object.assign(this, partial);
  }
}

export class XxxEntity {
  id: number;
  firstName: string;
  lastName: string;

  @Exclude()
  password: string;

  @Expose()
  get fullName(): string {
    return `${this.firstName} ${this.lastName}`;
  }

  @Transform(({ value }) => value.name)
  role: RoleEntity;

  constructor(partial: Partial<XxxEntity>) {
    Object.assign(this, partial);
  }
}
""",
        "function": "nestjs_serializer_exclude_expose_transform",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "sample/21-serializer/src/entities/xxx.entity.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 25-dynamic-modules — DYNAMIC MODULE PATTERN
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 27. Dynamic module register ─────────────────────────────────────────
    {
        "normalized_code": """\
import { DynamicModule, Module } from '@nestjs/common';
import { ConfigService } from './config.service';

const CONFIG_OPTIONS = 'CONFIG_OPTIONS';

export interface ConfigModuleOptions {
  folder: string;
}

@Module({})
export class ConfigModule {
  static register(options: ConfigModuleOptions): DynamicModule {
    return {
      module: ConfigModule,
      providers: [
        { provide: CONFIG_OPTIONS, useValue: options },
        ConfigService,
      ],
      exports: [ConfigService],
    };
  }
}
""",
        "function": "nestjs_dynamic_module_register",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/25-dynamic-modules/src/config/config.module.ts",
    },

    # ── 28. Dynamic config service inject ───────────────────────────────────
    {
        "normalized_code": """\
import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';
import { Inject, Injectable } from '@nestjs/common';

const CONFIG_OPTIONS = 'CONFIG_OPTIONS';

interface ConfigOptions {
  folder: string;
}

interface EnvConfig {
  [key: string]: string;
}

@Injectable()
export class ConfigService {
  private readonly envConfig: EnvConfig;

  constructor(@Inject(CONFIG_OPTIONS) options: ConfigOptions) {
    const filePath = `${process.env.NODE_ENV || 'development'}.env`;
    const envFile = path.resolve(__dirname, '../../', options.folder, filePath);
    this.envConfig = dotenv.parse(fs.readFileSync(envFile));
  }

  get(key: string): string {
    return this.envConfig[key];
  }
}
""",
        "function": "nestjs_dynamic_config_service_inject",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/25-dynamic-modules/src/config/config.service.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 29-file-upload — FILE UPLOAD
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 29. File upload interceptor pipe ────────────────────────────────────
    {
        "normalized_code": """\
import { Body, Controller, ParseFilePipeBuilder, Post, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';

interface SampleDto {
  name: string;
}

@Controller()
export class AppController {
  @UseInterceptors(FileInterceptor('file'))
  @Post('file')
  uploadFile(
    @Body() body: SampleDto,
    @UploadedFile() file: Express.Multer.File,
  ): { body: SampleDto; file: string } {
    return { body, file: file.buffer.toString() };
  }

  @UseInterceptors(FileInterceptor('file'))
  @Post('file/pass-validation')
  uploadFileAndPassValidation(
    @Body() body: SampleDto,
    @UploadedFile(
      new ParseFilePipeBuilder()
        .addFileTypeValidator({ fileType: 'jpeg' })
        .build({ fileIsRequired: false }),
    )
    file?: Express.Multer.File,
  ): { body: SampleDto; file: string | undefined } {
    return { body, file: file?.buffer.toString() };
  }
}
""",
        "function": "nestjs_file_upload_interceptor_pipe",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "sample/29-file-upload/src/app.controller.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 01-cats-app — BOOTSTRAP
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 30. Bootstrap validation pipe ───────────────────────────────────────
    {
        "normalized_code": """\
import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(new ValidationPipe());
  await app.listen(3000);
}
bootstrap();
""",
        "function": "nestjs_bootstrap_validation_pipe",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sample/01-cats-app/src/main.ts",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 20-cache — HTTP CACHE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 31. Cache interceptor HTTP ──────────────────────────────────────────
    {
        "normalized_code": """\
import { CacheInterceptor } from '@nestjs/cache-manager';
import { ExecutionContext, Injectable } from '@nestjs/common';

@Injectable()
export class HttpCacheInterceptor extends CacheInterceptor {
  trackBy(context: ExecutionContext): string | undefined {
    const request = context.switchToHttp().getRequest();
    const { httpAdapter } = this.httpAdapterHost;

    const isGetRequest = httpAdapter.getRequestMethod(request) === 'GET';
    const excludePaths: string[] = [];
    if (
      !isGetRequest ||
      (isGetRequest &&
        excludePaths.includes(httpAdapter.getRequestUrl(request)))
    ) {
      return undefined;
    }
    return httpAdapter.getRequestUrl(request);
  }
}
""",
        "function": "nestjs_cache_interceptor_http",
        "feature_type": "middleware",
        "file_role": "utility",
        "file_path": "sample/20-cache/src/http-cache.interceptor.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "NestJS module decorator with controllers and providers",
    "NestJS controller CRUD decorators Get Post Param Body",
    "NestJS injectable service dependency injection",
    "NestJS guard CanActivate role-based access control",
    "NestJS pipe PipeTransform validation class-validator",
    "NestJS exception filter Catch HttpException",
    "NestJS interceptor RxJS transform response",
    "NestJS WebSocket gateway SubscribeMessage",
    "NestJS JWT auth guard bearer token verification",
    "NestJS dynamic module register DynamicModule pattern",
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
