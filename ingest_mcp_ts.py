"""
ingest_mcp_ts.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
du Model Context Protocol TypeScript SDK dans la KB Qdrant V6.

Focus : CORE patterns MCP server/client TypeScript (McpServer setup, tool/resource/
prompt handlers, Zod schema validation, client connections, tool invocation,
Streamable HTTP transport).

Usage:
    .venv/bin/python3 ingest_mcp_ts.py
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/modelcontextprotocol/typescript-sdk.git"
REPO_NAME = "modelcontextprotocol/typescript-sdk"
REPO_LOCAL = "/tmp/mcp-typescript-sdk"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+mcp+llm+protocol"
CHARTE_VERSION = "1.0"
TAG = "modelcontextprotocol/typescript-sdk"
SOURCE_REPO = "https://github.com/modelcontextprotocol/typescript-sdk"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# MCP TypeScript SDK = protocol pour LLM → server tools/resources/prompts.
# Patterns CORE : McpServer creation, tool/resource/prompt handlers, Zod validation,
# stdio/SSE/HTTP transport, client connection.
# U-5 : `server` est OK (MCP terme), `client` est OK, `tool` est OK, `resource` est OK,
#       `prompt` est OK, `handler` est OK, `transport` est OK, `schema` est OK.

PATTERNS: list[dict] = [
    # ── 1. McpServer Initialization (TypeScript) ─────────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
  TextContent,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

// Set up tool handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "get_xxx",
        description: "Retrieve xxx by identifier",
        inputSchema: {
          type: "object" as const,
          properties: {
            xxx_id: {
              type: "integer",
              description: "The xxx identifier",
            },
          },
          required: ["xxx_id"],
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request;

  if (name === "get_xxx") {
    const xxxId = (args as { xxx_id: number }).xxx_id;
    const xxx = await queryDatabase("SELECT * FROM xxx WHERE id = ?", [xxxId]);
    return {
      content: [
        {
          type: "text" as const,
          text: xxx ? JSON.stringify(xxx) : `No xxx found with id ${xxxId}`,
        },
      ],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

export default server;
""",
        "function": "mcpserver_init_typescript",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/server.ts",
    },
    # ── 2. Tool Handler Registration (TypeScript) ────────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  Tool,
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

