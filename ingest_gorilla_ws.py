"""
ingest_gorilla_ws.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du gorilla/websocket dans la KB Qdrant V6.

Focus : CORE WebSocket patterns (Upgrader config, Hub, read/write pumps, keepalive,
JSON encoding, connection lifecycle, origin checking, graceful shutdown).

Usage:
    .venv/bin/python3 ingest_gorilla_ws.py
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
REPO_URL = "https://github.com/gorilla/websocket.git"
REPO_NAME = "gorilla/websocket"
REPO_LOCAL = "/tmp/websocket"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+gorilla+websocket"
CHARTE_VERSION = "1.0"
TAG = "gorilla/websocket"
SOURCE_REPO = "https://github.com/gorilla/websocket"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# gorilla/websocket = HTTP WebSocket upgrade library.
# Patterns CORE : Upgrader configuration, Hub pub/sub, read/write pumps,
# JSON encoding, keepalive (ping/pong), connection lifecycle, origin checking.
# U-5 : client → OK (WebSocket client concept), message → payload/frame,
# user → OK (HTTP auth context), event → signal, task → job.

PATTERNS: list[dict] = [
    # ── 1. Upgrader configuration with buffer sizes and origin checking ─
    {
        "normalized_code": """\
package main

import (
	"net"
	"net/http"
	"time"
)

var upgrader = websocket.Upgrader{
	HandshakeTimeout: 10 * time.Second,
	ReadBufferSize:   4096,
	WriteBufferSize:  4096,
	CheckOrigin: func(r *http.Request) bool {
		origin := r.Header.Get("Origin")
		if origin == "" {
			return true
		}
		u, err := url.Parse(origin)
		if err != nil {
			return false
		}
		return u.Host == r.Host
	},
	EnableCompression: true,
}

func handleUpgrade(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		http.Error(w, "Upgrade failed", http.StatusBadRequest)
		return
	}
	defer conn.Close()
}
""",
        "function": "websocket_upgrader_config_origin_check",
        "feature_type": "config",
        "file_role": "route",
        "file_path": "server.go",
    },
    # ── 2. Hub pattern — register/unregister/broadcast channels ─────────
    {
        "normalized_code": """\
package main

type Hub struct {
	clients    map[*Client]bool
	broadcast  chan []byte
	register   chan *Client
	unregister chan *Client
	done       chan bool
	mu         sync.Mutex
}

func NewHub() *Hub {
	return &Hub{
		clients:    make(map[*Client]bool),
		broadcast:  make(chan []byte, 256),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		done:       make(chan bool),
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = true
			h.mu.Unlock()
		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
			}
			h.mu.Unlock()
		case payload := <-h.broadcast:
			h.mu.Lock()
			for client := range h.clients {
				select {
				case client.send <- payload:
				default:
					close(client.send)
					delete(h.clients, client)
				}
			}
			h.mu.Unlock()
		case <-h.done:
			return
		}
	}
}

func (h *Hub) Stop() {
	close(h.done)
}
""",
        "function": "hub_pattern_register_broadcast",
        "feature_type": "pattern",
        "file_role": "model",
        "file_path": "hub.go",
    },
    # ── 3. Client read pump — message reception with deadline/limit ─────
    {
        "normalized_code": """\
package main

import (
	"bytes"
	"log"
	"time"
)

const (
	writeWait     = 10 * time.Second
	pongWait      = 60 * time.Second
	maxFrameSize  = 1 << 20
)

func (c *Client) ReadPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()
	c.conn.SetReadLimit(maxFrameSize)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})
	for {
		_, payload, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(
				err,
				websocket.CloseGoingAway,
				websocket.CloseAbnormalClosure,
			) {
				log.Printf("error: %v", err)
			}
			break
		}
		payload = bytes.TrimSpace(payload)
		c.hub.broadcast <- payload
	}
}
""",
        "function": "client_read_pump_deadline_limit",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "client.go",
    },
    # ── 4. Client write pump — message sending with ping/pong keepalive ─
    {
        "normalized_code": """\
