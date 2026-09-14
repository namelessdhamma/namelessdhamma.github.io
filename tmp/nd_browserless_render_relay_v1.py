import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "").strip()
RELAY_TOKEN = os.environ.get("ND_BROWSERLESS_RENDER_RELAY_TOKEN", "").strip()
MCP_URL = "https://mcp.browserless.io/mcp"

ALLOWED_TOOLS = {
    "browserless_export",
    "browserless_skill",
    "browserless_agent",
    "browserless_search",
    "browserless_performance",
    "browserless_account",
    "browserless_usage",
    "browserless_sessions",
    "browserless_logs",
    "browserless_smartscraper",
    "browserless_function",
    "browserless_map",
    "browserless_crawl",
    "browserless_profiles",
}

def scrub(text):
    s = str(text)
    if BROWSERLESS_TOKEN:
        s = s.replace(BROWSERLESS_TOKEN, "[REDACTED]")
    if RELAY_TOKEN:
        s = s.replace(RELAY_TOKEN, "[REDACTED]")
    return s[:4000]

def parse_sse(raw):
    text = raw.decode("utf-8", "replace")
    payloads = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                payloads.append(json.loads(line[6:]))
            except Exception:
                pass
    if not payloads:
        raise RuntimeError("Browserless MCP returned no parsable SSE data")
    return payloads[-1]

def post_mcp(payload, session_id=None):
    if not BROWSERLESS_TOKEN:
        raise RuntimeError("BROWSERLESS_API_TOKEN is not configured")
    headers = {
        "Authorization": "Bearer " + BROWSERLESS_TOKEN,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "ND-True-Doctor-Render-Relay/1.0",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
        headers["MCP-Protocol-Version"] = "2025-06-18"
    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return r.status, dict(r.headers.items()), raw
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError("Browserless MCP HTTP %s: %s" % (e.code, scrub(body)))

def call_browserless_tool(tool, arguments):
    if tool not in ALLOWED_TOOLS:
        raise RuntimeError("tool is not allowlisted")
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ND True Doctor Render Relay", "version": "1.0"},
        },
    }
    status, headers, raw = post_mcp(init)
    if status != 200:
        raise RuntimeError("initialize failed")
    init_msg = parse_sse(raw)
    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    if not session_id:
        raise RuntimeError("Browserless MCP did not return a session id")

    post_mcp(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        session_id,
    )

    status, _, raw = post_mcp(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        },
        session_id,
    )
    if status != 200:
        raise RuntimeError("tools/call failed")
    msg = parse_sse(raw)
    return {
        "ok": True,
        "serverInfo": ((init_msg.get("result") or {}).get("serverInfo") or {}),
        "tool": tool,
        "response": msg,
    }

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        if not RELAY_TOKEN:
            return False
        path = self.path.split("?", 1)[0]
        return path.endswith("/" + RELAY_TOKEN)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_json(200, {
                "ok": True,
                "service": "ND Browserless Render Relay",
                "version": "1.0.0",
                "browserless_configured": bool(BROWSERLESS_TOKEN),
                "relay_configured": bool(RELAY_TOKEN),
            })
            return
        expected = "/browserless/profiles/" + RELAY_TOKEN if RELAY_TOKEN else ""
        if expected and path == expected:
            try:
                out = call_browserless_tool(
                    "browserless_profiles",
                    {"limit": 20, "offset": 0, "_prompt": "ND Doctor Render relay verification: list Browserless profiles only; no mutation."},
                )
                self.send_json(200, out)
            except Exception as e:
                self.send_json(502, {"ok": False, "error": scrub(e)})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        expected = "/browserless/call/" + RELAY_TOKEN if RELAY_TOKEN else ""
        if not expected or path != expected:
            self.send_json(404, {"error": "not_found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            tool = str(body.get("tool") or "")
            args = body.get("arguments") or {}
            if not isinstance(args, dict):
                raise RuntimeError("arguments must be an object")
            out = call_browserless_tool(tool, args)
            self.send_json(200, out)
        except Exception as e:
            self.send_json(400, {"ok": False, "error": scrub(e)})

print(json.dumps({
    "service": "ND Browserless Render Relay",
    "version": "1.0.0",
    "port": PORT,
    "browserless_configured": bool(BROWSERLESS_TOKEN),
    "relay_configured": bool(RELAY_TOKEN),
}), flush=True)

ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