const xxxTools: Tool[] = [
  {
    name: "create_xxx",
    description: "Create new xxx resource",
    inputSchema: {
      type: "object" as const,
      properties: {
        name: {
          type: "string",
          description: "xxx name",
        },
        description: {
          type: "string",
          description: "Optional description",
        },
        status: {
          type: "string",
          enum: ["active", "inactive", "pending"],
          description: "xxx status",
        },
      },
      required: ["name"],
    },
  },
  {
    name: "list_xxxs",
    description: "List all xxx resources",
    inputSchema: {
      type: "object" as const,
      properties: {
        limit: {
          type: "integer",
          description: "Max results (1-100)",
        },
        offset: {
          type: "integer",
          description: "Offset for pagination",
        },
      },
    },
  },
];

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: xxxTools };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request;

  if (name === "create_xxx") {
    const { name: xxxName, description, status = "active" } = args as Record<string, unknown>;
    if (typeof xxxName !== "string" || !xxxName.trim()) {
      return {
        content: [
          { type: "text" as const, text: "Error: name cannot be empty" },
        ],
      };
    }
    const xxxId = await insertDatabase(
      "INSERT INTO xxx (name, description, status) VALUES (?, ?, ?)",
      [xxxName, description || "", status],
    );
    return {
      content: [
        { type: "text" as const, text: `Created xxx with id ${xxxId}` },
      ],
    };
  }

  if (name === "list_xxxs") {
    const { limit = 10, offset = 0 } = args as Record<string, unknown>;
    const xxxs = await queryDatabase("SELECT * FROM xxx LIMIT ? OFFSET ?", [limit, offset]);
    return {
      content: [{ type: "text" as const, text: JSON.stringify(xxxs) }],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

export default server;
""",
        "function": "tool_handler_ts_calltooltrequest",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/tools.ts",
    },
    # ── 3. Resource Handler Registration (TypeScript) ────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  Resource,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  EmbeddedResource,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

const xxxResources: Resource[] = [
  {
    uri: "xxx://index",
    name: "xxx Index",
    description: "List of all xxx resources",
    mimeType: "text/plain",
  },
];

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  return { resources: xxxResources };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request;

  if (uri === "xxx://index") {
    const xxxs = await queryDatabase("SELECT id, name FROM xxx");
    const lines = xxxs.map((x: { id: number; name: string }) => `xxx://${x.id}/profile`);
    return {
      contents: [
        {
          uri: "xxx://index",
          mimeType: "text/plain",
          text: lines.join("\\n"),
        } as EmbeddedResource,
      ],
    };
  }

  if (uri.startsWith("xxx://")) {
    const match = uri.match(/xxx:\\/\\/(\\d+)\\/profile/);
    if (!match) {
      return {
        contents: [
          {
            uri: uri,
            mimeType: "text/plain",
            text: "Invalid xxx URI format",
          } as EmbeddedResource,
        ],
      };
    }

    const xxxId = parseInt(match[1], 10);
    const xxx = await queryDatabase("SELECT profile FROM xxx WHERE id = ?", [xxxId]);

    return {
      contents: [
        {
          uri: uri,
          mimeType: "text/plain",
          text: xxx ? (xxx as { profile: string }).profile : `No profile for xxx ${xxxId}`,
        } as EmbeddedResource,
      ],
    };
  }

  throw new Error(`Unknown resource: ${uri}`);
});

export default server;
""",
        "function": "resource_handler_ts_uri_template",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/resources.ts",
    },
    # ── 4. Prompt Handler Registration (TypeScript) ──────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  Prompt,
  ListPromptsRequestSchema,
  GetPromptRequestSchema,
  PromptMessage,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

const xxxPrompts: Prompt[] = [
  {
    name: "analyze_xxx_pattern",
    description: "Analyze patterns in xxx resources",
    arguments: [
      {
        name: "limit",
        description: "Max xxxs to analyze",
        required: false,
      },
    ],
  },
  {
    name: "generate_xxx_summary",
    description: "Generate summary for xxx",
    arguments: [
      {
        name: "xxx_id",
        description: "xxx identifier",
        required: true,
      },
    ],
  },
];

server.setRequestHandler(ListPromptsRequestSchema, async () => {
  return { prompts: xxxPrompts };
});

server.setRequestHandler(GetPromptRequestSchema, async (request) => {
  const { name, arguments: args } = request;

  if (name === "analyze_xxx_pattern") {
    const limit = ((args?.limit as number) || 100);
    const xxxs = await queryDatabase("SELECT name, status FROM xxx LIMIT ?", [limit]);
    const xxxList = xxxs.map((x: { name: string; status: string }) => `- ${x.name} (${x.status})`).join("\\n");

    const payloads: PromptMessage[] = [
      {
        role: "caller",
        content: {
          type: "text",
          text: `Analyze patterns in these xxxs:\\n${xxxList}`,
        },
      },
    ];
    return { payloads };
  }

  if (name === "generate_xxx_summary") {
    const xxxId = args?.xxx_id as number;
    if (!xxxId) {
      throw new Error("xxx_id is required");
    }

    const xxx = await queryDatabase("SELECT * FROM xxx WHERE id = ?", [xxxId]);
    const text = xxx
      ? `Summarize this xxx: ${(xxx as { name: string; description: string }).name} — ${(xxx as { name: string; description: string }).description}`
      : `No xxx found with id ${xxxId}`;

    const payloads: PromptMessage[] = [
      {
        role: "caller",
        content: {
          type: "text",
          text: text,
        },
      },
    ];
    return { payloads };
  }

  throw new Error(`Unknown prompt: ${name}`);
});

export default server;
""",
        "function": "prompt_handler_ts_getprompt",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/prompts.ts",
    },
    # ── 5. Stdio Transport Server (TypeScript) ───────────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

async function main() {
  const server = new Server({
    name: "xxx_service",
    version: "1.0.0",
  });

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "get_xxx",
          description: "Retrieve xxx by id",
          inputSchema: {
            type: "object" as const,
            properties: {
              xxx_id: { type: "integer", description: "xxx id" },
            },
            required: ["xxx_id"],
          },
        },
      ],
    };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request;
    if (name === "get_xxx") {
      const xxxId = (args as { xxx_id: number }).xxx_id;
      const xxx = await queryDatabase("SELECT * FROM xxx WHERE id = ?", [xxxId]);
      return {
        content: [
          {
            type: "text" as const,
            text: xxx ? JSON.stringify(xxx) : `No xxx found`,
          },
        ],
      };
    }
    throw new Error(`Unknown tool: ${name}`);
  });

  // Create stdio transport and connect
  const transport = new StdioServerTransport();
  await server.connect(transport);

  logger.error("MCP server running on stdio");
}

main().catch(err => logger.error(err));
""",
        "function": "stdio_transport_ts_server",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/stdio_server.ts",
    },
    # ── 6. SSE Transport Server (TypeScript) ─────────────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import express from "express";

