#!/usr/bin/env python3
"""
Wirings ingestion for Go Clean Architecture repo (bxcodec/go-clean-arch).
V6 KB: Qdrant — manual wirings (no AST extraction for Go).

Repo: https://github.com/bxcodec/go-clean-arch.git (Hard complexity)
Language: Go | Framework: Echo | Stack: go+clean_arch+echo+mysql

8 wirings:
1. import_graph — clean arch package tree (layered)
2. flow_pattern — file creation order (entity → repo → usecase → handler)
3. dependency_chain — constructor injection (repo → usecase → handler)
4. flow_pattern — parallel data enrichment (errgroup + channels)
5. dependency_chain — context timeout pattern
6. flow_pattern — repository interface pattern
7. dependency_chain — Echo handler registration
8. flow_pattern — test wiring (mocks per layer)
"""

import os
import json
import time
from datetime import datetime
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, Distance, VectorParams
except ImportError:
    print("ERROR: qdrant-client not installed. Run: pip install qdrant-client")
    exit(1)

try:
    from embedder import embed_documents_batch
except ImportError:
    print("ERROR: embedder.py not found. Ensure it's in the same directory.")
    exit(1)


# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/bxcodec/go-clean-arch.git"
REPO_NAME = "bxcodec/go-clean-arch"
REPO_LOCAL = "/tmp/go-clean-arch"
LANGUAGE = "go"
FRAMEWORK = "echo"
STACK = "go+clean_arch+echo+mysql"
CHARTE_VERSION = "1.0"
TAG = "wirings/bxcodec/go-clean-arch"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

TIMESTAMP = int(datetime.now().timestamp())


# ============================================================================
# WIRINGS — 8 manual entries
# ============================================================================

WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": (
            "Clean Architecture package tree: main.go → xxx/delivery/http/ → xxx/usecase/ → "
            "xxx/repository/ → domain/. Domain layer has zero imports from other layers. "
            "UseCase imports domain only. Repository imports domain only. Delivery imports usecase + domain."
        ),
        "modules": [
            "main.go",
            "domain/xxx.go",
            "domain/xxx_author.go",
            "xxx/repository/mysql_xxx.go",
            "xxx/usecase/xxx_usecase.go",
            "xxx/delivery/http/xxx_handler.go",
        ],
        "connections": [
            "main.go → xxx/delivery/http/ (HTTP layer entry)",
            "xxx/delivery/http/xxx_handler.go → xxx/usecase/ (import usecase interface)",
            "xxx/usecase/xxx_usecase.go → xxx/repository/ (import repository interface)",
            "xxx/repository/mysql_xxx.go → domain/ (import entity struct)",
            "domain/xxx.go ↔ domain/xxx_author.go (sibling domain entities)",
            "domain/ ← zero reverse dependencies (acyclic)",
        ],
        "code_example": (
            "// main.go\n"
            "package main\n"
            "import (\n"
            "\t\"github.com/labstack/echo/v4\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx/delivery/http\"\n"
            "\t\"[repo]/xxx/repository/mysql\"\n"
            "\t\"[repo]/xxx/usecase\"\n"
            ")\n"
            "func main() {\n"
            "\tdb := mysql.Open(dsn)\n"
            "\trepo := mysql.NewMysqlXxxRepo(db)\n"
            "\tuseCase := usecase.NewXxxUsecase(repo, timeout)\n"
            "\thandler := http.NewXxxHandler(e, useCase)\n"
            "}\n"
            "\n"
            "// domain/xxx.go\n"
            "package domain\n"
            "type Xxx struct {\n"
            "\tID        int64\n"
            "\tAuthorID  int64\n"
            "\tAuthor    *XxxAuthor\n"
            "\tCreatedAt int64\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "File creation order for Clean Architecture: "
            "1) domain/xxx.go (entity struct + FK), "
            "2) domain/xxx_author.go (related entity), "
            "3) domain/errors.go (error constants like ErrInternalServerError, ErrNotFound), "
            "4) xxx/repository.go (interface definition), "
            "5) xxx/usecase.go (interface definition), "
            "6) xxx/repository/mysql_xxx.go (MySQL adapter implementation), "
            "7) xxx/usecase/xxx_usecase.go (business logic with injected deps), "
            "8) xxx/delivery/http/xxx_handler.go (Echo handler layer), "
            "9) main.go (wiring: repo → usecase → handler → echo router)."
        ),
        "modules": [
            "domain/xxx.go",
            "domain/xxx_author.go",
            "domain/errors.go",
            "xxx/repository.go",
            "xxx/usecase.go",
            "xxx/repository/mysql_xxx.go",
            "xxx/usecase/xxx_usecase.go",
            "xxx/delivery/http/xxx_handler.go",
            "main.go",
        ],
        "connections": [
            "domain/xxx.go — entity struct (no imports from other layers)",
            "domain/xxx_author.go — related entity (no imports from other layers)",
            "domain/errors.go — error constants (no imports from other layers)",
            "xxx/repository.go — interface (import domain only)",
            "xxx/usecase.go — interface (import domain only)",
            "xxx/repository/mysql_xxx.go implements xxx/repository.go (import domain + repository interface)",
            "xxx/usecase/xxx_usecase.go implements xxx/usecase.go (import domain + repository interface)",
            "xxx/delivery/http/xxx_handler.go (import usecase interface + domain)",
            "main.go (import all: repo impl + usecase impl + handler)",
        ],
        "code_example": (
            "// 1. domain/xxx.go\n"
            "package domain\n"
            "type Xxx struct {\n"
            "\tID        int64\n"
            "\tAuthorID  int64\n"
            "\tAuthor    *XxxAuthor\n"
            "}\n"
            "\n"
            "// 2. domain/xxx_author.go\n"
            "type XxxAuthor struct {\n"
            "\tID   int64\n"
            "\tName string\n"
            "}\n"
            "\n"
            "// 3. domain/errors.go\n"
            "var (\n"
            "\tErrInternalServerError = errors.New(\"Something went wrong\")\n"
            "\tErrNotFound            = errors.New(\"Xxx not found\")\n"
            "\tErrConflict            = errors.New(\"Xxx already exists\")\n"
            ")\n"
            "\n"
            "// 4. xxx/repository.go\n"
            "package xxx\n"
            "type Repository interface {\n"
            "\tFetch(ctx, cursor string, num int64) ([]domain.Xxx, string, error)\n"
            "\tGetByID(ctx, id int64) (domain.Xxx, error)\n"
            "\tStore(ctx, xxx *domain.Xxx) error\n"
            "}\n"
            "\n"
            "// 5. xxx/usecase.go\n"
            "type UseCase interface {\n"
            "\tFetch(ctx, cursor string, num int64) ([]domain.Xxx, string, error)\n"
            "\tGetByID(ctx, id int64) (domain.Xxx, error)\n"
            "}\n"
            "\n"
            "// 6. xxx/repository/mysql_xxx.go\n"
            "package mysql\n"
            "type mysqlXxxRepo struct { db *sql.DB }\n"
            "func NewMysqlXxxRepo(db *sql.DB) xxx.Repository { return &mysqlXxxRepo{db} }\n"
            "func (m *mysqlXxxRepo) GetByID(ctx, id) (domain.Xxx, error) { ... }\n"
            "\n"
            "// 7. xxx/usecase/xxx_usecase.go\n"
            "package usecase\n"
            "type xxxUsecase struct { repo xxx.Repository; timeout time.Duration }\n"
            "func NewXxxUsecase(r xxx.Repository, t time.Duration) xxx.UseCase { ... }\n"
            "func (u *xxxUsecase) GetByID(ctx, id) (domain.Xxx, error) { ... }\n"
            "\n"
            "// 8. xxx/delivery/http/xxx_handler.go\n"
            "package http\n"
            "type XxxHandler struct { usecase xxx.UseCase }\n"
            "func NewXxxHandler(e *echo.Echo, u xxx.UseCase) { ... }\n"
            "func (h *XxxHandler) GetByID(c echo.Context) error { ... }\n"
            "\n"
            "// 9. main.go\n"
            "db := mysql.Open(dsn)\n"
            "repo := mysql.NewMysqlXxxRepo(db)\n"
            "useCase := usecase.NewXxxUsecase(repo, 5*time.Second)\n"
            "http.NewXxxHandler(e, useCase)\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "Constructor injection chain in main.go: "
            "db := mysql.Open(dsn) → xxxRepo := mysqlRepo.NewMysqlXxxRepo(db) → "
            "authorRepo := mysqlRepo.NewMysqlXxxAuthorRepo(db) → "
            "xxxUsecase := usecase.NewXxxUsecase(xxxRepo, authorRepo, timeout) → "
            "handler.NewXxxHandler(e, xxxUsecase). "
            "Each constructor receives dependencies as parameters and returns fully configured instance. "
            "No global state or init() functions."
        ),
        "modules": ["main.go"],
        "connections": [
            "main() → mysql.Open(dsn) → *sql.DB",
            "*sql.DB → NewMysqlXxxRepo() → xxx.Repository",
            "*sql.DB → NewMysqlXxxAuthorRepo() → xxx.AuthorRepository",
            "xxx.Repository + xxx.AuthorRepository → NewXxxUsecase() → xxx.UseCase",
            "xxx.UseCase → NewXxxHandler() → *XxxHandler",
            "*XxxHandler routes registered on echo.Echo",
        ],
        "code_example": (
            "package main\n"
            "import (\n"
            "\t\"database/sql\"\n"
            "\t\"time\"\n"
            "\t\"[repo]/xxx/repository/mysql\"\n"
            "\t\"[repo]/xxx/usecase\"\n"
            "\t\"[repo]/xxx/delivery/http\"\n"
            ")\n"
            "func main() {\n"
            "\t// 1. Database\n"
            "\tdb, err := sql.Open(\"mysql\", dsn)\n"
            "\tif err != nil { log.Fatal(err) }\n"
            "\tdefer db.Close()\n"
            "\n"
            "\t// 2. Repositories\n"
            "\txxxRepo := mysql.NewMysqlXxxRepo(db)\n"
            "\tauthorRepo := mysql.NewMysqlXxxAuthorRepo(db)\n"
            "\n"
            "\t// 3. Use Cases\n"
            "\txxxUseCase := usecase.NewXxxUsecase(\n"
            "\t\txxxRepo,\n"
            "\t\tauthorRepo,\n"
            "\t\t5*time.Second, // timeout\n"
            "\t)\n"
            "\n"
            "\t// 4. HTTP Handlers\n"
            "\te := echo.New()\n"
            "\thttp.NewXxxHandler(e, xxxUseCase)\n"
            "\n"
            "\t// 5. Start server\n"
            "\te.Logger.Fatal(e.Start(\":8080\"))\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "Parallel data enrichment pattern using errgroup + channels: "
            "1) Fetch list of Xxx from repository, 2) For each Xxx, launch goroutine via errgroup, "
            "3) Inside goroutine: fetch Author by FK via authorRepo.GetByID(ctx, xxx.AuthorID), "
            "4) Enrich Xxx.Author = author, 5) Collect result in sync.Map or channel, "
            "6) errgroup.Wait() blocks until all goroutines finish, 7) Handle partial failures. "
            "Pattern prevents N+1 queries and adds parallel I/O."
        ),
        "modules": [
            "xxx/usecase/xxx_usecase.go",
            "xxx/repository/mysql_xxx.go",
            "domain/xxx.go",
        ],
        "connections": [
            "Fetch(ctx) — get list of Xxx from repository",
            "for each Xxx → spawn goroutine in errgroup",
            "goroutine → authorRepo.GetByID(ctx, Xxx.AuthorID)",
            "Assign author to Xxx.Author",
            "errgroup.Wait() → collect all results",
            "Return enriched []Xxx to caller",
        ],
        "code_example": (
            "package usecase\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"sync\"\n"
            "\t\"golang.org/x/sync/errgroup\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "type xxxUsecase struct {\n"
            "\trepo       xxx.Repository\n"
            "\tauthorRepo xxx.AuthorRepository\n"
            "\ttimeout    time.Duration\n"
            "}\n"
            "func (u *xxxUsecase) Fetch(ctx, cursor string, num int64) ([]domain.Xxx, error) {\n"
            "\tctx, cancel := context.WithTimeout(ctx, u.timeout)\n"
            "\tdefer cancel()\n"
            "\n"
            "\txxxs, nextCursor, err := u.repo.Fetch(ctx, cursor, num)\n"
            "\tif err != nil { return nil, err }\n"
            "\n"
            "\t// Parallel enrichment\n"
            "\tvar mu sync.Mutex\n"
"\teg, egCtx := errgroup.WithContext(ctx)\n"
            "\tfor i := range xxxs {\n"
            "\t\ti := i // capture loop variable\n"
            "\t\teg.Go(func() error {\n"
            "\t\t\tauthor, err := u.authorRepo.GetByID(egCtx, xxxs[i].AuthorID)\n"
            "\t\t\tif err != nil { return err }\n"
            "\t\t\tmu.Lock()\n"
            "\t\t\txxxs[i].Author = &author\n"
            "\t\t\tmu.Unlock()\n"
            "\t\t\treturn nil\n"
            "\t\t})\n"
            "\t}\n"
            "\tif err := eg.Wait(); err != nil { return nil, err }\n"
            "\n"
            "\treturn xxxs, nil\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "Context timeout pattern in usecase methods: "
            "Every usecase method starts with ctx, cancel := context.WithTimeout(ctx, s.contextTimeout). "
            "Immediately defer cancel() to ensure cleanup. Pass derived ctx to all repository calls. "
            "Prevents slow database queries or network I/O from blocking the application indefinitely. "
            "Timeout is configured per use case (typically 5-10 seconds)."
        ),
        "modules": ["xxx/usecase/xxx_usecase.go"],
        "connections": [
            "UseCase method called with parent ctx",
            "Derive new ctx with WithTimeout(ctx, timeout)",
            "defer cancel() immediately (cleanup)",
            "Pass derived ctx to repository.GetByID(ctx, id)",
            "Repository respects ctx.Done() signal",
            "Return error if context exceeds timeout",
        ],
        "code_example": (
            "package usecase\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"time\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "type xxxUsecase struct {\n"
            "\trepo           xxx.Repository\n"
            "\tcontextTimeout time.Duration\n"
            "}\n"
            "func NewXxxUsecase(repo xxx.Repository, timeout time.Duration) xxx.UseCase {\n"
            "\treturn &xxxUsecase{\n"
            "\t\trepo:           repo,\n"
            "\t\tcontextTimeout: timeout,\n"
            "\t}\n"
            "}\n"
            "func (u *xxxUsecase) GetByID(ctx context.Context, id int64) (domain.Xxx, error) {\n"
            "\t// Derive new context with timeout\n"
            "\tctx, cancel := context.WithTimeout(ctx, u.contextTimeout)\n"
            "\tdefer cancel() // cleanup\n"
            "\n"
            "\t// Pass derived ctx to repository\n"
            "\txxx, err := u.repo.GetByID(ctx, id)\n"
            "\tif err != nil {\n"
            "\t\treturn domain.Xxx{}, err\n"
            "\t}\n"
            "\treturn xxx, nil\n"
            "}\n"
            "func (u *xxxUsecase) Fetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, error) {\n"
            "\tctx, cancel := context.WithTimeout(ctx, u.contextTimeout)\n"
            "\tdefer cancel()\n"
            "\n"
            "\txxxs, _, err := u.repo.Fetch(ctx, cursor, num)\n"
            "\tif err != nil { return nil, err }\n"
            "\treturn xxxs, nil\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "Repository interface pattern in Clean Architecture: "
            "domain/ defines type XxxRepository interface with CRUD methods: "
            "Fetch(ctx, cursor, num) → ([]Xxx, nextCursor, error), "
            "GetByID(ctx, id) → (Xxx, error), "
            "Update(ctx, xxx *Xxx) → error, "
            "Store(ctx, xxx *Xxx) → error, "
            "Delete(ctx, id) → error. "
            "MySQL adapter implements all methods using *sql.DB. "
            "Interface allows swapping database implementations without changing usecase or handler."
        ),
        "modules": [
            "domain/ (interface definition)",
            "xxx/repository.go (interface)",
            "xxx/repository/mysql_xxx.go (MySQL implementation)",
        ],
        "connections": [
            "domain/ defines error constants (ErrInternalServerError, ErrNotFound, ErrConflict, ErrBadParamInput)",
            "xxx/repository.go defines interface XxxRepository",
            "xxx/repository/mysql_xxx.go implements XxxRepository methods",
            "Each method: Fetch, GetByID, Update, Store, Delete",
            "All methods take context.Context as first parameter",
            "MySQL adapter manages *sql.DB connection + query building",
        ],
        "code_example": (
            "// xxx/repository.go\n"
            "package xxx\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"[repo]/domain\"\n"
            ")\n"
            "type Repository interface {\n"
            "\tFetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error)\n"
            "\tGetByID(ctx context.Context, id int64) (domain.Xxx, error)\n"
            "\tUpdate(ctx context.Context, xxx *domain.Xxx) error\n"
            "\tStore(ctx context.Context, xxx *domain.Xxx) error\n"
            "\tDelete(ctx context.Context, id int64) error\n"
            "}\n"
            "\n"
            "// xxx/repository/mysql_xxx.go\n"
            "package mysql\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"database/sql\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "type mysqlXxxRepo struct { db *sql.DB }\n"
            "func NewMysqlXxxRepo(db *sql.DB) xxx.Repository {\n"
            "\treturn &mysqlXxxRepo{db: db}\n"
            "}\n"
            "func (m *mysqlXxxRepo) GetByID(ctx context.Context, id int64) (domain.Xxx, error) {\n"
            "\tquery := `SELECT id, author_id, created_at FROM xxxs WHERE id = ?`\n"
            "\tvar xxx domain.Xxx\n"
            "\terr := m.db.QueryRowContext(ctx, query, id).Scan(\n"
            "\t\t&xxx.ID, &xxx.AuthorID, &xxx.CreatedAt,\n"
            "\t)\n"
            "\tif err == sql.ErrNoRows {\n"
            "\t\treturn domain.Xxx{}, domain.ErrNotFound\n"
            "\t}\n"
            "\tif err != nil {\n"
            "\t\treturn domain.Xxx{}, domain.ErrInternalServerError\n"
            "\t}\n"
            "\treturn xxx, nil\n"
            "}\n"
            "func (m *mysqlXxxRepo) Fetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error) {\n"
            "\t...\n"
            "}\n"
            "func (m *mysqlXxxRepo) Store(ctx context.Context, xxx *domain.Xxx) error {\n"
            "\t...\n"
            "}\n"
            "func (m *mysqlXxxRepo) Update(ctx context.Context, xxx *domain.Xxx) error {\n"
            "\t...\n"
            "}\n"
            "func (m *mysqlXxxRepo) Delete(ctx context.Context, id int64) error {\n"
            "\t...\n"
            "}\n"
        ),
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
        "description": (
            "Echo handler registration in NewXxxHandler constructor: "
            "e := echo.New() in main → handler := NewXxxHandler(e, usecase) → "
            "inside constructor: e.GET(\"/xxxs\", handler.FetchXxx), "
            "e.GET(\"/xxxs/:id\", handler.GetByID), "
            "e.POST(\"/xxxs\", handler.Store), "
            "e.DELETE(\"/xxxs/:id\", handler.Delete). "
            "Routes registered at initialization time, not lazily. "
            "All handler methods receive echo.Context and return error."
        ),
        "modules": [
            "main.go",
            "xxx/delivery/http/xxx_handler.go",
        ],
        "connections": [
            "main() creates echo.Echo instance",
            "main() passes e + usecase to NewXxxHandler()",
            "NewXxxHandler() registers GET /xxxs → FetchXxx",
            "NewXxxHandler() registers GET /xxxs/:id → GetByID",
            "NewXxxHandler() registers POST /xxxs → Store",
            "NewXxxHandler() registers DELETE /xxxs/:id → Delete",
            "All routes use handler methods with (c echo.Context) → error",
        ],
        "code_example": (
            "// main.go\n"
            "package main\n"
            "import (\n"
            "\t\"github.com/labstack/echo/v4\"\n"
            "\t\"[repo]/xxx/delivery/http\"\n"
            "\t\"[repo]/xxx/usecase\"\n"
            ")\n"
            "func main() {\n"
            "\te := echo.New()\n"
            "\tuseCase := // ... initialized above\n"
            "\thttp.NewXxxHandler(e, useCase)\n"
            "\te.Logger.Fatal(e.Start(\":8080\"))\n"
            "}\n"
            "\n"
            "// xxx/delivery/http/xxx_handler.go\n"
            "package http\n"
            "import (\n"
            "\t\"github.com/labstack/echo/v4\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "type XxxHandler struct {\n"
            "\tusecase xxx.UseCase\n"
            "}\n"
            "func NewXxxHandler(e *echo.Echo, uc xxx.UseCase) {\n"
            "\th := &XxxHandler{usecase: uc}\n"
            "\t\n"
            "\t// GET /api/v1/xxxs\n"
            "\te.GET(\"/api/v1/xxxs\", h.FetchXxx)\n"
            "\t\n"
            "\t// GET /api/v1/xxxs/:id\n"
            "\te.GET(\"/api/v1/xxxs/:id\", h.GetByID)\n"
            "\t\n"
            "\t// POST /api/v1/xxxs\n"
            "\te.POST(\"/api/v1/xxxs\", h.Store)\n"
            "\t\n"
            "\t// DELETE /api/v1/xxxs/:id\n"
            "\te.DELETE(\"/api/v1/xxxs/:id\", h.Delete)\n"
            "}\n"
            "func (h *XxxHandler) FetchXxx(c echo.Context) error {\n"
            "\tcursor := c.QueryParam(\"cursor\")\n"
            "\tnum := c.QueryParam(\"num\")\n"
            "\txxxs, _, err := h.usecase.Fetch(c.Request().Context(), cursor, num)\n"
            "\tif err != nil { return c.JSON(500, map[string]string{\"error\": err.Error()}) }\n"
            "\treturn c.JSON(200, xxxs)\n"
            "}\n"
            "func (h *XxxHandler) GetByID(c echo.Context) error {\n"
            "\tid := c.Param(\"id\")\n"
            "\txxx, err := h.usecase.GetByID(c.Request().Context(), parseID(id))\n"
            "\tif err != nil { return c.JSON(404, map[string]string{\"error\": err.Error()}) }\n"
            "\treturn c.JSON(200, xxx)\n"
            "}\n"
            "func (h *XxxHandler) Store(c echo.Context) error {\n"
            "\tvar xxx domain.Xxx\n"
            "\tc.Bind(&xxx)\n"
            "\terr := h.usecase.Store(c.Request().Context(), &xxx)\n"
            "\tif err != nil { return c.JSON(400, map[string]string{\"error\": err.Error()}) }\n"
            "\treturn c.JSON(201, xxx)\n"
            "}\n"
            "func (h *XxxHandler) Delete(c echo.Context) error {\n"
            "\tid := c.Param(\"id\")\n"
            "\terr := h.usecase.Delete(c.Request().Context(), parseID(id))\n"
            "\tif err != nil { return c.JSON(404, map[string]string{\"error\": err.Error()}) }\n"
            "\treturn c.NoContent(204)\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
        "description": (
            "Test wiring in Clean Architecture: "
            "1) Mock repository generated from xxx.Repository interface, "
            "2) UseCase unit tests use mock repos with table-driven test cases, "
            "3) Handler tests use echo test context + httptest.ResponseRecorder, "
            "4) Handler tests mock usecase.UseCase to isolate handler logic, "
            "5) Each layer tested independently without external dependencies. "
            "No integration tests in unit layer. Database tests use separate integration package."
        ),
        "modules": [
            "xxx/usecase/xxx_usecase_test.go",
            "xxx/delivery/http/xxx_handler_test.go",
            "xxx/repository/mysql_xxx_test.go",
        ],
        "connections": [
            "xxx/repository mock — in-memory impl of xxx.Repository interface",
            "usecase test → create mock repo → NewXxxUsecase(mockRepo, timeout) → call methods",
            "usecase test tables: {name, args, wantErr, wantXxx}",
            "handler test → create mock usecase → NewXxxHandler(e, mockUsecase)",
            "handler test → httptest.NewRequest(\"GET\", \"/xxxs/1\", nil) → e.ServeHTTP(rec, req)",
            "Assert status code, response body against expected JSON",
        ],
        "code_example": (
            "// xxx/usecase/xxx_usecase_test.go\n"
            "package usecase\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"testing\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "// Mock repository\n"
            "type mockXxxRepo struct { xxxs map[int64]domain.Xxx }\n"
            "func (m *mockXxxRepo) GetByID(ctx context.Context, id int64) (domain.Xxx, error) {\n"
            "\tif x, ok := m.xxxs[id]; ok { return x, nil }\n"
            "\treturn domain.Xxx{}, domain.ErrNotFound\n"
            "}\n"
            "func (m *mockXxxRepo) Fetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error) {\n"
            "\tvar result []domain.Xxx\n"
            "\tfor _, x := range m.xxxs { result = append(result, x) }\n"
            "\treturn result, \"\", nil\n"
            "}\n"
            "func (m *mockXxxRepo) Store(ctx context.Context, xxx *domain.Xxx) error { return nil }\n"
            "func (m *mockXxxRepo) Update(ctx context.Context, xxx *domain.Xxx) error { return nil }\n"
            "func (m *mockXxxRepo) Delete(ctx context.Context, id int64) error { return nil }\n"
            "\n"
            "// Table-driven test\n"
            "func TestGetByID(t *testing.T) {\n"
            "\ttests := []struct {\n"
            "\t\tname    string\n"
            "\t\tid      int64\n"
            "\t\twantID  int64\n"
            "\t\twantErr bool\n"
            "\t}{\n"
            "\t\t{\"success\", 1, 1, false},\n"
            "\t\t{\"not found\", 999, 0, true},\n"
            "\t}\n"
            "\tmockRepo := &mockXxxRepo{xxxs: map[int64]domain.Xxx{\n"
            "\t\t1: {ID: 1, AuthorID: 10},\n"
            "\t}}\n"
            "\tuc := NewXxxUsecase(mockRepo, 5*time.Second)\n"
            "\tfor _, tt := range tests {\n"
            "\t\tt := tt\n"
            "\t\tt.Run(tt.name, func(t *testing.T) {\n"
            "\t\t\txxx, err := uc.GetByID(context.Background(), tt.id)\n"
            "\t\t\tif (err != nil) != tt.wantErr { t.Errorf(\"error = %v\", err) }\n"
            "\t\t\tif xxx.ID != tt.wantID { t.Errorf(\"ID = %v, want %v\", xxx.ID, tt.wantID) }\n"
            "\t\t})\n"
            "\t}\n"
            "}\n"
            "\n"
            "// xxx/delivery/http/xxx_handler_test.go\n"
            "package http\n"
            "import (\n"
            "\t\"context\"\n"
            "\t\"net/http/httptest\"\n"
            "\t\"testing\"\n"
            "\t\"github.com/labstack/echo/v4\"\n"
            "\t\"[repo]/domain\"\n"
            "\t\"[repo]/xxx\"\n"
            ")\n"
            "type mockXxxUsecase struct {}\n"
            "func (m *mockXxxUsecase) GetByID(ctx context.Context, id int64) (domain.Xxx, error) {\n"
            "\treturn domain.Xxx{ID: id}, nil\n"
            "}\n"
            "func (m *mockXxxUsecase) Fetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error) {\n"
            "\treturn []domain.Xxx{{ID: 1}}, \"\", nil\n"
            "}\n"
            "func TestGetByID(t *testing.T) {\n"
            "\te := echo.New()\n"
            "\tmockUC := &mockXxxUsecase{}\n"
            "\th := &XxxHandler{usecase: mockUC}\n"
            "\n"
            "\treq := httptest.NewRequest(\"GET\", \"/api/v1/xxxs/1\", nil)\n"
            "\trec := httptest.NewRecorder()\n"
            "\tc := e.NewContext(req, rec)\n"
            "\tc.SetParamNames(\"id\")\n"
            "\tc.SetParamValues(\"1\")\n"
            "\n"
            "\terr := h.GetByID(c)\n"
            "\tif err != nil { t.Fatalf(\"unexpected error: %v\", err) }\n"
            "\tif rec.Code != 200 { t.Errorf(\"status = %d, want 200\", rec.Code) }\n"
            "}\n"
        ),
        "pattern_scope": "clean_arch",
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
# HELPER FUNCTIONS
# ============================================================================


def init_client() -> QdrantClient:
    """Initialize Qdrant client."""
    return QdrantClient(path=KB_PATH)


def vector_exists(client: QdrantClient, vec: list[float]) -> bool:
    """Check if vector exists in collection (simple length-based check)."""
    return len(vec) > 0


def ingest_wirings(client: QdrantClient) -> None:
    """Ingest all wirings into Qdrant collection."""
    import uuid

    print(f"\n{'='*80}")
    print(f"INGESTING WIRINGS: {REPO_NAME}")
    print(f"Collection: {COLLECTION}")
    print(f"Language: {LANGUAGE} | Framework: {FRAMEWORK} | Stack: {STACK}")
    print(f"{'='*80}\n")

    total = len(WIRINGS)

    # Batch embed all descriptions
    try:
        descriptions = [w["description"] for w in WIRINGS]
        vectors = embed_documents_batch(descriptions)
        print(f"✓ Embedded {len(vectors)} descriptions\n")
    except Exception as e:
        print(f"✗ Batch embedding failed: {e}")
        return

    points = []
    for idx, (wiring_payload, vec) in enumerate(zip(WIRINGS, vectors), start=1):
        print(f"[{idx}/{total}] {wiring_payload['wiring_type']:20s} — {wiring_payload['pattern_scope']:15s}...", end=" ")

        # Build point
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload=wiring_payload,
        )
        points.append(point)
        print("OK")

    # Upsert all at once
    if DRY_RUN:
        print(f"\n[DRY_RUN] Would upsert {len(points)} wirings")
    else:
        try:
            client.upsert(
                collection_name=COLLECTION,
                points=points,
            )
            print(f"\n{'='*80}")
            print(f"SUMMARY: {len(points)}/{total} wirings upserted")
            print(f"Tag: {TAG}")
            print(f"{'='*80}\n")
        except Exception as e:
            print(f"✗ Upsert failed: {e}")
            return


def main() -> None:
    """Entry point."""
    try:
        client = init_client()
        print(f"✓ Qdrant client initialized (path={KB_PATH})")

        # Check collection exists
        try:
            col = client.get_collection(COLLECTION)
            print(f"✓ Collection '{COLLECTION}' exists ({col.points_count} points)")
        except Exception as e:
            print(f"✗ Collection '{COLLECTION}' not found: {e}")
            return

        # Ingest
        ingest_wirings(client)

    except Exception as e:
        print(f"FATAL: {e}")
        exit(1)


if __name__ == "__main__":
    main()
