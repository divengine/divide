// An MCP client on the official TypeScript SDK, against divide's HTTP server:
// node ts_client.mjs URL [TOKEN]  ->  one JSON line with what it saw.
// NODE_PATH (or a node_modules beside it) must hold @modelcontextprotocol/sdk.
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(path.join(process.env.MCP_TS_SDK || process.cwd(), "node_modules", "x.js"));
const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const { StreamableHTTPClientTransport } = require("@modelcontextprotocol/sdk/client/streamableHttp.js");

const [url, token] = process.argv.slice(2);
const headers = token ? { Authorization: `Bearer ${token}` } : {};
const transport = new StreamableHTTPClientTransport(new URL(url), { requestInit: { headers } });
const client = new Client({ name: "ts-sdk-check", version: "1.0.0" });
await client.connect(transport);
const tools = await client.listTools();
const info = await client.callTool({ name: "project_info", arguments: {} });
const bad = await client.callTool({ name: "div_check", arguments: { template: "../outside.tpl" } });
const out = {
  protocolVersion: transport.protocolVersion ?? null,
  sessionId: transport.sessionId ?? null,
  server: client.getServerVersion(),
  tools: tools.tools.map((t) => t.name),
  project: info.structuredContent?.project?.name ?? null,
  infoError: info.isError ?? false,
  badError: bad.isError ?? false,
  badText: bad.content?.[0]?.text ?? null,
};
await client.close();
console.log(JSON.stringify(out));