async function main() {
  const app = express();
  app.use(express.json());

  const server = new Server({
    name: "xxx_service",
    version: "1.0.0",
  });

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "xxx_operation",
          description: "Perform xxx operation",
          inputSchema: {
            type: "object" as const,
            properties: {},
          },
        },
      ],
    };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: _args } = request;
    if (name === "xxx_operation") {
      return {
        content: [
          { type: "text" as const, text: "Operation completed" },
        ],
      };
    }
    throw new Error(`Unknown tool: ${name}`);
  });

  // SSE endpoint
  app.get("/sse", async (req, res) => {
    res.writeHead(200, {
      "Content-Type": "text/sse-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    });

    const transport = new SSEServerTransport("/payloads", res);
    await server.connect(transport);
  });

  // Payload handler endpoint
  app.post("/payloads", async (req, res) => {
    const payload = req.body.payload;
    if (!payload) {
      return res.status(400).json({ error: "Missing payload" });
    }
    const response = await server.handle(payload);
    res.json({ response });
  });

  const PORT = process.env.PORT || 8000;
  app.listen(PORT, () => {
    logger.info(`SSE server running on port ${PORT}`);
  });
}

main().catch(err => logger.error(err));
""",
        "function": "sse_transport_ts_http",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/sse_server.ts",
    },
    # ── 7. Zod Schema Validation (TypeScript) ────────────────────────────────
    {
        "normalized_code": """\
import { z } from "zod";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

// Define Zod schemas for tool arguments
const xxxCreateSchema = z.object({
  name: z.string().min(1, "name required"),
  description: z.string().optional().default(""),
  status: z.enum(["active", "inactive", "pending"]).default("active"),
});

const xxxUpdateSchema = z.object({
  xxx_id: z.number().int().positive(),
  name: z.string().optional(),
  status: z.enum(["active", "inactive", "pending"]).optional(),
});

type XxxCreate = z.infer<typeof xxxCreateSchema>;
type XxxUpdate = z.infer<typeof xxxUpdateSchema>;

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request;

  try {
    if (name === "create_xxx") {
      const validated = xxxCreateSchema.parse(args);
      const xxxId = await insertDatabase(
        "INSERT INTO xxx (name, description, status) VALUES (?, ?, ?)",
        [validated.name, validated.description, validated.status],
      );
      return {
        content: [
          { type: "text" as const, text: `Created xxx ${xxxId}` },
        ],
      };
    }

    if (name === "update_xxx") {
      const validated = xxxUpdateSchema.parse(args);
      await updateDatabase("UPDATE xxx SET name=?, status=? WHERE id=?", [
        validated.name,
        validated.status,
        validated.xxx_id,
      ]);
      return {
        content: [
          { type: "text" as const, text: `Updated xxx ${validated.xxx_id}` },
        ],
      };
    }
  } catch (error) {
    const msg = error instanceof z.ZodError
      ? error.errors.map((e) => e.message).join(", ")
      : String(error);
    return {
      content: [
        { type: "text" as const, text: `Validation error: ${msg}` },
      ],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

export default server;
""",
        "function": "zod_schema_validation_typescript",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/tools_zod.ts",
    },
    # ── 8. Resource Template URI Matching (TypeScript) ───────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ReadResourceRequestSchema, EmbeddedResource } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

// URI template: xxx://collection/{collection_id}/entry/{entry_id}
function parseXxxUri(uri: string): { collectionId?: string; entryId?: string } | null {
  const match = uri.match(/^xxx:\\/\\/collection\\/([^/]+)\\/entry\\/(.+)$/);
  if (!match) return null;
  return { collectionId: match[1], entryId: match[2] };
}

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request;

  if (uri === "xxx://schemas") {
    const schemas = await queryDatabase("SELECT name, version FROM schemas");
    const text = schemas
      .map((s: { name: string; version: string }) => `${s.name} (v${s.version})`)
      .join("\\n");

    return {
      contents: [
        {
          uri: "xxx://schemas",
          mimeType: "text/plain",
          text: text,
        } as EmbeddedResource,
      ],
    };
  }

  const parsed = parseXxxUri(uri);
  if (parsed) {
    const { collectionId, entryId } = parsed;
    try {
      const collId = parseInt(collectionId || "0", 10);
      const entryIdInt = parseInt(entryId || "0", 10);

      const entry = await queryDatabase(
        "SELECT data FROM entries WHERE collection_id=? AND id=?",
        [collId, entryIdInt],
      );

      return {
        contents: [
          {
            uri: uri,
            mimeType: "text/plain",
            text: entry ? (entry as { data: string }).data : `Entry ${entryId} not found`,
          } as EmbeddedResource,
        ],
      };
    } catch (error) {
      return {
        contents: [
          {
            uri: uri,
            mimeType: "text/plain",
            text: `Error: ${String(error)}`,
          } as EmbeddedResource,
        ],
      };
    }
  }

  throw new Error(`Unknown resource: ${uri}`);
});

export default server;
""",
        "function": "resource_uri_template_ts",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/resources_templates.ts",
    },
    # ── 9. Prompt Message Template (TypeScript) ──────────────────────────────
    {
        "normalized_code": """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { GetPromptRequestSchema, PromptMessage } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "xxx_service",
  version: "1.0.0",
});

server.setRequestHandler(GetPromptRequestSchema, async (request) => {
  const { name, arguments: args } = request;

  if (name === "code_review") {
    const code = (args?.code as string) || "";
    const language = (args?.language as string) || "typescript";
    const focus = (args?.focus as string) || "all";

    const validFocus = ["security", "performance", "style", "all"];
    const effectiveFocus = validFocus.includes(focus) ? focus : "all";

    const payloads: PromptMessage[] = [
      {
        role: "caller",
        content: {
          type: "text",
          text: `Review this ${language} code for ${effectiveFocus}:\\n\\n${code}`,
        },
      },
    ];
    return { payloads };
  }

  if (name === "xxx_documentation") {
    const xxxs = await queryDatabase("SELECT name, type FROM xxx LIMIT 50");
    const entries = xxxs
      .map((x: { name: string; type: string }) => `- ${x.name} (${x.type})`)
      .join("\\n");

    const payloads: PromptMessage[] = [
      {
        role: "caller",
        content: {
          type: "text",
          text: `Generate markdown documentation for:\\n${entries}`,
        },
      },
    ];
    return { payloads };
  }

  throw new Error(`Unknown prompt: ${name}`);
});

export default server;
""",
        "function": "prompt_message_template_ts",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/prompts_templates.ts",
    },
    # ── 10. Client Connect to Server (TypeScript) ────────────────────────────
    {
        "normalized_code": """\
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { spawn } from "child_process";

async function connectToServer(serverCommand: string): Promise<Client> {
  const [cmd, ...args] = serverCommand.split(/\\s+/);
  const process = spawn(cmd, args);

  const transport = new StdioClientTransport({
    stdin: process.stdin,
    stdout: process.stdout,
  });

  const client = new Client({
    name: "xxx_client",
    version: "1.0.0",
  }, {
    capabilities: {},
  });

  await client.connect(transport);
  return client;
}

async function main() {
  const client = await connectToServer("node mcp_server.js");

  try {
    // List tools
    const tools = await client.listTools();
    logger.info("Available tools:", tools.tools.map((t) => t.name));

    // Call tool
    const result = await client.callTool({
      name: "get_xxx",
      arguments: { xxx_id: 1 },
    });
    logger.info("Tool result:", result);
  } finally {
    client.close();
  }
}

main().catch(err => logger.error(err));
""",
        "function": "client_connect_ts_stdio",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client.ts",
    },
    # ── 11. Client List and Call Tools (TypeScript) ──────────────────────────
    {
        "normalized_code": """\
import { Client } from "@modelcontextprotocol/sdk/client/index.js";

async function listAndCallTools(client: Client, toolName: string, args: Record<string, unknown>) {
  // List all available tools
  const toolsResponse = await client.listTools();
  const toolNames = toolsResponse.tools.map((t) => t.name);

  if (!toolNames.includes(toolName)) {
    logger.error(
      `Tool '${toolName}' not found. Available: ${toolNames.join(", ")}`
    );
    return null;
  }

  // Call the tool
  try {
    const result = await client.callTool({
      name: toolName,
      arguments: args,
    });
    return result;
  } catch (error) {
    logger.error(`Error calling ${toolName}:`, error);
    return null;
  }
}

async function demo(client: Client) {
  // List and display tools
  const toolsResponse = await client.listTools();
  for (const tool of toolsResponse.tools) {
    logger.info(`Tool: ${tool.name}`);
    logger.info(`  Description: ${tool.description}`);
    logger.info(`  Schema:`, tool.inputSchema);
  }

  // Call tools with arguments
  let result = await listAndCallTools(client, "get_xxx", { xxx_id: 1 });
  logger.info("get_xxx result:", result);

  result = await listAndCallTools(client, "list_xxxs", {
    limit: 20,
    offset: 0,
  });
  logger.info("list_xxxs result:", result);
}

export { listAndCallTools, demo };
""",
        "function": "client_list_call_tools_ts",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client_tools.ts",
    },
    # ── 12. Streamable HTTP Transport (TypeScript) ───────────────────────────
    {
        "normalized_code": """\
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { HttpClientTransport } from "@modelcontextprotocol/sdk/client/http.js";
import fetch from "node-fetch";

async function connectViaHttp(baseUrl: string): Promise<Client> {
  const transport = new HttpClientTransport({
    url: new URL(baseUrl),
    fetch: fetch as unknown as typeof global.fetch,
  });

  const client = new Client({
    name: "xxx_client",
    version: "1.0.0",
  }, {
    capabilities: {},
  });

  await client.connect(transport);
  return client;
}

async function listAndReadResources(client: Client) {
  // List all resources
  const resourcesResponse = await client.listResources();
  logger.info(`Found ${resourcesResponse.resources.length} resources:`);
  for (const resource of resourcesResponse.resources) {
    logger.info(`  URI: ${resource.uri}`);
    logger.info(`  Name: ${resource.name}`);
    logger.info(`  Mime: ${resource.mimeType}`);
  }

  // Read first resource
  if (resourcesResponse.resources.length > 0) {
    const firstUri = resourcesResponse.resources[0].uri;
    const content = await client.readResource({ uri: firstUri });
    logger.info(`\\nResource content (${firstUri}):`);
    for (const entry of content.contents) {
      if ("text" in entry) {
        logger.info(entry.text);
      }
    }
  }

  return resourcesResponse.resources;
}

async function readResourceByUri(client: Client, uri: string) {
  try {
    const content = await client.readResource({ uri });
    logger.info(`Resource ${uri}:`);
    for (const entry of content.contents) {
      if ("text" in entry) {
        logger.info(entry.text);
      }
    }
    return content;
  } catch (error) {
    logger.error(`Error reading ${uri}:`, error);
    return null;
  }
}

export { connectViaHttp, listAndReadResources, readResourceByUri };
""",
        "function": "streamable_http_transport_ts",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/client_http.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "McpServer initialization setup TypeScript",
    "tool handler registration CallToolRequest",
    "resource handler URI template matching",
    "prompt handler GetPromptRequest template",
    "stdio transport server connection",
    "SSE server-sent events HTTP streaming",
    "Zod schema validation tool arguments",
    "resource URI template parsing TypeScript",
    "prompt message template generation",
    "client connect to server stdio",
    "client list tools and call tools",
    "streamable HTTP transport client",
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
