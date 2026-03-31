"""
ingest_channels.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de django/channels dans la KB Qdrant V6.

Focus : CORE patterns WebSocket/async (consumer base class, JSON consumer,
channel layer groups, room join/leave, connection auth, message routing,
ASGI application wrapper, async consumer lifecycle).

Usage:
    .venv/bin/python3 ingest_channels.py
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
REPO_URL = "https://github.com/django/channels.git"
REPO_NAME = "django/channels"
REPO_LOCAL = "/tmp/channels"
LANGUAGE = "python"
FRAMEWORK = "django"
STACK = "django+channels+websocket+redis"
CHARTE_VERSION = "1.0"
TAG = "django/channels"
SOURCE_REPO = "https://github.com/django/channels"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Django Channels = async WebSocket framework with channel layer & group messaging.
# Patterns CORE : base consumer classes, JSON encoding, group broadcast, auth, lifecycle.
# U-5 : user → xxx, message → payload/frame, room → group, connection → scope

PATTERNS: list[dict] = [
    # ── 1. Async consumer base class (ASGI interface) ───────────────────────
    {
        "normalized_code": """\
from typing import Any, Awaitable, Callable

import asyncio
from asgiref.sync import async_to_sync


class AsyncConsumer:
    \"\"\"
    Base consumer class implementing ASGI spec with channel layer management
    and type-based frame routing to handler methods.
    \"\"\"

    channel_layer_alias: str = "default"

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        \"\"\"ASGI entry point: dispatch frames to type-based handlers.\"\"\"
        self.scope = scope
        self.base_send = send

        if self.channel_layer:
            self.channel_name = await self.channel_layer.new_channel()
            self.channel_receive = self.channel_layer.receive.__aenter__

        try:
            await self._await_many_dispatch(
                [receive, getattr(self, "channel_receive", None)],
                self.dispatch,
            )
        except StopConsumer:
            pass

    async def dispatch(self, frame: dict[str, Any]) -> None:
        \"\"\"Route incoming frame to handler by type field.\"\"\"
        if "type" not in frame:
            raise ValueError("Incoming frame has no 'type' attribute")

        handler_name = frame["type"].replace(".", "_")
        handler = getattr(self, handler_name, None)
        if handler:
            await handler(frame)
        else:
            raise ValueError(f"No handler for frame type {frame['type']}")

    async def send(self, payload: dict[str, Any]) -> None:
        \"\"\"Override-able send method for subclasses.\"\"\"
        await self.base_send(payload)

    @classmethod
    def as_asgi(cls, **initkwargs: Any):
        \"\"\"Return ASGI v3 callable that instantiates consumer per scope.\"\"\"
        async def app(scope, receive, send):
            consumer = cls(**initkwargs)
            return await consumer(scope, receive, send)

        app.consumer_class = cls
        app.consumer_initkwargs = initkwargs
        return app
""",
        "function": "async_consumer_base_class",
        "feature_type": "consumer",
        "file_role": "model",
        "file_path": "channels/consumer.py",
    },
    # ── 2. Async WebSocket consumer with lifecycle (connect/disconnect) ─────
    {
        "normalized_code": """\
from typing import Any, Optional

import json


