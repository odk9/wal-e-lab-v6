"""
ingest_wild_workouts.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de ThreeDotsLabs/wild-workouts-go-ddd-example dans la KB Qdrant V6.

Go B — DDD + CQRS + Clean Architecture. Chi + gRPC + Firestore.

Usage:
    .venv/bin/python3 ingest_wild_workouts.py
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
REPO_URL = "https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example.git"
REPO_NAME = "ThreeDotsLabs/wild-workouts-go-ddd-example"
REPO_LOCAL = "/tmp/wild_workouts"
LANGUAGE = "go"
FRAMEWORK = "chi"
STACK = "go+ddd+cqrs+grpc+firestore+chi"
CHARTE_VERSION = "1.0"
TAG = "ThreeDotsLabs/wild-workouts-go-ddd-example"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Training→Xxx, training→xxx, trainings→xxxs
#       User→XxxUser, user→xxxUser, users→xxxUsers (FORBIDDEN)
#       notes→remarks
#       Kept: chi, grpc, firestore, context, error, http, logrus, time
# G-1: no panic(). G-2: no fmt.Println/Printf.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Domain entity with constructor + methods ─────────────────────────
    {
        "normalized_code": """\
package xxx

import (
\t"errors"
\t"time"
)

type Xxx struct {
\tuuid          string
\txxxUserUUID   string
\txxxUserName   string
\tscheduledTime time.Time
\tremarks       string
\tproposedNewTime time.Time
\tmoveProposedBy  XxxUserType
\tcanceled      bool
}

func NewXxx(uuid string, xxxUserUUID string, xxxUserName string, scheduledTime time.Time) (*Xxx, error) {
\tif uuid == "" {
\t\treturn nil, errors.New("empty uuid")
\t}
\tif xxxUserUUID == "" {
\t\treturn nil, errors.New("empty xxxUser uuid")
\t}
\tif xxxUserName == "" {
\t\treturn nil, errors.New("empty xxxUser name")
\t}
\tif scheduledTime.IsZero() {
\t\treturn nil, errors.New("zero scheduled time")
\t}

\treturn &Xxx{
\t\tuuid:        uuid,
\t\txxxUserUUID: xxxUserUUID,
\t\txxxUserName: xxxUserName,
\t\tscheduledTime: scheduledTime,
\t}, nil
}

func (t *Xxx) Cancel() error {
\tif t.canceled {
\t\treturn errors.New("already canceled")
\t}
\tt.canceled = true
\treturn nil
}

func (t *Xxx) UpdateRemarks(remarks string) error {
\tif len(remarks) > 1000 {
\t\treturn errors.New("remark too long")
\t}
\tt.remarks = remarks
\treturn nil
}

func (t *Xxx) RescheduleXxx(newTime time.Time) error {
\tif newTime.IsZero() {
\t\treturn errors.New("zero reschedule time")
\t}
\tif !t.canBeCanceledForFree() {
\t\treturn errors.New("cannot reschedule less than 24h before")
\t}
\tt.scheduledTime = newTime
\treturn nil
}

func (t *Xxx) canBeCanceledForFree() bool {
\treturn time.Until(t.scheduledTime) >= time.Hour*24
}

func (t *Xxx) UUID() string           { return t.uuid }
func (t *Xxx) XxxUserUUID() string    { return t.xxxUserUUID }
func (t *Xxx) ScheduledTime() time.Time { return t.scheduledTime }
func (t *Xxx) Remarks() string        { return t.remarks }
""",
        "function": "ddd_domain_entity_constructor_methods",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "internal/xxxs/domain/xxx/xxx.go",
    },

    # ── 2. Domain value object — type-safe enum ────────────────────────────
    {
        "normalized_code": """\
package xxx

type XxxUserType struct {
\ts string
}

var (
\tProvider = XxxUserType{"provider"}
\tAttendee = XxxUserType{"attendee"}
)

func (u XxxUserType) IsZero() bool {
\treturn u == XxxUserType{}
}

func NewXxxUserTypeFromString(s string) (XxxUserType, error) {
\tswitch s {
\tcase "provider":
\t\treturn Provider, nil
\tcase "attendee":
\t\treturn Attendee, nil
\t}
\treturn XxxUserType{}, errInvalidXxxUserType
}
""",
        "function": "ddd_value_object_type_safe_enum",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "internal/xxxs/domain/xxx/xxx_user_type.go",
    },

    # ── 3. Domain value object — user context ──────────────────────────────
    {
        "normalized_code": """\
package xxx

type XxxUser struct {
\txxxUserUUID string
\txxxUserType XxxUserType
}

func NewXxxUser(xxxUserUUID string, xxxUserType XxxUserType) (XxxUser, error) {
\tif xxxUserUUID == "" {
\t\treturn XxxUser{}, errors.New("missing xxxUser UUID")
\t}
\tif xxxUserType.IsZero() {
\t\treturn XxxUser{}, errors.New("missing xxxUser type")
\t}
\treturn XxxUser{xxxUserUUID: xxxUserUUID, xxxUserType: xxxUserType}, nil
}

