"""
ingest_go_redis.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de redis/go-redis dans la KB Qdrant V6.

Focus : CORE patterns Redis client (connection, pipelining, pub/sub, Lua scripting,
transactions, streams, cluster/ring/sentinel, TTL, connection pooling, context support).

NOT patterns CRUD/API — patterns de client Redis réutilisables.

Usage:
    .venv/bin/python3 ingest_go_redis.py
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
REPO_URL = "https://github.com/redis/go-redis.git"
REPO_NAME = "redis/go-redis"
REPO_LOCAL = "/tmp/go-redis"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+redis+cache"
CHARTE_VERSION = "1.0"
TAG = "redis/go-redis"
SOURCE_REPO = "https://github.com/redis/go-redis"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# go-redis = Redis client library for Go.
# Patterns CORE : connection setup, pipelining, pub/sub, scripting, transactions,
# streams, cluster/ring/sentinel failover, TTL, pool config, context.Context support.
# U-5 : user → xxx, message → payload, order → sequence, item → element,
# tag → label, event → signal, task → job, post → entry, comment → annotation.
# KEEP: Client, Options, Pipeline, PubSub, Script, Tx, Stream, Cluster, Sentinel, Ring, Cmd, StatusCmd, StringCmd, ctx.

PATTERNS: list[dict] = [
    # ── 1. Client initialization with Options ──────────────────────────────────
    {
        "normalized_code": """\
import (
	"context"
	"crypto/tls"
	"time"

	"github.com/redis/go-redis/v9"
)


type Options struct {
	Addr         string
	Network      string
	Password     string
	DB           int
	MaxRetries   int
	PoolSize     int
	PoolTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	DialTimeout  time.Duration
	TLSConfig    *tls.Config
}


func newClient(ctx context.Context, opt *redis.Options) *redis.Client {
	return redis.NewClient(opt)
}


func closeClient(ctx context.Context, cli *redis.Client) error {
	return cli.Close()
}
""",
        "function": "client_init_options_poolconfig",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "redis.go",
    },
    # ── 2. Pipelining — batch commands, send once, read once ─────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/redis/go-redis/v9"
)


func executePipeline(ctx context.Context, cli *redis.Client) error {
	pipe := cli.Pipeline()
	defer pipe.Close()

	incr := pipe.Incr(ctx, "counter")
	set := pipe.Set(ctx, "key", "value", 0)
	get := pipe.Get(ctx, "key")

	_, err := pipe.Exec(ctx)
	if err != nil {
		return err
	}

	incrVal := incr.Val()
	getVal := get.Val()
	_ = incrVal
	_ = getVal
	return nil
}


func pipelineWithDo(ctx context.Context, cli *redis.Client) error {
	pipe := cli.Pipeline()
	defer pipe.Close()

	cmd1 := pipe.Do(ctx, "INCR", "signal")
	cmd2 := pipe.Do(ctx, "GET", "data")

	_, err := pipe.Exec(ctx)
	return err
}
""",
        "function": "pipeline_batch_exec_commands",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pipeline.go",
    },
    # ── 3. Pub/Sub — Subscribe, Publish, Channel listening ───────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/redis/go-redis/v9"
)


func pubSubSubscribe(ctx context.Context, cli *redis.Client) {
	ps := cli.Subscribe(ctx, "signal1", "signal2")
	defer ps.Close()

	for {
		select {
		case <-ctx.Done():
			return
		case payload := <-ps.Channel():
			if payload == nil {
				return
			}
			_ = payload.Channel
			_ = payload.Payload
		}
	}
}


func pubSubPublish(ctx context.Context, cli *redis.Client, channel, payload string) error {
	result := cli.Publish(ctx, channel, payload)
	numSubscribers := result.Val()
	_ = numSubscribers
	return result.Err()
}