class AsyncWebsocketConsumer(AsyncConsumer):
    \"\"\"
    Async WebSocket consumer with channel layer group support and lifecycle hooks.
    Handles accept/reject, send/receive, and group membership.
    \"\"\"

    groups: list[str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.groups is None:
            self.groups = []

    async def websocket_connect(self, payload: dict[str, Any]) -> None:
        \"\"\"Called on WebSocket open. Subscribe to groups and call hook.\"\"\"
        try:
            for group in self.groups:
                await self.channel_layer.group_add(group, self.channel_name)
        except AttributeError:
            raise InvalidChannelLayerError("Channel layer unconfigured or groups unsupported")

        try:
            await self.connect()
        except AcceptConnection:
            await self.accept()
        except DenyConnection:
            await self.close()

    async def connect(self) -> None:
        \"\"\"Accept incoming WebSocket (override to implement custom auth).\"\"\"
        await self.accept()

    async def accept(self, subprotocol: Optional[str] = None) -> None:
        \"\"\"Accept the WebSocket connection.\"\"\"
        payload = {"type": "websocket.accept", "subprotocol": subprotocol}
        await self.base_send(payload)

    async def websocket_receive(self, payload: dict[str, Any]) -> None:
        \"\"\"Called on frame receive. Decode and call receive hook.\"\"\"
        if "text" in payload:
            await self.receive(text_frame=payload["text"])
        elif "bytes" in payload:
            await self.receive(bytes_frame=payload["bytes"])

    async def receive(
        self,
        text_frame: Optional[str] = None,
        bytes_frame: Optional[bytes] = None,
    ) -> None:
        \"\"\"Override to handle incoming WebSocket frames.\"\"\"
        pass

    async def send(
        self,
        text_frame: Optional[str] = None,
        bytes_frame: Optional[bytes] = None,
        close: bool = False,
    ) -> None:
        \"\"\"Send frame back to client.\"\"\"
        if text_frame is not None:
            await self.base_send({"type": "websocket.send", "text": text_frame})
        elif bytes_frame is not None:
            await self.base_send({"type": "websocket.send", "bytes": bytes_frame})
        else:
            raise ValueError("Must provide text_frame or bytes_frame")
        if close:
            await self.close(close)

    async def websocket_disconnect(self, payload: dict[str, Any]) -> None:
        \"\"\"Called on disconnect. Unsubscribe from groups and call hook.\"\"\"
        try:
            for group in self.groups:
                await self.channel_layer.group_discard(group, self.channel_name)
        except AttributeError:
            raise InvalidChannelLayerError("Channel layer unconfigured or groups unsupported")

        await self.disconnect(payload.get("code"))
        raise StopConsumer()

    async def disconnect(self, code: int) -> None:
        \"\"\"Override to handle disconnection.\"\"\"
        pass

    async def close(self, code: Optional[int] = None) -> None:
        \"\"\"Close the WebSocket from server.\"\"\"
        payload = {"type": "websocket.close"}
        if code is not None and code is not True:
            payload["code"] = code
        await self.base_send(payload)
""",
        "function": "async_websocket_consumer_lifecycle",
        "feature_type": "consumer",
        "file_role": "model",
        "file_path": "channels/generic/websocket.py",
    },
    # ── 3. JSON WebSocket consumer (auto-encode/decode) ────────────────────
    {
        "normalized_code": """\
import json
from typing import Any, Optional


class AsyncJsonWebsocketConsumer(AsyncWebsocketConsumer):
    \"\"\"
    Async WebSocket consumer with automatic JSON encoding/decoding.
    receive_json/send_json instead of raw text frames.
    \"\"\"

    async def receive(
        self,
        text_frame: Optional[str] = None,
        bytes_frame: Optional[bytes] = None,
        **kwargs: Any,
    ) -> None:
        \"\"\"Receive hook: decode text frame as JSON and call receive_json.\"\"\"
        if text_frame:
            content = self.decode_json(text_frame)
            await self.receive_json(content, **kwargs)
        else:
            raise ValueError("No text frame for incoming WebSocket")

    async def receive_json(
        self,
        content: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        \"\"\"Override to handle decoded JSON content.\"\"\"
        pass

    async def send_json(self, content: dict[str, Any], close: bool = False) -> None:
        \"\"\"Encode content as JSON and send to client.\"\"\"
        text_frame = self.encode_json(content)
        await self.send(text_frame=text_frame, close=close)

    @staticmethod
    def decode_json(text_frame: str) -> dict[str, Any]:
        \"\"\"Override to customize JSON decoding.\"\"\"
        return json.loads(text_frame)

    @staticmethod
    def encode_json(content: dict[str, Any]) -> str:
        \"\"\"Override to customize JSON encoding.\"\"\"
        return json.dumps(content)
""",
        "function": "json_websocket_consumer_auto_encode",
        "feature_type": "consumer",
        "file_role": "model",
        "file_path": "channels/generic/websocket.py",
    },
    # ── 4. Channel layer group send/receive (broadcast pattern) ──────────────
    {
        "normalized_code": """\
from typing import Any, Optional


async def broadcast_to_group(
    channel_layer: Any,
    group: str,
    payload_type: str,
    **payload_data: Any,
) -> None:
    \"\"\"Send a frame to all consumers in a group.\"\"\"
    await channel_layer.group_send(
        group,
        {"type": payload_type, **payload_data},
    )


async def join_group(
    channel_layer: Any,
    group: str,
    channel_name: str,
) -> None:
    \"\"\"Add consumer channel to a group.\"\"\"
    await channel_layer.group_add(group, channel_name)


async def leave_group(
    channel_layer: Any,
    group: str,
    channel_name: str,
) -> None:
    \"\"\"Remove consumer channel from a group.\"\"\"
    await channel_layer.group_discard(group, channel_name)


async def handle_group_broadcast(
    self,
    signal: dict[str, Any],
) -> None:
    \"\"\"Generic handler for group broadcast frames. Override in consumer.\"\"\"
    await self.send_json(signal)
""",
        "function": "channel_layer_group_send_receive",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "channels/layers.py",
    },
    # ── 5. Room join pattern (WebSocket scope-based room identification) ────
    {
        "normalized_code": """\
from typing import Any, Optional


class RoomConsumer(AsyncWebsocketConsumer):
    \"\"\"
    Base consumer pattern for room-based communication (chat, collaboration).
    Extract room ID from URL scope and manage group membership.
    \"\"\"

    async def connect(self) -> None:
        \"\"\"Extract room from scope and join group.\"\"\"
        self.room = self.scope["url_route"]["kwargs"].get("room", "default")
        self.room_group = f"room_{self.room}"

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        \"\"\"Leave room group on disconnect.\"\"\"
        await self.channel_layer.group_discard(self.room_group, self.channel_name)

    async def receive_json(self, content: dict[str, Any]) -> None:
        \"\"\"Broadcast incoming payload to room.\"\"\"
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "room_signal",
                "sender": self.channel_name,
                "payload": content,
            },
        )

    async def room_signal(self, signal: dict[str, Any]) -> None:
        \"\"\"Handler for room broadcast. Send to all in group.\"\"\"
        payload = signal["payload"]
        await self.send_json({"type": "room_signal", **payload})
