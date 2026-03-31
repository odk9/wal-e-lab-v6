"""
ingest_pino.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de Pino (fast JSON logging pour Node.js) dans la KB Qdrant V6.

Focus : Patterns de logging JSON performant — create logger, child loggers,
custom levels, serializers, redaction, transports, pretty print, pino-http
middleware, multistream, async mode, destination streams, custom formatters,
log rotation.

Usage:
    .venv/bin/python3 ingest_pino.py
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
REPO_URL = "https://github.com/pinojs/pino.git"
REPO_NAME = "pinojs/pino"
REPO_LOCAL = "/tmp/pino"
LANGUAGE = "javascript"
FRAMEWORK = "generic"
STACK = "javascript+pino+logging"
CHARTE_VERSION = "1.0"
TAG = "pinojs/pino"
SOURCE_REPO = "https://github.com/pinojs/pino"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Pino = fast JSON logging library for Node.js.
# Patterns CORE : logger creation, child loggers, serializers, transports, middleware.
# U-5 : `logger`, `stream`, `transport`, `handler`, `level`, `format`, `processor` sont OK (TECHNICAL_TERMS).

PATTERNS: list[dict] = [
    # ── 1. Create root logger with options ──────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  transport: {
    target: 'pino-pretty',
    options: {
      colorize: true,
      translateTime: 'SYS:standard',
      ignore: 'pid,hostname',
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

logger.info({ xxx: 'value' }, 'xxx log_entry');
logger.warn({ error: 'xxx_event' }, 'Warning');
logger.error(new Error('xxx_error'), 'Fatal error');

export default logger;
""",
        "function": "create_pino_root_logger",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
    # ── 2. Child logger with context binding ──────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino();

function createChildLogger(requestId, accountId) {
  \"\"\"Create child logger with request and account context.

  Child loggers inherit parent's transports and options,
  but add their own context fields.
  \"\"\"
  return logger.child({
    requestId: requestId,
    accountId: accountId,
    environment: process.env.NODE_ENV,
  });
}

// Usage: all logs from this logger include context
const childLogger = createChildLogger('req-abc123', 42);
childLogger.info({ action: 'xxx_started' }, 'Processing request');
childLogger.info({ action: 'xxx_completed', duration_ms: 145 });
""",
        "function": "create_child_logger_context",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/logger.js",
    },
    # ── 3. Custom log levels ────────────────────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino({
  level: 'debug',
  customLevels: {
    audit: 25,
    trace: 10,
    metrics: 35,
  },
  useOnlyCustomLevels: false,
});

// Use custom levels
logger.audit({ action: 'account_login', account_id: 123 }, 'Audit log_entry');
logger.metrics({ endpoint: '/api/xxx', response_time_ms: 42 }, 'Metrics');
logger.trace({ xxx: 'value', nesting: 'deep' }, 'Trace');

// Custom level handler
logger.on('level-change', (lvl, prevLvl, name) => {
  logger.info({ prevLevel: prevLvl, newLevel: lvl }, 'Level changed');
});
""",
        "function": "custom_log_levels",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
    # ── 4. Serializer functions for objects ──────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino({
  serializers: {
    req(request) {
      return {
        method: request.method,
        url: request.url,
        headers: request.headers,
        remoteAddress: request.ip,
      };
    },
    res(response) {
      return {
        statusCode: response.statusCode,
        headers: response.headers,
      };
    },
    err: pino.stdSerializers.err,
    xxx(obj) {
      // Custom serializer for app-specific object
      return {
        id: obj.id,
        name: obj.name,
        // Omit sensitive fields (password, token)
      };
    },
  },
});

