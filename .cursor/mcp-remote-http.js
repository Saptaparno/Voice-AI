#!/usr/bin/env node
/**
 * mcp-remote-http
 * Forces Streamable HTTP transport (POST-only) to a remote MCP server.
 * Wraps @modelcontextprotocol/sdk to bypass mcp-remote's SSE fallback.
 *
 * Usage: node mcp-remote-http.js <server-url> [port]
 *
 * Examples:
 *   node mcp-remote-http.js https://plivo.com/docs/mcp 3000
 *   node mcp-remote-http.js https://example.com/mcp 8080
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { randomUUID } from "crypto";

const serverUrl = process.argv[2];
const port = parseInt(process.argv[3] || "3100", 10);

if (!serverUrl) {
  console.error("Usage: node mcp-remote-http.js <server-url> [port]");
  console.error("Example: node mcp-remote-http.js https://plivo.com/docs/mcp 3100");
  process.exit(1);
}

const sessionId = randomUUID();

const transport = new StreamableHTTPClientTransport(serverUrl, {
  sessionId,
  // Never fall back to SSE — strictly POST
  requestOptions: { signal: AbortSignal.timeout(10_000) },
});

const client = new Client(
  {
    name: "mcp-remote-http",
    version: "1.0.0",
  },
  {
    capabilities: { sampling: {} },
  }
);

async function main() {
  try {
    await client.connect(transport);
    console.error(`[mcp-remote-http] Connected to ${serverUrl} (session: ${sessionId})`);
    console.error(`[mcp-remote-http] Listening on http://localhost:${port} for Cursor MCP stdio bridge`);

    // Bridge: any incoming stdio messages → client
    process.on("message", async (msg) => {
      try {
        const parsed = JSON.parse(msg);
        await client.request(parsed.method, parsed.params, parsed.id);
      } catch (e) {
        console.error("[mcp-remote-http] Request error:", e.message);
      }
    });

    // Bridge: any client notifications → stdio
    client.on("notification", (method, params) => {
      process.send?.(JSON.stringify({ method, params }));
    });

    client.on("response", (response) => {
      process.send?.(JSON.stringify(response));
    });

    process.on("close", () => {
      client.close();
    });
  } catch (err) {
    console.error(`[mcp-remote-http] Connection failed: ${err.message}`);
    process.exit(1);
  }
}

main();
