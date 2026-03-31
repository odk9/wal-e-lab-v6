"""
Wirings ingestion script for NestJS nest repository (TypeScript Hard).

Manual wirings extraction (no AST — TypeScript complexity too high).
9 wirings patterns: import_graph, dependency_chain, flow_pattern.

Constants:
- REPO_URL: https://github.com/nestjs/nest.git
- REPO_NAME: nestjs/nest
- LANGUAGE: typescript
- FRAMEWORK: nestjs
- STACK: nestjs+typescript+decorators+di
- COLLECTION: wirings
"""

import os
import sys
from datetime import datetime
import json
from pathlib import Path

# Ensure KB utilities are available
sys.path.insert(0, str(Path(__file__).parent))

try:
    import qdrant_client
    from qdrant_client.models import PointStruct, Distance, VectorParams
except ImportError:
    print("ERROR: qdrant-client not installed. Install with:")
    print("  .venv/bin/pip install qdrant-client")
    sys.exit(1)

try:
    from embedder import embed_documents_batch
except ImportError:
    print("ERROR: embedder module not found. Ensure embedder.py is in the same directory.")
    sys.exit(1)

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/nestjs/nest.git"
REPO_NAME = "nestjs/nest"
REPO_LOCAL = "/tmp/nest"
LANGUAGE = "typescript"
FRAMEWORK = "nestjs"
STACK = "nestjs+typescript+decorators+di"
CHARTE_VERSION = "1.0"
TAG = "wirings/nestjs/nest"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# Timestamp for all wirings in this batch
CREATED_AT = int(datetime.utcnow().timestamp())

# ============================================================================
# WIRINGS DEFINITIONS (9 manual patterns)
# ============================================================================

WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "NestJS module dependency tree: AppModule imports XxxModule, which registers XxxController and XxxService. Service injected into Controller via constructor DI.",
        "modules": [
            "app.module.ts",
            "xxx/xxx.module.ts",
            "xxx/xxx.controller.ts",
            "xxx/xxx.service.ts",
        ],
        "connections": [
            "app.module.ts imports XxxModule",
            "xxx.module.ts declares XxxController",
            "xxx.module.ts provides XxxService",
            "xxx.controller.ts injects XxxService via constructor",
        ],
        "code_example": """// xxx.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class XxxService {
  create(data: any) {
    return { id: 1, ...data };
  }
}

// xxx.controller.ts
import { Controller, Post, Body } from '@nestjs/common';
import { XxxService } from './xxx.service';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  create(@Body() createXxxDto: any) {
    return this.xxxService.create(createXxxDto);
  }
}

// xxx.module.ts
import { Module } from '@nestjs/common';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

@Module({
  controllers: [XxxController],
  providers: [XxxService],
})
export class XxxModule {}

// app.module.ts
import { Module } from '@nestjs/common';
import { XxxModule } from './xxx/xxx.module';

@Module({
  imports: [XxxModule],
})
export class AppModule {}
""",
        "pattern_scope": "nestjs_module",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Complete module file creation order in NestJS: interface → DTO → service → controller → module → app.module → main.ts",
        "modules": [
            "xxx.interface.ts",
            "dto/create-xxx.dto.ts",
            "xxx.service.ts",
            "xxx.controller.ts",
            "xxx.module.ts",
            "app.module.ts",
            "main.ts",
        ],
        "connections": [
            "create-xxx.dto.ts implements Xxx interface",
            "xxx.service.ts uses Xxx interface for types",
            "xxx.controller.ts calls xxx.service.ts methods",
            "xxx.module.ts exports XxxService and XxxController",
            "app.module.ts imports XxxModule",
            "main.ts creates AppModule",
        ],
        "code_example": """// xxx.interface.ts
export interface Xxx {
  id: number;
  name: string;
  description?: string;
}

// dto/create-xxx.dto.ts
import { IsString, IsNotEmpty, IsOptional } from 'class-validator';

export class CreateXxxDto {
  @IsString()
  @IsNotEmpty()
  name: string;

  @IsString()
  @IsOptional()
  description?: string;
}

// xxx.service.ts
import { Injectable } from '@nestjs/common';
import { Xxx } from './xxx.interface';
import { CreateXxxDto } from './dto/create-xxx.dto';

@Injectable()
export class XxxService {
  private xxxs: Xxx[] = [];
  private idCounter = 1;

  create(createXxxDto: CreateXxxDto): Xxx {
    const xxx: Xxx = { id: this.idCounter++, ...createXxxDto };
    this.xxxs.push(xxx);
    return xxx;
  }

  findAll(): Xxx[] {
    return this.xxxs;
  }
}

// xxx.controller.ts
import { Controller, Post, Get, Body } from '@nestjs/common';
import { XxxService } from './xxx.service';
import { CreateXxxDto } from './dto/create-xxx.dto';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  create(@Body() createXxxDto: CreateXxxDto) {
    return this.xxxService.create(createXxxDto);
  }

  @Get()
  findAll() {
    return this.xxxService.findAll();
  }
}

// xxx.module.ts
import { Module } from '@nestjs/common';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

@Module({
  controllers: [XxxController],
  providers: [XxxService],
  exports: [XxxService],
})
export class XxxModule {}

// app.module.ts
import { Module } from '@nestjs/common';
import { XxxModule } from './xxx/xxx.module';

@Module({
  imports: [XxxModule],
})
export class AppModule {}

// main.ts
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  await app.listen(3000);
}

bootstrap();
""",
        "pattern_scope": "nestjs_module",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "NestJS DI container: @Injectable marks providers → @Module registers in providers array → constructor injects dependencies → container manages singleton lifecycle",
        "modules": [
            "xxx.service.ts",
            "yyy.service.ts",
            "xxx.controller.ts",
            "xxx.module.ts",
        ],
        "connections": [
            "XxxService marked @Injectable",
            "YyyService marked @Injectable",
            "xxx.module.ts provides [XxxService, YyyService]",
            "xxx.controller.ts constructor receives XxxService",
        ],
        "code_example": """// yyy.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class YyyService {
  getValue(): string {
    return 'yyy-value';
  }
}

// xxx.service.ts
import { Injectable } from '@nestjs/common';
import { YyyService } from '../yyy/yyy.service';

@Injectable()
export class XxxService {
  constructor(private readonly yyyService: YyyService) {}

  getXxx() {
    const yyyValue = this.yyyService.getValue();
    return { xxx: 'data', yyyValue };
  }
}

// xxx.controller.ts
import { Controller, Get } from '@nestjs/common';
import { XxxService } from './xxx.service';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Get()
  findAll() {
    return this.xxxService.getXxx();
  }
}

// xxx.module.ts
import { Module } from '@nestjs/common';
import { XxxService } from './xxx.service';
import { XxxController } from './xxx.controller';
import { YyyService } from '../yyy/yyy.service';

@Module({
  controllers: [XxxController],
  providers: [XxxService, YyyService],
})
export class XxxModule {}
""",
        "pattern_scope": "nestjs_di",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Guard + Decorator composition: Custom decorator stores metadata → Guard reads metadata via Reflector → checks condition → allow or deny access",
        "modules": [
            "decorators/roles.decorator.ts",
            "guards/roles.guard.ts",
            "xxx.controller.ts",
        ],
        "connections": [
            "@Roles decorator sets metadata 'roles'",
            "RolesGuard reads metadata via Reflector.get('roles')",
            "RolesGuard compares user roles with required roles",
            "Controller method protected by @UseGuards(RolesGuard)",
        ],
        "code_example": """// decorators/roles.decorator.ts
import { SetMetadata } from '@nestjs/common';

export const Roles = (...roles: string[]) => SetMetadata('roles', roles);

// guards/roles.guard.ts
import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Roles } from '../decorators/roles.decorator';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<string[]>(
      'roles',
      context.getHandler(),
    );
    if (!requiredRoles) {
      return true;
    }

    const { user } = context.switchToHttp().getRequest();
    return requiredRoles.some((role) => user.roles?.includes(role));
  }
}

// xxx.controller.ts
import { Controller, Get, UseGuards } from '@nestjs/common';
import { Roles } from '../decorators/roles.decorator';
import { RolesGuard } from '../guards/roles.guard';

@Controller('xxxs')
@UseGuards(RolesGuard)
export class XxxController {
  @Get('admin')
  @Roles('admin')
  adminOnly() {
    return { message: 'admin-only-data' };
  }

  @Get('user')
  @Roles('user', 'admin')
  userOrAdmin() {
    return { message: 'user-accessible-data' };
  }
}
""",
        "pattern_scope": "nestjs_guard",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Complete NestJS request lifecycle: Middleware → Guards → Interceptors (pre) → Pipes (validation) → Controller → Service → Interceptors (post) → Exception filters → Response",
        "modules": [
            "middleware/logging.middleware.ts",
            "guards/auth.guard.ts",
            "interceptors/logging.interceptor.ts",
            "pipes/validation.pipe.ts",
            "xxx.controller.ts",
            "xxx.service.ts",
            "filters/http-exception.filter.ts",
        ],
        "connections": [
            "Request → Middleware logs incoming",
            "Middleware → Guards check authorization",
            "Guards → Interceptors pre-process request",
            "Interceptors → Pipes validate/transform data",
            "Pipes → Controller route handler",
            "Controller → Service business logic",
            "Service response → Interceptors post-process",
            "Interceptors → Exception filter (if error)",
            "Filter → Response sent",
        ],
        "code_example": """// middleware/logging.middleware.ts
import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';

@Injectable()
export class LoggingMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
    next();
  }
}

// guards/auth.guard.ts
import { Injectable, CanActivate, ExecutionContext, UnauthorizedException } from '@nestjs/common';

@Injectable()
export class AuthGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const authHeader = request.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      throw new UnauthorizedException('Missing or invalid token');
    }
    return true;
  }
}

// interceptors/logging.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const now = Date.now();
    return next.handle().pipe(
      tap(() => {
        console.log(`Response time: ${Date.now() - now}ms`);
      }),
    );
  }
}

// pipes/validation.pipe.ts (built-in ValidationPipe shown)
// dto/create-xxx.dto.ts
import { IsString, IsNotEmpty } from 'class-validator';

export class CreateXxxDto {
  @IsString()
  @IsNotEmpty()
  name: string;
}

// filters/http-exception.filter.ts
import { ExceptionFilter, Catch, ArgumentsHost, HttpException } from '@nestjs/common';
import { Response } from 'express';

@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const status = exception.getStatus();

    response.status(status).json({
      statusCode: status,
      message: exception.getResponse(),
      timestamp: new Date().toISOString(),
    });
  }
}

// xxx.controller.ts
import { Controller, Post, Body, UseGuards, UseInterceptors } from '@nestjs/common';
import { XxxService } from './xxx.service';
import { CreateXxxDto } from './dto/create-xxx.dto';
import { AuthGuard } from '../guards/auth.guard';
import { LoggingInterceptor } from '../interceptors/logging.interceptor';

@Controller('xxxs')
@UseGuards(AuthGuard)
@UseInterceptors(LoggingInterceptor)
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  create(@Body() createXxxDto: CreateXxxDto) {
    return this.xxxService.create(createXxxDto);
  }
}

// xxx.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class XxxService {
  create(data: any) {
    return { id: 1, ...data };
  }
}
""",
        "pattern_scope": "nestjs_request_lifecycle",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Pipe validation wiring: class-validator decorators on DTO → ValidationPipe (global or per-route) validates and transforms → throws BadRequestException on validation failure → exception filter formats error response",
        "modules": [
            "dto/create-xxx.dto.ts",
            "pipes/validation.pipe.ts",
            "xxx.controller.ts",
            "filters/http-exception.filter.ts",
        ],
        "connections": [
            "CreateXxxDto has @IsString, @IsNotEmpty decorators",
            "Controller route uses @UsePipes(ValidationPipe)",
            "ValidationPipe validates request body against DTO",
            "ValidationPipe throws BadRequestException on failure",
            "HttpExceptionFilter catches and formats response",
        ],
        "code_example": """// dto/create-xxx.dto.ts
import { IsString, IsNotEmpty, IsInt, Min, Max } from 'class-validator';

export class CreateXxxDto {
  @IsString()
  @IsNotEmpty()
  name: string;

  @IsInt()
  @Min(1)
  @Max(100)
  priority: number;
}

// xxx.controller.ts
import { Controller, Post, Body, UsePipes, BadRequestException } from '@nestjs/common';
import { ValidationPipe } from '@nestjs/common';
import { XxxService } from './xxx.service';
import { CreateXxxDto } from './dto/create-xxx.dto';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  @UsePipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true }))
  create(@Body() createXxxDto: CreateXxxDto) {
    return this.xxxService.create(createXxxDto);
  }
}

// xxx.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class XxxService {
  create(data: any) {
    return { id: 1, created: true, ...data };
  }
}

// Example: POST /xxxs with invalid data
// Request: { "name": 123, "priority": 150 }
// ValidationPipe rejects: "name must be a string", "priority must not be greater than 100"
// HttpExceptionFilter formats: { "statusCode": 400, "message": [...], "error": "Bad Request" }
""",
        "pattern_scope": "nestjs_validation",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Exception filter wiring: service throws HttpException/NotFoundException → ExceptionFilter.catch() transforms → response.status().json() formats and sends response",
        "modules": [
            "xxx.service.ts",
            "xxx.controller.ts",
            "filters/http-exception.filter.ts",
        ],
        "connections": [
            "Service throws HttpException or NotFoundException",
            "ExceptionFilter.catch() catches exception",
            "Filter extracts status and message",
            "Filter formats JSON response with statusCode, message, timestamp",
            "Response sent to client",
        ],
        "code_example": """// xxx.service.ts
import { Injectable, NotFoundException, BadRequestException } from '@nestjs/common';

@Injectable()
export class XxxService {
  private xxxs = [{ id: 1, name: 'xxx1' }];

  findOne(id: number) {
    const xxx = this.xxxs.find((x) => x.id === id);
    if (!xxx) {
      throw new NotFoundException(`Xxx with id ${id} not found`);
    }
    return xxx;
  }

  create(data: any) {
    if (!data.name) {
      throw new BadRequestException('Name is required');
    }
    const xxx = { id: this.xxxs.length + 1, ...data };
    this.xxxs.push(xxx);
    return xxx;
  }
}

// xxx.controller.ts
import { Controller, Get, Post, Param, Body } from '@nestjs/common';
import { XxxService } from './xxx.service';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.xxxService.findOne(Number(id));
  }

  @Post()
  create(@Body() createXxxDto: any) {
    return this.xxxService.create(createXxxDto);
  }
}

// filters/http-exception.filter.ts
import { ExceptionFilter, Catch, ArgumentsHost, HttpException, NotFoundException, BadRequestException } from '@nestjs/common';
import { Response } from 'express';

@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const status = exception.getStatus();
    const exceptionResponse = exception.getResponse() as any;

    response.status(status).json({
      statusCode: status,
      message: exceptionResponse.message || exception.message,
      error: exceptionResponse.error,
      timestamp: new Date().toISOString(),
    });
  }
}

// app.module.ts
import { Module } from '@nestjs/common';
import { APP_FILTER } from '@nestjs/core';
import { XxxModule } from './xxx/xxx.module';
import { HttpExceptionFilter } from './filters/http-exception.filter';

@Module({
  imports: [XxxModule],
  providers: [
    {
      provide: APP_FILTER,
      useClass: HttpExceptionFilter,
    },
  ],
})
export class AppModule {}

// Example: GET /xxxs/999 (not found)
// Response: { "statusCode": 404, "message": "Xxx with id 999 not found", "error": "Not Found", "timestamp": "2026-03-31T..." }
""",
        "pattern_scope": "nestjs_exception_handling",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Interceptor pattern: @UseInterceptors marks controller/route → intercept() receives request context and next handler → next.handle() returns Observable → map/tap for logging, caching, or serialization",
        "modules": [
            "interceptors/logging.interceptor.ts",
            "interceptors/caching.interceptor.ts",
            "xxx.controller.ts",
            "xxx.service.ts",
        ],
        "connections": [
            "@UseInterceptors(LoggingInterceptor) on controller",
            "LoggingInterceptor.intercept() receives context and next",
            "next.handle() subscribes to service Observable",
            "tap() operator logs after response",
            "CachingInterceptor caches based on request URL",
        ],
        "code_example": """// interceptors/logging.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const now = Date.now();
    console.log(`[${new Date().toISOString()}] ${request.method} ${request.url}`);

    return next.handle().pipe(
      tap((data) => {
        console.log(`Response time: ${Date.now() - now}ms`);
        console.log('Response data:', data);
      }),
    );
  }
}

// interceptors/caching.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable, of } from 'rxjs';

@Injectable()
export class CachingInterceptor implements NestInterceptor {
  private cache = new Map<string, any>();

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const key = `${request.method}:${request.url}`;

    if (this.cache.has(key)) {
      return of(this.cache.get(key));
    }

    return next.handle().pipe(
      tap((data) => {
        this.cache.set(key, data);
      }),
    );
  }
}

// xxx.controller.ts
import { Controller, Get, Param, UseInterceptors } from '@nestjs/common';
import { XxxService } from './xxx.service';
import { LoggingInterceptor } from '../interceptors/logging.interceptor';
import { CachingInterceptor } from '../interceptors/caching.interceptor';

@Controller('xxxs')
@UseInterceptors(LoggingInterceptor, CachingInterceptor)
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Get()
  findAll() {
    return this.xxxService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.xxxService.findOne(Number(id));
  }
}

// xxx.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class XxxService {
  private xxxs = [
    { id: 1, name: 'xxx1' },
    { id: 2, name: 'xxx2' },
  ];

  findAll() {
    return this.xxxs;
  }

  findOne(id: number) {
    return this.xxxs.find((x) => x.id === id);
  }
}
""",
        "pattern_scope": "nestjs_interceptor",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "NestJS testing wiring: Test.createTestingModule() compiles module → get() retrieves service/controller → mock providers with jest.fn() → supertest calls app.getHttpServer() for integration tests",
        "modules": [
            "xxx.service.ts",
            "xxx.controller.ts",
            "xxx.module.ts",
            "xxx.controller.spec.ts",
        ],
        "connections": [
            "Test module created with XxxModule",
            "XxxService compiled and available via get()",
            "Jest mocks can override providers",
            "Controller tested via supertest(app.getHttpServer())",
            "Service tested via direct get(XxxService)",
        ],
        "code_example": """// xxx.service.ts
import { Injectable } from '@nestjs/common';

@Injectable()
export class XxxService {
  create(data: any) {
    return { id: 1, ...data };
  }

  findAll() {
    return [{ id: 1, name: 'xxx1' }];
  }
}

// xxx.controller.ts
import { Controller, Get, Post, Body } from '@nestjs/common';
import { XxxService } from './xxx.service';

@Controller('xxxs')
export class XxxController {
  constructor(private readonly xxxService: XxxService) {}

  @Post()
  create(@Body() createXxxDto: any) {
    return this.xxxService.create(createXxxDto);
  }

  @Get()
  findAll() {
    return this.xxxService.findAll();
  }
}

// xxx.module.ts
import { Module } from '@nestjs/common';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

@Module({
  controllers: [XxxController],
  providers: [XxxService],
})
export class XxxModule {}

// xxx.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { XxxService } from './xxx.service';

describe('XxxService', () => {
  let service: XxxService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [XxxService],
    }).compile();

    service = module.get<XxxService>(XxxService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should create xxx', () => {
    const result = service.create({ name: 'test' });
    expect(result).toEqual({ id: 1, name: 'test' });
  });

  it('should return all xxxs', () => {
    const result = service.findAll();
    expect(result.length).toBeGreaterThan(0);
  });
});

// xxx.controller.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { XxxController } from './xxx.controller';
import { XxxService } from './xxx.service';

describe('XxxController', () => {
  let controller: XxxController;
  let service: XxxService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [XxxController],
      providers: [
        {
          provide: XxxService,
          useValue: {
            create: jest.fn().mockReturnValue({ id: 1, name: 'test' }),
            findAll: jest.fn().mockReturnValue([{ id: 1, name: 'xxx1' }]),
          },
        },
      ],
    }).compile();

    controller = module.get<XxxController>(XxxController);
    service = module.get<XxxService>(XxxService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  it('should create xxx', async () => {
    const result = await controller.create({ name: 'test' });
    expect(result).toEqual({ id: 1, name: 'test' });
    expect(service.create).toHaveBeenCalledWith({ name: 'test' });
  });

  it('should return all xxxs', async () => {
    const result = await controller.findAll();
    expect(result).toEqual([{ id: 1, name: 'xxx1' }]);
  });
});

// app.e2e-spec.ts (integration test with supertest)
import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from './../src/app.module';

describe('AppController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('/xxxs (GET)', () => {
    return request(app.getHttpServer())
      .get('/xxxs')
      .expect(200)
      .expect((res) => {
        expect(Array.isArray(res.body)).toBe(true);
      });
  });

  it('/xxxs (POST)', () => {
    return request(app.getHttpServer())
      .post('/xxxs')
      .send({ name: 'new-xxx' })
      .expect(201)
      .expect((res) => {
        expect(res.body).toHaveProperty('id');
      });
  });
});
""",
        "pattern_scope": "nestjs_testing",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": CREATED_AT,
        "_tag": TAG,
    },
]