func pubSubPubsubChannels(ctx context.Context, cli *redis.Client) ([]string, error) {
	result := cli.PubSubChannels(ctx)
	return result.Val(), result.Err()
}
""",
        "function": "pubsub_subscribe_publish_channel",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pubsub.go",
    },
    # ── 4. Lua Scripting — NewScript, Run, EvalSha, server-side SHA ──────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/redis/go-redis/v9"
)


func runLuaScript(ctx context.Context, cli *redis.Client) error {
	script := redis.NewScript(`
		local value = redis.call('GET', KEYS[1])
		if not value then
			return redis.call('SET', KEYS[1], ARGV[1])
		end
		return value
	`)

	result := script.Run(ctx, cli, []string{"mykey"}, "default_value")
	if result.Err() != nil {
		return result.Err()
	}
	_ = result.Val()
	return nil
}


func evalSha(ctx context.Context, cli *redis.Client, sha1 string, keys []string) error {
	result := cli.EvalSha(ctx, sha1, keys, "arg1", "arg2")
	return result.Err()
}


func scriptLoadAndRun(ctx context.Context, cli *redis.Client) error {
	script := redis.NewScriptServerSHA(`
		return redis.call('SET', KEYS[1], ARGV[1])
	`)

	result := script.Run(ctx, cli, []string{"key"}, "value")
	return result.Err()
}
""",
        "function": "lua_script_run_evalsha_load",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "script.go",
    },
    # ── 5. Transactions with WATCH — conditional execution ───────────────────
    {
        "normalized_code": """\
import (
	"context"
	"errors"

	"github.com/redis/go-redis/v9"
)


func transactionWithWatch(ctx context.Context, cli *redis.Client) error {
	err := cli.Watch(ctx, func(tx *redis.Tx) error {
		val, err := tx.Get(ctx, "mykey").Result()
		if err != nil && err != redis.Nil {
			return err
		}

		_, err = tx.TxPipelined(ctx, func(pipe redis.Pipeliner) error {
			pipe.Set(ctx, "mykey", "new_value", 0)
			pipe.Incr(ctx, "counter")
			return nil
		})

		return err
	}, "mykey")

	if errors.Is(err, redis.TxFailedErr) {
		return errors.New("transaction aborted due to watched key change")
	}
	return err
}


func txPipeline(ctx context.Context, cli *redis.Client) ([]redis.Cmder, error) {
	cmds, err := cli.TxPipelined(ctx, func(pipe redis.Pipeliner) error {
		pipe.Incr(ctx, "sequence")
		pipe.Get(ctx, "signal")
		return nil
	})
	return cmds, err
}
""",
        "function": "transaction_watch_txpipeline_conditional",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "tx.go",
    },
    # ── 6. Streams — XAdd (append), XRead, XReadGroup (consumer group) ───────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/redis/go-redis/v9"
)


func streamAppendEntry(ctx context.Context, cli *redis.Client) (string, error) {
	result := cli.XAdd(ctx, &redis.XAddArgs{
		Stream: "mystream",
		Values: map[string]interface{}{
			"field1": "value1",
			"field2": "value2",
		},
	})
	return result.Val(), result.Err()
}


func streamReadLatest(ctx context.Context, cli *redis.Client) error {
	result := cli.XRead(ctx, &redis.XReadArgs{
		Streams: []string{"mystream", "$"},
		Count:   10,
	})
	if result.Err() != nil {
		return result.Err()
	}
	for _, stream := range result.Val() {
		_ = stream.Stream
		_ = stream.Messages
	}
	return nil
}


func streamConsumerGroup(ctx context.Context, cli *redis.Client) error {
	if err := cli.XGroupCreate(ctx, "mystream", "mygroup", "$").Err(); err != nil {
		return err
	}

	result := cli.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    "mygroup",
		Consumer: "consumer1",
		Streams:  []string{"mystream", ">"},
	})
	if result.Err() != nil {
		return result.Err()
	}

	for _, stream := range result.Val() {
		for _, msg := range stream.Messages {
			ackErr := cli.XAck(ctx, "mystream", "mygroup", msg.ID).Err()
			_ = ackErr
		}
	}
	return nil
}
""",
        "function": "stream_xadd_xread_xreadgroup_consumer",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "stream_commands.go",
    },
    # ── 7. Cluster Client — multi-node routing, slot discovery ──────────────
    {
        "normalized_code": """\
import (
	"context"
	"crypto/tls"
	"time"

	"github.com/redis/go-redis/v9"
)


type ClusterOptions struct {
	Addrs        []string
	Password     string
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	PoolSize     int
	TLSConfig    *tls.Config
}


func newClusterClient(ctx context.Context, opt *redis.ClusterOptions) *redis.ClusterClient {
	return redis.NewClusterClient(opt)
}


func clusterGetSlot(ctx context.Context, cli *redis.ClusterClient) error {
	result := cli.Get(ctx, "mykey")
	if result.Err() != nil {
		return result.Err()
	}
	_ = result.Val()
	return nil
}
""",
        "function": "cluster_client_multislot_discovery",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "cluster.go",
    },
    # ── 8. Ring (consistent hashing) — sharding across multiple nodes ───────
    {
        "normalized_code": """\
import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)


type RingOptions struct {
	Addrs              map[string]string
	PoolSize           int
	ReadTimeout        time.Duration
	WriteTimeout       time.Duration
	HeartbeatFrequency time.Duration
}


