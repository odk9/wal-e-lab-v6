#!/usr/bin/env python3
"""
Wal-e Lab V6 — Wirings Ingestion Script
Repo: ThreeDotsLabs/wild-workouts-go-ddd-example (Go Medium — DDD+CQRS)

NO AST extraction (Go language). Manual wiring patterns based on DDD architecture.
Inserts 8 wiring patterns into Qdrant collection "wirings".

CONSTANTS:
- REPO_URL: https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example.git
- LANGUAGE: go
- FRAMEWORK: chi
- STACK: go+ddd+cqrs+grpc+firestore+chi
- CHARTE_VERSION: 1.0
- TAG: wirings/ThreeDotsLabs/wild-workouts-go-ddd-example
"""

import json
import time
from typing import Any
from dataclasses import dataclass

# Qdrant imports
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, Distance, VectorParams
except ImportError:
    raise ImportError("Install qdrant-client: pip install qdrant-client")

# Embedder import
try:
    from embedder import embed_documents_batch
except ImportError:
    raise ImportError("embedder.py not found in current directory")


# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example.git"
REPO_NAME = "ThreeDotsLabs/wild-workouts-go-ddd-example"
REPO_LOCAL = "/tmp/wild-workouts-go-ddd-example"
LANGUAGE = "go"
FRAMEWORK = "chi"
STACK = "go+ddd+cqrs+grpc+firestore+chi"
CHARTE_VERSION = "1.0"
TAG = f"wirings/{REPO_NAME}"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

TIMESTAMP = int(time.time())


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class WiringPayload:
    """Qdrant wiring point payload"""
    wiring_type: str                # "import_graph" | "dependency_chain" | "flow_pattern"
    description: str                # semantic description for embedding
    modules: list[str]              # files involved
    connections: list[str]          # links/flows between modules
    code_example: str               # normalized Go code example
    pattern_scope: str              # "ddd_domain" | "ddd_cqrs" | "ddd_dependency_inversion" | "crud_simple"
    language: str
    framework: str
    stack: str
    source_repo: str
    charte_version: str
    created_at: int
    _tag: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to Qdrant payload dict"""
        return {
            "wiring_type": self.wiring_type,
            "description": self.description,
            "modules": self.modules,
            "connections": self.connections,
            "code_example": self.code_example,
            "pattern_scope": self.pattern_scope,
            "language": self.language,
            "framework": self.framework,
            "stack": self.stack,
            "source_repo": self.source_repo,
            "charte_version": self.charte_version,
            "created_at": self.created_at,
            "_tag": self._tag,
        }


# ============================================================================
# WIRING PATTERNS (MANUAL — NO AST)
# ============================================================================

def create_wirings() -> list[WiringPayload]:
    """
    Create 8 manual wiring patterns for DDD/CQRS Go architecture.

    Returns:
        List of WiringPayload objects ready for Qdrant insertion.
    """
    wirings = []

    # ========================================================================
    # WIRING 1: Import Graph — DDD Package Dependency Tree
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="import_graph",
        description="DDD package dependency tree: cmd/main.go imports ports (HTTP/gRPC) which import app layer (use cases) which import domain layer (entities, VOs, repository interfaces). Domain has ZERO external dependencies. Adapters import domain, not reverse.",
        modules=[
            "cmd/main.go",
            "ports/http/handler.go",
            "ports/grpc/handler.go",
            "app/command/xxx_handler.go",
            "app/query/xxx_handler.go",
            "domain/xxx/xxx.go",
            "domain/xxx/repository.go",
            "domain/xxx/errors.go",
            "adapters/storage/xxxfirestorerepository.go",
        ],
        connections=[
            "cmd/main.go → ports/http/ (NewXxxHTTPServer)",
            "cmd/main.go → ports/grpc/ (NewXxxGRPCServer)",
            "ports/http/ → app/command (XxxCommandHandler)",
            "ports/http/ → app/query (XxxQueryHandler)",
            "ports/grpc/ → app/command (XxxCommandHandler)",
            "app/command/ → domain/xxx/ (Repository interface, entity)",
            "app/query/ → domain/xxx/ (Repository interface)",
            "adapters/storage/ → domain/xxx/ (implements Repository interface)",
        ],
        code_example="""