# ============================================================================
# QDRANT CLIENT INITIALIZATION
# ============================================================================


def init_qdrant():
    """Initialize Qdrant client and ensure collection exists."""
    client = qdrant_client.QdrantClient(path=KB_PATH)
    try:
        client.get_collection(COLLECTION)
        print(f"✓ Collection '{COLLECTION}' exists")
    except Exception:
        print(f"✗ Collection '{COLLECTION}' not found. Please run setup_collections.py first.")
        sys.exit(1)
    return client


# ============================================================================
# EMBEDDING & INSERTION
# ============================================================================


def embed_and_insert(client: qdrant_client.QdrantClient, wirings: list) -> int:
    """Embed and insert wirings into Qdrant."""
    import uuid

    inserted_count = 0

    # Batch embed all descriptions
    try:
        descriptions = [w["description"] for w in wirings]
        embeddings = embed_documents_batch(descriptions)
    except Exception as e:
        print(f"ERROR: Batch embedding failed: {e}")
        return 0

    # Build all points
    points = []
    for idx, (wiring, embedding) in enumerate(zip(wirings, embeddings), start=1):
        print(f"\n[{idx}/{len(wirings)}] {wiring['wiring_type']} - {wiring['pattern_scope']}")

        # Build payload
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

        # Create point
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload=payload,
        )
        points.append(point)
        print(f"  ✓ Prepared")
        inserted_count += 1

    # Upsert all points at once
    try:
        if not DRY_RUN:
            client.upsert(
                collection_name=COLLECTION,
                points=points,
            )
            print(f"\n✓ Upserted {len(points)} wirings")
    except Exception as e:
            print(f"  ✗ Insertion failed: {e}")

    return inserted_count


# ============================================================================
# MAIN
# ============================================================================


def main():
    """Main entry point."""
    print(f"=" * 80)
    print(f"Wirings Ingestion: NestJS nest (TypeScript Hard)")
    print(f"=" * 80)
    print(f"Repo: {REPO_URL}")
    print(f"Language: {LANGUAGE}")
    print(f"Framework: {FRAMEWORK}")
    print(f"Collection: {COLLECTION}")
    print(f"Wirings count: {len(WIRINGS)}")
    print(f"DRY_RUN: {DRY_RUN}")
    print()

    # Initialize Qdrant
    print("Initializing Qdrant client...")
    client = init_qdrant()

    # Embed and insert
    print("\nEmbedding and inserting wirings...")
    inserted = embed_and_insert(client, WIRINGS)

    # Summary
    print(f"\n{'=' * 80}")
    print(f"Summary")
    print(f"{'=' * 80}")
    print(f"Inserted: {inserted}/{len(WIRINGS)} wirings")
    if inserted == len(WIRINGS):
        print(f"✓ All wirings ingested successfully")
    else:
        print(f"⚠ {len(WIRINGS) - inserted} wirings failed")


if __name__ == "__main__":
    main()
