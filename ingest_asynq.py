"""
ingest_asynq.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de hibiken/asynq dans la KB Qdrant V6.

Focus : CORE patterns Go background task queue (Client init, Task creation,
Server/worker, Handler registration, scheduled/periodic tasks, retry config,
queue priority, middleware, error handling, task lifecycle, graceful shutdown).

Usage:
    .venv/bin/python3 ingest_asynq.py
"""

from __future__ import annotations

import subprocess
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
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/hibiken/asynq.git"
REPO_NAME = "hibiken/asynq"
REPO_LOCAL = "/tmp/asynq"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+asynq+redis+queue"
CHARTE_VERSION = "1.0"
TAG = "hibiken/asynq"
SOURCE_REPO = "https://github.com/hibiken/asynq"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Asynq = background task queue powered by Redis.
# Patterns CORE : Client initialization, Task creation/enqueueing, Server/Worker setup,
# Handler registration, Scheduled/Periodic tasks, Retry logic, Queue priority,
# Middleware/hooks, Error handling, Task lifecycle states, Graceful shutdown.
#
# U-5 (entités métier) : task → work_unit, user → xxx, message → payload,
# order → sequence, item → element, post → entry, comment → annotation,
# event → signal. KEEP: asynq type names (Task, Client, Server, Handler, etc.),
# Go/stdlib terms (context, error, chan).