package main

import (
	"log"
	"time"
)

func (c *Client) WritePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()
	for {
		select {
		case payload, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			w.Write(payload)
			if err := w.Close(); err != nil {
				return
			}
		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
""",
        "function": "client_write_pump_ping_pong_keepalive",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "client.go",
    },
    # ── 5. Connection lifecycle — register → pumps → cleanup ────────────
    {
        "normalized_code": """\
package main

import (
	"log"
	"net/http"
)

func ServeWebSocket(hub *Hub, w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("upgrade error:", err)
		return
	}
	client := &Client{
		hub:  hub,
		conn: conn,
		send: make(chan []byte, 256),
	}
	hub.register <- client
	go client.WritePump()
	go client.ReadPump()
}

func (c *Client) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}
""",
        "function": "connection_lifecycle_register_pumps_cleanup",
        "feature_type": "pattern",
        "file_role": "route",
        "file_path": "server.go",
    },
    # ── 6. JSON encoding — write/read structured data over WebSocket ────
    {
        "normalized_code": """\
package main

import (
	"encoding/json"
	"io"
	"log"
)

type Payload struct {
	Type    string      `json:"type"`
	Content interface{} `json:"content"`
	Sender  string      `json:"sender"`
}

func (c *Client) WriteJSON(v interface{}) error {
	w, err := c.conn.NextWriter(websocket.TextMessage)
	if err != nil {
		return err
	}
	defer w.Close()
	return json.NewEncoder(w).Encode(v)
}

func (c *Client) ReadJSON(v interface{}) error {
	_, r, err := c.conn.NextReader()
	if err != nil {
		return err
	}
	defer r.Close()
	err = json.NewDecoder(r).Decode(v)
	if err == io.EOF {
		return io.ErrUnexpectedEOF
	}
	return err
}
""",
        "function": "json_encoding_write_read_structured",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "json.go",
    },
    # ── 7. Binary frame handling — ReadMessage/WriteMessage with type ───
    {
        "normalized_code": """\
package main

import (
	"log"
)

func (c *Client) HandleFrames() {
	defer c.conn.Close()
	c.conn.SetReadLimit(1 << 20)
	for {
		msgType, frame, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err) {
				log.Printf("close error: %v", err)
			}
			break
		}
		switch msgType {
		case websocket.TextMessage:
			err := c.conn.WriteMessage(websocket.TextMessage, frame)
			if err != nil {
				return
			}
		case websocket.BinaryMessage:
			err := c.conn.WriteMessage(websocket.BinaryMessage, frame)
			if err != nil {
				return
			}
		case websocket.CloseMessage:
			return
		}
	}
}
""",
        "function": "binary_frame_read_write_message_type",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "conn.go",
    },
    # ── 8. Graceful shutdown — close signal propagation ──────────────────
    {
        "normalized_code": """\
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

