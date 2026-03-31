"""
ingest_ioredis.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de redis/ioredis dans la KB Qdrant V6.

Focus : CORE patterns Redis client (client init, pipeline, pub/sub, Lua scripts,
cluster mode, sentinel failover, streams, transactions, auto-reconnect, event handling).

Usage:
    .venv/bin/python3 ingest_ioredis.py
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
REPO_URL = "https://github.com/redis/ioredis.git"
REPO_NAME = "redis/ioredis"
REPO_LOCAL = "/tmp/ioredis"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+ioredis+redis+cache"
CHARTE_VERSION = "1.0"
TAG = "redis/ioredis"
SOURCE_REPO = "https://github.com/redis/ioredis"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# ioredis = TypeScript Redis client. CORE patterns: initialization, pipelining,
# pub/sub, Lua scripting, cluster mode, sentinel, streams, transactions,
# auto-reconnect, event-driven error handling.
# U-5: xxx (client), xxxs (multiple), keep Redis/Cluster/Pipeline/PubSub/Sentinel/Lua/etc.

PATTERNS: list[dict] = [
    # ── 1. Redis client initialization (host/port/password/TLS) ────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis({
  host: "127.0.0.1",
  port: 6379,
  password: "secret_password",
  tls: {
    ca: fs.readFileSync("ca.pem"),
    cert: fs.readFileSync("cert.pem"),
    key: fs.readFileSync("key.pem"),
  },
  retryStrategy: (times: number) => {
    const delay = Math.min(times * 50, 2000);
    return delay;
  },
  maxRetriesPerRequest: 3,
  enableReadyCheck: true,
  lazyConnect: false,
});

xxx.on("connect", () => {
  logger.info("connected to redis");
});

xxx.on("error", (err) => {
  logger.error("redis error", { error: err });
});

const value = await xxx.get("key");
await xxx.set("key", "value", "EX", 3600);
""",
        "function": "redis_client_init_host_port_password_tls",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "examples/usage.ts",
    },
    # ── 2. Pipeline chaining commands ─────────────────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis();

const pipeline = xxx
  .pipeline()
  .set("k1", "v1")
  .set("k2", "v2")
  .set("k3", "v3")
  .get("k1")
  .get("k2")
  .del("k3");

const results = await pipeline.exec();

results.forEach((result, idx) => {
  if (result[0]) {
    logger.error(`command failed`, { index: idx, error: result[0] });
  } else {
    logger.debug(`command result`, { index: idx, value: result[1] });
  }
});
""",
        "function": "pipeline_chain_commands",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/usage.ts",
    },
    # ── 3. Pub/Sub subscribe/publish ──────────────────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxxPublisher = new Redis();
const xxxSubscriber = new Redis();

xxxSubscriber.subscribe("label:account:update", "label:system:alert");

xxxSubscriber.on("signal", (label: string, payload: string) => {
  logger.info(`received on ${label}`, { payload });
});

xxxSubscriber.on("psubscribe", (pattern: string, count: number) => {
  logger.info(`subscribed to pattern ${pattern}`, { count });
});

xxxSubscriber.psubscribe("label:*");

await xxxPublisher.publish("label:account:update", "account 123 updated");
await xxxPublisher.publish("label:system:alert", "system restart scheduled");
""",
        "function": "pubsub_subscribe_publish",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/pubsub.ts",
    },
    # ── 4. Lua script definition and execution ────────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis();

xxx.defineCommand("xxxOperation", {
  numberOfKeys: 1,
  lua: `
    local value = redis.call('get', KEYS[1])
    if not value then
      redis.call('set', KEYS[1], ARGV[1])
      return 1
    else
      return 0
    end
  `,
});

const result = await xxx.xxxOperation("key1", "value1");
logger.info("script executed", { result });

const evalResult = await xxx.eval(
  `
    return redis.call('get', KEYS[1])
  `,
  1,
  "mykey"
);
""",
        "function": "lua_script_define_command_evalsha",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/lua.ts",
    },
    # ── 5. Cluster mode with natural key routing ─────────────────────────────
    {
        "normalized_code": """\
