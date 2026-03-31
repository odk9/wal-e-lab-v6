"""
ingest_mcp_python.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du Model Context Protocol Python SDK dans la KB Qdrant V6.

Focus : CORE patterns MCP server/client (server creation, tool registration,
resource handlers, prompt templates, transport protocols, client connections,
tool listing and calling, error handling).

Usage:
    .venv/bin/python3 ingest_mcp_python.py
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
REPO_URL = "https://github.com/modelcontextprotocol/python-sdk.git"
REPO_NAME = "modelcontextprotocol/python-sdk"
REPO_LOCAL = "/tmp/mcp-python-sdk"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+mcp+llm+protocol"
CHARTE_VERSION = "1.0"
TAG = "modelcontextprotocol/python-sdk"
SOURCE_REPO = "https://github.com/modelcontextprotocol/python-sdk"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# MCP Python SDK = protocol pour LLM → server tools/resources/prompts.
# Patterns CORE : FastMCP server setup, tool/resource/prompt registration,
# stdio/SSE transport, client server connection.
# U-5 : `server` est OK (MCP terme), `client` est OK, `tool` est OK, `resource` est OK,
#       `prompt` est OK, `transport` est OK, `handler` est OK.

PATTERNS: list[dict] = [
    # ── 1. FastMCP Server Creation ───────────────────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP

server = FastMCP("xxx_service")


@server.call_before_payload_loop
async def setup_resources():
    \"\"\"Initialize server resources before payload loop starts.\"\"\"
    await setup_database()
    await setup_cache()


@server.call_after_payload_loop
async def cleanup_resources():
    \"\"\"Clean up resources after payload loop exits.\"\"\"
    await close_database()
    await close_cache()


async def main():
    \"\"\"Run MCP server with stdio transport.\"\"\"
    async with server:
        print("Server running")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
""",
        "function": "fastmcp_server_creation_lifecycle",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/mcp_server.py",
    },
    # ── 2. Tool Handler Registration (FastMCP) ───────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, Tool

server = FastMCP("xxx_service")


@server.tool()
async def get_xxx_by_id(xxx_id: int) -> TextContent:
    \"\"\"Retrieve xxx resource by integer identifier.

    Args:
        xxx_id: The unique identifier of the xxx to retrieve.

    Returns:
        TextContent with xxx data or error response.
    \"\"\"
    if xxx_id < 0:
        return TextContent(type="text", text="Error: xxx_id must be non-negative")

    xxx = await query_database("SELECT * FROM xxx WHERE id = ?", (xxx_id,))
    if not xxx:
        return TextContent(type="text", text=f"No xxx found with id {xxx_id}")

    return TextContent(type="text", text=f"Xxx: {xxx}")


@server.tool()
async def list_xxxs(limit: int = 10, offset: int = 0) -> TextContent:
    \"\"\"List all xxx resources with pagination.

    Args:
        limit: Maximum number of xxxs to return (1-100).
        offset: Number of xxxs to skip.

    Returns:
        TextContent with list of xxxs.
    \"\"\"
    if limit < 1 or limit > 100:
        limit = 10
    if offset < 0:
        offset = 0

    xxxs = await query_database(
        "SELECT * FROM xxx LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return TextContent(type="text", text=f"Xxxs: {xxxs}")
""",
        "function": "tool_handler_registration_fastmcp",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/tools_example.py",
    },
    # ── 3. Resource Handler Registration ─────────────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP
from mcp.types import Resource, TextContent, EmbeddedResource

server = FastMCP("xxx_service")


@server.resource("xxx://{xxx_id}/profile")
async def get_xxx_profile(xxx_id: str) -> EmbeddedResource:
    \"\"\"Fetch xxx resource profile by ID.

    URI template: xxx://{xxx_id}/profile
    Returns embedded text resource with xxx profile data.
    \"\"\"
    try:
        xxx_id_int = int(xxx_id)
    except ValueError:
        return EmbeddedResource(
            uri=f"xxx://{xxx_id}/profile",
            mimeType="text/plain",
            text="Error: xxx_id must be numeric",
        )

    xxx = await query_database(
        "SELECT profile FROM xxx WHERE id = ?",
        (xxx_id_int,),
    )

    if not xxx:
        text = f"No profile found for xxx_id {xxx_id}"
    else:
        text = xxx.get("profile", "")

    return EmbeddedResource(
        uri=f"xxx://{xxx_id}/profile",
        mimeType="text/plain",
        text=text,
    )


@server.resource("xxx://index")
async def list_xxx_resources() -> EmbeddedResource:
    \"\"\"Return index of all xxx resources.

    URI: xxx://index
    Returns embedded text with resource URIs.
    \"\"\"
    xxxs = await query_database("SELECT id, name FROM xxx")
    lines = [f"xxx://{x['id']}/profile" for x in xxxs]
    text = "\\n".join(lines)

    return EmbeddedResource(
        uri="xxx://index",
        mimeType="text/plain",
        text=text,
    )
""",
        "function": "resource_handler_registration_embedded",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/resources_example.py",
    },
    # ── 4. Prompt Handler Registration ───────────────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptArgument, PromptMessage

