"""
ingest_mcp_go.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du protocole MCP (Model Context Protocol) en Go depuis mark3labs/mcp-go dans la KB Qdrant V6.

Focus : Patterns Core pour construire des MCP servers en Go — service creation,
tool registration, resource handling, prompt templates, transports (stdio/SSE),
capabilities, handlers, lifecycle hooks.

Usage:
    .venv/bin/python3 ingest_mcp_go.py
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
REPO_URL = "https://github.com/mark3labs/mcp-go.git"
REPO_NAME = "mark3labs/mcp-go"
REPO_LOCAL = "/tmp/mcp-go"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+mcp+llm+protocol"
CHARTE_VERSION = "1.0"
TAG = "mark3labs/mcp-go"
SOURCE_REPO = "https://github.com/mark3labs/mcp-go"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# MCP Go = Protocol library pour LLM-powered applications.
# Patterns CORE : server setup, tool/resource/prompt handlers, transports,
# capabilities, lifecycle management.
# U-5 : `server`, `handler`, `tool`, `resource`, `protocol`, `transport` sont OK.

PATTERNS: list[dict] = [
    # ── 1. MCP Server Creation and Configuration ───────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "github.com/mark3labs/mcp-go/client"
    "github.com/mark3labs/mcp-go/server"
)

type XxxServer struct {
    name    string
    version string
    handler *server.RequestHandler
}

func NewXxxServer(name, version string) *XxxServer {
    return &XxxServer{
        name:    name,
        version: version,
        handler: server.NewRequestHandler(),
    }
}

func (s *XxxServer) Start(ctx context.Context) error {
    return s.handler.Listen(ctx)
}

func (s *XxxServer) SetCapabilities(cap *server.ServerCapabilities) {
    s.handler.SetCapabilities(cap)
}
""",
        "function": "create_mcp_server_go",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/xxx_server.go",
    },
    # ── 2. Register Tool Handler ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "github.com/mark3labs/mcp-go/server"
)

func (s *XxxServer) RegisterToolHandler() {
    s.handler.RegisterHandler(
        "tools/list",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            return &server.Response{
                Content: []interface{}{
                    map[string]interface{}{
                        "name":        "xxx_action",
                        "description": "Perform xxx_action with input parameters",
                        "inputSchema": map[string]interface{}{
                            "type": "object",
                            "properties": map[string]interface{}{
                                "param_xxx": map[string]interface{}{
                                    "type":        "string",
                                    "description": "Input parameter xxx",
                                },
                            },
                            "required": []string{"param_xxx"},
                        },
                    },
                },
            }, nil
        },
    )
}

func (s *XxxServer) RegisterToolCallHandler() {
    s.handler.RegisterHandler(
        "tools/call",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            args := req.Params["arguments"].(map[string]interface{})
            paramXxx := args["param_xxx"].(string)
            result := performXxxAction(ctx, paramXxx)
            return &server.Response{Content: result}, nil
        },
    )
}
""",
        "function": "register_tool_handler_go",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_server.go",
    },
    # ── 3. Register Resource Handler ───────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "github.com/mark3labs/mcp-go/server"
)

func (s *XxxServer) RegisterResourceHandler() {
    s.handler.RegisterHandler(
        "resources/list",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            return &server.Response{
                Content: []interface{}{
                    map[string]interface{}{
                        "uri":         "file:///xxx/resource",
                        "name":        "xxx_resource",
                        "description": "Resource xxx description",
                        "mimeType":    "text/plain",
                    },
                },
            }, nil
        },
    )

    s.handler.RegisterHandler(
        "resources/read",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            uri := req.Params["uri"].(string)
            content := readXxxResource(ctx, uri)
            return &server.Response{
                Content: []map[string]interface{}{
                    {"uri": uri, "contents": content, "mimeType": "text/plain"},
                },
            }, nil
        },
    )
}
""",
        "function": "register_resource_handler_go",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_server.go",
    },
    # ── 4. Register Prompt Handler ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "github.com/mark3labs/mcp-go/server"
)

