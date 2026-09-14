import json
import os
import subprocess
import sys
import time
import socket
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError

# ND Internet Access Mesh v1 / Browserless Front Proxy successor v6.
# Additive wrapper around the pinned, already-qualified Browserless front proxy v5.
# No new service is required: intended to run inside the existing nd-qstash-control-v2 host.

PORT = int(os.environ.get("PORT", "3000"))
INNER_PORT = int(os.environ.get("ND_INNER_GATEWAY_PORT", "3001"))
MESH_ROUTE_TOKEN = os.environ.get("ND_INTERNET_MESH_ROUTE_TOKEN", "").strip()
MESH_PATH = ("/internet/mcp/" + MESH_ROUTE_TOKEN) if MESH_ROUTE_TOKEN else ""

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "").strip()
KERNEL_TOKEN = os.environ.get("KERNEL_API_KEY", "").strip()
TINYFISH_TOKEN = os.environ.get("TINYFISH_API_KEY", "").strip()
if BROWSERLESS_TOKEN.lower().startswith("bearer "):
    BROWSERLESS_TOKEN = BROWSERLESS_TOKEN[7:].strip()
if KERNEL_TOKEN.lower().startswith("bearer "):
    KERNEL_TOKEN = KERNEL_TOKEN[7:].strip()
if TINYFISH_TOKEN.lower().startswith("bearer "):
    TINYFISH_TOKEN = TINYFISH_TOKEN[7:].strip()

# Exact parent pin, recovered from GitHub history 2026-09-14.
PARENT_SHA = "0969b31ca70b04d37d9bc262ef33d51ad03bb37b"
PARENT_URL = os.environ.get(
    "ND_INTERNET_MESH_PARENT_URL",
    "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/" + PARENT_SHA + "/tmp/nd_gateway_browserless_frontproxy_v5.py",
)
INNER_URL = "http://127.0.0.1:%d" % INNER_PORT

PROVIDERS = {
    "browserless": {
        "url": os.environ.get("ND_BROWSERLESS_MCP_URL", "https://mcp.browserless.io/mcp"),
        "headers": lambda: {
            "Authorization": "Bearer " + BROWSERLESS_TOKEN,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "ND-Internet-Mesh/1.0",
        },
        "configured": lambda: bool(BROWSERLESS_TOKEN),
        "allow": {
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
        },
    },
    "kernel": {
        "url": os.environ.get("ND_KERNEL_MCP_URL", "https://mcp.onkernel.com/mcp"),
        "headers": lambda: {
            "Authorization": "Bearer " + KERNEL_TOKEN,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "ND-Internet-Mesh/1.0",
        },
        "configured": lambda: bool(KERNEL_TOKEN),
        # Bounded browser/internet surface only. Account billing, API-key mutation,
        # credentials, payments and vault management deliberately stay out.
        "allow": {
            "get_connection_context",
            "search_docs",
            "manage_profiles",
            "manage_browsers",
            "browser_curl",
            "computer_action",
            "execute_playwright_code",
            "webmcp",
            "manage_replays",
        },
    },
    "tinyfish": {
        "url": os.environ.get("ND_TINYFISH_MCP_URL", "https://agent.tinyfish.ai/mcp"),
        "headers": lambda: {
            "X-API-Key": TINYFISH_TOKEN,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "ND-Internet-Mesh/1.0",
            "X-TF-Request-Origin": "nd-internet-mesh",
            "X-TF-Client-Name": "nd-internet-mesh",
            "X-TF-Client-Version": "1.0.0",
        },
        "configured": lambda: bool(TINYFISH_TOKEN),
        "allow": {
            "search",
            "fetch_content",
            "run_web_automation",
            "wait_for_run",
            "get_run",
            "list_runs",
            "cancel_run",
            "get_wallet",
        },
    },
}

# Process-local dedupe: a last line of defence for operations that can create
# paid runs or browser sessions. Durable replay protection remains the caller's
# responsibility; ambiguous/lost responses are never auto-retried here.
_DEDUPE = {}
_DEDUPE_TTL = 900
SENSITIVE_STARTS = {
    ("tinyfish", "run_web_automation"),
    ("kernel", "manage_browsers"),
}


def _provider_tokens():
    return [x for x in (BROWSERLESS_TOKEN, KERNEL_TOKEN, TINYFISH_TOKEN, MESH_ROUTE_TOKEN) if x]


def clean_error(value):
    s = str(value)
    for token in _provider_tokens():
        s = s.replace(token, "[REDACTED]")
        try:
            s = s.replace(urllib.parse.quote(token, safe=""), "[REDACTED]")
        except Exception:
            pass
    return s[:2000]


def parse_mcp_response(raw, content_type=""):
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in (content_type or "").lower() or text.lstrip().startswith("data:"):
        messages = []
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    messages.append(json.loads(payload))
                except Exception:
                    continue
        if not messages:
            raise RuntimeError("upstream_mcp_returned_no_parsable_sse_data")
        return messages[-1]
    try:
        return json.loads(text)
    except Exception:
        raise RuntimeError("upstream_mcp_returned_non_json_response")