type Server struct {
	hub    *Hub
	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

func (s *Server) Shutdown(timeout time.Duration) error {
	s.cancel()
	done := make(chan error)
	go func() {
		s.wg.Wait()
		done <- nil
	}()
	select {
	case err := <-done:
		return err
	case <-time.After(timeout):
		return context.DeadlineExceeded
	}
}

func (s *Server) handleSignals() {
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	log.Println("shutdown signal received")
	s.Shutdown(30 * time.Second)
}
""",
        "function": "graceful_shutdown_close_signal",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "server.go",
    },
    # ── 9. Concurrent write protection — mutex on hub broadcast ─────────
    {
        "normalized_code": """\
package main

import (
	"sync"
)

type Hub struct {
	mu         sync.RWMutex
	clients    map[*Client]bool
	broadcast  chan []byte
}

func (h *Hub) Broadcast(payload []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	select {
	case h.broadcast <- payload:
	default:
		log.Printf("broadcast channel full, dropping payload")
	}
}

func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

func (h *Hub) Register(client *Client) {
	select {
	case h.register <- client:
	case <-h.done:
	}
}
""",
        "function": "concurrent_write_protection_mutex_hub",
        "feature_type": "pattern",
        "file_role": "model",
        "file_path": "hub.go",
    },
    # ── 10. Dialer for client connections — dial upstream WebSocket ─────
    {
        "normalized_code": """\
package main

import (
	"log"
	"net/url"
	"time"

	"github.com/gorilla/websocket"
)

var dialer = websocket.Dialer{
	HandshakeTimeout: 10 * time.Second,
	ReadBufferSize:   4096,
	WriteBufferSize:  4096,
}

func ConnectToServer(addr string) (*websocket.Conn, error) {
	u := url.URL{Scheme: "ws", Host: addr, Path: "/ws"}
	log.Printf("connecting to %s", u.String())
	conn, _, err := dialer.Dial(u.String(), nil)
	if err != nil {
		log.Println("dial error:", err)
		return nil, err
	}
	return conn, nil
}

func (c *Client) WriteControl(messageType int, payload []byte) error {
	return c.conn.WriteControl(messageType, payload, time.Now().Add(5*time.Second))
}
""",
        "function": "client_dialer_upstream_connect",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "client.go",
    },
    # ── 11. ReadDeadline + PongHandler for ping/pong heartbeat ──────────
    {
        "normalized_code": """\
package main

import (
	"time"
)

const (
	pongWait   = 60 * time.Second
	pingPeriod = (pongWait * 9) / 10
)

func (c *Client) SetupHeartbeat() {
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})
}

func (c *Client) SendPing() error {
	return c.conn.WriteControl(
		websocket.PingMessage,
		[]byte{},
		time.Now().Add(10*time.Second),
	)
}

func (c *Client) DetectDeadConnection(timeout time.Duration) bool {
	c.conn.SetReadDeadline(time.Now().Add(timeout))
	_, _, err := c.conn.NextReader()
	return err != nil
}
""",
        "function": "heartbeat_deadline_pong_handler",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "conn.go",
    },
    # ── 12. NextWriter pattern for batching outbound messages ───────────
    {
        "normalized_code": """\
package main

import (
	"bytes"
	"log"
)

func (c *Client) WriteMessagesBuffered() error {
	w, err := c.conn.NextWriter(websocket.TextMessage)
	if err != nil {
		return err
	}
	defer w.Close()
	for {
		select {
		case payload, ok := <-c.send:
			if !ok {
				return nil
			}
			w.Write(payload)
			w.Write([]byte("\n"))
			n := len(c.send)
			for i := 0; i < n; i++ {
				w.Write(<-c.send)
				w.Write([]byte("\n"))
			}
		default:
			return nil
		}
	}
}

func (c *Client) WriteNextMessage(msgType int, data []byte) error {
	w, err := c.conn.NextWriter(msgType)
	if err != nil {
		return err
	}
	_, err = w.Write(data)
	if err != nil {
		w.Close()
		return err
	}
	return w.Close()
}
""",
        "function": "next_writer_buffer_outbound_messages",
        "feature_type": "pattern",
        "file_role": "utility",
        "file_path": "client.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "WebSocket upgrader configuration with buffer sizes and origin checking",
    "hub pattern with register unregister broadcast channels",
    "client read pump message reception with deadline and limit",
    "client write pump ping pong keepalive",
    "connection lifecycle register pumps cleanup",
    "JSON encoding write read structured data WebSocket",
    "binary frame handling read write message type",
    "graceful shutdown close signal propagation",
    "concurrent write protection mutex hub broadcast",
    "dialer client connections upstream WebSocket",
    "heartbeat deadline pong handler ping",
    "next writer buffer outbound messages",
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