// cmd/main.go
package main

import (
	"github.com/ThreeDotsLabs/xxx/ports/http"
	"github.com/ThreeDotsLabs/xxx/ports/grpc"
	"github.com/ThreeDotsLabs/xxx/app/command"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
	"github.com/ThreeDotsLabs/xxx/adapters/storage"
)

func main() {
	firestoreClient := initFirestore()
	repo := storage.NewXxxFirestoreRepository(firestoreClient)

	cmdHandler := command.NewXxxCommandHandler(repo)
	httpServer := http.NewXxxHTTPServer(cmdHandler)
	grpcServer := grpc.NewXxxGRPCServer(cmdHandler)

	httpServer.Start()
	grpcServer.Start()
}

// domain/xxx/repository.go — defines port (interface)
package xxx

import "context"

type XxxRepository interface {
	GetXxx(ctx context.Context, id string) (*Xxx, error)
	SaveXxx(ctx context.Context, xxx *Xxx) error
}

// adapters/storage/xxxfirestorerepository.go — implements port
package storage

import (
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
	"cloud.google.com/go/firestore"
)

type XxxFirestoreRepository struct {
	client *firestore.Client
}

func (r XxxFirestoreRepository) GetXxx(ctx context.Context, id string) (*xxx.Xxx, error) {
	// implementation
}
""",
        pattern_scope="ddd_domain",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 2: Flow Pattern — DDD File Creation Order
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="flow_pattern",
        description="DDD file creation order for a complete feature: 1) domain/xxx/xxx.go (entity with private fields and methods), 2) domain/xxx/repository.go (port interface), 3) domain/xxx/errors.go (domain-specific errors), 4) domain/xxx/xxx_user.go (value objects, type-safe enums), 5) app/command/ (command handlers with business logic), 6) app/query/ (query handlers for reads), 7) adapters/xxxFirestoreRepository (persistence implementation), 8) ports/http/handler.go (HTTP endpoints), 9) ports/grpc/ (gRPC service), 10) cmd/main.go (wire and start).",
        modules=[
            "domain/xxx/xxx.go",
            "domain/xxx/repository.go",
            "domain/xxx/errors.go",
            "domain/xxx/xxx_user.go",
            "app/command/xxx_command.go",
            "app/command/xxx_handler.go",
            "app/query/xxx_query.go",
            "app/query/xxx_handler.go",
            "adapters/storage/xxxfirestorerepository.go",
            "ports/http/handler.go",
            "ports/grpc/handler.go",
            "cmd/main.go",
        ],
        connections=[
            "domain entities → methods (Cancel, Reschedule, UpdateRemarks)",
            "command → entity methods (trigger state changes)",
            "query → repository (read-only access)",
            "HTTP handler → command handler → repository → entity",
            "gRPC handler → command handler → repository → entity",
        ],
        code_example="""
// domain/xxx/xxx.go — entity
package xxx

import "errors"

type Xxx struct {
	id       string
	status   string
	remarks  string
	userType XxxUserType
}

func NewXxx(id, status string) (*Xxx, error) {
	if id == "" {
		return nil, ErrInvalidID
	}
	return &Xxx{id: id, status: status}, nil
}

func (x *Xxx) Cancel() error {
	if x.status == "cancelled" {
		return ErrAlreadyCancelled
	}
	x.status = "cancelled"
	return nil
}

func (x *Xxx) UpdateRemarks(remarks string) error {
	if len(remarks) > 1000 {
		return ErrRemarksToLong
	}
	x.remarks = remarks
	return nil
}

// domain/xxx/errors.go
var (
	ErrInvalidID         = errors.New("invalid id")
	ErrAlreadyCancelled  = errors.New("already cancelled")
	ErrRemarksToLong     = errors.New("remarks longer than 1000 chars")
	ErrNotFound          = errors.New("not found")
)

// app/command/xxx_handler.go — command handler
package command

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type XxxCommandHandler struct {
	repo xxx.XxxRepository
}

func NewXxxCommandHandler(repo xxx.XxxRepository) *XxxCommandHandler {
	return &XxxCommandHandler{repo: repo}
}

type CancelXxxCommand struct {
	XxxID string
}