import { Cluster } from "ioredis";

const xxxCluster = new Cluster(
  [
    { host: "127.0.0.1", port: 7000 },
    { host: "127.0.0.1", port: 7001 },
    { host: "127.0.0.1", port: 7002 },
  ],
  {
    enableReadyCheck: true,
    enableOfflineQueue: true,
    maxRetries: 10,
    retryDelayBase: 100,
    dnsLookup: (address, callback) => {
      dns.lookup(address, callback);
    },
  }
);

xxxCluster.on("node error", (err, node) => {
  logger.error(`node error`, { node, error: err });
});

xxxCluster.on("cluster error", (err) => {
  logger.error("cluster error", { error: err });
});

const slotValue = await xxxCluster.get("slot:key:1");
await xxxCluster.set("slot:key:1", "value1");

const batchResults = await xxxCluster.pipeline()
  .set("slot:key:1", "v1")
  .set("slot:key:2", "v2")
  .mget("slot:key:1", "slot:key:2")
  .exec();
""",
        "function": "cluster_mode_natural_key_routing",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "examples/cluster.ts",
    },
    # ── 6. Sentinel auto-failover ────────────────────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis({
  sentinels: [
    { host: "sentinel1.local", port: 26379 },
    { host: "sentinel2.local", port: 26379 },
    { host: "sentinel3.local", port: 26379 },
  ],
  name: "mymaster",
  password: "sentinel_password",
  sentinelPassword: "sentinel_pass",
  sentinelRetryStrategy: (times: number) => {
    const delay = Math.min(times * 10, 1000);
    return delay;
  },
  enableOfflineQueue: true,
  enableTLSForSentinelMode: true,
});

xxx.on("sentinel-reconnect", () => {
  logger.info("reconnected to sentinel");
});

xxx.on("sentinel-error", (err) => {
  logger.error("sentinel error", { error: err });
});

const value = await xxx.get("key");
""",
        "function": "sentinel_auto_failover_master_replica",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "examples/sentinel.ts",
    },
    # ── 7. Streams: XADD / XREAD / XREADGROUP ───────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis();

const entryId = await xxx.xadd(
  "stream:log",
  "*",
  "signal_type",
  "account.login",
  "account_id",
  "acc_123",
  "timestamp",
  new Date().toISOString()
);

const xxxs = await xxx.xread("COUNT", 10, "STREAMS", "stream:log", "0");

const groupXxxs = await xxx.xreadgroup(
  "GROUP",
  "consumer_group_1",
  "consumer_1",
  "STREAMS",
  "stream:log",
  ">"
);

for (const [streamKey, streamXxxs] of groupXxxs || []) {
  for (const [id, fields] of streamXxxs || []) {
    await xxx.xack("stream:log", "consumer_group_1", id);
    logger.info(`processed entry`, { id, fields });
  }
}
""",
        "function": "streams_xadd_xread_xreadgroup",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/streams.ts",
    },
    # ── 8. Transactions: MULTI / EXEC with rollback ──────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis();

const txn = xxx.multi();
txn.incr("counter:page_views");
txn.set("cache:last_update", new Date().toISOString());
txn.expire("cache:last_update", 86400);
txn.lpush("log:activity", "page_view operation");

txn.on("signal", (msg) => {
  logger.info("transaction signal", { msg });
});

try {
  const results = await txn.exec();
  logger.info("transaction executed", { results });
} catch (err) {
  logger.error("transaction failed", { error: err });
  await txn.discard();
}

const pipelineWithTxn = xxx
  .pipeline()
  .multi()
  .set("k1", "v1")
  .set("k2", "v2")
  .exec()
  .pipeline()
  .get("k1")
  .get("k2");

const pipelineResults = await pipelineWithTxn.exec();
""",
        "function": "transactions_multi_exec_discard",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/transactions.ts",
    },
    # ── 9. Auto-reconnect with exponential backoff ───────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis({
  host: "127.0.0.1",
  port: 6379,
  retryStrategy: (times: number): number | null => {
    if (times > 10) {
      logger.error("max reconnect attempts exceeded");
      return null;
    }
    const delay = Math.min(Math.pow(2, times) * 100, 30000);
    logger.info(`reconnect attempt`, { times, delay });
    return delay;
  },
  reconnectOnError: (err) => {
    const targetError = err.message.includes("READONLY");
    if (targetError) {
      return true;
    }
    return false;
  },
  maxRetriesPerRequest: 3,
  enableOfflineQueue: true,
});

