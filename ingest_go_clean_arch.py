"""
ingest_go_clean_arch.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de bxcodec/go-clean-arch dans la KB Qdrant V6.

Go C — Clean Architecture (Uncle Bob). Echo + MySQL. 4 layers.

Usage:
    .venv/bin/python3 ingest_go_clean_arch.py
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
REPO_URL = "https://github.com/bxcodec/go-clean-arch.git"
REPO_NAME = "bxcodec/go-clean-arch"
REPO_LOCAL = "/tmp/go_clean_arch"
LANGUAGE = "go"
FRAMEWORK = "echo"
STACK = "go+clean_arch+echo+mysql"
CHARTE_VERSION = "1.0"
TAG = "bxcodec/go-clean-arch"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/bxcodec/go-clean-arch"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Article→Xxx, article→xxx, articles→xxxs
#       Author→XxxAuthor, author→xxxAuthor
#       "Item" in error messages → "record"
#       Kept: http, context, error, echo, sql, gorm, validator
# G-1: no panic(). G-2: no fmt.Println/Printf.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Domain entity ────────────────────────────────────────────────────
    {
        "normalized_code": """\
package domain

import "time"

type Xxx struct {
\tID        int64     `json:"id"`
\tTitle     string    `json:"title" validate:"required"`
\tContent   string    `json:"content" validate:"required"`
\tXxxAuthor XxxAuthor `json:"xxx_author"`
\tUpdatedAt time.Time `json:"updated_at"`
\tCreatedAt time.Time `json:"created_at"`
}
""",
        "function": "domain_entity_struct",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "domain/xxx.go",
    },

    # ── 2. Domain related entity ────────────────────────────────────────────
    {
        "normalized_code": """\
package domain

type XxxAuthor struct {
\tID        int64  `json:"id"`
\tName      string `json:"name"`
\tCreatedAt string `json:"created_at"`
\tUpdatedAt string `json:"updated_at"`
}
""",
        "function": "domain_related_entity",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "domain/xxx_author.go",
    },

    # ── 3. Domain error constants ───────────────────────────────────────────
    {
        "normalized_code": """\
package domain

import "errors"

var (
\tErrInternalServerError = errors.New("internal server error")
\tErrNotFound            = errors.New("your requested record is not found")
\tErrConflict            = errors.New("your record already exists")
\tErrBadParamInput       = errors.New("given param is not valid")
)
""",
        "function": "domain_errors_constants",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "domain/errors.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SERVICE (USECASE) LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 4. Repository + service interfaces ──────────────────────────────────
    {
        "normalized_code": """\
package xxx

import (
\t"context"

\t"project/domain"
)

type XxxRepository interface {
\tFetch(ctx context.Context, cursor string, num int64) (res []domain.Xxx, nextCursor string, err error)
\tGetByID(ctx context.Context, id int64) (domain.Xxx, error)
\tGetByTitle(ctx context.Context, title string) (domain.Xxx, error)
\tUpdate(ctx context.Context, ar *domain.Xxx) error
\tStore(ctx context.Context, a *domain.Xxx) error
\tDelete(ctx context.Context, id int64) error
}

type XxxAuthorRepository interface {
\tGetByID(ctx context.Context, id int64) (domain.XxxAuthor, error)
}
""",
        "function": "repository_interfaces_ports",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "xxx/interfaces.go",
    },

    # ── 5. Service struct + constructor ─────────────────────────────────────
    {
        "normalized_code": """\
package xxx

import (
\t"context"
\t"time"

\t"golang.org/x/sync/errgroup"
\t"github.com/sirupsen/logrus"

\t"project/domain"
)

type Service struct {
\txxxRepo       XxxRepository
\txxxAuthorRepo XxxAuthorRepository
}

func NewService(a XxxRepository, ar XxxAuthorRepository) *Service {
\treturn &Service{
\t\txxxRepo:       a,
\t\txxxAuthorRepo: ar,
\t}
}
""",
        "function": "service_struct_constructor_di",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "xxx/service.go",
    },

    # ── 6. Service — Fetch with parallel related data enrichment ────────────
    {
        "normalized_code": """\