func (s *XxxServer) RegisterPromptHandler() {
    s.handler.RegisterHandler(
        "prompts/list",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            return &server.Response{
                Content: []interface{}{
                    map[string]interface{}{
                        "name":        "xxx_prompt",
                        "description": "Prompt template for xxx operation",
                        "arguments": []map[string]interface{}{
                            {
                                "name":        "operation_name",
                                "description": "Name of the operation",
                                "required":    true,
                            },
                        },
                    },
                },
            }, nil
        },
    )

    s.handler.RegisterHandler(
        "prompts/get",
        func(ctx context.Context, req *server.Request) (*server.Response, error) {
            name := req.Params["name"].(string)
            args := req.Params["arguments"].(map[string]interface{})
            prompt := buildXxxPrompt(ctx, name, args)
            return &server.Response{Content: prompt}, nil
        },
    )
}
""",
        "function": "register_prompt_handler_go",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_server.go",
    },
    # ── 5. Stdio Transport Setup ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "log"
    "os"
    "github.com/mark3labs/mcp-go/server"
    "github.com/mark3labs/mcp-go/transport"
)

func SetupStdioTransport(srv *XxxServer) (*transport.StdioTransport, error) {
    // Initialize stdio transport for stdin/stdout communication with LLM client.
    tr := transport.NewStdioTransport(
        transport.StdioTransportConfig{
            Stdin:  os.Stdin,
            Stdout: os.Stdout,
        },
    )

    // Mount server handlers to transport.
    tr.SetMessageHandler(srv.handler.HandleMessage)
    return tr, nil
}

func main() {
    srv := NewXxxServer("xxx-server", "1.0.0")
    tr, err := SetupStdioTransport(srv)
    if err != nil {
        log.Fatalf("Failed to setup stdio transport: %v", err)
    }

    ctx := context.Background()
    if err := tr.Listen(ctx); err != nil {
        log.Fatalf("Stdio transport error: %v", err)
    }
}
""",
        "function": "stdio_transport_go",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/main.go",
    },
    # ── 6. SSE Transport Setup ─────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "log"
    "net/http"
    "github.com/mark3labs/mcp-go/server"
    "github.com/mark3labs/mcp-go/transport"
)

func SetupSSETransport(srv *XxxServer, addr string) (*transport.SSETransport, error) {
    // Initialize SSE (server-sent entries) transport for HTTP streaming.
    tr := transport.NewSSETransport(
        transport.SSETransportConfig{
            Addr:    addr,
            Encoder: nil,
        },
    )

    // Mount server handlers.
    tr.SetMessageHandler(srv.handler.HandleMessage)

    // HTTP endpoint for SSE connection.
    http.HandleFunc("/sse", func(w http.ResponseWriter, r *http.Request) {
        tr.ServeHTTP(w, r)
    })

    return tr, nil
}

func main() {
    srv := NewXxxServer("xxx-server", "1.0.0")
    tr, err := SetupSSETransport(srv, ":8080")
    if err != nil {
        log.Fatalf("Failed to setup SSE transport: %v", err)
    }

    log.Println("SSE server listening on http://localhost:8080")
    if err := http.ListenAndServe(":8080", nil); err != nil {
        log.Fatalf("HTTP server error: %v", err)
    }
}
""",
        "function": "sse_transport_go",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/sse_main.go",
    },
    # ── 7. Tool Schema Definition ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "github.com/mark3labs/mcp-go/server"
)

type XxxToolSchema struct {
    Name        string                 `json:"name"`
    Description string                 `json:"description"`
    InputSchema map[string]interface{} `json:"inputSchema"`
}

func DefineXxxToolSchema() XxxToolSchema {
    return XxxToolSchema{
        Name:        "xxx_tool",
        Description: "Tool for xxx operation with input validation",
        InputSchema: map[string]interface{}{
            "type": "object",
            "properties": map[string]interface{}{
                "action": map[string]interface{}{
                    "type":        "string",
                    "description": "Action to perform",
                    "enum":        []string{"create", "read", "update", "delete"},
                },
                "resource_id": map[string]interface{}{
                    "type":        "integer",
                    "description": "Resource ID for operation",
                },
                "data": map[string]interface{}{
                    "type":        "object",
                    "description": "Data payload",
                },
            },
            "required": []string{"action", "resource_id"},
        },
    }
}
""",
        "function": "tool_schema_definition_go",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "examples/xxx_schema.go",
    },
    # ── 8. Resource Template Definition ────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "github.com/mark3labs/mcp-go/server"
)

type XxxResourceTemplate struct {
    URITemplate string
    Name        string
    Description string
    MimeType    string
}

func DefineXxxResourceTemplate() XxxResourceTemplate {
    return XxxResourceTemplate{
        URITemplate: "file:///xxx/{resource_type}/{resource_id}",
        Name:        "xxx_resource",
        Description: "Template for accessing xxx resource by type and ID",
        MimeType:    "application/json",
    }
}

