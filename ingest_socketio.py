"""
ingest_socketio.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de socketio/socket.io dans la KB Qdrant V6.

Focus : CORE real-time WebSocket patterns (server initialization, namespaces,
rooms, broadcast, event handlers, middleware, adapter, handshake, reconnection).

Usage:
    .venv/bin/python3 ingest_socketio.py
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
REPO_URL = "https://github.com/socketio/socket.io.git"
REPO_NAME = "socketio/socket.io"
REPO_LOCAL = "/tmp/socket.io"
LANGUAGE = "typescript"
FRAMEWORK = "express"
STACK = "express+socketio+websocket"
CHARTE_VERSION = "1.0"
TAG = "socketio/socket.io"
SOURCE_REPO = "https://github.com/socketio/socket.io"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Socket.io = real-time WebSocket framework.
# Patterns CORE : namespace/room mgmt, broadcast, event handlers, middleware, adapter.
# U-5 TypeScript: socket, io, namespace, room, adapter, broadcast, emit, on, middleware,
#                 handshake, ack — KEEP. user→xxx, message→payload/frame, event→signal/action

PATTERNS: list[dict] = [
    # ── 1. Server initialization with HTTP attachment ──────────────────────────
    {
        "normalized_code": """\
import { createServer } from "http";
import type { Server as HTTPServer } from "http";
import { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function create_server(): Server<DefaultEventsMap> {
    const http_server: HTTPServer = createServer();
    const io = new Server<DefaultEventsMap>(http_server, {
        cors: {
            origin: "*",
            methods: ["GET", "POST"],
        },
        serveClient: true,
        path: "/socket.io",
    });
    return io;
}

export { create_server };
""",
        "function": "server_init_http_attachment",
        "feature_type": "config",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/index.ts",
    },
    # ── 2. Namespace creation and event handler registration ────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

interface ListResponse {
    data: Record<string, unknown>[];
}

interface CreateResponse {
    id: number;
    [key: string]: unknown;
}

function register_namespace(io: Server<DefaultEventsMap>): void {
    const nsp = io.of("/api");
    nsp.on("connection", (socket: Socket<DefaultEventsMap>) => {
        console.debug(`socket ${socket.id} connected to /api`);

        socket.on("resource:list", (callback: (response: ListResponse) => void) => {
            const response: ListResponse = { data: [] };
            callback(response);
        });

        socket.on("resource:create", (frame: Record<string, any>, ack: (err: Error | null, result?: CreateResponse) => void) => {
            try {
                const result: CreateResponse = { id: 1, ...frame };
                ack(null, result);
            } catch (error) {
                ack(error as Error);
            }
        });

        socket.on("disconnect", (reason: string) => {
            console.debug(`socket ${socket.id} disconnected: ${reason}`);
        });
    });
}

export { register_namespace };
""",
        "function": "namespace_creation_event_handlers",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/namespace.ts",
    },
    # ── 3. Room join/leave and socket-level broadcast ─────────────────────────
    {
        "normalized_code": """\
import type { Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function room_management(socket: Socket<DefaultEventsMap>): void {
    socket.on("join:room", (room_name: string) => {
        socket.join(room_name);
        socket.to(room_name).emit("xxx:joined", {
            socket_id: socket.id,
            timestamp: Date.now(),
        });
    });

    socket.on("leave:room", (room_name: string) => {
        socket.leave(room_name);
        socket.to(room_name).emit("xxx:left", {
            socket_id: socket.id,
        });
    });

    socket.on("list:rooms", (callback: (rooms: string[]) => void) => {
        const rooms = Array.from(socket.rooms);
        callback(rooms);
    });
}

export { room_management };
""",
        "function": "room_join_leave_broadcast",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/socket.ts",
    },
    # ── 4. Broadcast to room and to namespace ────────────────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function broadcast_operations(io: Server<DefaultEventsMap>, socket: Socket<DefaultEventsMap>): void {
    socket.on("notify:room", (room_name: string, frame: Record<string, any>) => {
        io.to(room_name).emit("notification", {
            source: socket.id,
            payload: frame,
            timestamp: Date.now(),
        });
    });

    socket.on("notify:namespace", (frame: Record<string, any>) => {
        io.emit("broadcast:namespace", {
            source: socket.id,
            payload: frame,
        });
    });

    socket.on("notify:except_room", (room_name: string, frame: Record<string, any>) => {
        socket.to(room_name).except(socket.id).emit("broadcast", frame);
    });

    socket.on("notify:multiple_rooms", (rooms: string[], frame: Record<string, any>) => {
        io.to(rooms).emit("multi_room", frame);
    });
}