func (a *Service) fillXxxAuthorDetails(ctx context.Context, data []domain.Xxx) ([]domain.Xxx, error) {
\tg, ctx := errgroup.WithContext(ctx)
\tmapXxxAuthors := map[int64]domain.XxxAuthor{}

\tfor _, xxx := range data {
\t\tmapXxxAuthors[xxx.XxxAuthor.ID] = domain.XxxAuthor{}
\t}
\tchanXxxAuthor := make(chan domain.XxxAuthor)
\tfor xxxAuthorID := range mapXxxAuthors {
\t\txxxAuthorID := xxxAuthorID
\t\tg.Go(func() error {
\t\t\tres, err := a.xxxAuthorRepo.GetByID(ctx, xxxAuthorID)
\t\t\tif err != nil {
\t\t\t\treturn err
\t\t\t}
\t\t\tchanXxxAuthor <- res
\t\t\treturn nil
\t\t})
\t}

\tgo func() {
\t\tdefer close(chanXxxAuthor)
\t\terr := g.Wait()
\t\tif err != nil {
\t\t\tlogrus.Error(err)
\t\t\treturn
\t\t}
\t}()

\tfor xxxAuthor := range chanXxxAuthor {
\t\tif xxxAuthor != (domain.XxxAuthor{}) {
\t\t\tmapXxxAuthors[xxxAuthor.ID] = xxxAuthor
\t\t}
\t}

\tif err := g.Wait(); err != nil {
\t\treturn nil, err
\t}

\tfor index, record := range data {
\t\tif a, ok := mapXxxAuthors[record.XxxAuthor.ID]; ok {
\t\t\tdata[index].XxxAuthor = a
\t\t}
\t}
\treturn data, nil
}

func (a *Service) Fetch(ctx context.Context, cursor string, num int64) (res []domain.Xxx, nextCursor string, err error) {
\tres, nextCursor, err = a.xxxRepo.Fetch(ctx, cursor, num)
\tif err != nil {
\t\treturn nil, "", err
\t}
\tres, err = a.fillXxxAuthorDetails(ctx, res)
\tif err != nil {
\t\tnextCursor = ""
\t}
\treturn
}
""",
        "function": "service_fetch_parallel_enrichment",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "xxx/service.go",
    },

    # ── 7. Service — CRUD operations ────────────────────────────────────────
    {
        "normalized_code": """\
func (a *Service) GetByID(ctx context.Context, id int64) (res domain.Xxx, err error) {
\tres, err = a.xxxRepo.GetByID(ctx, id)
\tif err != nil {
\t\treturn
\t}
\tresXxxAuthor, err := a.xxxAuthorRepo.GetByID(ctx, res.XxxAuthor.ID)
\tif err != nil {
\t\treturn domain.Xxx{}, err
\t}
\tres.XxxAuthor = resXxxAuthor
\treturn
}

func (a *Service) Update(ctx context.Context, ar *domain.Xxx) error {
\tar.UpdatedAt = time.Now()
\treturn a.xxxRepo.Update(ctx, ar)
}

func (a *Service) GetByTitle(ctx context.Context, title string) (res domain.Xxx, err error) {
\tres, err = a.xxxRepo.GetByTitle(ctx, title)
\tif err != nil {
\t\treturn
\t}
\tresXxxAuthor, err := a.xxxAuthorRepo.GetByID(ctx, res.XxxAuthor.ID)
\tif err != nil {
\t\treturn domain.Xxx{}, err
\t}
\tres.XxxAuthor = resXxxAuthor
\treturn
}

func (a *Service) Store(ctx context.Context, m *domain.Xxx) error {
\texistedXxx, _ := a.GetByTitle(ctx, m.Title)
\tif existedXxx != (domain.Xxx{}) {
\t\treturn domain.ErrConflict
\t}
\treturn a.xxxRepo.Store(ctx, m)
}

