"""
ingest_redis_py.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de redis/redis-py dans la KB Qdrant V6.

Focus : CORE patterns Redis client — connection pooling, pipeline, pubsub,
transactions, streams, Lua scripting, cluster/sentinel support.
PAS des patterns CRUD/API — patterns de communication avec Redis.

Usage:
    .venv/bin/python3 ingest_redis_py.py
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
REPO_URL = "https://github.com/redis/redis-py.git"
REPO_NAME = "redis/redis-py"
REPO_LOCAL = "/tmp/redis-py"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+redis+cache"
CHARTE_VERSION = "1.0"
TAG = "redis/redis-py"
SOURCE_REPO = "https://github.com/redis/redis-py"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Redis-py = client Python pour Redis. CORE patterns = connection, pipeline,
# pubsub, transactions, streams, Lua scripting, cluster/sentinel support.
# U-5 : `xxx` pour noms génériques d'entités, KEEP Redis terms.

PATTERNS: list[dict] = [
    # ── 1. Connection pooling — get/release connection ───────────────────────
    {
        "normalized_code": """\
from typing import Optional

from redis.connection import Connection, ConnectionPool


class ConnectionPool:
    \"\"\"Manages a pool of reusable connections to a Redis server.\"\"\"

    def __init__(
        self,
        connection_class: type = Connection,
        max_connections: int = 50,
        **connection_kwargs,
    ) -> None:
        self.connection_class = connection_class
        self.connection_kwargs = connection_kwargs
        self.max_connections = max_connections
        self._available_connections = []
        self._in_use_connections = set()
        self._lock = threading.RLock()

    def get_connection(self, command_name: Optional[str] = None) -> Connection:
        \"\"\"Get a connection from the pool (or create new if limit not reached).\"\"\"
        with self._lock:
            if self._available_connections:
                connection = self._available_connections.pop()
            elif len(self._in_use_connections) < self.max_connections:
                connection = self.connection_class(**self.connection_kwargs)
            else:
                raise MaxConnectionsError("Connection pool exhausted")
            self._in_use_connections.add(connection)
            return connection

    def release(self, connection: Connection) -> None:
        \"\"\"Return a connection to the pool.\"\"\"
        with self._lock:
            if connection in self._in_use_connections:
                self._in_use_connections.discard(connection)
                self._available_connections.append(connection)
""",
        "function": "connection_pool_management",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "redis/connection.py",
    },
    # ── 2. Redis client initialization — URL parsing / host/port ─────────────
    {
        "normalized_code": """\
from typing import Optional
from urllib.parse import parse_qs, urlparse

from redis.connection import ConnectionPool


class Xxx:
    \"\"\"Redis client for executing commands against a Redis server.\"\"\"

    @classmethod
    def from_url(
        cls,
        url: str,
        encoding: str = "utf-8",
        decode_responses: bool = False,
        **kwargs,
    ):
        \"\"\"Create a Redis client from a connection URL string.

        URL format: redis://[auth_name][:auth_key]@host[:port]/[db]
        \"\"\"
        parsed = urlparse(url)
        if parsed.scheme not in ("redis", "rediss"):
            raise ValueError(f"Invalid URL scheme: {parsed.scheme}")

        hostname = parsed.hostname or "localhost"
        port = parsed.port or 6379
        db = int(parsed.path.lstrip("/") or 0) if parsed.path else 0
        auth_key = parsed.password
        auth_name = parsed.username

        return cls(
            host=hostname,
            port=port,
            db=db,
            auth_name=auth_name,
            auth_key=auth_key,
            encoding=encoding,
            decode_responses=decode_responses,
            **kwargs,
        )

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        auth_key: Optional[str] = None,
        auth_name: Optional[str] = None,
        encoding: str = "utf-8",
        decode_responses: bool = False,
        connection_pool: Optional[ConnectionPool] = None,
    ) -> None:
        if connection_pool is None:
            connection_pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                auth_key=auth_key,
                auth_name=auth_name,
                encoding=encoding,
                decode_responses=decode_responses,
            )
        self.connection_pool = connection_pool
""",
        "function": "redis_client_init_from_url",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "redis/client.py",
    },
    # ── 3. Pipeline — batched command execution ───────────────────────────────
    {
        "normalized_code": """\
from typing import List, Optional, Any

from redis.client import Redis