func (u XxxUser) UUID() string         { return u.xxxUserUUID }
func (u XxxUser) Type() XxxUserType    { return u.xxxUserType }
func (u XxxUser) IsProvider() bool     { return u.xxxUserType == Provider }
""",
        "function": "ddd_value_object_user_context",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "internal/xxxs/domain/xxx/xxx_user.go",
    },

    # ── 4. Repository interface (port) ─────────────────────────────────────
    {
        "normalized_code": """\
package xxx

import "context"

type Repository interface {
\tAddXxx(ctx context.Context, tr *Xxx) error

\tGetXxx(ctx context.Context, xxxUUID string, xxxUser XxxUser) (*Xxx, error)

\tUpdateXxx(
\t\tctx context.Context,
\t\txxxUUID string,
\t\txxxUser XxxUser,
\t\tupdateFn func(ctx context.Context, tr *Xxx) (*Xxx, error),
\t) error
}
""",
        "function": "ddd_repository_interface_port",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "internal/xxxs/domain/xxx/repository.go",
    },

    # ── 5. Domain errors — custom types ────────────────────────────────────
    {
        "normalized_code": """\
package xxx

import "fmt"

type NotFoundError struct {
\tXxxUUID string
}

func (e NotFoundError) Error() string {
\treturn fmt.Sprintf("record '%s' not found", e.XxxUUID)
}

type ForbiddenToSeeError struct {
\tRequestingXxxUserUUID string
\tOwnerXxxUserUUID      string
}

func (e ForbiddenToSeeError) Error() string {
\treturn fmt.Sprintf("xxxUser '%s' cannot see record owned by '%s'", e.RequestingXxxUserUUID, e.OwnerXxxUserUUID)
}

var errInvalidXxxUserType = errors.New("invalid xxxUser type")
""",
        "function": "ddd_domain_errors_custom_types",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/xxxs/domain/xxx/errors.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CQRS — COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 6. CQRS command handler interface ──────────────────────────────────
    {
        "normalized_code": """\
package decorator

import "context"

type CommandHandler[C any] interface {
\tHandle(ctx context.Context, cmd C) error
}

type QueryHandler[Q any, R any] interface {
\tHandle(ctx context.Context, q Q) (R, error)
}
""",
        "function": "cqrs_handler_interfaces_generic",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/common/decorator/handler.go",
    },

    # ── 7. Command: Schedule (create) ──────────────────────────────────────
    {
        "normalized_code": """\
package command

import (
\t"context"
\t"time"

\t"project/internal/xxxs/domain/xxx"
)

type ScheduleXxx struct {
\tXxxUUID       string
\tXxxUserUUID   string
\tXxxUserName   string
\tScheduledTime time.Time
\tRemarks       string
}

type XxxUserService interface {
\tUpdateBalance(ctx context.Context, xxxUserID string, amountChange int) error
}

type ProviderService interface {
\tScheduleSlot(ctx context.Context, scheduledTime time.Time) error
\tCancelSlot(ctx context.Context, scheduledTime time.Time) error
\tMoveSlot(ctx context.Context, newTime time.Time, originalTime time.Time) error
}

type scheduleXxxHandler struct {
\trepo            xxx.Repository
\txxxUserService  XxxUserService
\tproviderService ProviderService
}