func (a *Service) Delete(ctx context.Context, id int64) error {
\texistedXxx, err := a.xxxRepo.GetByID(ctx, id)
\tif err != nil {
\t\treturn err
\t}
\tif existedXxx == (domain.Xxx{}) {
\t\treturn domain.ErrNotFound
\t}
\treturn a.xxxRepo.Delete(ctx, id)
}
""",
        "function": "service_crud_operations",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "xxx/service.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # REPOSITORY LAYER (MySQL)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 8. MySQL repository — fetch helper + Fetch/GetByID ──────────────────
    {
        "normalized_code": """\
package mysql

import (
\t"context"
\t"database/sql"

\t"github.com/sirupsen/logrus"

\t"project/domain"
\t"project/internal/repository"
)

type XxxRepository struct {
\tConn *sql.DB
}

func NewXxxRepository(conn *sql.DB) *XxxRepository {
\treturn &XxxRepository{conn}
}

func (m *XxxRepository) fetch(ctx context.Context, query string, args ...interface{}) (result []domain.Xxx, err error) {
\trows, err := m.Conn.QueryContext(ctx, query, args...)
\tif err != nil {
\t\tlogrus.Error(err)
\t\treturn nil, err
\t}
\tdefer func() {
\t\terrRow := rows.Close()
\t\tif errRow != nil {
\t\t\tlogrus.Error(errRow)
\t\t}
\t}()
\tresult = make([]domain.Xxx, 0)
\tfor rows.Next() {
\t\tt := domain.Xxx{}
\t\txxxAuthorID := int64(0)
\t\terr = rows.Scan(&t.ID, &t.Title, &t.Content, &xxxAuthorID, &t.UpdatedAt, &t.CreatedAt)
\t\tif err != nil {
\t\t\tlogrus.Error(err)
\t\t\treturn nil, err
\t\t}
\t\tt.XxxAuthor = domain.XxxAuthor{ID: xxxAuthorID}
\t\tresult = append(result, t)
\t}
\treturn result, nil
}

func (m *XxxRepository) Fetch(ctx context.Context, cursor string, num int64) (res []domain.Xxx, nextCursor string, err error) {
\tquery := `SELECT id, title, content, xxx_author_id, updated_at, created_at FROM xxx WHERE created_at > ? ORDER BY created_at LIMIT ?`
\tdecodedCursor, err := repository.DecodeCursor(cursor)
\tif err != nil && cursor != "" {
\t\treturn nil, "", domain.ErrBadParamInput
\t}
\tres, err = m.fetch(ctx, query, decodedCursor, num)
\tif err != nil {
\t\treturn nil, "", err
\t}
\tif len(res) == int(num) {
\t\tnextCursor = repository.EncodeCursor(res[len(res)-1].CreatedAt)
\t}
\treturn
}

func (m *XxxRepository) GetByID(ctx context.Context, id int64) (res domain.Xxx, err error) {
\tquery := `SELECT id, title, content, xxx_author_id, updated_at, created_at FROM xxx WHERE ID = ?`
\tlist, err := m.fetch(ctx, query, id)
\tif err != nil {
\t\treturn domain.Xxx{}, err
\t}
\tif len(list) > 0 {
\t\tres = list[0]
\t} else {
\t\treturn res, domain.ErrNotFound
\t}
\treturn
}
""",
        "function": "mysql_repository_fetch_get",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/repository/mysql/xxx.go",
    },

    # ── 9. MySQL repository — Store, Delete, Update ─────────────────────────
    {
        "normalized_code": """\
func (m *XxxRepository) GetByTitle(ctx context.Context, title string) (res domain.Xxx, err error) {
\tquery := `SELECT id, title, content, xxx_author_id, updated_at, created_at FROM xxx WHERE title = ?`
\tlist, err := m.fetch(ctx, query, title)
\tif err != nil {
\t\treturn
\t}
\tif len(list) > 0 {
\t\tres = list[0]
\t} else {
\t\treturn res, domain.ErrNotFound
\t}
\treturn
}

