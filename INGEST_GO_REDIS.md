# ingest_go_redis.py — Redis Client Library Ingestion

## Overview
Extracts, normalizes (Wal-e Charte), and indexes 12 CORE patterns from `redis/go-redis` into Qdrant KB.

## Patterns Extracted (12)

| # | Function | Feature Type | Description |
|---|----------|--------------|-------------|
| 1 | `client_init_options_poolconfig` | config | Client init, Options struct, connection pool config (Addr, Password, DB, PoolSize, timeouts) |
| 2 | `pipeline_batch_exec_commands` | crud | Pipelining: batch commands, send once, read responses in single Exec() call |
| 3 | `pubsub_subscribe_publish_channel` | crud | Pub/Sub: Subscribe (channels), Publish (send), Channel() (receive messages) |
| 4 | `lua_script_run_evalsha_load` | crud | Lua scripting: NewScript, Run, EvalSha, NewScriptServerSHA (server-side SHA) |
| 5 | `transaction_watch_txpipeline_conditional` | crud | Transactions: Watch (optimistic lock), TxPipelined, TxFailedErr handling |
| 6 | `stream_xadd_xread_xreadgroup_consumer` | crud | Streams: XAdd (append), XRead (read), XReadGroup (consumer groups), XAck |
| 7 | `cluster_client_multislot_discovery` | config | Cluster client: multi-node routing, slot discovery, ClusterClient |
| 8 | `ring_consistent_hash_sharding` | config | Ring (consistent hash): sharding across multiple nodes via Rendezvous |
| 9 | `sentinel_failover_masterfailover_discovery` | config | Sentinel: master/replica auto-discovery, failover via FailoverOptions |
| 10 | `ttl_expiry_set_ex_px_expire` | crud | Key expiry: Set with timeout, TTL check, Expire command |
| 11 | `hash_set_sorted_set_operations` | crud | Data structures: HSet/HGet/HGetAll, SAdd/SMembers, ZAdd/ZRange |
| 12 | `context_cancellation_timeout_propagation` | config | Context support: cancellation, timeout propagation via ctx.Context |

## Normalization (Charte Wal-e)

All 12 patterns **pass Charte validation** (0 violations):

- **U-5 (Entity names):** Replaced domain entities with placeholders
  - `user` → `xxx`, `message` → `payload`, `item` → `element`, `order` → `sequence`, `task` → `job`, `tag` → `label`, `event` → `signal`, `post` → `entry`, `comment` → `annotation`
  - **KEPT:** `Client`, `Options`, `Pipeline`, `PubSub`, `Script`, `Tx`, `Stream`, `Cluster`, `Sentinel`, `Ring`, `Cmd`, `StatusCmd`, `StringCmd`, `ctx` (Go/Redis-specific, not domain entities)

- **G-2 (No fmt.Println):** All patterns use structured logging or silent operation
- **No unwrap()** (unsafe error handling): All patterns use proper error handling
- **No blocked/unsafe constructs**

## Usage

```bash
cd /sessions/sweet-practical-fermi/mnt/Wal-e\ Lab\ V6

# Set DRY_RUN = False in ingest_go_redis.py

.venv/bin/python3 ingest_go_redis.py
```

## Output

- Indexes 12 patterns into `patterns` collection
- Runs 12 semantic audit queries (full coverage)
- Reports violations, query scores, KB before/after counts
- In DRY_RUN mode: cleans up test data after validation

## Architecture Rationale

**go-redis** is the canonical Redis client for Go. Patterns cover:
- **Connection management** (pool, options, cluster, ring, sentinel)
- **Command batching** (pipelining, transactions)
- **Pub/Sub** (publish/subscribe pattern)
- **Advanced features** (Lua scripting, streams, consumer groups)
- **Data structures** (hash, set, sorted set)
- **Concurrency** (context.Context cancellation/timeout)

This enables the generator to build real Redis clients by pattern assembly rather than from scratch.