def post_mcp(provider, payload, session_id=None, timeout=100):
    cfg = PROVIDERS[provider]
    if not cfg["configured"]():
        raise RuntimeError(provider + "_not_configured")
    headers = cfg["headers"]()
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    headers["MCP-Protocol-Version"] = "2025-06-18"
    req = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, dict(response.headers.items()), raw
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise RuntimeError("%s MCP HTTP %s: %s" % (provider, exc.code, clean_error(body)))
    except URLError as exc:
        raise RuntimeError("%s MCP network error: %s" % (provider, clean_error(exc)))


def init_upstream(provider):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ND Internet Mesh", "version": "1.0.0"},
        },
    }
    status, headers, raw = post_mcp(provider, payload, timeout=45)
    if status != 200:
        raise RuntimeError(provider + " initialize failed")
    msg = parse_mcp_response(raw, headers.get("Content-Type", ""))
    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    if session_id:
        # Notification response can be 200/202/204 depending on server implementation.
        post_mcp(
            provider,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            session_id,
            timeout=30,
        )
    return session_id, msg


def upstream_request(provider, method, params=None, timeout=100):
    session_id, init_msg = init_upstream(provider)
    payload = {"jsonrpc": "2.0", "id": 2, "method": method}
    if params is not None:
        payload["params"] = params
    status, headers, raw = post_mcp(provider, payload, session_id, timeout=timeout)
    if status != 200:
        raise RuntimeError(provider + " " + method + " failed")
    return init_msg, parse_mcp_response(raw, headers.get("Content-Type", ""))


def filtered_tools(provider):
    init_msg, msg = upstream_request(provider, "tools/list", {}, timeout=45)
    result = msg.get("result") or {}
    tools = result.get("tools") or []
    allow = PROVIDERS[provider]["allow"]
    filtered = [x for x in tools if isinstance(x, dict) and x.get("name") in allow]
    return {
        "ok": True,
        "provider": provider,
        "serverInfo": ((init_msg.get("result") or {}).get("serverInfo") or {}),
        "tools": filtered,
        "count": len(filtered),
    }


def _dedupe_get(key):
    if not key:
        return None
    now = time.time()
    old = [k for k, v in _DEDUPE.items() if now - v[0] > _DEDUPE_TTL]
    for k in old:
        _DEDUPE.pop(k, None)
    item = _DEDUPE.get(key)
    return item[1] if item else None


def _dedupe_put(key, value):
    if key:
        _DEDUPE[key] = (time.time(), value)


def provider_call(provider, tool, arguments=None, request_key=None):
    if provider not in PROVIDERS:
        raise RuntimeError("unknown_provider")
    if tool not in PROVIDERS[provider]["allow"]:
        raise RuntimeError("tool_not_allowlisted")
    if not isinstance(arguments or {}, dict):
        raise RuntimeError("arguments_must_be_an_object")

    # Only use dedupe where a duplicate could create a material/cost side effect.
    sensitive = (provider, tool) in SENSITIVE_STARTS
    if provider == "kernel" and tool == "manage_browsers":
        sensitive = str((arguments or {}).get("action") or "") == "create"
    if sensitive and request_key:
        cached = _dedupe_get(provider + ":" + tool + ":" + request_key)
        if cached is not None:
            return dict(cached, deduplicated=True)

    init_msg, msg = upstream_request(
        provider,
        "tools/call",
        {"name": tool, "arguments": arguments or {}},
        timeout=120,
    )
    out = {
        "ok": True,
        "provider": provider,
        "tool": tool,
        "serverInfo": ((init_msg.get("result") or {}).get("serverInfo") or {}),
        "response": msg,
        "retry_policy": "NO_AUTOMATIC_RETRY_ON_AMBIGUOUS_OR_LOST_RESPONSE" if sensitive else "BOUNDED_CALLER_RETRY_AFTER_STATUS_CHECK",
    }
    if sensitive and request_key:
        _dedupe_put(provider + ":" + tool + ":" + request_key, out)
    return out


def mesh_status():
    return {
        "ok": True,
        "service": "ND Internet Access Mesh",
        "version": "1.0.0-qualification",
        "parent": {"browserless_frontproxy": "v5", "sha": PARENT_SHA},
        "route": "native_provider_mcp_via_existing_nd_host",
        "providers": {
            name: {
                "configured": bool(cfg["configured"]()),
                "upstream": cfg["url"],
                "allowlisted_tools": len(cfg["allow"]),
            }
            for name, cfg in PROVIDERS.items()
        },
        "route_token_configured": bool(MESH_ROUTE_TOKEN),
        "secrets_returned": False,
        "automatic_retry_for_sensitive_start": False,
    }


