import http from "node:http";

const token = process.env.ND_GODOT_MCP_PATH_TOKEN;
if (!token) throw new Error("ND_GODOT_MCP_PATH_TOKEN is required");

const listenPort = Number(process.env.PORT || 5678);
const internalPort = Number(process.env.ND_GODOT_INTERNAL_MCP_PORT || 8001);
const publicMcpPath = `/mcp/${token}`;

function proxy(req, res, targetPath) {
  const headers = { ...req.headers, host: `127.0.0.1:${internalPort}` };
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
  upstream.on("error", err => {
    if (!res.headersSent) {
      res.writeHead(503, { "content-type": "text/plain; charset=utf-8" });
    }
    res.end("upstream unavailable");
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
