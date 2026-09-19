from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional


PORT = int(os.environ.get("PORT", "3000"))
INNER_PORT = int(os.environ.get("ND_SUPERVISOR_INNER_PORT", "3977"))
PATH_TOKEN = (
    os.environ.get("ND_SUPERVISOR_DISPATCH_PATH_TOKEN", "").strip()
    or os.environ.get("ND_OPENAI_AGENTS_MCP_PATH_TOKEN", "").strip()
)
GITHUB_PAT = os.environ.get("ND_GITHUB_PAT", "").strip()
LEDGER_REPO = os.environ.get(
    "ND_SUPERVISOR_LEDGER_REPO", "namelessdhamma/nameless-dhamma-vault"
).strip()
LEDGER_BRANCH = os.environ.get("ND_SUPERVISOR_LEDGER_BRANCH", "main").strip()
LEDGER_PREFIX = os.environ.get(
    "ND_SUPERVISOR_LEDGER_PREFIX", ".nd-runtime/supervisor-dispatch/receipts"
).strip().strip("/")
LEDGER_MODE = os.environ.get("ND_SUPERVISOR_LEDGER_MODE", "github").strip().lower()
SOURCE_REPO = os.environ.get(
    "ND_SUPERVISOR_SOURCE_REPO", "namelessdhamma/namelessdhamma.github.io"
).strip()
SOURCE_REF = os.environ.get("ND_SUPERVISOR_SOURCE_REF", "main").strip()

# Exact production entry currently used by nd-qstash-control-v2.
UPSTREAM_ENTRY = os.environ.get(
    "ND_SUPERVISOR_UPSTREAM_ENTRY",
    "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/"
    "1a7f53b5f351942838c6ea2e14280308529cefd5/tmp/nd_remotion_mcp_front_v1.py",
).strip()
INNER_ENTRY_PATH = "/tmp/nd_supervisor_inner_entry.py"
MODULE_DIR = pathlib.Path("/tmp/nd-supervisor-dispatch-modules")

_SECRET_VALUES = [x for x in (PATH_TOKEN, GITHUB_PAT) if x]


def clean(value: Any) -> str:
    text = str(value)
    for secret in _SECRET_VALUES:
        text = text.replace(secret, "[REDACTED]")
    return text[:5000]


def _raw_url(path: str) -> str:
    owner, repo = SOURCE_REPO.split("/", 1)
    return (
        "https://raw.githubusercontent.com/"
        + urllib.parse.quote(owner, safe="")
        + "/"
        + urllib.parse.quote(repo, safe="")
        + "/"
        + urllib.parse.quote(SOURCE_REF, safe="")
        + "/"
        + path.lstrip("/")
    )


def _bootstrap_modules() -> None:
    """
    Production bootstrap only. CI imports this file without calling main(), so tests
    can inject local modules instead of reaching the network.
    """
    MODULE_DIR.mkdir(parents=True, exist_ok=True)
    for name in (
        "nd_supervisor_dispatch_v01.py",
        "nd_supervisor_dispatch_v02.py",
        "nd_supervisor_resolver_v01.py",
    ):
        urllib.request.urlretrieve(_raw_url("tmp/" + name), str(MODULE_DIR / name))
    if str(MODULE_DIR) not in sys.path:
        sys.path.insert(0, str(MODULE_DIR))


def _runtime():
    d2 = importlib.import_module("nd_supervisor_dispatch_v02")
    d1 = importlib.import_module("nd_supervisor_dispatch_v01")
    return d1, d2