func (m *XxxRepository) Store(ctx context.Context, a *domain.Xxx) error {
\tquery := `INSERT xxx SET title=?, content=?, xxx_author_id=?, updated_at=?, created_at=?`
\tstmt, err := m.Conn.PrepareContext(ctx, query)
\tif err != nil {
\t\treturn err
\t}
\tres, err := stmt.ExecContext(ctx, a.Title, a.Content, a.XxxAuthor.ID, a.UpdatedAt, a.CreatedAt)
\tif err != nil {
\t\treturn err
\t}
\tlastID, err := res.LastInsertId()
\tif err != nil {
\t\treturn err
\t}
\ta.ID = lastID
\treturn nil
}

func (m *XxxRepository) Delete(ctx context.Context, id int64) error {
\tquery := "DELETE FROM xxx WHERE id = ?"
\tstmt, err := m.Conn.PrepareContext(ctx, query)
\tif err != nil {
\t\treturn err
\t}
\tres, err := stmt.ExecContext(ctx, id)
\tif err != nil {
\t\treturn err
\t}
\trowsAffected, err := res.RowsAffected()
\tif err != nil {
\t\treturn err
\t}
\tif rowsAffected != 1 {
\t\treturn fmt.Errorf("unexpected rows affected: %d", rowsAffected)
\t}
\treturn nil
}

func (m *XxxRepository) Update(ctx context.Context, ar *domain.Xxx) error {
\tquery := `UPDATE xxx SET title=?, content=?, xxx_author_id=?, updated_at=? WHERE ID = ?`
\tstmt, err := m.Conn.PrepareContext(ctx, query)
\tif err != nil {
\t\treturn err
\t}
\tres, err := stmt.ExecContext(ctx, ar.Title, ar.Content, ar.XxxAuthor.ID, ar.UpdatedAt, ar.ID)
\tif err != nil {
\t\treturn err
\t}
\taffect, err := res.RowsAffected()
\tif err != nil {
\t\treturn err
\t}
\tif affect != 1 {
\t\treturn fmt.Errorf("unexpected rows affected: %d", affect)
\t}
\treturn nil
}
""",
        "function": "mysql_repository_store_delete_update",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/repository/mysql/xxx.go",
    },

    # ── 10. Related entity MySQL repository ─────────────────────────────────
    {
        "normalized_code": """\
package mysql

import (
\t"context"
\t"database/sql"

\t"project/domain"
)

type XxxAuthorRepository struct {
\tDB *sql.DB
}

func NewXxxAuthorRepository(db *sql.DB) *XxxAuthorRepository {
\treturn &XxxAuthorRepository{DB: db}
}

func (m *XxxAuthorRepository) getOne(ctx context.Context, query string, args ...interface{}) (res domain.XxxAuthor, err error) {
\tstmt, err := m.DB.PrepareContext(ctx, query)
\tif err != nil {
\t\treturn domain.XxxAuthor{}, err
\t}
\trow := stmt.QueryRowContext(ctx, args...)
\tres = domain.XxxAuthor{}
\terr = row.Scan(&res.ID, &res.Name, &res.CreatedAt, &res.UpdatedAt)
\treturn
}

func (m *XxxAuthorRepository) GetByID(ctx context.Context, id int64) (domain.XxxAuthor, error) {
\tquery := `SELECT id, name, created_at, updated_at FROM xxx_author WHERE id=?`
\treturn m.getOne(ctx, query, id)
}
""",
        "function": "mysql_related_entity_repository",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/repository/mysql/xxx_author.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DELIVERY LAYER (Echo HTTP)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. Echo HTTP handler — CRUD + error mapping ────────────────────────
    {
        "normalized_code": """\
package rest

import (
\t"context"
\t"net/http"
\t"strconv"

\t"github.com/labstack/echo/v4"
\t"github.com/sirupsen/logrus"
\tvalidator "gopkg.in/go-playground/validator.v9"

\t"project/domain"
)

type ResponseError struct {
\tDetail string `json:"detail"`
}

type XxxService interface {
\tFetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error)
\tGetByID(ctx context.Context, id int64) (domain.Xxx, error)
\tUpdate(ctx context.Context, ar *domain.Xxx) error
\tGetByTitle(ctx context.Context, title string) (domain.Xxx, error)
\tStore(context.Context, *domain.Xxx) error
\tDelete(ctx context.Context, id int64) error
}

