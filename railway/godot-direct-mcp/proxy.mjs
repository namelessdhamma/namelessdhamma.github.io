import http from "node:http";

const token = process.env.ND_GODOT_MCP_PATH_TOKEN;
if (!token) throw new Error("ND_GODOT_MCP_PATH_TOKEN is required");

const listenPort = Number(process.env.PORT || 5678);
const internalPort = Number(process.env.ND_GODOT_INTERNAL_MCP_PORT || 8001);
const publicMcpPath = `/mcp/${token}`;

function boundedMs(name, fallback, min, max) {
  const n = Number(process.env[name] || fallback);
  return Math.max(min, Math.min(max, Number.isFinite(n) ? n : fallback));
}

// All normal upstream Godot tool defaults finish inside 5 minutes. Keep an outer
// 10-minute inactivity boundary for the direct MCP route; intentionally longer work
// belongs on the qualified GitHub Actions DURABLE_ASYNC contour instead of foreground HTTP.
const mcpTimeoutMs = boundedMs("ND_GODOT_PROXY_TIMEOUT_MS", 600_000, 5_000, 3_660_000);
const healthTimeoutMs = boundedMs("ND_GODOT_HEALTH_TIMEOUT_MS", 5_000, 1_000, 30_000);

function proxy(req, res, targetPath) {
  const headers = { ...req.headers, host: `127.0.0.1:${internalPort}` };
  let timedOut = false;
  const upstream = http.request({
    hostname: "127.0.0.1",
    port: internalPort,
    method: req.method,
    path: targetPath,
    headers,
  }, upstreamRes => {
    res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
    upstreamRes.pipe(res);
  });
  const timeoutMs = targetPath === "/healthz" ? healthTimeoutMs : mcpTimeoutMs;
  upstream.setTimeout(timeoutMs, () => {
    timedOut = true;
    if (!res.headersSent) {
      res.writeHead(504, { "content-type": "text/plain; charset=utf-8" });
    }
    if (!res.writableEnded) res.end("upstream timeout");
    upstream.destroy();
    process.stderr.write(`ND_GODOT_PROXY_UPSTREAM_TIMEOUT ms=${timeoutMs} path=${targetPath}\n`);
  });
  upstream.on("error", err => {
    if (timedOut) return;
    if (!res.headersSent) {
      res.writeHead(503, { "content-type": "text/plain; charset=utf-8" });
    }
    if (!res.writableEnded) res.end("upstream unavailable");
    process.stderr.write(`ND_GODOT_PROXY_UPSTREAM_ERROR ${err.code || err.message}\n`);
  });
  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  let pathname;
  try {
    pathname = new URL(req.url || "/", "http://localhost").pathname;
  } catch {
    res.writeHead(400).end("bad request");
    return;
  }

  if (pathname === "/healthz" && req.method === "GET") {
    proxy(req, res, "/healthz");
    return;
  }

  if (pathname === publicMcpPath) {
    proxy(req, res, "/mcp");
    return;
  }

  res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  res.end("not found");
});

server.listen(listenPort, "0.0.0.0", () => {
  process.stdout.write(`ND_GODOT_PROXY_READY port=${listenPort}\n`);
});