xxx.on("reconnecting", () => {
  logger.info("attempting to reconnect to redis");
});

xxx.on("ready", () => {
  logger.info("redis connection ready");
});

xxx.on("close", () => {
  logger.info("redis connection closed");
});
""",
        "function": "auto_reconnect_exponential_backoff",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "examples/reconnect.ts",
    },
    # ── 10. Lazy connect: defer connection until first command ────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis({
  host: "127.0.0.1",
  port: 6379,
  lazyConnect: true,
});

logger.info("redis connection created but not established");

await xxx.connect();
logger.info("redis connection now established");

const value = await xxx.get("key");

xxx.on("error", (err) => {
  logger.error("connection error", { error: err });
  xxx.disconnect();
});

await xxx.quit();
""",
        "function": "lazy_connect_defer_connection",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "examples/lazy_connect.ts",
    },
    # ── 11. Event-driven error handling and recovery ──────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis({
  host: "127.0.0.1",
  port: 6379,
  enableOfflineQueue: true,
});

xxx.on("error", (err: Error) => {
  if (err.message.includes("ECONNREFUSED")) {
    logger.error("connection refused, retrying");
  } else if (err.message.includes("TIMEOUT")) {
    logger.error("command timeout");
  } else {
    logger.error("unknown error", { error: err });
  }
});

xxx.on("connect", () => {
  logger.info("connected to redis");
});

xxx.on("ready", () => {
  logger.info("redis ready for commands");
});

xxx.on("close", () => {
  logger.info("redis connection closed");
});

xxx.on("reconnecting", () => {
  logger.info("redis reconnecting");
});

xxx.on("end", () => {
  logger.info("redis connection ended");
});

process.on("unhandledRejection", (reason, promise) => {
  logger.error("unhandled rejection", { reason, promise });
  xxx.disconnect();
});
""",
        "function": "event_driven_error_handling_recovery",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/error_handling.ts",
    },
    # ── 12. Binary-safe buffers and encoding ─────────────────────────────────
    {
        "normalized_code": """\
import Redis from "ioredis";

const xxx = new Redis();

const binaryData = Buffer.from([0xFF, 0xFE, 0xFD, 0xFC]);
await xxx.set("binary:data", binaryData);

const retrieved = await xxx.getBuffer("binary:data");
logger.info("retrieved buffer", { buffer: retrieved });

const xxxNoEncoding = new Redis({
  host: "127.0.0.1",
  port: 6379,
  retryStrategy: (times) => {
    return times > 5 ? null : times * 50;
  },
});

const bufferResult = await xxxNoEncoding.mgetBuffer(
  "key1",
  "key2",
  "key3"
);

const stringResult = await xxxNoEncoding.mget(
  "key1",
  "key2",
  "key3"
);

await xxxNoEncoding.set("string:key", "string value");
const stringValue = await xxxNoEncoding.get("string:key");
""",
        "function": "binary_safe_buffers_and_encoding",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "examples/buffers.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "redis client initialization with host port password TLS",
    "pipeline chain multiple commands execute atomic",
    "pub/sub subscribe publish event-driven messaging",
    "lua script define command evalsha atomic operations",
    "cluster mode natural key routing slots",
    "sentinel auto-failover master replica high availability",
    "streams XADD XREAD XREADGROUP event log",
    "transactions multi exec discard atomic",
    "auto-reconnect exponential backoff retry strategy",
    "lazy connect defer connection establishment",
    "event-driven error handling recovery",
    "binary buffers encoding getBuffer mget",
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
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
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