type XxxHandler struct {
\tService XxxService
}

const defaultNum = 10

func NewXxxHandler(e *echo.Echo, svc XxxService) {
\thandler := &XxxHandler{Service: svc}
\te.GET("/xxxs", handler.FetchXxx)
\te.POST("/xxxs", handler.Store)
\te.GET("/xxxs/:id", handler.GetByID)
\te.DELETE("/xxxs/:id", handler.Delete)
}

func (a *XxxHandler) FetchXxx(c echo.Context) error {
\tnumS := c.QueryParam("num")
\tnum, err := strconv.Atoi(numS)
\tif err != nil || num == 0 {
\t\tnum = defaultNum
\t}
\tcursor := c.QueryParam("cursor")
\tctx := c.Request().Context()
\tlistXxx, nextCursor, err := a.Service.Fetch(ctx, cursor, int64(num))
\tif err != nil {
\t\treturn c.JSON(getStatusCode(err), ResponseError{Detail: err.Error()})
\t}
\tc.Response().Header().Set(`X-Cursor`, nextCursor)
\treturn c.JSON(http.StatusOK, listXxx)
}

func (a *XxxHandler) GetByID(c echo.Context) error {
\tidP, err := strconv.Atoi(c.Param("id"))
\tif err != nil {
\t\treturn c.JSON(http.StatusNotFound, domain.ErrNotFound.Error())
\t}
\tid := int64(idP)
\tctx := c.Request().Context()
\txxx, err := a.Service.GetByID(ctx, id)
\tif err != nil {
\t\treturn c.JSON(getStatusCode(err), ResponseError{Detail: err.Error()})
\t}
\treturn c.JSON(http.StatusOK, xxx)
}

func isRequestValid(m *domain.Xxx) (bool, error) {
\tvalidate := validator.New()
\terr := validate.Struct(m)
\tif err != nil {
\t\treturn false, err
\t}
\treturn true, nil
}

func (a *XxxHandler) Store(c echo.Context) error {
\tvar xxx domain.Xxx
\terr := c.Bind(&xxx)
\tif err != nil {
\t\treturn c.JSON(http.StatusUnprocessableEntity, err.Error())
\t}
\tvar ok bool
\tif ok, err = isRequestValid(&xxx); !ok {
\t\treturn c.JSON(http.StatusBadRequest, err.Error())
\t}
\tctx := c.Request().Context()
\terr = a.Service.Store(ctx, &xxx)
\tif err != nil {
\t\treturn c.JSON(getStatusCode(err), ResponseError{Detail: err.Error()})
\t}
\treturn c.JSON(http.StatusCreated, xxx)
}

func (a *XxxHandler) Delete(c echo.Context) error {
\tidP, err := strconv.Atoi(c.Param("id"))
\tif err != nil {
\t\treturn c.JSON(http.StatusNotFound, domain.ErrNotFound.Error())
\t}
\tid := int64(idP)
\tctx := c.Request().Context()
\terr = a.Service.Delete(ctx, id)
\tif err != nil {
\t\treturn c.JSON(getStatusCode(err), ResponseError{Detail: err.Error()})
\t}
\treturn c.NoContent(http.StatusNoContent)
}

func getStatusCode(err error) int {
\tif err == nil {
\t\treturn http.StatusOK
\t}
\tlogrus.Error(err)
\tswitch err {
\tcase domain.ErrInternalServerError:
\t\treturn http.StatusInternalServerError
\tcase domain.ErrNotFound:
\t\treturn http.StatusNotFound
\tcase domain.ErrConflict:
\t\treturn http.StatusConflict
\tdefault:
\t\treturn http.StatusInternalServerError
\t}
}
""",
        "function": "echo_handler_crud_error_mapping",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "internal/rest/xxx.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 12. CORS middleware ─────────────────────────────────────────────────
    {
        "normalized_code": """\
package middleware

import "github.com/labstack/echo/v4"

