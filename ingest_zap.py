"""
ingest_zap.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'uber-go/zap dans la KB Qdrant V6.

Focus : Structured, leveled, fast logging in Go — production/development loggers,
sugar logger, structured fields, custom encoders, sampled logger, core tee,
hooks, log rotation (lumberjack), custom log levels, atomic level changes,
named logger context.

Usage:
    .venv/bin/python3 ingest_zap.py
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
REPO_URL = "https://github.com/uber-go/zap.git"
REPO_NAME = "uber-go/zap"
REPO_LOCAL = "/tmp/zap"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+zap+logging"
CHARTE_VERSION = "1.0"
TAG = "uber-go/zap"
SOURCE_REPO = "https://github.com/uber-go/zap"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Zap = structured, leveled, fast logging in Go.
# Patterns CORE : production logger, development logger, sugar logger,
# structured fields, custom encoder, sampled logger, core tee, hooks,
# log rotation, custom level, atomic level, named logger context.
# Technical terms kept: logger, handler, level, encoder, core, sink, field, etc.

PATTERNS: list[dict] = [
    # ── 1. Production Logger — NewProduction ──────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"log/slog"
	"os"

	"go.uber.org/zap"
)

func NewProductionLogger() *zap.Logger {
	\"""Create production logger with JSON output and sampled high-level logs.\"""
	config := zap.NewProductionConfig()
	config.EncoderConfig.TimeKey = "timestamp"
	config.EncoderConfig.LevelKey = "level"
	config.EncoderConfig.MessageKey = "detail"
	config.EncoderConfig.StacktraceKey = "stacktrace"

	logger, err := config.Build()
	if err != nil {
		return nil
	}
	return logger
}

func main() {
	logger := NewProductionLogger()
	if logger == nil {
		return
	}
	defer logger.Sync()

	logger.Info("Server started", zap.String("version", "1.0.0"))
	logger.Error("Request failed", zap.Int("status", 500))
}
""",
        "function": "production_logger_newproduction",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/production_logger.go",
    },
    # ── 2. Development Logger — NewDevelopment ────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
)

func NewDevelopmentLogger() *zap.Logger {
	\"""Create development logger with colored console output and all levels.\"""
	config := zap.NewDevelopmentConfig()
	config.EncoderConfig.TimeKey = "time"
	config.EncoderConfig.LevelKey = "level"
	config.EncoderConfig.NameKey = "logger"
	config.EncoderConfig.CallerKey = "caller"
	config.EncoderConfig.MessageKey = "msg"
	config.EncoderConfig.StacktraceKey = "stacktrace"

	logger, err := config.Build(
		zap.AddCallerSkip(1),
		zap.AddStacktrace(zap.WarnLevel),
	)
	if err != nil {
		return nil
	}
	return logger
}

func main() {
	logger := NewDevelopmentLogger()
	if logger == nil {
		return
	}
	defer logger.Sync()

	logger.Debug("Debug detail", zap.String("module", "auth"))
	logger.Info("Account logged in", zap.String("account_id", "123"))
}
""",
        "function": "development_logger_newdevelopment",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/development_logger.go",
    },
    # ── 3. Sugar Logger — High-Level Interface ────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"fmt"
	"os"

	"go.uber.org/zap"
)

func ExampleSugarLogger() error {
	\"""Sugar logger provides a more flexible interface with Printf-style logging.\"""
	logger, err := zap.NewProduction()
	if err != nil {
		return fmt.Errorf("failed to initialize logger: %w", err)
	}
	defer logger.Sync()

	sugar := logger.Sugar()

	sugar.Infof("Request received from %s with status %d", "192.168.1.1", 200)
	sugar.Warnw("Slow query detected", "duration_ms", 1500, "query", "SELECT * FROM xxx")
	sugar.Errorw("Transaction failed", "error", "connection timeout", "retry_count", 3)
	sugar.Infoa("Cache miss", "key", "session:account:123", "ttl", 3600)
	return nil
}

func main() {
	if err := ExampleSugarLogger(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
""",
        "function": "sugar_logger_highlevel_interface",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/sugar_logger.go",
    },
    # ── 4. Structured Fields — With() ─────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
)