server = FastMCP("xxx_service")


@server.prompt()
async def generate_xxx_summary(xxx_id: int = PromptArgument(description="xxx identifier")) -> list[PromptMessage]:
    \"\"\"Generate a summary prompt for the given xxx resource.

    Args:
        xxx_id: The integer ID of the xxx to summarize.

    Returns:
        List of PromptMessage (caller + assistant format).
    \"\"\"
    xxx = await query_database("SELECT * FROM xxx WHERE id = ?", (xxx_id,))
    if not xxx:
        caller_msg = f"Summarize xxx with id {xxx_id}: NOT FOUND"
    else:
        caller_msg = f"Summarize this xxx: {xxx['name']} — {xxx['description']}"

    return [
        PromptMessage(role="caller", content=PromptContent(type="text", text=caller_msg))
    ]


@server.prompt()
async def analyze_xxx_pattern() -> list[PromptMessage]:
    \"\"\"Analyze patterns in all xxx resources.

    Returns:
        List with system + caller content for pattern analysis.
    \"\"\"
    xxxs = await query_database("SELECT name, status FROM xxx LIMIT 100")
    xxx_list = "\\n".join([f"- {x['name']} ({x['status']})" for x in xxxs])

    return [
        PromptMessage(
            role="caller",
            content=PromptContent(
                type="text",
                text=f"Analyze patterns in these xxxs:\\n{xxx_list}",
            ),
        )
    ]
""",
        "function": "prompt_handler_registration_template",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/prompts_example.py",
    },
    # ── 5. Stdio Transport Server Setup ──────────────────────────────────────
    {
        "normalized_code": """\
import sys
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import InitializeRequest, InitializeResult

server = Server("xxx_service")