class Pipeline(Redis):
    \"\"\"Batch multiple Redis commands for atomic execution.

    Pipelines group commands together to reduce round-trip latency
    and optionally execute them as a transaction (wrapped with MULTI/EXEC).
    \"\"\"

    def __init__(
        self,
        connection_pool,
        response_callbacks,
        transaction: bool = True,
        shard_hint: Optional[str] = None,
    ) -> None:
        self.connection_pool = connection_pool
        self.response_callbacks = response_callbacks
        self.transaction = transaction
        self.shard_hint = shard_hint
        self.command_stack: List[tuple] = []
        self.watching = False
        self.explicit_transaction = False

    def __enter__(self) -> "Pipeline":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.reset()

    def reset(self) -> None:
        \"\"\"Clear the command stack and reset transaction state.\"\"\"
        self.command_stack = []
        self.watching = False
        self.explicit_transaction = False

    def execute(self, raise_on_error: bool = True) -> List[Any]:
        \"\"\"Execute all queued commands and return results as a list.\"\"\"
        if not self.command_stack:
            return []
        if self.transaction and not self.explicit_transaction:
            self.command_stack = [
                (b"MULTI",) + ((),)
            ] + self.command_stack + [(b"EXEC",) + ((),)]
        connection = self.connection_pool.get_connection()
        try:
            for cmd, args, _ in self.command_stack:
                connection.send_command(cmd, *args)
            return [connection.read_response() for _ in self.command_stack]
        finally:
            self.reset()
            self.connection_pool.release(connection)