func CORS(next echo.HandlerFunc) echo.HandlerFunc {
\treturn func(c echo.Context) error {
\t\tc.Response().Header().Set("Access-Control-Allow-Origin", "*")
\t\treturn next(c)
\t}
}
""",
        "function": "echo_cors_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/rest/middleware/cors.go",
    },

    # ── 13. Request timeout middleware ──────────────────────────────────────
    {
        "normalized_code": """\
package middleware

import (
\t"context"
\t"time"

\techo "github.com/labstack/echo/v4"
)

func SetRequestContextWithTimeout(d time.Duration) echo.MiddlewareFunc {
\treturn func(next echo.HandlerFunc) echo.HandlerFunc {
\t\treturn func(c echo.Context) error {
\t\t\tctx, cancel := context.WithTimeout(c.Request().Context(), d)
\t\t\tdefer cancel()
\t\t\tnewRequest := c.Request().WithContext(ctx)
\t\t\tc.SetRequest(newRequest)
\t\t\treturn next(c)
\t\t}
\t}
}
""",
        "function": "echo_timeout_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/rest/middleware/timeout.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 14. Cursor-based pagination helper ──────────────────────────────────
    {
        "normalized_code": """\
package repository

import (
\t"encoding/base64"
\t"time"
)

const timeFormat = "2006-01-02T15:04:05.999Z07:00"

func DecodeCursor(encodedTime string) (time.Time, error) {
\tbyt, err := base64.StdEncoding.DecodeString(encodedTime)
\tif err != nil {
\t\treturn time.Time{}, err
\t}
\ttimeString := string(byt)
\tt, err := time.Parse(timeFormat, timeString)
\treturn t, err
}