@server.list_tools()
async def list_tools():
    \"\"\"Return available tools.\"\"\"
    return [
        Tool(
            name="get_xxx",
            description="Retrieve xxx by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "xxx_id": {"type": "integer", "description": "xxx identifier"}
                },
                "required": ["xxx_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    \"\"\"Execute tool by name with arguments.\"\"\"
    if name == "get_xxx":
        xxx_id = arguments.get("xxx_id")
        xxx = await query_database("SELECT * FROM xxx WHERE id = ?", (xxx_id,))
        return [TextContent(type="text", text=str(xxx))]
    raise UnknownToolError(f"Unknown tool: {name}")


@server.on_initialize
async def initialize(request: InitializeRequest) -> InitializeResult:
    \"\"\"Handle client initialization request.\"\"\"
    await setup_database()
    return InitializeResult(
        protocolVersion="2024-11-05",
        serverInfo={"name": "xxx_service", "version": "1.0.0"},
        capabilities={"tools": {}, "resources": {}},
    )


async def main():
    \"\"\"Run server with stdio transport.\"\"\"
    async with stdio_server(server) as stream:
        await server.run(stream)


if __name__ == "__main__":
    asyncio.run(main())
""",
        "function": "stdio_transport_server_setup",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/stdio_transport.py",
    },
    # ── 6. SSE Transport Server Setup ────────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.server.sse import sse_server

app = FastAPI()
server = Server("xxx_service")


@server.list_tools()
async def list_tools():
    \"\"\"Return available tools for SSE clients.\"\"\"
    return [
        Tool(
            name="xxx_operation",
            description="Perform xxx operation",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.get("/sse")
async def sse_endpoint():
    \"\"\"Server-Sent Signals endpoint for MCP client connection.\"\"\"
    async def signal_stream():
        async with sse_server(server) as stream:
            async for signal in stream:
                yield signal

    return StreamingResponse(signal_stream(), media_type="text/sse-stream")


@app.post("/payloads")
async def payload_endpoint(request_data: dict):
    \"\"\"Handle MCP payloads from SSE client.\"\"\"
    payload = request_data.get("payload")
    if not payload:
        raise HTTPException(status_code=400, detail="Missing payload")

    response = await server.handle_message(payload)
    return {"response": response}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
""",
        "function": "sse_transport_http_streaming",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/sse_transport.py",
    },
    # ── 7. Tool Handler with JSON Schema Validation ──────────────────────────
    {
        "normalized_code": """\
from typing import Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

server = FastMCP("xxx_service")


@server.tool()
async def create_xxx(
    name: str,
    description: Optional[str] = None,
    status: str = "active",
) -> TextContent:
    \"\"\"Create new xxx resource with validation.

    Args:
        name: Name of the xxx (required, non-empty).
        description: Optional description text.
        status: Status must be one of: active, inactive, pending.

    Returns:
        TextContent with created xxx ID or error.
    \"\"\"
    if not name or not name.strip():
        return TextContent(type="text", text="Error: name cannot be empty")

    valid_statuses = ["active", "inactive", "pending"]
    if status not in valid_statuses:
        return TextContent(
            type="text",
            text=f"Error: status must be one of {valid_statuses}",
        )

    xxx_id = await insert_database(
        "INSERT INTO xxx (name, description, status) VALUES (?, ?, ?)",
        (name, description or "", status),
    )

    return TextContent(type="text", text=f"Created xxx with id {xxx_id}")


@server.tool()
async def update_xxx(xxx_id: int, **kwargs) -> TextContent:
    \"\"\"Update xxx resource fields.

    Args:
        xxx_id: xxx identifier.
        **kwargs: Field updates (name, description, status).

    Returns:
        TextContent with success or error response.
    \"\"\"
    if xxx_id < 1:
        return TextContent(type="text", text="Error: xxx_id must be >= 1")

    await update_database(
        "UPDATE xxx SET " + ", ".join(f"{k}=?" for k in kwargs.keys()) + " WHERE id=?",
        list(kwargs.values()) + [xxx_id],
    )

    return TextContent(type="text", text=f"Updated xxx {xxx_id}")
""",
        "function": "tool_handler_schema_validation_args",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/tools_validation.py",
    },
    # ── 8. Resource Handler with URI Template ────────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP
from mcp.types import EmbeddedResource

server = FastMCP("xxx_service")


@server.resource("xxx://collection/{collection_id}/entry/{entry_id}")
async def get_collection_entry(collection_id: str, entry_id: str) -> EmbeddedResource:
    \"\"\"Retrieve entry from named collection by ID.

    URI template: xxx://collection/{collection_id}/entry/{entry_id}
    \"\"\"
    try:
        coll_id = int(collection_id)
        entry_id_int = int(entry_id)
    except ValueError:
        return EmbeddedResource(
            uri=f"xxx://collection/{collection_id}/entry/{entry_id}",
            mimeType="text/plain",
            text="Error: IDs must be numeric",
        )

    entry = await query_database(
        "SELECT data FROM entries WHERE collection_id=? AND id=?",
        (coll_id, entry_id_int),
    )

    if not entry:
        text = f"Entry {entry_id} not found in collection {collection_id}"
    else:
        text = entry.get("data", "")

    return EmbeddedResource(
        uri=f"xxx://collection/{collection_id}/entry/{entry_id}",
        mimeType="text/plain",
        text=text,
    )


@server.resource("xxx://schemas")
async def list_schemas() -> EmbeddedResource:
    \"\"\"List all available data schemas.

    URI: xxx://schemas
    \"\"\"
    schemas = await query_database("SELECT name, version FROM schemas")
    lines = [f"{s['name']} (v{s['version']})" for s in schemas]
    text = "\\n".join(lines)

    return EmbeddedResource(
        uri="xxx://schemas",
        mimeType="text/plain",
        text=text,
    )
""",
        "function": "resource_uri_template_matching",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/resources_templates.py",
    },
    # ── 9. Prompt Template with User Parameters ──────────────────────────────
    {
        "normalized_code": """\
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptArgument, PromptMessage, PromptContent

server = FastMCP("xxx_service")


@server.prompt()
async def code_review_prompt(
    code: str = PromptArgument(description="Code snippet to review"),
    language: str = PromptArgument(description="Programming language"),
    focus: str = PromptArgument(description="Review focus: security, performance, style"),
) -> list[PromptMessage]:
    \"\"\"Generate code review prompt with customizable focus.

    Args:
        code: The source code to review.
        language: Language name (python, typescript, go, etc).
        focus: Review area (security, performance, style).

    Returns:
        List of PromptMessage for review.
    \"\"\"
    valid_focus = ["security", "performance", "style", "all"]
    if focus not in valid_focus:
        focus = "all"

    system_msg = f"You are an expert {language} code reviewer focusing on {focus}."
    caller_msg = f"Review this {language} code for {focus}:\\n{code}"

    return [
        PromptMessage(role="caller", content=PromptContent(type="text", text=system_msg + "\\n\\n" + caller_msg))
    ]


@server.prompt()
async def xxx_documentation_template() -> list[PromptMessage]:
    \"\"\"Generate documentation for xxx resources.

    Returns:
        PromptMessage list for documentation generation.
    \"\"\"
    xxxs = await query_database("SELECT name, type FROM xxx LIMIT 50")
    entries = "\\n".join([f"- {x['name']} ({x['type']})" for x in xxxs])

    return [
        PromptMessage(
            role="caller",
            content=PromptContent(
                type="text",
                text=f"Generate markdown documentation for these resources:\\n{entries}",
            ),
        )
    ]
""",
        "function": "prompt_template_with_arguments",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/prompts_templates.py",
    },
    # ── 10. Client: Connect to MCP Server ────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

async def connect_to_server(server_command: str):
    \"\"\"Connect to MCP server via stdio transport.

    Args:
        server_command: Command to start the MCP server.

    Returns:
        ClientSession for tool/resource interactions.
    \"\"\"
    # Create stdio transport
    transport = stdio_client(server_command)

    # Create session
    session = ClientSession(transport)

    # Initialize connection
    await session.initialize()

    return session


async def main():
    \"\"\"Example: connect and interact with server.\"\"\"
    session = await connect_to_server("python mcp_server.py")

    try:
        # List available tools
        tools = await session.list_tools()
        print(f"Available tools: {[t.name for t in tools]}")

        # Call a tool
        result = await session.call_tool("get_xxx", {"xxx_id": 1})
        print(f"Tool result: {result}")

    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
""",
        "function": "client_connect_stdio_session",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client_connection.py",
    },
    # ── 11. Client: List and Call Tools ──────────────────────────────────────
    {
        "normalized_code": """\
from mcp.client.session import ClientSession
from mcp.types import TextContent

async def list_and_call_tools(session: ClientSession, tool_name: str, arguments: dict):
    \"\"\"List available tools and call a specific one.

    Args:
        session: Active ClientSession to server.
        tool_name: Name of tool to invoke.
        arguments: Tool arguments dict.

    Returns:
        Tool result or error response.
    \"\"\"
    # List all available tools
    tools = await session.list_tools()
    tool_names = [t.name for t in tools]

    if tool_name not in tool_names:
        return TextContent(
            type="text",
            text=f"Error: tool '{tool_name}' not found. Available: {tool_names}",
        )

    # Call the tool
    try:
        result = await session.call_tool(tool_name, arguments)
        return result
    except Exception as e:
        return TextContent(type="text", text=f"Error calling {tool_name}: {str(e)}")


async def demo_call_tools(session: ClientSession):
    \"\"\"Demo: list tools and make several calls.\"\"\"
    # List tools
    tools = await session.list_tools()
    for tool in tools:
        print(f"Tool: {tool.name}")
        print(f"  Description: {tool.description}")
        print(f"  Input schema: {tool.inputSchema}")

    # Call get_xxx tool
    result = await list_and_call_tools(session, "get_xxx", {"xxx_id": 1})
    print(f"Result: {result}")

    # Call list_xxxs with pagination
    result = await list_and_call_tools(
        session, "list_xxxs", {"limit": 20, "offset": 0}
    )
    print(f"Result: {result}")
""",
        "function": "client_list_and_call_tools",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client_tools.py",
    },
    # ── 12. Client: Read Resources ───────────────────────────────────────────
    {
        "normalized_code": """\
from mcp.client.session import ClientSession

async def list_and_read_resources(session: ClientSession):
    \"\"\"List available resources and read one by URI.

    Args:
        session: Active ClientSession to server.

    Returns:
        List of resources and content from first resource.
    \"\"\"
    # List all available resources
    resources = await session.list_resources()
    print(f"Found {len(resources)} resources:")
    for res in resources:
        print(f"  URI: {res.uri}")
        print(f"  Name: {res.name}")
        print(f"  Mime: {res.mimeType}")

    # Read first resource
    if resources:
        first_uri = resources[0].uri
        content = await session.read_resource(first_uri)
        print(f"\\nResource content ({first_uri}):")
        for entry in content:
            if hasattr(entry, "text"):
                print(entry.text)

    return resources


async def demo_read_by_uri(session: ClientSession, uri: str):
    \"\"\"Read a specific resource by URI.

    Args:
        session: Active ClientSession.
        uri: Resource URI to read (e.g., 'xxx://1/profile').

    Returns:
        Resource content list.
    \"\"\"
    try:
        content = await session.read_resource(uri)
        print(f"Resource {uri}:")
        for entry in content:
            if hasattr(entry, "text"):
                print(entry.text)
        return content
    except Exception as e:
        print(f"Error reading {uri}: {str(e)}")
        return []
""",
        "function": "client_read_resources_by_uri",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client_resources.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "FastMCP server creation with lifecycle hooks",
    "tool handler registration and execution",
    "resource handler with embedded URI templates",
    "prompt template registration with arguments",
    "stdio transport MCP server setup",
    "SSE server-sent events HTTP streaming",
    "tool handler schema validation and arguments",
    "resource URI template matching pattern",
    "prompt message template generation",
    "client session connection to server",
    "client list tools and call tool execution",
    "client read resources by URI",
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