func newRingClient(ctx context.Context, opt *redis.RingOptions) *redis.Ring {
	return redis.NewRing(opt)
}


func ringSet(ctx context.Context, ring *redis.Ring, key, value string) error {
	return ring.Set(ctx, key, value, 0).Err()
}


func ringGet(ctx context.Context, ring *redis.Ring, key string) (string, error) {
	return ring.Get(ctx, key).Result()
}
""",
        "function": "ring_consistent_hash_sharding",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "ring.go",
    },
    # ── 9. Sentinel Failover — master/replica auto-discovery, failover ──────
    {
        "normalized_code": """\
import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)


type FailoverOptions struct {
	MasterName       string
	SentinelAddrs    []string
	SentinelPassword string
	Password         string
	DB               int
	PoolSize         int
	ReadTimeout      time.Duration
	WriteTimeout     time.Duration
}


func newFailoverClient(ctx context.Context, opt *redis.FailoverOptions) *redis.Client {
	return redis.NewFailoverClient(opt)
}


func newFailoverClusterClient(ctx context.Context, opt *redis.FailoverOptions) *redis.ClusterClient {
	return redis.NewFailoverClusterClient(opt)
}
""",
        "function": "sentinel_failover_masterfailover_discovery",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sentinel.go",
    },
    # ── 10. Key expiry (TTL) — Set with EX/PX, Expire, TTL commands ────────
    {
        "normalized_code": """\
import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)


func setWithExpiry(ctx context.Context, cli *redis.Client) error {
	err := cli.Set(ctx, "tempkey", "value", 10*time.Second).Err()
	return err
}


func ttlCheck(ctx context.Context, cli *redis.Client) (time.Duration, error) {
	result := cli.TTL(ctx, "tempkey")
	return result.Val(), result.Err()
}


func expireKey(ctx context.Context, cli *redis.Client, key string, ttl time.Duration) (bool, error) {
	result := cli.Expire(ctx, key, ttl)
	return result.Val(), result.Err()
}
""",
        "function": "ttl_expiry_set_ex_px_expire",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "commands.go",
    },
    # ── 11. Hash/Set/Sorted Set commands — HSet, SAdd, ZAdd ────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/redis/go-redis/v9"
)


func hashOperations(ctx context.Context, cli *redis.Client) error {
	pipe := cli.Pipeline()
	defer pipe.Close()

	pipe.HSet(ctx, "myhash", "field1", "value1", "field2", "value2")
	pipe.HGet(ctx, "myhash", "field1")
	pipe.HGetAll(ctx, "myhash")

	_, err := pipe.Exec(ctx)
	return err
}


func setOperations(ctx context.Context, cli *redis.Client) error {
	cli.SAdd(ctx, "myset", "element1", "element2")
	members, err := cli.SMembers(ctx, "myset").Result()
	_ = members
	return err
}


func sortedSetOperations(ctx context.Context, cli *redis.Client) error {
	cli.ZAdd(ctx, "myzset", redis.Z{Score: 1.0, Member: "element1"})
	cli.ZAdd(ctx, "myzset", redis.Z{Score: 2.0, Member: "element2"})
	range_result, err := cli.ZRange(ctx, "myzset", 0, -1).Result()
	_ = range_result
	return err
}
""",
        "function": "hash_set_sorted_set_operations",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "commands.go",
    },
    # ── 12. Context support — ctx cancellation, timeout propagation ─────────
    {
        "normalized_code": """\
import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)


func operationWithContext(ctx context.Context, cli *redis.Client) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	result := cli.Get(ctx, "mykey")
	if result.Err() != nil {
		return result.Err()
	}
	return nil
}


func pipelineWithCancellation(ctx context.Context, cli *redis.Client) error {
	pipe := cli.Pipeline()
	defer pipe.Close()

	pipe.Set(ctx, "key1", "val1", 0)
	pipe.Get(ctx, "key1")

	_, err := pipe.Exec(ctx)
	if err == context.Canceled {
		return err
	}
	return err
}
""",
        "function": "context_cancellation_timeout_propagation",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "commands.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Redis client connection pool configuration options",
    "pipelining batch commands execute once read results",
    "pub/sub subscribe publish channel receive messages",
    "Lua scripting eval evalsha server-side SHA loading",
    "transactions with WATCH key conditional execution",
    "Redis streams XAdd XRead consumer group XReadGroup",
    "cluster client multi-slot key routing discovery",
    "ring consistent hashing sharding multiple nodes",
    "sentinel failover master replica auto-discovery",
    "key expiry TTL set with timeout expire duration",
    "hash set sorted set operations HSet SAdd ZAdd",
    "context cancellation timeout propagation async",
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
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": True})
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