class GitHubReceiptLedger:
    """
    Durable operational receipt store over an existing qualified GitHub control path.
    One logical dispatch key maps to one file. Updates use GitHub content SHA as CAS.
    """

    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        prefix: str = LEDGER_PREFIX,
        transport=None,
    ):
        if not token:
            raise RuntimeError("github_pat_missing")
        self.token = token
        self.repo = repo
        self.branch = branch
        self.prefix = prefix.strip("/")
        self.transport = transport or self._http

    @staticmethod
    def file_key(dispatch_key: str) -> str:
        return hashlib.sha256(dispatch_key.encode("utf-8")).hexdigest()

    def path_for(self, dispatch_key: str) -> str:
        return self.prefix + "/" + self.file_key(dispatch_key) + ".json"

    def _http(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None
    ) -> tuple[int, Dict[str, Any]]:
        url = (
            "https://api.github.com/repos/"
            + self.repo
            + "/contents/"
            + urllib.parse.quote(path, safe="/")
        )
        if method == "GET":
            url += "?ref=" + urllib.parse.quote(self.branch, safe="")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ND-Supervisor-Dispatch/0.4",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8", "replace")
                return response.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                obj = json.loads(raw or "{}")
            except Exception:
                obj = {"raw": clean(raw)}
            return exc.code, obj

    def get(self, dispatch_key: str) -> Optional[Dict[str, Any]]:
        status, obj = self.transport("GET", self.path_for(dispatch_key), None)
        if status == 404:
            return None
        if status != 200:
            raise RuntimeError("github_ledger_get_%s:%s" % (status, clean(obj)))
        try:
            raw = base64.b64decode(str(obj.get("content") or "").replace("\n", ""))
            receipt = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("github_ledger_decode_failed:" + clean(exc)) from exc
        if receipt.get("dispatch_key") != dispatch_key:
            raise RuntimeError("github_ledger_dispatch_key_mismatch")
        receipt["_github_content_sha"] = obj.get("sha")
        return receipt

    def put(self, dispatch_key: str, value: Dict[str, Any]) -> None:
        path = self.path_for(dispatch_key)
        prior = self.get(dispatch_key)
        record = dict(value)
        record.pop("_github_content_sha", None)
        record["dispatch_key"] = dispatch_key
        record["ledger_updated_at"] = int(time.time())
        content = base64.b64encode(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        ).decode("ascii")
        body: Dict[str, Any] = {
            "message": "supervisor dispatch receipt: " + self.file_key(dispatch_key)[:16],
            "content": content,
            "branch": self.branch,
        }
        if prior and prior.get("_github_content_sha"):
            body["sha"] = prior["_github_content_sha"]
        status, obj = self.transport("PUT", path, body)
        if status not in (200, 201):
            raise RuntimeError("github_ledger_put_%s:%s" % (status, clean(obj)))


class MemoryLedger:
    """Test/development ledger implementing the same get/put contract."""

    def __init__(self):
        self.rows: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.rows.get(key)
        return None if row is None else dict(row)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        self.rows[key] = dict(value)


def get_ledger():
    if LEDGER_MODE == "memory":
        return MemoryLedger()
    if LEDGER_MODE == "file":
        d1, _ = _runtime()
        return d1.JsonLedger(os.environ.get("ND_SUPERVISOR_LEDGER_FILE", "/tmp/nd-supervisor-ledger.json"))
    if LEDGER_MODE == "github":
        return GitHubReceiptLedger(GITHUB_PAT, LEDGER_REPO, LEDGER_BRANCH)
    raise RuntimeError("unsupported_ledger_mode:" + LEDGER_MODE)


def supervisor_tool_call(
    name: str,
    args: Dict[str, Any],
    *,
    ledger=None,
    provider=None,
) -> Dict[str, Any]:
    _, d2 = _runtime()
    ledger = ledger or get_ledger()

    if name == "supervisor_status":
        return {
            "ok": True,
            "service": "nd-supervisor-dispatch",
            "version": "0.4.0-prototype",
            "ledger_mode": LEDGER_MODE,
            "ledger_repo": LEDGER_REPO if LEDGER_MODE == "github" else None,
            "path_token_configured": bool(PATH_TOKEN),
            "source_ref": SOURCE_REF,
            "upstream_entry": UPSTREAM_ENTRY,
            "production_adoption": False,
        }

    if name == "supervisor_submit":
        assignment = args.get("assignment")
        supervisor = args.get("supervisor")
        if not isinstance(assignment, dict) or not isinstance(supervisor, dict):
            raise RuntimeError("assignment_and_supervisor_required")
        authority = supervisor.get("authority_evidence")
        if not isinstance(authority, dict):
            raise RuntimeError("authority_evidence_required")
        for field in ("registry_hash", "artifact_id", "artifact_hash", "exact_status"):
            if not str(authority.get(field) or "").strip():
                raise RuntimeError("authority_evidence_missing:" + field)
        return d2.submit_dispatch(
            assignment,
            supervisor,
            ledger=ledger,
            provider=provider,
            dispatch_key=args.get("dispatch_key"),
        )

    if name == "supervisor_result":
        key = str(args.get("dispatch_key") or "").strip()
        if not key:
            raise RuntimeError("dispatch_key_required")
        return d2.refresh_dispatch(key, ledger=ledger, provider=provider)

    if name == "supervisor_cancel":
        key = str(args.get("dispatch_key") or "").strip()
        if not key:
            raise RuntimeError("dispatch_key_required")
        return d2.cancel_dispatch(key, ledger=ledger, provider=provider)

    raise RuntimeError("unknown_tool:" + name)