logger.info({ req: request }, 'Incoming request');
logger.error({ err: error }, 'Error occurred');
logger.warn({ xxx: myXxxObject }, 'Warning');
""",
        "function": "serializer_functions_objects",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/logger.js",
    },
    # ── 5. Redaction of sensitive paths ────────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino({
  redact: {
    paths: [
      'password',
      'token',
      'apiKey',
      'req.headers.authorization',
      'xxx.secret',
      'creditCard',
      'ssn',
    ],
    censor: '***REDACTED***',
    remove: false,
  },
});

logger.info({
  account: {
    id: 42,
    email: 'account@example.com',
    password: 'secret123',  // Will be redacted
  },
  apiKey: 'sk-12345',  // Will be redacted
  token: 'jwt-token-abc',  // Will be redacted
}, 'Account logged in');

logger.warn({
  creditCard: '4532-1111-2222-3333',  // Redacted
  amount: 99.99,  // Not redacted
}, 'Payment processed');
""",
        "function": "redaction_sensitive_paths",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/logger.js",
    },
    # ── 6. Transport worker for async logging ──────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';
import transport from 'pino-abstract-transport';
import fs from 'fs';

const pinoTransport = transport(
  async (source, options = {}) => {
    const output = fs.createWriteStream(options.path || './logs/app.log', {
      flags: 'a',
    });

    for await (const obj of source) {
      const xxx = {
        ...obj,
        timestamp: new Date().toISOString(),
        version: '1.0',
      };

      const line = JSON.stringify(xxx) + '\\n';
      output.write(line);
    }
  }
);

const logger = pino(
  {
    level: 'info',
  },
  pino.transport({
    target: pinoTransport,
    options: { path: './logs/app.log' },
  })
);

logger.info({ event: 'xxx_started' }, 'Application started');
""",
        "function": "transport_worker_async_logging",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/transport.js",
    },
    # ── 7. Pretty print configuration ──────────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';
import pinoPretty from 'pino-pretty';

const logger = pino(
  {
    level: process.env.LOG_LEVEL || 'debug',
  },
  pinoPretty({
    colorize: true,
    translateTime: 'SYS:standard',
    singleLine: false,
    ignore: 'pid,hostname',
    messageFormat: '{levelLabel} - {xxx}: {payload}',
    timestampKey: '@timestamp',
    lineEndMarker: '\\n',
  })
);

logger.debug({ xxx: 'debug_value' }, 'Debug payload');
logger.info({ xxx: 'info_value' }, 'Info payload');
logger.warn({ xxx: 'warning_value' }, 'Warning payload');
logger.error({ xxx: 'error_value' }, 'Error payload');
""",
        "function": "pretty_print_configuration",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
    # ── 8. Pino-http middleware for Express ────────────────────────────
    {
        "normalized_code": """\
import express from 'express';
import pinoHttp from 'pino-http';

const app = express();

const httpLogger = pinoHttp({
  level: process.env.LOG_LEVEL || 'info',
  transport: {
    target: 'pino-pretty',
    options: { colorize: true },
  },
  autoLogging: {
    ignore: (req) => req.url === '/health',
  },
  customLogLevel: (req, res) => {
    if (res.statusCode >= 400) return 'error';
    if (res.statusCode >= 200 && res.statusCode < 300) return 'info';
    return 'warn';
  },
});

app.use(httpLogger);

app.get('/api/xxx/:id', (req, res) => {
  const logger = req.log;
  logger.info({ id: req.params.id }, 'Fetching resource');

  res.json({ id: req.params.id, data: 'xxx_response' });
});

app.listen(3000);
""",
        "function": "pino_http_middleware_express",
        "feature_type": "route",
        "file_role": "middleware",
        "file_path": "middleware/logger.js",
    },
    # ── 9. Multistream for multiple outputs ──────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';
import fs from 'fs';

const targets = [
  {
    target: 'pino-pretty',
    level: 'debug',
    options: { colorize: true, translateTime: 'SYS:standard' },
  },
  {
    target: 'pino/file',
    level: 'info',
    options: { destination: './logs/app.log' },
  },
  {
    target: 'pino/file',
    level: 'error',
    options: { destination: './logs/error.log' },
  },
];