func EncodeCursor(t time.Time) string {
\ttimeString := t.Format(timeFormat)
\treturn base64.StdEncoding.EncodeToString([]byte(timeString))
}
""",
        "function": "cursor_pagination_encode_decode",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/repository/helper.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN / DI WIRING
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. Main.go — full DI wiring ───────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"database/sql"
\t"log"
\t"os"
\t"strconv"
\t"time"

\t_ "github.com/go-sql-driver/mysql"
\t"github.com/labstack/echo/v4"

\tmysqlRepo "project/internal/repository/mysql"
\t"project/xxx"
\t"project/internal/rest"
\t"project/internal/rest/middleware"
)

const (
\tdefaultTimeout = 30
\tdefaultAddress = ":9090"
)

func main() {
\tdbConn, err := sql.Open("mysql", os.Getenv("DATABASE_DSN"))
\tif err != nil {
\t\tlog.Fatal("failed to open connection to database", err)
\t}
\terr = dbConn.Ping()
\tif err != nil {
\t\tlog.Fatal("failed to ping database", err)
\t}
\tdefer func() {
\t\terr := dbConn.Close()
\t\tif err != nil {
\t\t\tlog.Fatal("got error when closing the DB connection", err)
\t\t}
\t}()

\te := echo.New()
\te.Use(middleware.CORS)
\ttimeoutStr := os.Getenv("CONTEXT_TIMEOUT")
\ttimeout, err := strconv.Atoi(timeoutStr)
\tif err != nil {
\t\ttimeout = defaultTimeout
\t}
\ttimeoutContext := time.Duration(timeout) * time.Second
\te.Use(middleware.SetRequestContextWithTimeout(timeoutContext))

\txxxAuthorRepo := mysqlRepo.NewXxxAuthorRepository(dbConn)
\txxxRepo := mysqlRepo.NewXxxRepository(dbConn)

\tsvc := xxx.NewService(xxxRepo, xxxAuthorRepo)
\trest.NewXxxHandler(e, svc)

\taddress := os.Getenv("SERVER_ADDRESS")
\tif address == "" {
\t\taddress = defaultAddress
\t}
\tlog.Fatal(e.Start(address))
}
""",
        "function": "main_di_wiring_echo",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/main.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. Service unit test with testify mock ─────────────────────────────
    {
        "normalized_code": """\
package xxx_test

import (
\t"context"
\t"errors"
\t"testing"

\t"github.com/stretchr/testify/assert"
\t"github.com/stretchr/testify/mock"

\t"project/xxx"
\t"project/xxx/mocks"
\t"project/domain"
)

func TestFetchXxx(t *testing.T) {
\tmockXxxRepo := new(mocks.XxxRepository)
\tmockXxx := domain.Xxx{Title: "Hello", Content: "Content"}
\tmockListXxx := make([]domain.Xxx, 0)
\tmockListXxx = append(mockListXxx, mockXxx)

\tt.Run("success", func(t *testing.T) {
\t\tmockXxxRepo.On("Fetch", mock.Anything, mock.AnythingOfType("string"),
\t\t\tmock.AnythingOfType("int64")).Return(mockListXxx, "next-cursor", nil).Once()
\t\tmockXxxAuthor := domain.XxxAuthor{ID: 1, Name: "Author Name"}
\t\tmockXxxAuthorRepo := new(mocks.XxxAuthorRepository)
\t\tmockXxxAuthorRepo.On("GetByID", mock.Anything, mock.AnythingOfType("int64")).Return(mockXxxAuthor, nil)
\t\tu := xxx.NewService(mockXxxRepo, mockXxxAuthorRepo)
\t\tlist, nextCursor, err := u.Fetch(context.TODO(), "12", int64(1))
\t\tassert.Equal(t, "next-cursor", nextCursor)
\t\tassert.NotEmpty(t, nextCursor)
\t\tassert.NoError(t, err)
\t\tassert.Len(t, list, len(mockListXxx))
\t\tmockXxxRepo.AssertExpectations(t)
\t\tmockXxxAuthorRepo.AssertExpectations(t)
\t})
}

func TestStore(t *testing.T) {
\tmockXxxRepo := new(mocks.XxxRepository)
\tmockXxx := domain.Xxx{Title: "Hello", Content: "Content"}

\tt.Run("success", func(t *testing.T) {
\t\ttempMockXxx := mockXxx
\t\ttempMockXxx.ID = 0
\t\tmockXxxRepo.On("GetByTitle", mock.Anything, mock.AnythingOfType("string")).Return(domain.Xxx{}, domain.ErrNotFound).Once()
\t\tmockXxxRepo.On("Store", mock.Anything, mock.AnythingOfType("*domain.Xxx")).Return(nil).Once()
\t\tmockXxxAuthorRepo := new(mocks.XxxAuthorRepository)
\t\tu := xxx.NewService(mockXxxRepo, mockXxxAuthorRepo)
\t\terr := u.Store(context.TODO(), &tempMockXxx)
\t\tassert.NoError(t, err)
\t\tassert.Equal(t, mockXxx.Title, tempMockXxx.Title)
\t\tmockXxxRepo.AssertExpectations(t)
\t})
}

func TestDelete(t *testing.T) {
\tmockXxxRepo := new(mocks.XxxRepository)
\tmockXxx := domain.Xxx{Title: "Hello", Content: "Content"}

\tt.Run("success", func(t *testing.T) {
\t\tmockXxxRepo.On("GetByID", mock.Anything, mock.AnythingOfType("int64")).Return(mockXxx, nil).Once()
\t\tmockXxxRepo.On("Delete", mock.Anything, mock.AnythingOfType("int64")).Return(nil).Once()
\t\tmockXxxAuthorRepo := new(mocks.XxxAuthorRepository)
\t\tu := xxx.NewService(mockXxxRepo, mockXxxAuthorRepo)
\t\terr := u.Delete(context.TODO(), mockXxx.ID)
\t\tassert.NoError(t, err)
\t\tmockXxxRepo.AssertExpectations(t)
\t})

\tt.Run("not-found", func(t *testing.T) {
\t\tmockXxxRepo.On("GetByID", mock.Anything, mock.AnythingOfType("int64")).Return(domain.Xxx{}, nil).Once()
\t\tmockXxxAuthorRepo := new(mocks.XxxAuthorRepository)
\t\tu := xxx.NewService(mockXxxRepo, mockXxxAuthorRepo)
\t\terr := u.Delete(context.TODO(), mockXxx.ID)
\t\tassert.Error(t, err)
\t\tmockXxxRepo.AssertExpectations(t)
\t})
}
""",
        "function": "service_unit_test_testify_mock",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "xxx/service_test.go",
    },

    # ── 17. Mockery generated mock ──────────────────────────────────────────
    {
        "normalized_code": """\
package mocks

import (
\t"context"

\t"project/domain"
\t"github.com/stretchr/testify/mock"
)

type XxxRepository struct {
\tmock.Mock
}

func (_m *XxxRepository) Delete(ctx context.Context, id int64) error {
\tret := _m.Called(ctx, id)
\tvar r0 error
\tif rf, ok := ret.Get(0).(func(context.Context, int64) error); ok {
\t\tr0 = rf(ctx, id)
\t} else {
\t\tr0 = ret.Error(0)
\t}
\treturn r0
}

func (_m *XxxRepository) Fetch(ctx context.Context, cursor string, num int64) ([]domain.Xxx, string, error) {
\tret := _m.Called(ctx, cursor, num)
\tvar r0 []domain.Xxx
\tvar r1 string
\tvar r2 error
\tif rf, ok := ret.Get(0).(func(context.Context, string, int64) ([]domain.Xxx, string, error)); ok {
\t\treturn rf(ctx, cursor, num)
\t}
\tif ret.Get(0) != nil {
\t\tr0 = ret.Get(0).([]domain.Xxx)
\t}
\tr1 = ret.Get(1).(string)
\tr2 = ret.Error(2)
\treturn r0, r1, r2
}

func (_m *XxxRepository) GetByID(ctx context.Context, id int64) (domain.Xxx, error) {
\tret := _m.Called(ctx, id)
\tvar r0 domain.Xxx
\tvar r1 error
\tif rf, ok := ret.Get(0).(func(context.Context, int64) (domain.Xxx, error)); ok {
\t\treturn rf(ctx, id)
\t}
\tr0 = ret.Get(0).(domain.Xxx)
\tr1 = ret.Error(1)
\treturn r0, r1
}

func (_m *XxxRepository) Store(ctx context.Context, a *domain.Xxx) error {
\tret := _m.Called(ctx, a)
\tvar r0 error
\tif rf, ok := ret.Get(0).(func(context.Context, *domain.Xxx) error); ok {
\t\tr0 = rf(ctx, a)
\t} else {
\t\tr0 = ret.Error(0)
\t}
\treturn r0
}

func NewXxxRepository(t interface {
\tmock.TestingT
\tCleanup(func())
}) *XxxRepository {
\tmockObj := &XxxRepository{}
\tmockObj.Mock.Test(t)
\tt.Cleanup(func() { mockObj.AssertExpectations(t) })
\treturn mockObj
}
""",
        "function": "mockery_generated_repository_mock",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "xxx/mocks/XxxRepository.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Go clean architecture domain entity struct",
    "Repository interface port with CRUD methods",
    "Service layer usecase with dependency injection constructor",
    "Parallel data enrichment with errgroup goroutines",
    "MySQL repository with prepared statement and row scanning",
    "Echo HTTP handler CRUD with domain error to status mapping",
    "Echo CORS middleware",
    "Request context timeout middleware",
    "Cursor-based pagination with base64 encoding",
    "Main.go dependency injection wiring Echo server",
    "Go unit test with testify mock assertions",
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
            client=client, collection=COLLECTION, query_vector=vec,
            language=LANGUAGE, limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q, "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q, "function": "NO_RESULT", "file_role": "?",
                "score": 0.0, "code_preview": "", "norm_ok": False,
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
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        print("\n  6b. Normalization audit:")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    No violations detected ✓")

    finally:
        print(f"\n── Step 7: {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points deleted. Count final: {count_final}")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")

    count_now = client.count(collection_name=COLLECTION).count
    report = audit_report(
        repo_name=REPO_NAME, dry_run=DRY_RUN, count_before=count_initial,
        count_after=count_now, patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed, query_results=query_results,
        violations=violations,
    )
    print(report)


if __name__ == "__main__":
    main()