func LogWithContext() {
	\"""Use With() to attach structured fields to logger.\"""
	logger, _ := zap.NewProduction()
	defer logger.Sync()

	contextLogger := logger.With(
		zap.String("request_id", "req-001"),
		zap.String("account_id", "acc-123"),
		zap.String("session", "sess-456"),
	)

	contextLogger.Info("Processing request")
	contextLogger.Error("Validation failed", zap.String("field", "email"))

	anotherLogger := contextLogger.With(
		zap.String("component", "validator"),
	)
	anotherLogger.Debug("Field validation started")
}

func main() {
	LogWithContext()
}
""",
        "function": "structured_fields_with_context",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/structured_fields.go",
    },
    # ── 5. Custom Encoder Config ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

func NewCustomEncoderLogger() *zap.Logger {
	\"""Create logger with custom encoder configuration.\"""
	encoderConfig := zapcore.EncoderConfig{
		TimeKey:        "ts",
		LevelKey:       "lvl",
		NameKey:        "logger",
		CallerKey:      "caller",
		FunctionKey:    zapcore.OmitKey,
		MessageKey:     "msg",
		StacktraceKey:  "stack",
		LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    zapcore.CapitalLevelEncoder,
		EncodeTime:     zapcore.ISO8601TimeEncoder,
		EncodeDuration: zapcore.StringDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	}

	core := zapcore.NewCore(
		zapcore.NewJSONEncoder(encoderConfig),
		zapcore.AddSync(os.Stderr),
		zap.InfoLevel,
	)

	logger := zap.New(core, zap.AddCaller(), zap.AddStacktrace(zap.ErrorLevel))
	return logger
}

func main() {
	logger := NewCustomEncoderLogger()
	defer logger.Sync()

	logger.Info("Custom encoder initialized")
}
""",
        "function": "custom_encoder_config_fields",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/custom_encoder.go",
    },
    # ── 6. Sampled Logger ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

func NewSampledLogger() *zap.Logger {
	\"""Create logger that samples high-volume logs to reduce I/O.\"""
	config := zap.NewProductionConfig()

	config.Sampling = &zap.SamplingConfig{
		Initial:    100,
		Thereafter: 100,
	}

	logger, _ := config.Build()
	defer logger.Sync()

	return logger
}

func main() {
	logger := NewSampledLogger()

	for i := 0; i < 1000; i++ {
		logger.Info("Repetitive log_entry", zap.Int("index", i))
	}
}
""",
        "function": "sampled_logger_high_volume",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/sampled_logger.go",
    },
    # ── 7. Core Tee — Multi-Output Logger ─────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"os"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

func NewTeeLogger() *zap.Logger {
	\"""Create logger that writes to both stderr and file.\"""
	consoleEncoder := zapcore.NewConsoleEncoder(zap.NewDevelopmentEncoderConfig())
	jsonEncoder := zapcore.NewJSONEncoder(zap.NewProductionEncoderConfig())

	consoleCore := zapcore.NewCore(
		consoleEncoder,
		zapcore.AddSync(os.Stderr),
		zap.InfoLevel,
	)

	file, _ := os.Create("/tmp/app.log")
	fileCore := zapcore.NewCore(
		jsonEncoder,
		zapcore.AddSync(file),
		zap.DebugLevel,
	)

	teeCore := zapcore.NewTee(consoleCore, fileCore)
	logger := zap.New(teeCore, zap.AddCaller())

	return logger
}

func main() {
	logger := NewTeeLogger()
	defer logger.Sync()

	logger.Info("This goes to both console and file")
}
""",
        "function": "core_tee_multi_output",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/tee_logger.go",
    },
    # ── 8. Log Hooks ──────────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

type CustomHook struct {
	onError func(ent *zapcore.Entry) error
}

func (h *CustomHook) OnWrite(ent *zapcore.Entry, fields []zapcore.Field) error {
	if ent.Level >= zapcore.ErrorLevel {
		return h.onError(ent)
	}
	return nil
}

func NewLoggerWithHooks() *zap.Logger {
	\"""Create logger with custom hooks for error handling.\"""
	config := zap.NewProductionConfig()

	logger, _ := config.Build()

	hook := &CustomHook{
		onError: func(ent *zapcore.Entry) error {
			_ = SendAlertToMonitoring(ent.Message)
			return nil
		},
	}

	return logger
}

func SendAlertToMonitoring(msg string) error {
	return nil
}

func main() {
	logger := NewLoggerWithHooks()
	defer logger.Sync()

	logger.Error("Critical error occurred")
}
""",
        "function": "log_hooks_custom_behavior",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/hooks_logger.go",
    },
    # ── 9. Log Rotation with Lumberjack ───────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
)