const logger = pino(
  { level: 'debug' },
  pino.transport({
    targets: targets,
  })
);

logger.debug({ xxx: 'value' }, 'Debug payload');
logger.info({ xxx: 'info' }, 'Info payload');
logger.error({ xxx: 'error' }, 'Error payload');
""",
        "function": "multistream_multiple_outputs",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
    # ── 10. Async mode for high throughput ──────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';

const logger = pino({
  level: 'info',
  transport: {
    target: 'pino-pretty',
    options: { colorize: true },
  },
  base: {
    application: 'xxx-service',
    environment: process.env.NODE_ENV,
  },
}, pino.transport({
  target: 'pino-abstract-transport',
  options: {
    asyncMode: true,
    bufferSize: 1000,
  },
}));

// High throughput logging
async function logHighVolume() {
  for (let i = 0; i < 10000; i++) {
    logger.info({
      log_entry: 'xxx_event',
      index: i,
      timestamp: new Date().toISOString(),
    }, `LogEntry ${i}`);
  }

  // Flush remaining logs
  await logger.flush();
}

logHighVolume().catch(console.error);
""",
        "function": "async_mode_high_throughput",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
    # ── 11. Custom destination stream ──────────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';
import { Transform } from 'stream';
import fs from 'fs';

// Custom transform stream for filtering
class FilterStream extends Transform {
  constructor(minLevel) {
    super({ objectMode: true });
    this.minLevel = minLevel;
    this.levels = { debug: 10, info: 20, warn: 30, error: 40 };
  }

  _transform(chunk, enc, callback) {
    const level = this.levels[chunk.level] || 20;
    if (level >= this.levels[this.minLevel]) {
      this.push(chunk);
    }
    callback();
  }
}

const filterStream = new FilterStream('warn');
const fileStream = fs.createWriteStream('./logs/warnings.log');

const logger = pino(
  { level: 'debug' },
  pino.transport({
    targets: [
      { target: 'pino-pretty', level: 'debug' },
    ],
  })
);

logger.info({ xxx: 'info' }, 'Not logged to file');
logger.warn({ xxx: 'warning' }, 'Logged to file');
logger.error({ xxx: 'error' }, 'Also logged to file');
""",
        "function": "custom_destination_stream",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/logger.js",
    },
    # ── 12. Log rotation setup ───────────────────────────────────────────
    {
        "normalized_code": """\
import pino from 'pino';
import PinoRotate from 'pino-rotating-file';

const logger = pino(
  {
    level: process.env.LOG_LEVEL || 'info',
    base: {
      application: 'xxx-service',
    },
  },
  pino.transport({
    target: 'pino-rotate',
    options: {
      dir: './logs',
      dateFormat: 'YYYY-MM-DD',
      mkdir: true,
      retention: {
        interval: 86400000,  // 1 day
        count: 30,  // Keep 30 days
      },
      size: '100M',  // Rotate at 100MB
    },
  })
);

// Hook for rotation log_entries
logger.on('rotate', (filename) => {
  logger.info({ filename }, 'Log rotated');
});

logger.info({ log_entry: 'xxx_started' }, 'Application started');
logger.info({ log_entry: 'xxx_request', path: '/api/xxx' }, 'Processing request');
logger.error({ log_entry: 'xxx_error', code: 'ECONNREFUSED' }, 'Connection error');
""",
        "function": "log_rotation_setup",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "lib/logger.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create pino root logger with options",
    "child logger with context binding request ID user",
    "custom log levels audit trace metrics",
    "serializer functions for request response objects",
    "redaction of sensitive password token paths",
    "transport worker async logging to file",
    "pretty print colorize translate time",
    "pino-http middleware express request logging",
    "multistream multiple output destinations",
    "async mode high throughput logging",
    "custom destination stream filtering",
    "log rotation daily file cleanup",
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