def mcp_tools():
    return [
        {
            "name": "internet_status",
            "description": "Return redacted ND Internet Access Mesh route/configuration status for Browserless, Kernel and TinyFish.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "internet_provider_tools",
            "description": "Discover the current allow-listed tools and live schemas exposed by one upstream provider MCP.",
            "inputSchema": {
                "type": "object",
                "properties": {"provider": {"type": "string", "enum": ["browserless", "kernel", "tinyfish"]}},
                "required": ["provider"],
                "additionalProperties": False,
            },
        },
        {
            "name": "internet_call",
            "description": "Call one allow-listed provider tool through the independent ND relay. For paid/run-start or browser-create operations provide request_key and never blindly retry after an ambiguous response.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["browserless", "kernel", "tinyfish"]},
                    "tool": {"type": "string", "minLength": 1, "maxLength": 120},
                    "arguments": {"type": "object", "additionalProperties": True},
                    "request_key": {"type": "string", "minLength": 1, "maxLength": 160},
                },
                "required": ["provider", "tool"],
                "additionalProperties": False,
            },
        },
    ]


def mcp_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def mcp_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": clean_error(message)}}


def tool_payload(result, is_error=False):
    text = json.dumps(result, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "structuredContent": result, "isError": bool(is_error)}


def mcp_dispatch(req):
    if not isinstance(req, dict):
        return 400, mcp_error(None, -32600, "Invalid Request")
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion") or "2025-06-18"
        return 200, mcp_result(
            rid,
            {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ND Internet Access Mesh", "version": "1.0.0-qualification"},
                "instructions": (
                    "Independent failover surface for Browserless, Kernel and TinyFish. "
                    "Discover provider schemas before calls. No blind retries for TinyFish run_web_automation "
                    "or Kernel browser creation after ambiguous/lost responses."
                ),
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return 202, None
    if method == "ping":
        return 200, mcp_result(rid, {})
    if method == "tools/list":
        return 200, mcp_result(rid, {"tools": mcp_tools()})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "internet_status":
                result = mesh_status()
            elif name == "internet_provider_tools":
                provider = str(args.get("provider") or "").strip().lower()
                if provider not in PROVIDERS:
                    raise RuntimeError("unknown_provider")
                result = filtered_tools(provider)
            elif name == "internet_call":
                provider = str(args.get("provider") or "").strip().lower()
                tool = str(args.get("tool") or "").strip()
                result = provider_call(provider, tool, args.get("arguments") or {}, args.get("request_key"))
            else:
                raise RuntimeError("unknown_mesh_tool")
            return 200, mcp_result(rid, tool_payload(result, False))
        except Exception as exc:
            err = {"ok": False, "error": clean_error(exc)}
            return 200, mcp_result(rid, tool_payload(err, True))
    return 200, mcp_error(rid, -32601, "Method not found")


# Start exact pinned Browserless v5 as the inner process so all existing routes survive unchanged.
inner_path = "/tmp/nd_browserless_frontproxy_v5_parent.py"
parent_src = urllib.request.urlopen(PARENT_URL, timeout=30).read()
open(inner_path, "wb").write(parent_src)
inner_env = dict(os.environ)
inner_env["PORT"] = str(INNER_PORT)
# Parent itself uses an inner gateway; push its own child farther inward.
inner_env["ND_INNER_GATEWAY_PORT"] = str(INNER_PORT + 1)
child = subprocess.Popen([sys.executable, "-u", inner_path], env=inner_env)

# Bound startup gate: do not advertise the outer route until the preserved parent
# has actually bound its port. This prevents a cold-deploy race from looking like
# a provider failure.
def _wait_for_inner(port, seconds=15):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except Exception as exc:
            last = exc
            time.sleep(0.1)
    raise RuntimeError("inner_gateway_start_timeout: " + clean_error(last))

_wait_for_inner(INNER_PORT)


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def forward(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(n) if n else None
        url = INNER_URL + self.path
        headers = {}
        for k, v in self.headers.items():
            if k.lower() in ("host", "connection", "content-length", "transfer-encoding"):
                continue
            headers[k] = v
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                raw = response.read()
                self.send_response(response.status)
                for k, v in response.headers.items():
                    if k.lower() in ("connection", "transfer-encoding", "content-length"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        except HTTPError as exc:
            raw = exc.read()
            self.send_response(exc.code)
            for k, v in exc.headers.items():
                if k.lower() in ("connection", "transfer-encoding", "content-length"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception as exc:
            self.send_json(502, {"error": "inner_gateway_unavailable", "detail": clean_error(exc)})

    def handle_mesh_mcp(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            status, body = mcp_dispatch(req)
            if body is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_json(status, body)
        except Exception as exc:
            self.send_json(400, mcp_error(None, -32700, clean_error(exc)))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if MESH_ROUTE_TOKEN and path == "/internet/status/" + MESH_ROUTE_TOKEN:
            self.send_json(200, mesh_status())
            return
        self.forward()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if MESH_ROUTE_TOKEN and path == MESH_PATH:
            self.handle_mesh_mcp()
            return
        self.forward()


print(
    "ND_INTERNET_MESH_V1_START "
    + json.dumps(
        {
            "port": PORT,
            "inner_port": INNER_PORT,
            "parent_sha": PARENT_SHA,
            "mesh_path_configured": bool(MESH_ROUTE_TOKEN),
            "browserless_configured": bool(BROWSERLESS_TOKEN),
            "kernel_configured": bool(KERNEL_TOKEN),
            "tinyfish_configured": bool(TINYFISH_TOKEN),
        }
    ),
    flush=True,
)
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