func ExpandResourceURI(template XxxResourceTemplate, resourceType, resourceID string) string {
    uri := template.URITemplate
    uri = strings.ReplaceAll(uri, "{resource_type}", resourceType)
    uri = strings.ReplaceAll(uri, "{resource_id}", resourceID)
    return uri
}
""",
        "function": "resource_template_go",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "examples/xxx_resource.go",
    },
    # ── 9. Prompt Template Definition ──────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "github.com/mark3labs/mcp-go/server"
)

type XxxPromptTemplate struct {
    Name        string
    Description string
    Arguments   []XxxPromptArg
    Template    string
}

type XxxPromptArg struct {
    Name        string
    Description string
    Required    bool
}

func DefineXxxPromptTemplate() XxxPromptTemplate {
    return XxxPromptTemplate{
        Name:        "xxx_prompt",
        Description: "Prompt template for xxx operation",
        Arguments: []XxxPromptArg{
            {Name: "context", Description: "Operation context", Required: true},
            {Name: "constraints", Description: "Operation constraints", Required: false},
        },
        Template: "You are performing: {{.context}}. Constraints: {{.constraints}}",
    }
}

func (t XxxPromptTemplate) Render(args map[string]interface{}) string {
    text := t.Template
    for k, v := range args {
        placeholder := fmt.Sprintf("{{.%s}}", k)
        text = strings.ReplaceAll(text, placeholder, fmt.Sprintf("%v", v))
    }
    return text
}
""",
        "function": "prompt_template_go",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "examples/xxx_prompt.go",
    },
    # ── 10. Server Capabilities Configuration ──────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "github.com/mark3labs/mcp-go/server"
)

func ConfigureXxxServerCapabilities() *server.ServerCapabilities {
    return &server.ServerCapabilities{
        Tools: &server.ToolCapability{
            ListChanged: true,
        },
        Resources: &server.ResourceCapability{
            Subscribe: true,
            ListChanged: true,
        },
        Prompts: &server.PromptCapability{
            ListChanged: true,
        },
        Logging: &server.LoggingCapability{},
    }
}

func (s *XxxServer) InitializeCapabilities(ctx context.Context) error {
    caps := ConfigureXxxServerCapabilities()
    s.SetCapabilities(caps)
    return nil
}
""",
        "function": "server_capabilities_go",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/xxx_server.go",
    },
    # ── 11. Tool Call Handler Implementation ────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "encoding/json"
    "github.com/mark3labs/mcp-go/server"
)

type ToolCallRequest struct {
    Name      string                 `json:"name"`
    Arguments map[string]interface{} `json:"arguments"`
}

type ToolCallResult struct {
    Content []map[string]interface{} `json:"content"`
    IsError bool                     `json:"isError"`
}

func (s *XxxServer) HandleToolCall(ctx context.Context, toolName string, args map[string]interface{}) (*ToolCallResult, error) {
    switch toolName {
    case "xxx_action":
        return handleXxxAction(ctx, args)
    case "yyy_action":
        return handleYyyAction(ctx, args)
    default:
        return &ToolCallResult{
            Content: []map[string]interface{}{
                {"type": "text", "text": "Unknown tool: " + toolName},
            },
            IsError: true,
        }, nil
    }
}

func handleXxxAction(ctx context.Context, args map[string]interface{}) (*ToolCallResult, error) {
    result := map[string]interface{}{"status": "success", "data": args}
    return &ToolCallResult{
        Content: []map[string]interface{}{
            {"type": "text", "text": jsonString(result)},
        },
    }, nil
}
""",
        "function": "tool_call_handler_go",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_server.go",
    },
    # ── 12. Server Lifecycle Hooks ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "context"
    "log"
)

type XxxServerLifecycle struct {
    onInit    []func(context.Context) error
    onShutdown []func(context.Context) error
}

func NewXxxServerLifecycle() *XxxServerLifecycle {
    return &XxxServerLifecycle{
        onInit:     []func(context.Context) error{},
        onShutdown: []func(context.Context) error{},
    }
}

func (lc *XxxServerLifecycle) RegisterInitHook(fn func(context.Context) error) {
    lc.onInit = append(lc.onInit, fn)
}

func (lc *XxxServerLifecycle) RegisterShutdownHook(fn func(context.Context) error) {
    lc.onShutdown = append(lc.onShutdown, fn)
}

func (lc *XxxServerLifecycle) RunInitHooks(ctx context.Context) error {
    for _, hook := range lc.onInit {
        if err := hook(ctx); err != nil {
            log.Printf("Init hook failed: %v", err)
            return err
        }
    }
    return nil
}

func (lc *XxxServerLifecycle) RunShutdownHooks(ctx context.Context) error {
    for _, hook := range lc.onShutdown {
        if err := hook(ctx); err != nil {
            log.Printf("Shutdown hook failed: %v", err)
        }
    }
    return nil
}
""",
        "function": "server_lifecycle_hooks_go",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/xxx_lifecycle.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "MCP server creation and configuration in Go",
    "register tool handler with schema in Go",
    "register resource handler and read endpoint",
    "register prompt handler with templates",
    "stdio transport setup and listening",
    "SSE Server-Sent Events transport HTTP",
    "tool schema definition with input validation",
    "resource template URI expansion",
    "prompt template rendering with arguments",
    "server capabilities configuration tools resources",
    "tool call handler implementation dispatch",
    "server lifecycle hooks initialization shutdown",
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