func (h scheduleXxxHandler) Handle(ctx context.Context, cmd ScheduleXxx) error {
\ttr, err := xxx.NewXxx(cmd.XxxUUID, cmd.XxxUserUUID, cmd.XxxUserName, cmd.ScheduledTime)
\tif err != nil {
\t\treturn err
\t}
\tif cmd.Remarks != "" {
\t\tif err := tr.UpdateRemarks(cmd.Remarks); err != nil {
\t\t\treturn err
\t\t}
\t}
\tif err := h.repo.AddXxx(ctx, tr); err != nil {
\t\treturn err
\t}
\tif err := h.xxxUserService.UpdateBalance(ctx, cmd.XxxUserUUID, -1); err != nil {
\t\treturn err
\t}
\tif err := h.providerService.ScheduleSlot(ctx, cmd.ScheduledTime); err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "cqrs_command_schedule_create",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/xxxs/app/command/schedule_xxx.go",
    },

    # ── 8. Command: Cancel — repository callback pattern ───────────────────
    {
        "normalized_code": """\
package command

import (
\t"context"

\t"project/internal/xxxs/domain/xxx"
)

type CancelXxx struct {
\tXxxUUID string
\tXxxUser xxx.XxxUser
}

type cancelXxxHandler struct {
\trepo            xxx.Repository
\txxxUserService  XxxUserService
\tproviderService ProviderService
}

func (h cancelXxxHandler) Handle(ctx context.Context, cmd CancelXxx) error {
\treturn h.repo.UpdateXxx(ctx, cmd.XxxUUID, cmd.XxxUser,
\t\tfunc(ctx context.Context, tr *xxx.Xxx) (*xxx.Xxx, error) {
\t\t\tif err := tr.Cancel(); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\tif tr.CanBeCanceledForFree() {
\t\t\t\tif err := h.xxxUserService.UpdateBalance(ctx, cmd.XxxUser.UUID(), 1); err != nil {
\t\t\t\t\treturn nil, err
\t\t\t\t}
\t\t\t}

\t\t\tif err := h.providerService.CancelSlot(ctx, tr.ScheduledTime()); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\treturn tr, nil
\t\t})
}
""",
        "function": "cqrs_command_cancel_callback",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/xxxs/app/command/cancel_xxx.go",
    },

    # ── 9. Command: Reschedule — update with cross-service ─────────────────
    {
        "normalized_code": """\
package command

import (
\t"context"
\t"time"

\t"project/internal/xxxs/domain/xxx"
)

type RescheduleXxx struct {
\tXxxUUID string
\tXxxUser xxx.XxxUser
\tNewTime time.Time
\tRemarks string
}

type rescheduleXxxHandler struct {
\trepo            xxx.Repository
\txxxUserService  XxxUserService
\tproviderService ProviderService
}

func (h rescheduleXxxHandler) Handle(ctx context.Context, cmd RescheduleXxx) error {
\treturn h.repo.UpdateXxx(ctx, cmd.XxxUUID, cmd.XxxUser,
\t\tfunc(ctx context.Context, tr *xxx.Xxx) (*xxx.Xxx, error) {
\t\t\toriginalTime := tr.ScheduledTime()

\t\t\tif cmd.Remarks != "" {
\t\t\t\tif err := tr.UpdateRemarks(cmd.Remarks); err != nil {
\t\t\t\t\treturn nil, err
\t\t\t\t}
\t\t\t}

\t\t\tif err := tr.RescheduleXxx(cmd.NewTime); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\tif err := h.providerService.MoveSlot(ctx, cmd.NewTime, originalTime); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\treturn tr, nil
\t\t})
}
""",
        "function": "cqrs_command_reschedule_cross_service",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/xxxs/app/command/reschedule_xxx.go",
    },

    # ── 10. Command: Request + Approve reschedule ──────────────────────────
    {
        "normalized_code": """\
package command

import (
\t"context"
\t"time"

\t"project/internal/xxxs/domain/xxx"
)

type RequestRescheduleXxx struct {
\tXxxUUID string
\tXxxUser xxx.XxxUser
\tNewTime time.Time
}

type requestRescheduleXxxHandler struct {
\trepo xxx.Repository
}

func (h requestRescheduleXxxHandler) Handle(ctx context.Context, cmd RequestRescheduleXxx) error {
\treturn h.repo.UpdateXxx(ctx, cmd.XxxUUID, cmd.XxxUser,
\t\tfunc(ctx context.Context, tr *xxx.Xxx) (*xxx.Xxx, error) {
\t\t\ttr.ProposeReschedule(cmd.NewTime, cmd.XxxUser.Type())
\t\t\treturn tr, nil
\t\t})
}

type ApproveRescheduleXxx struct {
\tXxxUUID string
\tXxxUser xxx.XxxUser
}

type approveRescheduleXxxHandler struct {
\trepo            xxx.Repository
\txxxUserService  XxxUserService
\tproviderService ProviderService
}

func (h approveRescheduleXxxHandler) Handle(ctx context.Context, cmd ApproveRescheduleXxx) error {
\treturn h.repo.UpdateXxx(ctx, cmd.XxxUUID, cmd.XxxUser,
\t\tfunc(ctx context.Context, tr *xxx.Xxx) (*xxx.Xxx, error) {
\t\t\toriginalTime := tr.ScheduledTime()

\t\t\tif err := tr.ApproveReschedule(cmd.XxxUser.Type()); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\tif err := h.providerService.MoveSlot(ctx, tr.ScheduledTime(), originalTime); err != nil {
\t\t\t\treturn nil, err
\t\t\t}

\t\t\treturn tr, nil
\t\t})
}
""",
        "function": "cqrs_command_request_approve",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/xxxs/app/command/request_approve.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CQRS — QUERIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. Query: AllXxx + XxxForUser ─────────────────────────────────────
    {
        "normalized_code": """\
package query

import (
\t"context"
\t"time"
)

type Xxx struct {
\tUUID           string
\tXxxUserUUID    string
\tXxxUserName    string
\tScheduledTime  time.Time
\tRemarks        string
\tProposedTime   *time.Time
\tMoveProposedBy *string
\tCanBeCancelled bool
}

type AllXxx struct{}

type allXxxHandler struct {
\treadModel AllXxxReadModel
}

type AllXxxReadModel interface {
\tAllXxx(ctx context.Context) ([]Xxx, error)
}

func (h allXxxHandler) Handle(ctx context.Context, _ AllXxx) ([]Xxx, error) {
\treturn h.readModel.AllXxx(ctx)
}

type XxxForXxxUser struct {
\tXxxUserUUID string
}

type xxxForXxxUserHandler struct {
\treadModel XxxForXxxUserReadModel
}

type XxxForXxxUserReadModel interface {
\tFindXxxForXxxUser(ctx context.Context, xxxUserUUID string) ([]Xxx, error)
}

func (h xxxForXxxUserHandler) Handle(ctx context.Context, q XxxForXxxUser) ([]Xxx, error) {
\treturn h.readModel.FindXxxForXxxUser(ctx, q.XxxUserUUID)
}
""",
        "function": "cqrs_queries_all_and_filtered",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "internal/xxxs/app/query/xxx.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION LAYER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 12. Application struct (CQRS container) ────────────────────────────
    {
        "normalized_code": """\
package app

import (
\t"project/internal/xxxs/app/command"
\t"project/internal/xxxs/app/query"
\t"project/internal/common/decorator"
)

type Application struct {
\tCommands Commands
\tQueries  Queries
}

type Commands struct {
\tApproveRescheduleXxx  decorator.CommandHandler[command.ApproveRescheduleXxx]
\tCancelXxx             decorator.CommandHandler[command.CancelXxx]
\tRejectRescheduleXxx   decorator.CommandHandler[command.RejectRescheduleXxx]
\tRescheduleXxx         decorator.CommandHandler[command.RescheduleXxx]
\tRequestRescheduleXxx  decorator.CommandHandler[command.RequestRescheduleXxx]
\tScheduleXxx           decorator.CommandHandler[command.ScheduleXxx]
}

type Queries struct {
\tAllXxx         decorator.QueryHandler[query.AllXxx, []query.Xxx]
\tXxxForXxxUser  decorator.QueryHandler[query.XxxForXxxUser, []query.Xxx]
}
""",
        "function": "cqrs_application_container",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "internal/xxxs/app/app.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # HTTP HANDLERS (PORTS)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. HTTP handler — GET list by role + POST create ──────────────────
    {
        "normalized_code": """\
package ports

import (
\t"net/http"

\t"github.com/go-chi/render"
\t"github.com/google/uuid"

\t"project/internal/common/auth"
\t"project/internal/xxxs/app"
\t"project/internal/xxxs/app/command"
\t"project/internal/xxxs/app/query"
)

type HttpServer struct {
\tapp app.Application
}

func NewHttpServer(app app.Application) HttpServer {
\treturn HttpServer{app: app}
}

func (h HttpServer) GetXxxs(w http.ResponseWriter, r *http.Request) {
\txxxUser, _ := auth.XxxUserFromCtx(r.Context())

\tvar xxxs []query.Xxx
\tvar err error
\tif xxxUser.Role == "provider" {
\t\txxxs, err = h.app.Queries.AllXxx.Handle(r.Context(), query.AllXxx{})
\t} else {
\t\txxxs, err = h.app.Queries.XxxForXxxUser.Handle(r.Context(), query.XxxForXxxUser{XxxUserUUID: xxxUser.UUID})
\t}
\tif err != nil {
\t\thttperr.RespondWithSlugError(err, w, r)
\t\treturn
\t}
\trender.Respond(w, r, mapXxxsToResponse(xxxs))
}

func (h HttpServer) CreateXxx(w http.ResponseWriter, r *http.Request) {
\tvar reqBody CreateXxxRequest
\trender.Decode(r, &reqBody)
\txxxUser, _ := auth.XxxUserFromCtx(r.Context())

\tcmd := command.ScheduleXxx{
\t\tXxxUUID:       uuid.New().String(),
\t\tXxxUserUUID:   xxxUser.UUID,
\t\tXxxUserName:   xxxUser.DisplayName,
\t\tScheduledTime: reqBody.Time,
\t\tRemarks:       reqBody.Remarks,
\t}
\terr := h.app.Commands.ScheduleXxx.Handle(r.Context(), cmd)
\tif err != nil {
\t\thttperr.RespondWithSlugError(err, w, r)
\t\treturn
\t}
\tw.Header().Set("content-location", "/xxxs/"+cmd.XxxUUID)
\tw.WriteHeader(http.StatusNoContent)
}
""",
        "function": "http_handler_get_list_post_create",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "internal/xxxs/ports/http.go",
    },

    # ── 14. HTTP handler — DELETE + PUT ────────────────────────────────────
    {
        "normalized_code": """\
func (h HttpServer) CancelXxx(w http.ResponseWriter, r *http.Request, xxxUUID openapi_types.UUID) {
\txxxUser, _ := newDomainXxxUserFromAuthXxxUser(r.Context())
\terr := h.app.Commands.CancelXxx.Handle(r.Context(), command.CancelXxx{
\t\tXxxUUID: xxxUUID.String(),
\t\tXxxUser: xxxUser,
\t})
\tif err != nil {
\t\thttperr.RespondWithSlugError(err, w, r)
\t\treturn
\t}
\tw.WriteHeader(http.StatusNoContent)
}

func (h HttpServer) RescheduleXxx(w http.ResponseWriter, r *http.Request, xxxUUID openapi_types.UUID) {
\tvar reqBody RescheduleXxxRequest
\trender.Decode(r, &reqBody)
\txxxUser, _ := newDomainXxxUserFromAuthXxxUser(r.Context())

\terr := h.app.Commands.RescheduleXxx.Handle(r.Context(), command.RescheduleXxx{
\t\tXxxUUID: xxxUUID.String(),
\t\tXxxUser: xxxUser,
\t\tNewTime: reqBody.Time,
\t\tRemarks: reqBody.Remarks,
\t})
\tif err != nil {
\t\thttperr.RespondWithSlugError(err, w, r)
\t\treturn
\t}
\tw.WriteHeader(http.StatusNoContent)
}

func (h HttpServer) RequestRescheduleXxx(w http.ResponseWriter, r *http.Request, xxxUUID openapi_types.UUID) {
\tvar reqBody RescheduleXxxRequest
\trender.Decode(r, &reqBody)
\txxxUser, _ := newDomainXxxUserFromAuthXxxUser(r.Context())

\terr := h.app.Commands.RequestRescheduleXxx.Handle(r.Context(), command.RequestRescheduleXxx{
\t\tXxxUUID: xxxUUID.String(),
\t\tXxxUser: xxxUser,
\t\tNewTime: reqBody.Time,
\t})
\tif err != nil {
\t\thttperr.RespondWithSlugError(err, w, r)
\t\treturn
\t}
\tw.WriteHeader(http.StatusNoContent)
}
""",
        "function": "http_handler_cancel_reschedule",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "internal/xxxs/ports/http.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DECORATORS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. Decorator — logging + metrics + ApplyDecorators ────────────────
    {
        "normalized_code": """\
package decorator

import (
\t"context"
\t"fmt"
\t"strings"
\t"time"

\t"github.com/sirupsen/logrus"
)

type MetricsClient interface {
\tInc(key string, value int)
}

type commandLoggingDecorator[C any] struct {
\tbase   CommandHandler[C]
\tlogger *logrus.Entry
}

func (d commandLoggingDecorator[C]) Handle(ctx context.Context, cmd C) (err error) {
\thandlerType := generateActionName(cmd)
\tlogger := d.logger.WithFields(logrus.Fields{
\t\t"command":      handlerType,
\t\t"command_body": fmt.Sprintf("%#v", cmd),
\t})
\tlogger.Debug("Executing command")
\tdefer func() {
\t\tif err == nil {
\t\t\tlogger.Info("Command executed successfully")
\t\t} else {
\t\t\tlogger.WithError(err).Error("Failed to execute command")
\t\t}
\t}()
\treturn d.base.Handle(ctx, cmd)
}

type commandMetricsDecorator[C any] struct {
\tbase   CommandHandler[C]
\tclient MetricsClient
}

func (d commandMetricsDecorator[C]) Handle(ctx context.Context, cmd C) (err error) {
\tstart := time.Now()
\tactionName := strings.ToLower(generateActionName(cmd))
\tdefer func() {
\t\tend := time.Since(start)
\t\td.client.Inc(fmt.Sprintf("commands.%s.duration", actionName), int(end.Seconds()))
\t\tif err == nil {
\t\t\td.client.Inc(fmt.Sprintf("commands.%s.success", actionName), 1)
\t\t} else {
\t\t\td.client.Inc(fmt.Sprintf("commands.%s.failure", actionName), 1)
\t\t}
\t}()
\treturn d.base.Handle(ctx, cmd)
}

func ApplyCommandDecorators[H any](handler CommandHandler[H], logger *logrus.Entry, metricsClient MetricsClient) CommandHandler[H] {
\treturn commandLoggingDecorator[H]{
\t\tbase: commandMetricsDecorator[H]{
\t\t\tbase:   handler,
\t\t\tclient: metricsClient,
\t\t},
\t\tlogger: logger,
\t}
}
""",
        "function": "decorator_logging_metrics_chain",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/common/decorator/command.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DI WIRING
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. Service wiring (DI) ────────────────────────────────────────────
    {
        "normalized_code": """\
package service

import (
\t"context"
\t"os"

\t"cloud.google.com/go/firestore"
\t"github.com/sirupsen/logrus"

\t"project/internal/xxxs/adapters"
\t"project/internal/xxxs/app"
\t"project/internal/xxxs/app/command"
\t"project/internal/xxxs/app/query"
\t"project/internal/common/metrics"
)

func NewApplication(ctx context.Context) (app.Application, func()) {
\tproviderClient, closeProviderClient, _ := grpcClient.NewProviderClient()
\txxxUserClient, closeXxxUserClient, _ := grpcClient.NewXxxUserClient()

\tproviderGrpc := adapters.NewProviderGrpc(providerClient)
\txxxUserGrpc := adapters.NewXxxUserGrpc(xxxUserClient)

\treturn newApplication(ctx, providerGrpc, xxxUserGrpc), func() {
\t\tcloseProviderClient()
\t\tcloseXxxUserClient()
\t}
}

func newApplication(ctx context.Context, providerSvc command.ProviderService, xxxUserSvc command.XxxUserService) app.Application {
\tclient, _ := firestore.NewClient(ctx, os.Getenv("GCP_PROJECT"))
\txxxRepository := adapters.NewXxxFirestoreRepository(client)

\tlogger := logrus.NewEntry(logrus.StandardLogger())
\tmetricsClient := metrics.NoOp{}

\treturn app.Application{
\t\tCommands: app.Commands{
\t\t\tCancelXxx:            command.NewCancelXxxHandler(xxxRepository, xxxUserSvc, providerSvc, logger, metricsClient),
\t\t\tRescheduleXxx:        command.NewRescheduleXxxHandler(xxxRepository, xxxUserSvc, providerSvc, logger, metricsClient),
\t\t\tRequestRescheduleXxx: command.NewRequestRescheduleXxxHandler(xxxRepository, logger, metricsClient),
\t\t\tScheduleXxx:          command.NewScheduleXxxHandler(xxxRepository, xxxUserSvc, providerSvc, logger, metricsClient),
\t\t},
\t\tQueries: app.Queries{
\t\t\tAllXxx:        query.NewAllXxxHandler(xxxRepository, logger, metricsClient),
\t\t\tXxxForXxxUser: query.NewXxxForXxxUserHandler(xxxRepository, logger, metricsClient),
\t\t},
\t}
}

func NewComponentTestApplication(ctx context.Context) app.Application {
\treturn newApplication(ctx, ProviderServiceMock{}, XxxUserServiceMock{})
}
""",
        "function": "di_wiring_service_layer",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "internal/xxxs/service/service.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH MIDDLEWARE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 17. Firebase auth middleware ───────────────────────────────────────
    {
        "normalized_code": """\
package auth

import (
\t"context"
\t"net/http"

\tfirebaseAuth "firebase.google.com/go/auth"
)

type FirebaseHttpMiddleware struct {
\tAuthClient *firebaseAuth.Client
}

type XxxUserCtx struct {
\tUUID        string
\tEmail       string
\tRole        string
\tDisplayName string
}

type ctxKey int

const xxxUserContextKey ctxKey = iota

func (a FirebaseHttpMiddleware) Middleware(next http.Handler) http.Handler {
\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
\t\tctx := r.Context()
\t\tbearerToken := a.tokenFromHeader(r)
\t\tif bearerToken == "" {
\t\t\thttperr.Unauthorised("empty-bearer-token", nil, w, r)
\t\t\treturn
\t\t}
\t\ttoken, err := a.AuthClient.VerifyIDToken(ctx, bearerToken)
\t\tif err != nil {
\t\t\thttperr.Unauthorised("unable-to-verify-jwt", err, w, r)
\t\t\treturn
\t\t}
\t\tctx = context.WithValue(ctx, xxxUserContextKey, XxxUserCtx{
\t\t\tUUID:        token.UID,
\t\t\tEmail:       token.Claims["email"].(string),
\t\t\tRole:        token.Claims["role"].(string),
\t\t\tDisplayName: token.Claims["name"].(string),
\t\t})
\t\tr = r.WithContext(ctx)
\t\tnext.ServeHTTP(w, r)
\t})
}

func XxxUserFromCtx(ctx context.Context) (XxxUserCtx, error) {
\tu, ok := ctx.Value(xxxUserContextKey).(XxxUserCtx)
\tif ok {
\t\treturn u, nil
\t}
\treturn XxxUserCtx{}, NoXxxUserInContextError
}
""",
        "function": "firebase_auth_middleware_context",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/common/auth/http.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # HTTP SERVER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 18. Chi HTTP server setup ──────────────────────────────────────────
    {
        "normalized_code": """\
package server

import (
\t"net/http"
\t"os"
\t"strings"

\t"github.com/go-chi/chi/v5"
\t"github.com/go-chi/chi/v5/middleware"
\t"github.com/go-chi/cors"
\t"github.com/sirupsen/logrus"

\t"project/internal/common/auth"
\t"project/internal/common/logs"
)

func RunHTTPServer(createHandler func(router chi.Router) http.Handler) {
\tRunHTTPServerOnAddr(":"+os.Getenv("PORT"), createHandler)
}

func RunHTTPServerOnAddr(addr string, createHandler func(router chi.Router) http.Handler) {
\tapiRouter := chi.NewRouter()
\tsetMiddlewares(apiRouter)

\trootRouter := chi.NewRouter()
\trootRouter.Mount("/api", createHandler(apiRouter))

\thttp.ListenAndServe(addr, rootRouter)
}

func setMiddlewares(router *chi.Mux) {
\trouter.Use(middleware.RequestID)
\trouter.Use(middleware.RealIP)
\trouter.Use(logs.NewStructuredLogger(logrus.StandardLogger()))
\trouter.Use(middleware.Recoverer)

\taddCorsMiddleware(router)
\taddAuthMiddleware(router)

\trouter.Use(
\t\tmiddleware.SetHeader("X-Content-Type-Options", "nosniff"),
\t\tmiddleware.SetHeader("X-Frame-Options", "deny"),
\t)
\trouter.Use(middleware.NoCache)
}

func addCorsMiddleware(router *chi.Mux) {
\tallowedOrigins := strings.Split(os.Getenv("CORS_ALLOWED_ORIGINS"), ";")
\tcorsMiddleware := cors.New(cors.Options{
\t\tAllowedOrigins:   allowedOrigins,
\t\tAllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
\t\tAllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token"},
\t})
\trouter.Use(corsMiddleware.Handler)
}

func addAuthMiddleware(router *chi.Mux) {
\trouter.Use(auth.FirebaseHttpMiddleware{}.Middleware)
}
""",
        "function": "chi_http_server_middleware_chain",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "internal/common/server/http.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 19. Slug errors + HTTP error mapping ───────────────────────────────
    {
        "normalized_code": """\
package errors

type ErrorType struct {
\tt string
}

var (
\tErrorTypeUnknown        = ErrorType{"unknown"}
\tErrorTypeAuthorization  = ErrorType{"authorization"}
\tErrorTypeIncorrectInput = ErrorType{"incorrect-input"}
)

type SlugError struct {
\terror     string
\tslug      string
\terrorType ErrorType
}

func (s SlugError) Error() string   { return s.error }
func (s SlugError) Slug() string    { return s.slug }
func (s SlugError) ErrorType() ErrorType { return s.errorType }

func NewSlugError(msg string, slug string) SlugError {
\treturn SlugError{error: msg, slug: slug, errorType: ErrorTypeUnknown}
}

func NewAuthorizationError(msg string, slug string) SlugError {
\treturn SlugError{error: msg, slug: slug, errorType: ErrorTypeAuthorization}
}

func NewIncorrectInputError(msg string, slug string) SlugError {
\treturn SlugError{error: msg, slug: slug, errorType: ErrorTypeIncorrectInput}
}
""",
        "function": "slug_error_types_constructors",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/common/errors/errors.go",
    },

    # ── 20. HTTP error response mapping ────────────────────────────────────
    {
        "normalized_code": """\
package httperr

import (
\t"net/http"

\t"project/internal/common/errors"
)

func RespondWithSlugError(err error, w http.ResponseWriter, r *http.Request) {
\tslugError, ok := err.(errors.SlugError)
\tif !ok {
\t\tInternalError("internal-server-error", err, w, r)
\t\treturn
\t}

\tswitch slugError.ErrorType() {
\tcase errors.ErrorTypeAuthorization:
\t\tUnauthorised(slugError.Slug(), slugError, w, r)
\tcase errors.ErrorTypeIncorrectInput:
\t\tBadRequest(slugError.Slug(), slugError, w, r)
\tdefault:
\t\tInternalError(slugError.Slug(), slugError, w, r)
\t}
}

func InternalError(slug string, err error, w http.ResponseWriter, r *http.Request) {
\thttpRespondWithError(err, slug, w, r, "Internal server error", http.StatusInternalServerError)
}

func Unauthorised(slug string, err error, w http.ResponseWriter, r *http.Request) {
\thttpRespondWithError(err, slug, w, r, "Unauthorised", http.StatusUnauthorized)
}

func BadRequest(slug string, err error, w http.ResponseWriter, r *http.Request) {
\thttpRespondWithError(err, slug, w, r, "Bad request", http.StatusBadRequest)
}
""",
        "function": "http_error_response_mapping",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/common/server/httperr/http_error.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # gRPC
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 21. gRPC adapter (calling external service) ────────────────────────
    {
        "normalized_code": """\
package adapters

import (
\t"context"
\t"time"

\t"google.golang.org/protobuf/types/known/timestamppb"

\t"project/internal/common/genproto/xxxUsers"
\t"project/internal/common/genproto/provider"
)

type XxxUserGrpc struct {
\tclient xxxUsers.XxxUsersServiceClient
}

func NewXxxUserGrpc(client xxxUsers.XxxUsersServiceClient) XxxUserGrpc {
\treturn XxxUserGrpc{client: client}
}

func (s XxxUserGrpc) UpdateBalance(ctx context.Context, xxxUserID string, amountChange int) error {
\t_, err := s.client.UpdateBalance(ctx, &xxxUsers.UpdateBalanceRequest{
\t\tXxxUserId:    xxxUserID,
\t\tAmountChange: int64(amountChange),
\t})
\treturn err
}

type ProviderGrpc struct {
\tclient provider.ProviderServiceClient
}

func NewProviderGrpc(client provider.ProviderServiceClient) ProviderGrpc {
\treturn ProviderGrpc{client: client}
}

func (s ProviderGrpc) ScheduleSlot(ctx context.Context, scheduledTime time.Time) error {
\t_, err := s.client.ScheduleSlot(ctx, &provider.UpdateHourRequest{
\t\tTime: timestamppb.New(scheduledTime),
\t})
\treturn err
}

func (s ProviderGrpc) CancelSlot(ctx context.Context, scheduledTime time.Time) error {
\t_, err := s.client.CancelSlot(ctx, &provider.UpdateHourRequest{
\t\tTime: timestamppb.New(scheduledTime),
\t})
\treturn err
}

func (s ProviderGrpc) MoveSlot(ctx context.Context, newTime time.Time, originalTime time.Time) error {
\terr := s.ScheduleSlot(ctx, newTime)
\tif err != nil {
\t\treturn err
\t}
\treturn s.CancelSlot(ctx, originalTime)
}
""",
        "function": "grpc_adapter_cross_service",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "internal/xxxs/adapters/grpc.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 22. Command unit test with manual mocks ────────────────────────────
    {
        "normalized_code": """\
package command_test

import (
\t"context"
\t"testing"
\t"time"

\t"github.com/stretchr/testify/require"

\t"project/internal/xxxs/domain/xxx"
)

type repositoryMock struct {
\tXxxs map[string]xxx.Xxx
}

func (r *repositoryMock) UpdateXxx(
\tctx context.Context,
\txxxUUID string,
\txxxUser xxx.XxxUser,
\tupdateFn func(ctx context.Context, tr *xxx.Xxx) (*xxx.Xxx, error),
) error {
\ttr, ok := r.Xxxs[xxxUUID]
\tif !ok {
\t\treturn fmt.Errorf("record '%s' not found", xxxUUID)
\t}
\tupdatedXxx, err := updateFn(ctx, &tr)
\tif err != nil {
\t\treturn err
\t}
\tr.Xxxs[xxxUUID] = *updatedXxx
\treturn nil
}

type providerServiceMock struct {
\tslotsCancelled []time.Time
}

func (t *providerServiceMock) CancelSlot(ctx context.Context, scheduledTime time.Time) error {
\tt.slotsCancelled = append(t.slotsCancelled, scheduledTime)
\treturn nil
}

type xxxUserServiceMock struct {
\tbalanceUpdates []balanceUpdate
}

type balanceUpdate struct {
\txxxUserID    string
\tamountChange int
}

func (u *xxxUserServiceMock) UpdateBalance(ctx context.Context, xxxUserID string, amountChange int) error {
\tu.balanceUpdates = append(u.balanceUpdates, balanceUpdate{xxxUserID, amountChange})
\treturn nil
}

func TestCancelXxx(t *testing.T) {
\txxx1, _ := xxx.NewXxx("uuid-1", "xxxUser-1", "Name", time.Now().Add(48*time.Hour))
\trepo := &repositoryMock{Xxxs: map[string]xxx.Xxx{"uuid-1": *xxx1}}
\tproviderSvc := &providerServiceMock{}
\txxxUserSvc := &xxxUserServiceMock{}

\thandler := NewCancelXxxHandler(repo, xxxUserSvc, providerSvc, nil, nil)
\txxxUser, _ := xxx.NewXxxUser("xxxUser-1", xxx.Attendee)
\terr := handler.Handle(context.Background(), CancelXxx{XxxUUID: "uuid-1", XxxUser: xxxUser})
\trequire.NoError(t, err)
\trequire.Len(t, providerSvc.slotsCancelled, 1)
\trequire.Len(t, xxxUserSvc.balanceUpdates, 1)
}
""",
        "function": "command_unit_test_manual_mocks",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "internal/xxxs/app/command/cancel_xxx_test.go",
    },

    # ── 23. Main.go entry point ────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"context"
\t"net/http"

\t"github.com/go-chi/chi/v5"

\t"project/internal/common/logs"
\t"project/internal/common/server"
\t"project/internal/xxxs/ports"
\t"project/internal/xxxs/service"
)

func main() {
\tlogs.Init()
\tctx := context.Background()
\tapp, cleanup := service.NewApplication(ctx)
\tdefer cleanup()

\tserver.RunHTTPServer(func(router chi.Router) http.Handler {
\t\treturn ports.HandlerFromMux(ports.NewHttpServer(app), router)
\t})
}
""",
        "function": "main_entry_point_ddd_service",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "internal/xxxs/main.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "DDD domain entity with constructor and business methods",
    "DDD value object type-safe enum pattern Go",
    "DDD repository interface port with callback update pattern",
    "CQRS command handler schedule create with cross-service calls",
    "CQRS command cancel with repository callback pattern",
    "CQRS query handler all and filtered by role",
    "CQRS application container commands and queries struct",
    "Go decorator pattern logging metrics for command handler",
    "Firebase auth middleware context extraction JWT",
    "Chi HTTP server middleware chain CORS auth recoverer",
    "Slug error type domain error to HTTP status mapping",
    "gRPC adapter calling external microservice protobuf",
    "DI wiring service layer with adapters and decorators",
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