export { broadcast_operations };
""",
        "function": "broadcast_room_namespace",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/broadcast-operator.ts",
    },
    # ── 5. Event emit with acknowledgement callbacks ─────────────────────────────
    {
        "normalized_code": """\
import type { Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

interface DataResponse {
    signal_id: string;
    data: unknown[];
}

interface SyncResponse {
    version: number;
    [key: string]: unknown;
}

function emit_with_ack(socket: Socket<DefaultEventsMap>): void {
    socket.on("request:data", (signal: string, ack: (err: Error | null, data?: DataResponse) => void) => {
        if (!signal) {
            ack(new Error("signal required"));
            return;
        }
        const result: DataResponse = { signal_id: signal, data: [] };
        ack(null, result);
    });

    socket.on("emit:client", () => {
        socket.emit("action:performed", { status: "ok" }, (acknowledgement: string | null) => {
            if (acknowledgement === null) {
                console.debug("client ack received");
            }
        });
    });

    socket.emit("sync:required", { version: 1 }, (err: Error | null, response?: SyncResponse) => {
        if (err) {
            console.debug(`ack error: ${err.message}`);
        } else {
            console.debug(`sync response:`, response);
        }
    });
}

export { emit_with_ack };
""",
        "function": "event_emit_acknowledge_callback",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/socket.ts",
    },
    # ── 6. Middleware pipeline for authentication and validation ────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

interface ExtendedError extends Error {
    data?: Record<string, any>;
}

function setup_middleware(io: Server<DefaultEventsMap>): void {
    io.use((socket: Socket<DefaultEventsMap>, next: (err?: ExtendedError) => void) => {
        const token = socket.handshake.auth.token as string | undefined;
        if (!token) {
            const err = new Error("authentication error") as ExtendedError;
            err.data = { content: "token missing" };
            next(err);
            return;
        }
        next();
    });

    io.use((socket: Socket<DefaultEventsMap>, next: (err?: ExtendedError) => void) => {
        const query = socket.handshake.query as Record<string, string>;
        if (!query.client_version) {
            next();
            return;
        }
        next();
    });

    io.on("connection", (socket: Socket<DefaultEventsMap>) => {
        console.debug(`authenticated socket: ${socket.id}`);
    });
}

export { setup_middleware };
""",
        "function": "middleware_auth_validation_pipeline",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "packages/socket.io/lib/index.ts",
    },
    # ── 7. Handshake data — query, auth, headers ──────────────────────────────────
    {
        "normalized_code": """\
import type { Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

interface HandshakeInfo {
    token: boolean;
    client_id: string;
    user_agent: string;
    address: string;
}

function access_handshake(socket: Socket<DefaultEventsMap>): void {
    const handshake = socket.handshake;

    const token = handshake.auth.token as string;
    const client_id = handshake.query.client_id as string;
    const user_agent = handshake.headers["user-agent"] as string;
    const remote_address = handshake.address;

    socket.on("handshake:info", (callback: (data: HandshakeInfo) => void) => {
        const info: HandshakeInfo = {
            token: !!token,
            client_id,
            user_agent,
            address: remote_address,
        };
        callback(info);
    });
}

export { access_handshake };
""",
        "function": "handshake_auth_query_headers",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "packages/socket.io/lib/socket-types.ts",
    },
    # ── 8. Adapter pattern for cluster/Redis distribution ────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { Adapter } from "socket.io-adapter";
import type { DefaultEventsMap } from "socket.io";

interface AdapterInfo {
    rooms: number;
    sockets: number;
}

function setup_adapter(io: Server<DefaultEventsMap>, AdapterClass: typeof Adapter): void {
    io.adapter((nsp: unknown): Adapter => {
        const adapter: Adapter = new AdapterClass(nsp);
        return adapter;
    });

    io.on("connection", async (socket: Socket<DefaultEventsMap>) => {
        const rooms = socket.rooms;
        const adapter: Adapter = io.of("/").adapter;

        const sockets_in_room = await adapter.sockets(rooms);
        console.debug(`sockets in rooms: ${sockets_in_room.size}`);

        socket.on("adapter:info", async (callback: (info: AdapterInfo) => void) => {
            const room_count = adapter.rooms.size;
            const socket_count = adapter.sids.size;
            const info: AdapterInfo = {
                rooms: room_count,
                sockets: socket_count,
            };
            callback(info);
        });
    });
}