PATTERNS: list[dict] = [
    # ── 1. Redis connection initialization + Client creation ──────────────────
    {
        "normalized_code": """\
package main

import (
	"github.com/hibiken/asynq"
	"github.com/redis/go-redis/v9"
)

func initializeRedisAndClient() *asynq.Client {
	redisClient := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})

	client := asynq.NewClientFromRedisClient(redisClient)
	return client
}
""",
        "function": "redis_client_initialization",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 2. Task creation with type, payload, and options (MaxRetry, ProcessIn) ─
    {
        "normalized_code": """\
package main

import (
	"encoding/json"
	"github.com/hibiken/asynq"
	"time"
)

type WorkPayload struct {
	ID    int    `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

func createWorkUnit(payload WorkPayload) (*asynq.Task, error) {
	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	asynqJob := asynq.NewTask(
		"work_unit:process",
		jsonPayload,
		asynq.MaxRetry(5),
		asynq.Timeout(10*time.Minute),
		asynq.Queue("high"),
	)
	return asynqJob, nil
}
""",
        "function": "task_creation_with_options",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 3. Client enqueue task + error handling ──────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"time"
)

func enqueueWorkUnit(ctx context.Context, client *asynq.Client, asynqJob *asynq.Task) (string, error) {
	info, err := client.EnqueueContext(ctx, asynqJob)
	if err != nil {
		return "", err
	}
	return info.ID, nil
}

func enqueueWorkUnitWithDelay(ctx context.Context, client *asynq.Client, asynqJob *asynq.Task, delay time.Duration) (string, error) {
	info, err := client.EnqueueContext(ctx, asynqJob, asynq.ProcessIn(delay))
	if err != nil {
		return "", err
	}
	return info.ID, nil
}
""",
        "function": "client_enqueue_task",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 4. Server initialization + config (Concurrency, Queues, StrictPriority) ─
    {
        "normalized_code": """\
package main

import (
	"github.com/hibiken/asynq"
	"github.com/redis/go-redis/v9"
)

func startServer(redisClient *redis.UniversalClient) (*asynq.Server, error) {
	server := asynq.NewServer(
		asynq.RedisClientOpt{Client: redisClient},
		asynq.Config{
			Concurrency:     10,
			Queues: map[string]int{
				"critical": 9,
				"high":     6,
				"default":  3,
				"low":      1,
			},
			StrictPriority: true,
		},
	)
	return server, nil
}
""",
        "function": "server_initialization_config",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 5. ServeMux creation + handler registration with pattern matching ─────
    {
        "normalized_code": """\
package main

import (
	"context"
	"encoding/json"
	"github.com/hibiken/asynq"
	"log"
)

type Xxx struct {
	ID    int
	Name  string
	Email string
}

func handleProcessWorkUnit(ctx context.Context, asynqJob *asynq.Task) error {
	var xxx Xxx
	if err := json.Unmarshal(asynqJob.Payload(), &xxx); err != nil {
		return err
	}
	log.Printf("Processing work unit: %d %s", xxx.ID, xxx.Name)
	return nil
}

func createServeMux() *asynq.ServeMux {
	mux := asynq.NewServeMux()
	mux.HandleFunc("work_unit:process", handleProcessWorkUnit)
	mux.HandleFunc("work_unit:delete", handleDeleteWorkUnit)
	mux.HandleFunc("signal:notify", handleSignalNotify)
	return mux
}
""",
        "function": "servemux_handler_registration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "asynq.go",
    },
    # ── 6. HandlerFunc type — wrapping ordinary functions as task handlers ─────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"log"
)

func handleProcessElement(ctx context.Context, asynqJob *asynq.Task) error {
	log.Printf("Processing element: %s", string(asynqJob.Payload()))
	return nil
}

func registerHandlersAsFunc(mux *asynq.ServeMux) {
	mux.Handle("element:create", asynq.HandlerFunc(handleProcessElement))
	mux.Handle("element:update", asynq.HandlerFunc(func(ctx context.Context, asynqJob *asynq.Task) error {
		log.Printf("Updated element")
		return nil
	}))
}
""",
        "function": "handler_func_adapter",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "asynq.go",
    },
    # ── 7. Scheduler initialization + periodic task registration (cron) ────────
    {
        "normalized_code": """\
package main

import (
	"github.com/hibiken/asynq"
	"github.com/redis/go-redis/v9"
	"time"
)

func initScheduler(redisClient redis.UniversalClient) (*asynq.Scheduler, error) {
	scheduler := asynq.NewSchedulerFromRedisClient(redisClient, &asynq.SchedulerOpts{
		Location: time.UTC,
	})
	return scheduler, nil
}

func registerPeriodicTasks(scheduler *asynq.Scheduler) error {
	scheduler.Register(
		"0 */1 * * *",
		asynq.NewTask("signal:hourly-sync", nil),
		&asynq.RegisterOptions{},
	)
	scheduler.Register(
		"0 0 * * *",
		asynq.NewTask("signal:daily-cleanup", nil),
		&asynq.RegisterOptions{},
	)
	return nil
}
""",
        "function": "scheduler_periodic_tasks_cron",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 8. Task retry configuration + custom retry delay function ──────────────
    {
        "normalized_code": """\
package main

import (
	"github.com/hibiken/asynq"
	"math"
	"time"
)

func exponentialBackoffRetryDelay(retryCount int, err error, asynqJob *asynq.Task) time.Duration {
	const baseDelay = 5 * time.Second
	const maxDelay = 1 * time.Hour

	delay := time.Duration(math.Pow(2, float64(retryCount))) * baseDelay
	if delay > maxDelay {
		delay = maxDelay
	}
	return delay
}

func createServerWithCustomRetry(redisClient interface{}) *asynq.Server {
	server := asynq.NewServer(
		asynq.RedisClientOpt{},
		asynq.Config{
			Concurrency:    10,
			RetryDelayFunc: exponentialBackoffRetryDelay,
		},
	)
	return server
}
""",
        "function": "retry_configuration_custom_delay",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 9. ErrorHandler + ErrorHandlerFunc adapter ────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"log"
)

func handleWorkUnitError(ctx context.Context, asynqJob *asynq.Task, err error) {
	log.Printf("Work unit %s failed: %v", asynqJob.Type(), err)
}

func createServerWithErrorHandler(redisClient interface{}) *asynq.Server {
	server := asynq.NewServer(
		asynq.RedisClientOpt{},
		asynq.Config{
			Concurrency:  10,
			ErrorHandler: asynq.ErrorHandlerFunc(handleWorkUnitError),
		},
	)
	return server
}

type CustomErrorHandler struct {
	logger interface{}
}

func (eh CustomErrorHandler) HandleError(ctx context.Context, asynqJob *asynq.Task, err error) {
	_ = eh.logger
}
""",
        "function": "error_handler_interface_adapter",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 10. Middleware chain (MiddlewareFunc) ──────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"log"
	"time"
)

func loggingMiddleware(handler asynq.Handler) asynq.Handler {
	return asynq.HandlerFunc(func(ctx context.Context, asynqJob *asynq.Task) error {
		log.Printf("Starting: %s", asynqJob.Type())
		start := time.Now()
		err := handler.ProcessTask(ctx, asynqJob)
		log.Printf("Completed: %s (duration: %v, error: %v)", asynqJob.Type(), time.Since(start), err)
		return err
	})
}

func recoveryMiddleware(handler asynq.Handler) asynq.Handler {
	return asynq.HandlerFunc(func(ctx context.Context, asynqJob *asynq.Task) error {
		defer func() {
			if r := recover(); r != nil {
				log.Printf("Panic in handler: %v", r)
			}
		}()
		return handler.ProcessTask(ctx, asynqJob)
	})
}

func registerMiddleware(mux *asynq.ServeMux) {
	mux.Use(loggingMiddleware)
	mux.Use(recoveryMiddleware)
}
""",
        "function": "middleware_chain_pattern",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 11. Task lifecycle + status queries via Inspector ──────────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"github.com/redis/go-redis/v9"
)

func queryTaskLifecycle(ctx context.Context, redisClient redis.UniversalClient, taskID string) (*asynq.TaskInfo, error) {
	inspector := asynq.NewInspector(asynq.RedisClientOpt{Client: redisClient})
	defer inspector.Close()

	info, err := inspector.GetTaskInfo(ctx, "default", taskID)
	if err != nil {
		return nil, err
	}
	return info, nil
}

func getQueueStats(ctx context.Context, inspector *asynq.Inspector, queueName string) (*asynq.QueueStats, error) {
	stats, err := inspector.GetQueueStats(ctx, queueName)
	if err != nil {
		return nil, err
	}
	return stats, nil
}
""",
        "function": "task_lifecycle_inspector",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
    # ── 12. Graceful shutdown + context cancellation ──────────────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"github.com/hibiken/asynq"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func gracefulShutdown(server *asynq.Server, scheduler *asynq.Scheduler) error {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		log.Printf("Received signal: %v", sig)

		if scheduler != nil {
			if err := scheduler.Shutdown(); err != nil {
				log.Printf("Error shutting down scheduler: %v", err)
			}
		}

		server.Quit()
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Start(); err != nil {
		log.Printf("Server error: %v", err)
		return err
	}

	return nil
}
""",
        "function": "graceful_shutdown_signal_handling",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "asynq.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Redis background task queue client initialization connection",
    "create task with payload retry configuration and queue priority",
    "enqueue task to Redis with error handling and delay",
    "initialize server with concurrency configuration queue setup",
    "register task handlers with ServeMux pattern matching routing",
    "scheduled periodic tasks cron expression Scheduler",
    "custom retry delay exponential backoff configuration",
    "error handler middleware error logging task failure",
    "middleware chain logging recovery panic protection",
    "task inspector lifecycle status active pending scheduled",
    "graceful shutdown signal handling context cancellation",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
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
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
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
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