func (h *XxxCommandHandler) CancelXxx(ctx context.Context, cmd CancelXxxCommand) error {
	x, err := h.repo.GetXxx(ctx, cmd.XxxID)
	if err != nil {
		return err
	}
	if err := x.Cancel(); err != nil {
		return err
	}
	return h.repo.SaveXxx(ctx, x)
}
""",
        pattern_scope="ddd_domain",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 3: Dependency Chain — Dependency Inversion Pattern
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="dependency_chain",
        description="Dependency inversion: domain defines interface Repository { GetXxx(ctx, id) → Xxx }. Adapter implements: type FirestoreXxxRepo struct{ client *firestore.Client }. Main wires: repo := adapters.NewFirestoreXxxRepo(client); handler := app.NewXxxHandler(repo). High-level modules (app) depend on abstractions (domain interfaces), not concrete implementations.",
        modules=[
            "domain/xxx/repository.go",
            "adapters/storage/xxxfirestorerepository.go",
            "app/command/xxx_handler.go",
            "cmd/main.go",
        ],
        connections=[
            "domain.Repository interface ← adapters.FirestoreXxxRepository (implements)",
            "app.XxxHandler depends on domain.Repository (injected)",
            "cmd/main creates concrete implementation and injects into handler",
        ],
        code_example="""
// domain/xxx/repository.go — high-level abstraction
package xxx

import "context"

type XxxRepository interface {
	GetXxx(ctx context.Context, id string) (*Xxx, error)
	SaveXxx(ctx context.Context, xxx *Xxx) error
	DeleteXxx(ctx context.Context, id string) error
}

// adapters/storage/xxxfirestorerepository.go — concrete implementation
package storage

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
	"cloud.google.com/go/firestore"
)

type XxxFirestoreRepository struct {
	client *firestore.Client
}

func NewXxxFirestoreRepository(client *firestore.Client) *XxxFirestoreRepository {
	return &XxxFirestoreRepository{client: client}
}

func (r *XxxFirestoreRepository) GetXxx(ctx context.Context, id string) (*xxx.Xxx, error) {
	doc, err := r.client.Collection("xxxs").Doc(id).Get(ctx)
	if err != nil {
		return nil, xxx.ErrNotFound
	}
	var data map[string]interface{}
	doc.DataTo(&data)
	// reconstruct entity from Firestore document
	return reconstructXxx(data)
}

func (r *XxxFirestoreRepository) SaveXxx(ctx context.Context, x *xxx.Xxx) error {
	_, err := r.client.Collection("xxxs").Doc(x.ID()).Set(ctx, x.ToMap())
	return err
}

// app/command/xxx_handler.go — depends on interface, not implementation
package command

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type XxxCommandHandler struct {
	repo xxx.XxxRepository  // interface type, not concrete
}

func NewXxxCommandHandler(repo xxx.XxxRepository) *XxxCommandHandler {
	return &XxxCommandHandler{repo: repo}
}

func (h *XxxCommandHandler) UpdateXxxRemarks(ctx context.Context, xxxID, remarks string) error {
	x, err := h.repo.GetXxx(ctx, xxxID)
	if err != nil {
		return err
	}
	if err := x.UpdateRemarks(remarks); err != nil {
		return err
	}
	return h.repo.SaveXxx(ctx, x)
}

// cmd/main.go — wire concrete implementation
package main

func main() {
	firestoreClient := initFirestore()
	repo := storage.NewXxxFirestoreRepository(firestoreClient)  // concrete
	handler := command.NewXxxCommandHandler(repo)  // injected as interface
}
""",
        pattern_scope="ddd_dependency_inversion",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 4: Flow Pattern — CQRS Command and Query Flows
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="flow_pattern",
        description="CQRS command flow: HTTP handler → app.XxxCommandHandler.Handle(ctx, command) → load entity from repo → entity.Method() validates business rules → repo.Save(entity). Query flow: HTTP handler → app.XxxQueryHandler.Handle(ctx, query) → repo.GetXxx() → return read model. Commands modify state (write), Queries only read (no side effects).",
        modules=[
            "ports/http/handler.go",
            "app/command/xxx_handler.go",
            "app/query/xxx_handler.go",
            "domain/xxx/xxx.go",
            "domain/xxx/repository.go",
        ],
        connections=[
            "HTTP POST/PUT/DELETE → CommandHandler.Handle()",
            "HTTP GET → QueryHandler.Handle()",
            "CommandHandler → repo.GetXxx() → entity.Method() → repo.SaveXxx()",
            "QueryHandler → repo.GetXxx() (read-only, no mutations)",
        ],
        code_example="""