func NewRotatingFileLogger() *zap.Logger {
	\"""Create logger with file rotation based on size and age.\"""
	w := &lumberjack.Logger{
		Filename:   "/var/log/app.log",
		MaxSize:    100,
		MaxBackups: 10,
		MaxAge:     30,
		Compress:   true,
	}

	core := zapcore.NewCore(
		zapcore.NewJSONEncoder(zap.NewProductionEncoderConfig()),
		zapcore.AddSync(w),
		zap.InfoLevel,
	)

	logger := zap.New(core, zap.AddCaller())
	return logger
}

func main() {
	logger := NewRotatingFileLogger()
	defer logger.Sync()

	logger.Info("Application started")
}
""",
        "function": "log_rotation_lumberjack_filesize",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/rotating_logger.go",
    },
    # ── 10. Custom Log Level ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

const (
	DebugLevel  = zapcore.DebugLevel
	InfoLevel   = zapcore.InfoLevel
	WarnLevel   = zapcore.WarnLevel
	ErrorLevel  = zapcore.ErrorLevel
	DPanicLevel = zapcore.DPanicLevel
	PanicLevel  = zapcore.PanicLevel
	FatalLevel  = zapcore.FatalLevel
)

func NewLoggerWithCustomLevel(level zapcore.Level) *zap.Logger {
	\"""Create logger with custom minimum level.\"""
	config := zap.NewProductionConfig()
	config.Level = zap.NewAtomicLevelAt(level)

	logger, _ := config.Build()
	return logger
}

func main() {
	logger := NewLoggerWithCustomLevel(zapcore.DebugLevel)
	defer logger.Sync()

	logger.Debug("Debug info")
	logger.Info("Info detail")
}
""",
        "function": "custom_log_level_selection",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "example/custom_level_logger.go",
    },
    # ── 11. Atomic Level Change ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

func NewLoggerWithDynamicLevel() *zap.Logger {
	\"""Create logger with atomically changeable level at runtime.\"""
	atomicLevel := zap.NewAtomicLevel()
	atomicLevel.SetLevel(zap.InfoLevel)

	config := zap.NewProductionConfig()
	config.Level = atomicLevel

	logger, _ := config.Build()

	go func() {
		atomicLevel.SetLevel(zap.DebugLevel)
		logger.Debug("Debug enabled at runtime")
		atomicLevel.SetLevel(zap.ErrorLevel)
		logger.Info("This won't be logged")
	}()

	return logger
}

func main() {
	logger := NewLoggerWithDynamicLevel()
	defer logger.Sync()

	logger.Info("Initial level: info")
}
""",
        "function": "atomic_level_change_runtime",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/atomic_level_logger.go",
    },
    # ── 12. Named Logger — Context Awareness ──────────────────────────────────
    {
        "normalized_code": """\
package main

import (
	"go.uber.org/zap"
)

func NewNamedLogger(name string) *zap.Logger {
	\"""Create named logger for tracking specific components.\"""
	logger, _ := zap.NewProduction()
	return logger.Named(name)
}

func main() {
	baseLogger, _ := zap.NewProduction()
	defer baseLogger.Sync()

	authLogger := baseLogger.Named("auth")
	dbLogger := baseLogger.Named("database")
	apiLogger := baseLogger.Named("api").Named("router")

	authLogger.Info("Account authentication started", zap.String("account", "alice"))
	dbLogger.Info("Connection pool initialized", zap.Int("size", 10))
	apiLogger.Info("Route registered", zap.String("method", "POST"), zap.String("path", "/api/accounts"))
}
""",
        "function": "named_logger_context_awareness",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "example/named_logger.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "production logger with JSON encoder and sampling",
    "development logger with colored output and stacktrace",
    "sugar logger high-level printf-style API",
    "structured fields and context propagation",
    "custom encoder configuration ISO8601 time",
    "sampled logger for high-volume events",
    "core tee multiple output file and console",
    "error hooks alert monitoring callback",
    "log rotation file size lumberjack backup",
    "atomic level change at runtime",
    "named logger component context awareness",
    "Go zap structured logging setup configuration",
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
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
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