export { setup_adapter };
""",
        "function": "adapter_cluster_distribution",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "packages/socket.io-adapter/lib/index.ts",
    },
    # ── 9. Reconnection and connection state recovery ──────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function setup_reconnection(io: Server<DefaultEventsMap>): void {
    const io_with_recovery = new Server<DefaultEventsMap>(null, {
        connectionStateRecovery: {
            maxDisconnectionDuration: 2 * 60 * 1000,
            skipMiddlewares: true,
        },
        pingInterval: 25_000,
        pingTimeout: 20_000,
    });

    io_with_recovery.on("connection", (socket: Socket<DefaultEventsMap>) => {
        const recovered = !!socket.recovered;
        console.debug(`socket ${socket.id} recovered: ${recovered}`);

        socket.on("reconnect_attempt", () => {
            console.debug("reconnection attempt");
        });

        socket.on("disconnect", (reason: string) => {
            console.debug(`disconnect reason: ${reason}`);
        });
    });
}

export { setup_reconnection };
""",
        "function": "reconnection_state_recovery",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "packages/socket.io/lib/index.ts",
    },
    # ── 10. Binary data streaming and volatile messages ──────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function binary_and_volatile(io: Server<DefaultEventsMap>, socket: Socket<DefaultEventsMap>): void {
    socket.on("upload:binary", (frame: ArrayBuffer) => {
        socket.emit("ack:received", { bytes: frame.byteLength });
    });

    socket.on("stream:start", () => {
        const buffer = Buffer.alloc(1024);
        socket.binary(true).emit("data:chunk", buffer);
    });

    socket.on("notify:volatile", (data: Record<string, any>) => {
        io.volatile.emit("volatile:signal", data);
    });

    socket.on("compress:toggle", () => {
        socket.compress(false).emit("uncompressed", { status: "ok" });
    });
}

export { binary_and_volatile };
""",
        "function": "binary_streaming_volatile_messages",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "packages/socket.io/lib/broadcast-operator.ts",
    },
    # ── 11. Socket disconnection and cleanup ──────────────────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { DefaultEventsMap } from "socket.io";

function disconnect_cleanup(io: Server<DefaultEventsMap>, socket: Socket<DefaultEventsMap>): void {
    socket.on("disconnect", (reason: string) => {
        console.debug(`socket disconnected: ${reason}`);

        const rooms = socket.rooms;
        for (const room of rooms) {
            io.to(room).emit("xxx:left", { socket_id: socket.id });
        }
    });

    socket.on("disconnect_request", (callback: (ack: string) => void) => {
        socket.disconnect(true);
        callback("disconnected");
    });

    io.disconnectSockets(new Set(["room1"]));
    io.of("/api").disconnectSockets();
}

export { disconnect_cleanup };
""",
        "function": "disconnect_cleanup_broadcast",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "packages/socket.io/lib/socket.ts",
    },
    # ── 12. Server-side event emission and typed events ────────────────────────
    {
        "normalized_code": """\
import type { Server, Socket } from "socket.io";
import type { EventsMap } from "socket.io";

interface ServerEvents extends EventsMap {
    "xxx:created": (data: Record<string, any>) => void;
    "xxx:updated": (id: number, data: Record<string, any>) => void;
}

interface ClientEvents extends EventsMap {
    "action:triggered": (signal: string) => void;
}

function typed_events(io: Server<ClientEvents, ServerEvents>): void {
    io.on("connection", (socket: Socket<ClientEvents, ServerEvents>) => {
        socket.on("action:triggered", (signal: string) => {
            socket.emit("xxx:created", {
                id: 1,
                signal,
                timestamp: Date.now(),
            });

            io.emit("xxx:updated", 1, { status: "active" });
        });
    });
}

export { typed_events };
""",
        "function": "server_side_typed_events",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "packages/socket.io/lib/typed-events.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "initialize socket.io server HTTP attachment",
    "namespace creation with event handler registration",
    "room join leave and socket broadcast",
    "broadcast to room and namespace channel",
    "event emit with acknowledgement callback function",
    "middleware pipeline authentication validation",
    "socket handshake auth query headers",
    "adapter cluster Redis distribution",
    "reconnection and connection state recovery",
    "binary data streaming volatile messages",
    "socket disconnection cleanup broadcast",
    "server-side typed events",
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