// ports/http/handler.go — HTTP entry points
package http

import (
	"github.com/go-chi/chi/v5"
	"github.com/ThreeDotsLabs/xxx/app/command"
	"github.com/ThreeDotsLabs/xxx/app/query"
)

type XxxHandler struct {
	cmdHandler   *command.XxxCommandHandler
	queryHandler *query.XxxQueryHandler
}

func NewXxxHandler(
	cmdHandler *command.XxxCommandHandler,
	queryHandler *query.XxxQueryHandler,
) *XxxHandler {
	return &XxxHandler{cmdHandler: cmdHandler, queryHandler: queryHandler}
}

func (h *XxxHandler) RegisterRoutes(r chi.Router) {
	r.Post("/xxxs", h.CreateXxx)
	r.Get("/xxxs/{xxxID}", h.GetXxx)
	r.Put("/xxxs/{xxxID}", h.UpdateXxx)
	r.Delete("/xxxs/{xxxID}", h.DeleteXxx)
}

func (h *XxxHandler) CreateXxx(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title string \`json:"title"\`
	}
	json.NewDecoder(r.Body).Decode(&req)

	cmd := command.CreateXxxCommand{Title: req.Title}
	result, err := h.cmdHandler.CreateXxx(r.Context(), cmd)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *XxxHandler) GetXxx(w http.ResponseWriter, r *http.Request) {
	xxxID := chi.URLParam(r, "xxxID")

	qry := query.GetXxxQuery{XxxID: xxxID}
	result, err := h.queryHandler.GetXxx(r.Context(), qry)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

// app/command/xxx_handler.go — CQRS command side
package command

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type XxxCommandHandler struct {
	repo xxx.XxxRepository
}

type CreateXxxCommand struct {
	Title string
}

func (h *XxxCommandHandler) CreateXxx(ctx context.Context, cmd CreateXxxCommand) (*CreateXxxResult, error) {
	x, err := xxx.NewXxx(cmd.Title)
	if err != nil {
		return nil, err
	}
	if err := h.repo.SaveXxx(ctx, x); err != nil {
		return nil, err
	}
	return &CreateXxxResult{XxxID: x.ID()}, nil
}

// app/query/xxx_handler.go — CQRS query side (read-only)
package query

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type XxxQueryHandler struct {
	repo xxx.XxxRepository
}

type GetXxxQuery struct {
	XxxID string
}

type XxxReadModel struct {
	ID    string \`json:"id"\`
	Title string \`json:"title"\`
}

func (h *XxxQueryHandler) GetXxx(ctx context.Context, qry GetXxxQuery) (*XxxReadModel, error) {
	x, err := h.repo.GetXxx(ctx, qry.XxxID)
	if err != nil {
		return nil, err
	}
	return &XxxReadModel{
		ID:    x.ID(),
		Title: x.Title(),
	}, nil
}
""",
        pattern_scope="ddd_cqrs",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 5: Dependency Chain — Domain Entity Encapsulation
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="dependency_chain",
        description="Domain entity encapsulation: private fields, only constructor NewXxx() + methods (Cancel, Reschedule, UpdateRemarks). Each method validates business rules and returns error. No setters. Immutability enforced via value objects. Only domain methods mutate state; external code must go through repository save/load cycle.",
        modules=[
            "domain/xxx/xxx.go",
            "domain/xxx/xxx_user.go",
        ],
        connections=[
            "Private fields → public methods only",
            "NewXxx() constructor → initializes entity with validation",
            "Methods (Cancel, Reschedule, UpdateRemarks) → modify state + validate",
            "Value objects (XxxUserType) → type-safe enums, prevent invalid states",
        ],
        code_example="""
// domain/xxx/xxx.go — encapsulated entity
package xxx

import "time"

type Xxx struct {
	id           string
	status       string
	remarks      string
	userType     XxxUserType
	createdAt    time.Time
	rescheduled  int
}

// Constructor with validation
func NewXxx(id, status string, userType XxxUserType) (*Xxx, error) {
	if id == "" {
		return nil, ErrInvalidID
	}
	if !isValidStatus(status) {
		return nil, ErrInvalidStatus
	}
	return &Xxx{
		id:        id,
		status:    status,
		userType:  userType,
		createdAt: time.Now(),
		rescheduled: 0,
	}, nil
}

// Public getters only, no setters
func (x *Xxx) ID() string {
	return x.id
}

func (x *Xxx) Status() string {
	return x.status
}

func (x *Xxx) UserType() XxxUserType {
	return x.userType
}

// Business method: Cancel
func (x *Xxx) Cancel() error {
	if x.status != "scheduled" {
		return ErrCannotCancelNotScheduled
	}
	x.status = "cancelled"
	return nil
}

// Business method: Reschedule with validation
func (x *Xxx) Reschedule(newTime time.Time) error {
	if time.Now().Add(24 * time.Hour).After(x.createdAt) {
		return ErrRescheduleWindowClosed
	}
	if x.rescheduled >= 3 {
		return ErrMaxReschedulesExceeded
	}
	x.rescheduled++
	return nil
}

// Business method: UpdateRemarks with validation
func (x *Xxx) UpdateRemarks(remarks string) error {
	if len(remarks) > 1000 {
		return ErrRemarksToLong
	}
	x.remarks = remarks
	return nil
}

// domain/xxx/xxx_user.go — type-safe value object
package xxx

type XxxUserType string

const (
	Provider XxxUserType = "provider"
	Attendee XxxUserType = "attendee"
)

func NewXxxUserType(s string) (XxxUserType, error) {
	switch s {
	case "provider", "attendee":
		return XxxUserType(s), nil
	default:
		return "", ErrInvalidUserType
	}
}

// Check authorization based on value object type
func (x *Xxx) CanCancel(userType XxxUserType) bool {
	return x.userType == userType || userType == Provider
}
""",
        pattern_scope="ddd_domain",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 6: Flow Pattern — gRPC Service Integration
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="flow_pattern",
        description="gRPC service wiring: proto definition → generated Go code → ports/grpc/server.go implements generated interface → app layer handlers → domain. Microservices communicate via gRPC for internal service-to-service calls while HTTP exposes public API.",
        modules=[
            "api/proto/xxx/xxx.proto",
            "api/proto/xxx/xxx_grpc.pb.go",
            "ports/grpc/handler.go",
            "app/command/xxx_handler.go",
            "domain/xxx/xxx.go",
        ],
        connections=[
            "proto definition → gRPC server interface",
            "ports/grpc/handler implements gRPC service",
            "gRPC handler → app.XxxCommandHandler",
            "app.XxxCommandHandler → domain entity and repository",
        ],
        code_example="""
// api/proto/xxx/xxx.proto
syntax = "proto3";

package xxx;

service XxxService {
	rpc CreateXxx(CreateXxxRequest) returns (CreateXxxResponse);
	rpc GetXxx(GetXxxRequest) returns (GetXxxResponse);
	rpc UpdateXxxRemarks(UpdateXxxRemarksRequest) returns (UpdateXxxRemarksResponse);
}

message CreateXxxRequest {
	string title = 1;
	string status = 2;
}

message CreateXxxResponse {
	string xxx_id = 1;
}

message GetXxxRequest {
	string xxx_id = 1;
}

message GetXxxResponse {
	string xxx_id = 1;
	string status = 2;
	string remarks = 3;
}

message UpdateXxxRemarksRequest {
	string xxx_id = 1;
	string remarks = 2;
}

message UpdateXxxRemarksResponse {
	bool success = 1;
}

// ports/grpc/handler.go — implements gRPC service
package grpc

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/app/command"
	pb "github.com/ThreeDotsLabs/xxx/api/proto/xxx"
)

type XxxGRPCServer struct {
	pb.UnimplementedXxxServiceServer
	cmdHandler *command.XxxCommandHandler
}

func NewXxxGRPCServer(cmdHandler *command.XxxCommandHandler) *XxxGRPCServer {
	return &XxxGRPCServer{cmdHandler: cmdHandler}
}

func (s *XxxGRPCServer) CreateXxx(ctx context.Context, req *pb.CreateXxxRequest) (*pb.CreateXxxResponse, error) {
	cmd := command.CreateXxxCommand{
		Title:  req.Title,
		Status: req.Status,
	}
	result, err := s.cmdHandler.CreateXxx(ctx, cmd)
	if err != nil {
		return nil, err
	}
	return &pb.CreateXxxResponse{XxxId: result.XxxID}, nil
}

func (s *XxxGRPCServer) GetXxx(ctx context.Context, req *pb.GetXxxRequest) (*pb.GetXxxResponse, error) {
	// query handler call
	x, err := s.queryHandler.GetXxx(ctx, req.XxxId)
	if err != nil {
		return nil, err
	}
	return &pb.GetXxxResponse{
		XxxId:   x.ID(),
		Status:  x.Status(),
		Remarks: x.Remarks(),
	}, nil
}

func (s *XxxGRPCServer) UpdateXxxRemarks(ctx context.Context, req *pb.UpdateXxxRemarksRequest) (*pb.UpdateXxxRemarksResponse, error) {
	cmd := command.UpdateXxxRemarksCommand{
		XxxID:   req.XxxId,
		Remarks: req.Remarks,
	}
	err := s.cmdHandler.UpdateXxxRemarks(ctx, cmd)
	return &pb.UpdateXxxRemarksResponse{Success: err == nil}, err
}

// cmd/main.go — wire gRPC server
func main() {
	listener, _ := net.Listen("tcp", ":50051")
	grpcServer := grpc.NewServer()
	xxxGRPCHandler := grpc.NewXxxGRPCServer(cmdHandler)
	pb.RegisterXxxServiceServer(grpcServer, xxxGRPCHandler)
	grpcServer.Serve(listener)
}
""",
        pattern_scope="ddd_cqrs",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 7: Dependency Chain — Value Object Type Safety
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="dependency_chain",
        description="Value object type safety: type XxxUserType string + const (Provider, Attendee XxxUserType = \"provider\", \"attendee\") + func NewXxxUserType(s string) (XxxUserType, error) with validation. Used in entity methods for authorization checks. Prevents invalid enums at compile-time and runtime.",
        modules=[
            "domain/xxx/xxx_user.go",
            "domain/xxx/xxx.go",
            "app/command/xxx_handler.go",
        ],
        connections=[
            "XxxUserType value object → type-safe enum",
            "NewXxxUserType() constructor → validates enum values",
            "Entity methods use XxxUserType for authorization",
            "CommandHandler passes user type through domain",
        ],
        code_example="""
// domain/xxx/xxx_user.go — type-safe value object
package xxx

import "errors"

type XxxUserType string

const (
	Provider XxxUserType = "provider"
	Attendee XxxUserType = "attendee"
)

var (
	ErrInvalidUserType = errors.New("invalid user type")
)

func NewXxxUserType(s string) (XxxUserType, error) {
	switch s {
	case "provider", "attendee":
		return XxxUserType(s), nil
	default:
		return "", ErrInvalidUserType
	}
}

func (ut XxxUserType) String() string {
	return string(ut)
}

func (ut XxxUserType) IsProvider() bool {
	return ut == Provider
}

func (ut XxxUserType) IsAttendee() bool {
	return ut == Attendee
}

// domain/xxx/xxx.go — entity uses value object
package xxx

type Xxx struct {
	id       string
	userType XxxUserType  // value object instead of plain string
	status   string
}

func NewXxx(id string, userType XxxUserType) (*Xxx, error) {
	if id == "" {
		return nil, ErrInvalidID
	}
	// userType already validated in NewXxxUserType()
	return &Xxx{id: id, userType: userType, status: "pending"}, nil
}

// Business rule: only provider can change remarks
func (x *Xxx) UpdateRemarks(remarks string, editor XxxUserType) error {
	if editor != Provider {
		return ErrOnlyProviderCanUpdateRemarks
	}
	if len(remarks) > 1000 {
		return ErrRemarksToLong
	}
	x.remarks = remarks
	return nil
}

// Business rule: attendee can cancel, provider must reschedule
func (x *Xxx) Cancel(requester XxxUserType) error {
	if requester == Attendee {
		x.status = "cancelled_by_attendee"
		return nil
	}
	if requester == Provider {
		x.status = "cancelled_by_provider"
		return nil
	}
	return ErrInvalidUserType
}

// app/command/xxx_handler.go — handler validates and constructs value objects
package command

import (
	"context"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type XxxCommandHandler struct {
	repo xxx.XxxRepository
}

type UpdateXxxRemarksCommand struct {
	XxxID   string
	Remarks string
	Editor  string  // user type as string from HTTP request
}

func (h *XxxCommandHandler) UpdateXxxRemarks(ctx context.Context, cmd UpdateXxxRemarksCommand) error {
	// Validate and construct value object
	editorType, err := xxx.NewXxxUserType(cmd.Editor)
	if err != nil {
		return err
	}

	x, err := h.repo.GetXxx(ctx, cmd.XxxID)
	if err != nil {
		return err
	}

	// Pass type-safe value object to entity method
	if err := x.UpdateRemarks(cmd.Remarks, editorType); err != nil {
		return err
	}

	return h.repo.SaveXxx(ctx, x)
}
""",
        pattern_scope="ddd_domain",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    # ========================================================================
    # WIRING 8: Flow Pattern — Test Wiring and Layers
    # ========================================================================
    wirings.append(WiringPayload(
        wiring_type="flow_pattern",
        description="Test wiring by layer: domain tests are pure unit tests with no mocks (entities are PODOs). App tests mock repository interface. Adapter tests integrate with Firestore emulator. Ports tests use httptest + chi test server. Domain layer is most testable because it has zero dependencies; test complexity increases at higher layers.",
        modules=[
            "domain/xxx/xxx_test.go",
            "app/command/xxx_handler_test.go",
            "adapters/storage/xxxfirestorerepository_test.go",
            "ports/http/handler_test.go",
        ],
        connections=[
            "domain/xxx_test: pure unit, no mocks",
            "app/xxx_handler_test: mock domain.Repository interface",
            "adapters/storage_test: integration with Firestore emulator",
            "ports/http_test: httptest.Server + chi router test",
        ],
        code_example="""
// domain/xxx/xxx_test.go — pure unit tests, no mocks
package xxx

import (
	"testing"
)

func TestNewXxx(t *testing.T) {
	x, err := NewXxx("id123", "scheduled")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if x.ID() != "id123" {
		t.Errorf("expected id123, got %s", x.ID())
	}
}

func TestCancelXxx(t *testing.T) {
	x, _ := NewXxx("id123", "scheduled")
	err := x.Cancel()
	if err != nil {
		t.Fatalf("cancel failed: %v", err)
	}
	if x.Status() != "cancelled" {
		t.Errorf("expected cancelled, got %s", x.Status())
	}
}

func TestCancelXxxTwice(t *testing.T) {
	x, _ := NewXxx("id123", "scheduled")
	x.Cancel()
	err := x.Cancel()  // second cancel should fail
	if err != ErrAlreadyCancelled {
		t.Errorf("expected ErrAlreadyCancelled, got %v", err)
	}
}

// app/command/xxx_handler_test.go — unit tests with mock repository
package command

import (
	"context"
	"testing"
	"github.com/ThreeDotsLabs/xxx/domain/xxx"
)

type MockXxxRepository struct {
	getXxxFunc func(context.Context, string) (*xxx.Xxx, error)
	saveXxxFunc func(context.Context, *xxx.Xxx) error
}

func (m *MockXxxRepository) GetXxx(ctx context.Context, id string) (*xxx.Xxx, error) {
	return m.getXxxFunc(ctx, id)
}

func (m *MockXxxRepository) SaveXxx(ctx context.Context, x *xxx.Xxx) error {
	return m.saveXxxFunc(ctx, x)
}

func TestCancelXxxCommand(t *testing.T) {
	mockRepo := &MockXxxRepository{
		getXxxFunc: func(ctx context.Context, id string) (*xxx.Xxx, error) {
			return xxx.NewXxx("id123", "scheduled")
		},
		saveXxxFunc: func(ctx context.Context, x *xxx.Xxx) error {
			return nil
		},
	}

	handler := NewXxxCommandHandler(mockRepo)
	err := handler.CancelXxx(context.Background(), CancelXxxCommand{XxxID: "id123"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

// adapters/storage/xxxfirestorerepository_test.go — integration with emulator
package storage

import (
	"context"
	"testing"
	"cloud.google.com/go/firestore"
)

func TestFirestoreXxxRepository(t *testing.T) {
	// Use Firestore emulator (start: gcloud beta emulators firestore start)
	ctx := context.Background()
	client, _ := firestore.NewClient(ctx, "demo-project")
	defer client.Close()

	repo := NewXxxFirestoreRepository(client)

	x, _ := xxx.NewXxx("id123", "scheduled")
	err := repo.SaveXxx(ctx, x)
	if err != nil {
		t.Fatalf("save failed: %v", err)
	}

	retrieved, err := repo.GetXxx(ctx, "id123")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if retrieved.Status() != "scheduled" {
		t.Errorf("expected scheduled, got %s", retrieved.Status())
	}
}

// ports/http/handler_test.go — test HTTP layer
package http

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"github.com/go-chi/chi/v5"
)

func TestCreateXxxHTTP(t *testing.T) {
	mockCmdHandler := &MockXxxCommandHandler{
		createXxxFunc: func(ctx context.Context, cmd command.CreateXxxCommand) (*command.CreateXxxResult, error) {
			return &command.CreateXxxResult{XxxID: "id123"}, nil
		},
	}

	handler := NewXxxHandler(mockCmdHandler, nil)

	body := map[string]string{"title": "Test"}
	jsonBody, _ := json.Marshal(body)
	req := httptest.NewRequest("POST", "/xxxs", bytes.NewReader(jsonBody))
	w := httptest.NewRecorder()

	router := chi.NewRouter()
	handler.RegisterRoutes(router)
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}
""",
        pattern_scope="crud_simple",
        language=LANGUAGE,
        framework=FRAMEWORK,
        stack=STACK,
        source_repo=REPO_URL,
        charte_version=CHARTE_VERSION,
        created_at=TIMESTAMP,
        _tag=TAG,
    ))

    return wirings


# ============================================================================
# QDRANT INSERTION
# ============================================================================

def insert_wirings_to_qdrant(wirings: list[WiringPayload]) -> None:
    """
    Insert wiring payloads into Qdrant collection "wirings".

    Args:
        wirings: List of WiringPayload objects to insert.
    """
    client = QdrantClient(path=KB_PATH)

    import uuid

    print(f"\n{'='*70}")
    print(f"Wal-e Lab V6 — Wirings Ingestion")
    print(f"Repo: {REPO_NAME}")
    print(f"Language: {LANGUAGE}")
    print(f"Framework: {FRAMEWORK}")
    print(f"Collection: {COLLECTION}")
    print(f"Wirings to insert: {len(wirings)}")
    print(f"Dry run: {DRY_RUN}")
    print(f"{'='*70}\n")

    # Batch embed all descriptions
    descriptions = [w.description for w in wirings]
    embeddings = embed_documents_batch(descriptions)

    points_to_insert = []

    for idx, (wiring, embedding) in enumerate(zip(wirings, embeddings), start=1):
        payload = wiring.to_dict()

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload=payload,
        )
        points_to_insert.append(point)

        print(f"[{idx}] {wiring.wiring_type:20} | {wiring.pattern_scope:25} | {wiring.description[:60]}...")

    print(f"\n{'='*70}")

    if DRY_RUN:
        print("DRY RUN — points prepared but NOT inserted.")
        print(f"Total points prepared: {len(points_to_insert)}")
        return

    # Insert into Qdrant
    try:
        client.upsert(
            collection_name=COLLECTION,
            points=points_to_insert,
        )
        print(f"\n✓ Successfully upserted {len(points_to_insert)} wiring points into '{COLLECTION}'")
    except Exception as e:
        print(f"\n✗ Error upserting points: {e}")
        raise

    # Verify insertion
    collection_info = client.get_collection(COLLECTION)
    print(f"✓ Collection '{COLLECTION}' now has {collection_info.points_count} points total")

    print(f"\n{'='*70}\n")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Entry point: create and insert wiring patterns."""
    print("\nGenerating wiring patterns...")
    wirings = create_wirings()
    print(f"✓ Generated {len(wirings)} wiring patterns\n")

    insert_wirings_to_qdrant(wirings)

    print("\nIngest complete!\n")


if __name__ == "__main__":
    main()