""",
        "function": "room_consumer_scope_based",
        "feature_type": "consumer",
        "file_role": "model",
        "file_path": "channels/generic/websocket.py",
    },
    # ── 6. Authentication check before connect (scope middleware) ──────────
    {
        "normalized_code": """\
from typing import Any, Optional

from asgiref.sync import sync_to_async


class AuthenticatedConsumer(AsyncWebsocketConsumer):
    \"\"\"
    WebSocket consumer requiring authentication. Check scope['principal']
    before accepting connection.
    \"\"\"

    async def connect(self) -> None:
        \"\"\"Accept only if principal is authenticated.\"\"\"
        principal = self.scope["principal"]
        if principal.is_authenticated:
            await self.accept()
        else:
            await self.close(code=4003)

    async def receive_json(self, content: dict[str, Any]) -> None:
        \"\"\"Handler with access to authenticated principal.\"\"\"
        principal = self.scope["principal"]
        await self.send_json(
            {"greeting": f"Hello {principal.username}", "payload": content}
        )
""",
        "function": "authenticated_consumer_scope_user",
        "feature_type": "consumer",
        "file_role": "model",
        "file_path": "channels/generic/websocket.py",
    },
    # ── 7. Protocol type router (HTTP + WebSocket + other) ─────────────────
    {
        "normalized_code": """\
from typing import Any, Callable, Awaitable


class ProtocolTypeRouter:
    \"\"\"
    ASGI router dispatching by protocol type (websocket, http, etc)
    to appropriate sub-applications.
    \"\"\"

    def __init__(
        self,
        app_mapping: dict[str, Callable[[dict, Any, Any], Awaitable]],
    ) -> None:
        self.app_mapping = app_mapping

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        \"\"\"Route by scope['type'] to mapped ASGI app.\"\"\"
        protocol = scope["type"]
        if protocol not in self.app_mapping:
            raise ValueError(f"No app configured for protocol {protocol}")

        app = self.app_mapping[protocol]
        await app(scope, receive, send)
""",
        "function": "protocol_type_router_asgi",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "channels/routing.py",
    },
    # ── 8. URL router for WebSocket path matching ────────────────────────
    {
        "normalized_code": """\
from typing import Any, Callable, Awaitable, Optional