TOOLS = [
    {
        "name": "supervisor_status",
        "description": "Check the generic ND supervisor dispatch bridge. No supervisor execution.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "supervisor_submit",
        "description": "Submit one authority-resolved ND supervisor assignment as a durable background run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "assignment": {"type": "object"},
                "supervisor": {"type": "object"},
                "dispatch_key": {"type": "string"},
            },
            "required": ["assignment", "supervisor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supervisor_result",
        "description": "Retrieve and verify the current result/status of a previously submitted supervisor dispatch.",
        "inputSchema": {
            "type": "object",
            "properties": {"dispatch_key": {"type": "string"}},
            "required": ["dispatch_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supervisor_cancel",
        "description": "Cancel an active supervisor dispatch while preserving its durable receipt.",
        "inputSchema": {
            "type": "object",
            "properties": {"dispatch_key": {"type": "string"}},
            "required": ["dispatch_key"],
            "additionalProperties": False,
        },
    },
]


def supervisor_mcp_path() -> str:
    return "/nd/supervisor/mcp/" + PATH_TOKEN if PATH_TOKEN else ""


def is_supervisor_mcp(path: str) -> bool:
    expected = supervisor_mcp_path()
    return bool(expected and path.split("?", 1)[0] == expected)


def _start_inner() -> subprocess.Popen:
    urllib.request.urlretrieve(UPSTREAM_ENTRY, INNER_ENTRY_PATH)
    env = dict(os.environ)
    env["PORT"] = str(INNER_PORT)
    # Prevent accidental recursive wrapping if this adapter becomes the outer entry.
    env["ND_SUPERVISOR_OUTER_ACTIVE"] = "1"
    return subprocess.Popen([sys.executable, "-u", INNER_ENTRY_PATH], env=env)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, code: int, obj: Any):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def forward(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(n) if n else None
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower()
                not in ("host", "connection", "content-length", "transfer-encoding")
            }
            req = urllib.request.Request(
                "http://127.0.0.1:%d%s" % (INNER_PORT, self.path),
                data=body,
                headers=headers,
                method=self.command,
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as response:
                    raw = response.read()
                    self.send_response(response.status)
                    for k, v in response.headers.items():
                        if k.lower() not in ("connection", "transfer-encoding", "content-length"):
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    if raw:
                        self.wfile.write(raw)
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                self.send_response(exc.code)
                for k, v in exc.headers.items():
                    if k.lower() not in ("connection", "transfer-encoding", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)
        except Exception as exc:
            self.send_json(502, {"ok": False, "error": "inner_forward_failed", "detail": clean(exc)})

    def handle_supervisor_mcp(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n <= 0 or n > 2 * 1024 * 1024:
                raise RuntimeError("invalid_body_size")
            msg = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
            method = str(msg.get("method") or "")
            mid = msg.get("id")
            if method == "initialize":
                params = msg.get("params") or {}
                result = {
                    "protocolVersion": params.get("protocolVersion") or "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "nd-supervisor-dispatch", "version": "0.4.0-prototype"},
                }
            elif method == "notifications/initialized":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = msg.get("params") or {}
                data = supervisor_tool_call(
                    str(params.get("name") or ""), params.get("arguments") or {}
                )
                result = {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "structuredContent": data,
                    "isError": False,
                }
            else:
                self.send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32601, "message": "Method not found"},
                    },
                )
                return
            self.send_json(200, {"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as exc:
            self.send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32000, "message": clean(exc)},
                },
            )

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/nd/supervisor/health":
            try:
                self.send_json(200, supervisor_tool_call("supervisor_status", {}))
            except Exception as exc:
                self.send_json(503, {"ok": False, "error": clean(exc)})
            return
        self.forward()

    def do_POST(self):
        if is_supervisor_mcp(self.path):
            self.handle_supervisor_mcp()
            return
        self.forward()

    def do_PUT(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def do_DELETE(self):
        self.forward()

    def do_OPTIONS(self):
        self.forward()


def main():
    if not PATH_TOKEN:
        raise RuntimeError("supervisor_dispatch_path_token_missing")
    _bootstrap_modules()
    child = _start_inner()
    print(
        "ND_SUPERVISOR_DISPATCH_OUTER_V0_4_READY "
        + json.dumps(
            {
                "port": PORT,
                "inner_port": INNER_PORT,
                "ledger_mode": LEDGER_MODE,
                "ledger_repo": LEDGER_REPO if LEDGER_MODE == "github" else None,
                "source_ref": SOURCE_REF,
                "path_token_configured": bool(PATH_TOKEN),
                "inner_pid": child.pid,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