""",
        "function": "pipeline_batched_execution",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/client.py",
    },
    # ── 4. Pub/Sub — subscribe/publish/listen ───────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, Callable, Dict, Any
import threading


class PubSub:
    \"\"\"Publish/Subscribe support for Redis channels.

    Allows subscribing to channels and patterns, then listening
    for payloads published to those channels.
    \"\"\"

    def __init__(
        self,
        connection_pool,
        shard_hint: Optional[str] = None,
        ignore_subscribe_payloads: bool = False,
    ) -> None:
        self.connection_pool = connection_pool
        self.shard_hint = shard_hint
        self.ignore_subscribe_payloads = ignore_subscribe_payloads
        self.connection = None
        self.subscribed_flag = threading.Condition()
        self.channels: Dict[str, Optional[Callable]] = {}
        self.patterns: Dict[str, Optional[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, *channel_names: str, **channel_callbacks: Callable) -> None:
        \"\"\"Subscribe to one or more channels.

        Args:
            *channel_names: positional channel names (no callback)
            **channel_callbacks: channel_name=callback_fn keyword pairs
        \"\"\"
        with self._lock:
            for channel in channel_names:
                self.channels[channel] = None
            for channel, callback in channel_callbacks.items():
                self.channels[channel] = callback
            self._subscribe(self.channels.keys())

    def psubscribe(self, *patterns: str, **pattern_callbacks: Callable) -> None:
        \"\"\"Subscribe to channels matching glob patterns.\"\"\"
        with self._lock:
            for pattern in patterns:
                self.patterns[pattern] = None
            for pattern, callback in pattern_callbacks.items():
                self.patterns[pattern] = callback
            self._psubscribe(self.patterns.keys())

    def listen(self):
        \"\"\"Listen for payloads on subscribed channels (blocking iterator).\"\"\"
        while True:
            payload = self.get_payload()
            if payload:
                yield payload

    def get_payload(self, ignore_subscribe_payloads: bool = False) -> Optional[Dict[str, Any]]:
        \"\"\"Get the next payload from the subscription (non-blocking).\"\"\"
        pass
""",
        "function": "pubsub_subscribe_publish",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/client.py",
    },
    # ── 5. Transactions (WATCH/MULTI/EXEC) ──────────────────────────────────
    {
        "normalized_code": """\
from typing import Callable, List, Any, Optional
import time


class Pipeline:
    \"\"\"Pipeline with transaction support via WATCH/MULTI/EXEC.\"\"\"

    def watch(self, *key_names: str) -> None:
        \"\"\"Watch keys for modifications before a transaction.

        If any watched key is modified before EXEC, WatchError is raised.
        \"\"\"
        if self.command_stack:
            raise RedisError("Cannot WATCH after commands issued")
        connection = self.connection_pool.get_connection()
        try:
            for key in key_names:
                connection.send_command(b"WATCH", key)
                connection.read_response()
            self.watching = True
        finally:
            self.connection_pool.release(connection)

    def multi(self) -> None:
        \"\"\"Start a transaction block (after optional WATCH calls).\"\"\"
        if self.explicit_transaction:
            raise RedisError("Cannot issue nested MULTI")
        self.explicit_transaction = True

    def execute(self, raise_on_error: bool = True) -> List[Any]:
        \"\"\"Execute all queued commands as a transaction.

        Wraps command_stack with MULTI and EXEC automatically.
        If a watched key was modified, WatchError is raised.
        \"\"\"
        if not self.command_stack:
            return []
        connection = self.connection_pool.get_connection()
        try:
            connection.send_command(b"MULTI")
            connection.read_response()
            for cmd, args in self.command_stack:
                connection.send_command(cmd, *args)
                connection.read_response()
            connection.send_command(b"EXEC")
            response = connection.read_response()
            if response is None:
                raise WatchError("Watched key was modified")
            return response
        except RedisError:
            raise
        finally:
            self.reset()
            self.connection_pool.release(connection)

    def unwatch(self) -> bool:
        \"\"\"Cancel all watched keys for this connection.\"\"\"
        if not self.watching:
            return False
        connection = self.connection_pool.get_connection()
        try:
            connection.send_command(b"UNWATCH")
            return connection.read_response()
        finally:
            self.connection_pool.release(connection)
""",
        "function": "transaction_watch_multi_exec",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/client.py",
    },
    # ── 6. Streams — XADD/XREAD/XREADGROUP ──────────────────────────────────
    {
        "normalized_code": """\
from typing import Dict, Optional, Any, List


def xadd(
    connection,
    stream_key: str,
    fields: Dict[str, Any],
    id_: str = "*",
    maxlen: Optional[int] = None,
    approximate: bool = True,
    minid: Optional[str] = None,
) -> str:
    \"\"\"Add an entry to a Redis stream.

    Args:
        stream_key: name of the stream
        fields: field/value pairs to add
        id_: stream entry ID (auto-generated if "*")
        maxlen: trim stream to this max length
        approximate: allow approximate trimming (faster)
        minid: trim entries before this ID

    Returns:
        The generated or provided entry ID
    \"\"\"
    pieces = [b"XADD", stream_key.encode()]
    if maxlen is not None and minid is None:
        pieces.extend([b"MAXLEN", b"~" if approximate else b"=", str(maxlen).encode()])
    if minid is not None and maxlen is None:
        pieces.extend([b"MINID", b"~" if approximate else b"=", minid.encode()])
    pieces.append(id_.encode())
    for field, value in fields.items():
        pieces.extend([field.encode(), str(value).encode()])
    connection.send_command(*pieces)
    return connection.read_response()


def xread(
    connection,
    streams: Dict[str, str],
    count: Optional[int] = None,
    block_ms: Optional[int] = None,
) -> List[tuple]:
    \"\"\"Read entries from one or more streams (XREAD command).

    Args:
        streams: dict of {stream_key: entry_id} to read from
        count: max entries to return per stream
        block_ms: block for this many milliseconds if no data

    Returns:
        List of (stream_key, [(entry_id, fields), ...]) tuples
    \"\"\"
    pieces = [b"XREAD"]
    if count is not None:
        pieces.extend([b"COUNT", str(count).encode()])
    if block_ms is not None:
        pieces.extend([b"BLOCK", str(block_ms).encode()])
    pieces.append(b"STREAMS")
    pieces.extend(k.encode() for k in streams.keys())
    pieces.extend(v.encode() for v in streams.values())
    connection.send_command(*pieces)
    return connection.read_response()


def xreadgroup(
    connection,
    group_name: str,
    consumer_name: str,
    streams: Dict[str, str],
    count: Optional[int] = None,
    block_ms: Optional[int] = None,
) -> List[tuple]:
    \"\"\"Read from a consumer group (XREADGROUP command).\"\"\"
    pieces = [b"XREADGROUP", b"GROUP", group_name.encode(), consumer_name.encode()]
    if count is not None:
        pieces.extend([b"COUNT", str(count).encode()])
    if block_ms is not None:
        pieces.extend([b"BLOCK", str(block_ms).encode()])
    pieces.append(b"STREAMS")
    pieces.extend(k.encode() for k in streams.keys())
    pieces.extend(v.encode() for v in streams.values())
    connection.send_command(*pieces)
    return connection.read_response()
""",
        "function": "stream_xadd_xread_xreadgroup",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 7. Lua scripting — register_script / evalsha ──────────────────────────
    {
        "normalized_code": """\
from typing import Any, List, Optional
import hashlib


class Script:
    \"\"\"Compiled Lua script with automatic SHA1 caching.\"\"\"

    def __init__(self, registered_client, code: str) -> None:
        self.registered_client = registered_client
        self.code = code
        self.sha = hashlib.sha1(code.encode()).hexdigest()

    def __call__(
        self,
        keys: Optional[List[str]] = None,
        args: Optional[List[Any]] = None,
        client: Optional[Any] = None,
    ) -> Any:
        \"\"\"Execute the script via EVALSHA (with fallback to EVAL).\"\"\"
        if client is None:
            client = self.registered_client
        keys = keys or []
        args = args or []
        try:
            return client.evalsha(self.sha, len(keys), *keys, *args)
        except ResponseError as exc:
            if "NOSCRIPT" in str(exc):
                return client.eval(self.code, len(keys), *keys, *args)
            raise


def register_script(client, script_code: str) -> Script:
    \"\"\"Register a Lua script and return a Script object for execution.

    The script will automatically use EVALSHA for fast re-execution,
    with fallback to EVAL on NOSCRIPT errors.
    \"\"\"
    return Script(client, script_code)


def eval_script_example():
    \"\"\"Example: register and execute a Lua script.\"\"\"
    script_code = "\"\"\"
        local key = KEYS[1]
        local value = redis.call('GET', key)
        return value
    \"\"\"

    client = Xxx(host="localhost", port=6379)
    script = register_script(client, script_code)

    result = script(keys=["my_key"])
    return result
""",
        "function": "lua_script_register_evalsha",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 8. Expiration / TTL operations ───────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, Union


def expire(
    connection,
    key: str,
    seconds: int,
    nx: bool = False,
    xx: bool = False,
    gt: bool = False,
    lt: bool = False,
) -> bool:
    \"\"\"Set key expiration timeout (in seconds).

    Args:
        key: key to expire
        seconds: expiration timeout in seconds
        nx: only set expiration if key has no timeout
        xx: only set expiration if key already has a timeout
        gt: only set if new timeout > current timeout
        lt: only set if new timeout < current timeout

    Returns:
        True if expiration was set, False otherwise
    \"\"\"
    pieces = [b"EXPIRE", key.encode(), str(seconds).encode()]
    if nx:
        pieces.append(b"NX")
    if xx:
        pieces.append(b"XX")
    if gt:
        pieces.append(b"GT")
    if lt:
        pieces.append(b"LT")
    connection.send_command(*pieces)
    return connection.read_response()


def pexpire(
    connection,
    key: str,
    milliseconds: int,
) -> bool:
    \"\"\"Set key expiration timeout (in milliseconds).\"\"\"
    connection.send_command(b"PEXPIRE", key.encode(), str(milliseconds).encode())
    return connection.read_response()


def ttl(connection, key: str) -> int:
    \"\"\"Get remaining time to live for a key (in seconds).

    Returns:
        >= 0: time to live in seconds
        -1: key exists but has no associated timeout
        -2: key does not exist
    \"\"\"
    connection.send_command(b"TTL", key.encode())
    return connection.read_response()


def pttl(connection, key: str) -> int:
    \"\"\"Get remaining time to live for a key (in milliseconds).\"\"\"
    connection.send_command(b"PTTL", key.encode())
    return connection.read_response()
""",
        "function": "ttl_expiration_operations",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 9. Hash operations (HSET/HGET/HGETALL) ──────────────────────────────
    {
        "normalized_code": """\
from typing import Dict, Any, Optional, List


def hset(connection, key: str, mapping: Dict[str, Any]) -> int:
    \"\"\"Set multiple hash fields and their values.

    Returns:
        Number of fields added (not including updated fields)
    \"\"\"
    pieces = [b"HSET", key.encode()]
    for field, value in mapping.items():
        pieces.extend([field.encode(), str(value).encode()])
    connection.send_command(*pieces)
    return connection.read_response()


def hget(connection, key: str, field: str) -> Optional[Any]:
    \"\"\"Get a single hash field value.\"\"\"
    connection.send_command(b"HGET", key.encode(), field.encode())
    return connection.read_response()


def hgetall(connection, key: str) -> Dict[str, Any]:
    \"\"\"Get all fields and values from a hash.\"\"\"
    connection.send_command(b"HGETALL", key.encode())
    response = connection.read_response()
    return dict(zip(response[::2], response[1::2]))


def hmget(connection, key: str, fields: List[str]) -> List[Optional[Any]]:
    \"\"\"Get multiple hash field values.\"\"\"
    pieces = [b"HMGET", key.encode()]
    pieces.extend(f.encode() for f in fields)
    connection.send_command(*pieces)
    return connection.read_response()


def hdel(connection, key: str, *field_names: str) -> int:
    \"\"\"Delete hash fields.

    Returns:
        Number of fields that were deleted
    \"\"\"
    pieces = [b"HDEL", key.encode()]
    pieces.extend(f.encode() for f in field_names)
    connection.send_command(*pieces)
    return connection.read_response()
""",
        "function": "hash_operations_hset_hget",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 10. Set operations (SADD/SMEMBERS/SINTER) ────────────────────────────
    {
        "normalized_code": """\
from typing import Set, Any, Optional


def sadd(connection, key: str, *elements: Any) -> int:
    \"\"\"Add one or more elements to a set.

    Returns:
        Number of elements added (not including duplicates)
    \"\"\"
    pieces = [b"SADD", key.encode()]
    pieces.extend(str(el).encode() for el in elements)
    connection.send_command(*pieces)
    return connection.read_response()


def smembers(connection, key: str) -> Set[Any]:
    \"\"\"Get all members of a set.\"\"\"
    connection.send_command(b"SMEMBERS", key.encode())
    return set(connection.read_response())


def sismember(connection, key: str, element: Any) -> bool:
    \"\"\"Check if an element is a member of a set.\"\"\"
    connection.send_command(b"SISMEMBER", key.encode(), str(element).encode())
    return bool(connection.read_response())


def sinter(connection, *set_keys: str) -> Set[Any]:
    \"\"\"Get the intersection of multiple sets.\"\"\"
    pieces = [b"SINTER"]
    pieces.extend(k.encode() for k in set_keys)
    connection.send_command(*pieces)
    return set(connection.read_response())


def sunion(connection, *set_keys: str) -> Set[Any]:
    \"\"\"Get the union of multiple sets.\"\"\"
    pieces = [b"SUNION"]
    pieces.extend(k.encode() for k in set_keys)
    connection.send_command(*pieces)
    return set(connection.read_response())


def srem(connection, key: str, *elements: Any) -> int:
    \"\"\"Remove elements from a set.

    Returns:
        Number of elements removed
    \"\"\"
    pieces = [b"SREM", key.encode()]
    pieces.extend(str(el).encode() for el in elements)
    connection.send_command(*pieces)
    return connection.read_response()
""",
        "function": "set_operations_sadd_smembers",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 11. Sorted Set operations (ZADD/ZRANGE/ZRANK) ────────────────────────
    {
        "normalized_code": """\
from typing import Any, Optional, List, Tuple


def zadd(
    connection,
    key: str,
    mapping: dict,
    nx: bool = False,
    xx: bool = False,
    ch: bool = False,
    incr: bool = False,
) -> Any:
    \"\"\"Add members with scores to a sorted set.

    Args:
        mapping: dict of {element: score}
        nx: only add new elements
        xx: only update existing elements
        ch: return number of added/changed elements (not total count)
        incr: increment score instead of replacing it

    Returns:
        Number of elements added, or incremented score if incr=True
    \"\"\"
    pieces = [b"ZADD", key.encode()]
    if nx:
        pieces.append(b"NX")
    if xx:
        pieces.append(b"XX")
    if ch:
        pieces.append(b"CH")
    if incr:
        pieces.append(b"INCR")
    for element, score in mapping.items():
        pieces.extend([str(score).encode(), str(element).encode()])
    connection.send_command(*pieces)
    return connection.read_response()


def zrange(
    connection,
    key: str,
    start: int,
    stop: int,
    byscore: bool = False,
    bylex: bool = False,
    rev: bool = False,
    withscores: bool = False,
    limit: Optional[Tuple[int, int]] = None,
) -> List[Any]:
    \"\"\"Get members from a sorted set by rank or score range.\"\"\"
    pieces = [b"ZRANGE", key.encode(), str(start).encode(), str(stop).encode()]
    if byscore:
        pieces.append(b"BYSCORE")
    if bylex:
        pieces.append(b"BYLEX")
    if rev:
        pieces.append(b"REV")
    if withscores:
        pieces.append(b"WITHSCORES")
    if limit is not None:
        offset, count = limit
        pieces.extend([b"LIMIT", str(offset).encode(), str(count).encode()])
    connection.send_command(*pieces)
    return connection.read_response()


def zrank(connection, key: str, element: Any) -> Optional[int]:
    \"\"\"Get the rank (index) of an element in a sorted set.\"\"\"
    connection.send_command(b"ZRANK", key.encode(), str(element).encode())
    return connection.read_response()


def zrem(connection, key: str, *elements: Any) -> int:
    \"\"\"Remove elements from a sorted set.\"\"\"
    pieces = [b"ZREM", key.encode()]
    pieces.extend(str(el).encode() for el in elements)
    connection.send_command(*pieces)
    return connection.read_response()
""",
        "function": "sorted_set_operations_zadd_zrange",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "redis/commands/core.py",
    },
    # ── 12. Cluster / Sentinel support ──────────────────────────────────────
    {
        "normalized_code": """\
from typing import List, Optional, Dict, Any


class ClusterConnectionPool:
    \"\"\"Connection pool for Redis Cluster (routes commands to appropriate nodes).\"\"\"

    def __init__(
        self,
        startup_nodes: List[Dict[str, Any]],
        skip_full_coverage_check: bool = False,
        max_connections_per_node: int = 32,
    ) -> None:
        \"\"\"Initialize cluster connection pool.

        Args:
            startup_nodes: initial list of {host, port} dicts to discover cluster
            skip_full_coverage_check: skip validation that all hash slots are covered
            max_connections_per_node: pool size per node
        \"\"\"
        self.startup_nodes = startup_nodes
        self.skip_full_coverage_check = skip_full_coverage_check
        self.max_connections_per_node = max_connections_per_node
        self._node_pools = {}
        self._slot_mapping = {}
        self._refresh_cluster_slots()

    def _refresh_cluster_slots(self) -> None:
        \"\"\"Query CLUSTER SLOTS and update internal node mapping.\"\"\"
        pass

    def get_connection(self, command_name: str, key: Optional[str] = None):
        \"\"\"Route command to appropriate cluster node based on key hash.\"\"\"
        pass


class SentinelConnectionPool:
    \"\"\"Connection pool for Redis Sentinel (automatic failover support).\"\"\"

    def __init__(
        self,
        service_name: str,
        sentinels: List[tuple],
        sentinel_kwargs: Optional[Dict] = None,
        **connection_kwargs,
    ) -> None:
        \"\"\"Initialize sentinel-managed connection pool.

        Args:
            service_name: name of the Redis service in Sentinel config
            sentinels: list of (host, port) tuples for Sentinel nodes
            sentinel_kwargs: kwargs for Sentinel connections
            **connection_kwargs: kwargs for Redis connections
        \"\"\"
        self.service_name = service_name
        self.sentinels = sentinels
        self.sentinel_kwargs = sentinel_kwargs or {}
        self.connection_kwargs = connection_kwargs
        self._master_connection = None

    def discover_master(self) -> tuple:
        \"\"\"Query Sentinel for current master address.

        Returns:
            (host, port) tuple for current master
        \"\"\"
        pass

    def get_connection(self):
        \"\"\"Get connection to current master (with failover awareness).\"\"\"
        pass
""",
        "function": "cluster_sentinel_connection_pools",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "redis/connection.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "connection pool management get release",
    "redis client initialization from URL host port",
    "pipeline batch multiple commands execute",
    "pub/sub subscribe publish listen channels",
    "transaction watch multi exec atomic",
    "stream xadd xread consumer group entries",
    "lua script register evalsha redis",
    "ttl expiration key timeout seconds",
    "hash operations hset hget hgetall fields",
    "set sadd smembers sinter union",
    "sorted set zadd zrange rank score",
    "cluster connection pool sentinel failover",
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