class URLRouter:
    \"\"\"
    ASGI router dispatching to consumers based on URL pattern matching.
    Uses Django URL resolvers (path, re_path).
    \"\"\"

    def __init__(self, routes: list) -> None:
        self.routes = routes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        \"\"\"Match URL path against routes and dispatch to consumer.\"\"\"
        path = scope.get("path", "")
        if not path:
            raise ValueError("No 'path' in scope")

        resolver = self._match_route(path)
        if not resolver:
            raise ValueError(f"No route matched for path {path}")

        scope["url_route"] = resolver
        app = resolver["app"]
        await app(scope, receive, send)

    def _match_route(self, path: str) -> Optional[dict]:
        \"\"\"Match path against configured routes.\"\"\"
        for route in self.routes:
            match = route.pattern.match(path)
            if match:
                return {
                    "app": route.callback,
                    "kwargs": match.groupdict(),
                }
        return None
""",
        "function": "url_router_asgi_path_matching",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "channels/routing.py",
    },
    # ── 9. Frame type handler name resolution ────────────────────────────────
    {
        "normalized_code": """\
def resolve_handler_name(frame: dict[str, str]) -> str:
    \"\"\"
    Extract frame type and convert to handler method name.
    Replaces dots with underscores for method name convention.

    Example: type='room.signal' → handler='room_signal'
    \"\"\"
    if "type" not in frame:
        raise ValueError("Frame has no 'type' attribute")

    frame_type = frame["type"]
    handler_name = frame_type.replace(".", "_")

    if handler_name.startswith("_"):
        raise ValueError(f"Invalid frame type (leading underscore): {frame_type}")

    return handler_name
""",
        "function": "message_type_to_handler_name",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "channels/consumer.py",
    },
    # ── 10. Database sync wrapper for ORM access in async consumer ──────────
    {
        "normalized_code": """\
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from asgiref.sync import sync_to_async


T = TypeVar("T")


def database_sync_to_async(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    \"\"\"
    Decorator to run a sync (ORM) function in a threadpool from async context.
    Useful for calling Django ORM from async consumer methods.
    \"\"\"
    return sync_to_async(func, thread_sensitive=True)


# Usage example:
class ChatConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def save_frame(self, content: str) -> dict[str, Any]:
        # ORM code runs in threadpool
        xxx = Frame.objects.create(content=content)
        return {"id": xxx.id, "created": str(xxx.created)}

    async def receive_json(self, content: dict[str, Any]) -> None:
        result = await self.save_frame(content["text"])
        await self.send_json(result)
""",
        "function": "database_sync_to_async_wrapper",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "channels/db.py",
    },
    # ── 11. Redis channel layer backend config pattern ─────────────────────
    {
        "normalized_code": """\
# settings.py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
            "capacity": 1500,
            "expiry": 10,
            "group_expiry": 86400,
        },
    }
}

# In-memory fallback for development:
CHANNEL_LAYERS_FALLBACK = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
        "CONFIG": {
            "capacity": 1500,
            "expiry": 10,
        },
    }
}
""",
        "function": "channel_layer_redis_config",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "channels/layers.py",
    },
    # ── 12. Async context manager for channel layer initialization ──────────
    {
        "normalized_code": """\
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional


@asynccontextmanager
async def get_channel_layer() -> AsyncGenerator[Any, None]:
    \"\"\"
    Context manager for channel layer with lifecycle management.
    Ensures proper cleanup of connections.
    \"\"\"
    from channels.layers import get_channel_layer as _get_layer

    layer = _get_layer()
    try:
        yield layer
    finally:
        # Cleanup if needed (e.g., close Redis connection)
        if hasattr(layer, "close"):
            await layer.close()


# Usage in consumer:
async def send_to_group(group: str, payload: dict[str, Any]) -> None:
    async with get_channel_layer() as layer:
        await layer.group_send(group, payload)
""",
        "function": "channel_layer_context_manager",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "channels/layers.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "async WebSocket consumer class lifecycle connect disconnect",
    "JSON WebSocket consumer automatic JSON encoding decoding",
    "channel layer group send receive broadcast pattern",
    "room-based WebSocket communication scope group membership",
    "authentication check WebSocket connect Django user",
    "protocol type router ASGI HTTP WebSocket dispatch",
    "URL router path matching Django channels routing",
    "database sync to async Django ORM threadpool",
    "Redis channel layer backend configuration",
    "message type to handler name routing",
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
    print(f"  {len(PATTERNS)} patterns extracted")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexed — KB: {count_after} points")

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
        print("  DRY_RUN — data removed")


if __name__ == "__main__":
    main()
