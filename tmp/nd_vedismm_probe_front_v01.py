import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "3000"))
INNER_PORT = int(os.environ.get("ND_VEDISMM_PROBE_INNER_PORT", "3977"))
BASE = os.environ.get("ND_VEDISMM_BASE_URL", "https://vedismm.ru/api/v1").rstrip("/")
EMAIL = os.environ.get("ND_VEDISMM_EMAIL", "").strip()
PASSWORD = os.environ.get("ND_VEDISMM_PASSWORD", "")
VK_TOKEN = os.environ.get("VK_GROUP_TOKEN", "").strip()
VK_SCREEN = os.environ.get("VK_GROUP_SCREEN_NAME", "namelessdhamma").strip().lstrip("@")
PROBE_TOKEN = os.environ.get("ND_VEDISMM_PROBE_TOKEN", "").strip()
TARGET_GROUP_ID = "228330620"
TARGET_SCREEN = "namelessdhamma"

UPSTREAM = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a7f53b5f351942838c6ea2e14280308529cefd5/tmp/nd_remotion_mcp_front_v1.py"
UPSTREAM_PATH = "/tmp/nd_existing_gateway_vedismm_inner.py"
urllib.request.urlretrieve(UPSTREAM, UPSTREAM_PATH)
child_env = dict(os.environ)
child_env["PORT"] = str(INNER_PORT)
child = subprocess.Popen([sys.executable, "-u", UPSTREAM_PATH], env=child_env)
INNER = "http://127.0.0.1:%d" % INNER_PORT

SECRETS = [EMAIL, PASSWORD, VK_TOKEN, PROBE_TOKEN]

def clean(value):
    s = str(value)
    for secret in SECRETS:
        if secret:
            s = s.replace(secret, "[REDACTED]")
    return s[:4000]

def api_json(path, method="GET", body=None, bearer=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "ND-VediSMM-Probe/0.1"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw or "{}") if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            obj = json.loads(raw or "{}")
        except Exception:
            obj = {"raw": clean(raw)}
        return e.code, obj

def sanitized_account(row):
    if not isinstance(row, dict):
        return {}
    keys = ("id","network","connection_mode","target_type","external_id","title","username","status",
            "token_expires_at","last_health_check_at","attention_required","attention_reason",
            "recommended_action","has_error")
    return {k: row.get(k) for k in keys}

def is_target(row):
    if not isinstance(row, dict):
        return False
    ext = str(row.get("external_id") or "").lstrip("-")
    username = str(row.get("username") or "").lstrip("@").lower()
    title = str(row.get("title") or "").strip().lower()
    return ext == TARGET_GROUP_ID or username == TARGET_SCREEN or title == "nameless dhamma"

def qualify_connect():
    missing = [name for name, val in (
        ("ND_VEDISMM_EMAIL", EMAIL),
        ("ND_VEDISMM_PASSWORD", PASSWORD),
        ("VK_GROUP_TOKEN", VK_TOKEN),
        ("ND_VEDISMM_PROBE_TOKEN", PROBE_TOKEN),
    ) if not val]
    if missing:
        return 503, {"ok": False, "stage": "config", "missing": missing}

    code, login = api_json("/auth/login", "POST", {
        "email": EMAIL,
        "password": PASSWORD,
        "client_name": "ND VediSMM qualification",
    })
    if code != 200:
        return 502, {"ok": False, "stage": "login", "http": code, "detail": clean(login)}
    access = str(((login.get("data") or {}).get("access_token") or "")).strip()
    if not access:
        return 502, {"ok": False, "stage": "login", "http": code, "error": "access_token_missing"}

    # Idempotent readback first.
    acode, accounts_obj = api_json("/accounts?limit=100", bearer=access)
    accounts = (accounts_obj.get("data") or []) if isinstance(accounts_obj, dict) else []
    existing = [x for x in accounts if is_target(x)]
    if acode == 200 and existing:
        return 200, {
            "ok": True,
            "stage": "already_connected",
            "connection_created": False,
            "account": sanitized_account(existing[0]),
            "secrets_exposed": False,
        }

    scode, start = api_json("/connection-sessions", "POST", {
        "network": "vk",
        "mode": "manual",
        "credentials": {
            "access_token": VK_TOKEN,
            "community": VK_SCREEN,
        },
    }, access)
    if scode not in (200, 201, 202):
        return 502, {"ok": False, "stage": "start_connection", "http": scode, "detail": clean(start)}

    data = start.get("data") or {}
    session_id = str(data.get("id") or data.get("session_id") or "").strip()
    candidates = data.get("candidates") or data.get("targets") or []
    if not isinstance(candidates, list):
        candidates = []
    target = None
    for row in candidates:
        if is_target(row):
            target = row
            break
    if target is None and len(candidates) == 1:
        # Accept sole candidate only if its external id is the known group id after normalization,
        # or if VediSMM omitted metadata other than the candidate id.
        row = candidates[0]
        if str(row.get("external_id") or "").lstrip("-") == TARGET_GROUP_ID:
            target = row

    safe_candidates = [{
        "id": x.get("id"),
        "target_type": x.get("target_type"),
        "external_id": x.get("external_id"),
        "title": x.get("title"),
        "username": x.get("username"),
        "already_connected": x.get("already_connected"),
    } for x in candidates[:20] if isinstance(x, dict)]

    if not session_id:
        return 502, {"ok": False, "stage": "start_connection", "error": "session_id_missing", "candidates": safe_candidates}
    if target is None:
        return 409, {"ok": False, "stage": "candidate_selection", "error": "target_not_found", "candidates": safe_candidates}

    cand_id = str(target.get("id") or "")
    if not cand_id:
        return 502, {"ok": False, "stage": "candidate_selection", "error": "candidate_id_missing"}

    ccode, confirmed = api_json("/connection-sessions/%s/confirm" % urllib.parse.quote(session_id, safe=""), "POST", {
        "candidate_ids": [cand_id]
    }, access)
    if ccode not in (200, 201, 202):
        return 502, {
            "ok": False,
            "stage": "confirm_connection",
            "http": ccode,
            "candidate": safe_candidates,
            "detail": clean(confirmed),
        }

    rcode, readback = api_json("/accounts?limit=100", bearer=access)
    rows = (readback.get("data") or []) if isinstance(readback, dict) else []
    matches = [x for x in rows if is_target(x)]
    if rcode != 200 or not matches:
        return 502, {
            "ok": False,
            "stage": "account_readback",
            "http": rcode,
            "error": "confirmed_but_account_not_found",
        }
    return 200, {
        "ok": True,
        "stage": "confirmed",
        "connection_created": True,
        "account": sanitized_account(matches[0]),
        "candidate": {
            "external_id": target.get("external_id"),
            "title": target.get("title"),
            "username": target.get("username"),
        },
        "secrets_exposed": False,
    }

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass
    def send_json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)
    def authorized(self):
        supplied = self.headers.get("X-ND-VediSMM-Probe-Token", "")
        if not supplied:
            try:
                qs = urllib.parse.urlsplit(self.path).query
                supplied = (urllib.parse.parse_qs(qs).get("token") or [""])[0]
            except Exception:
                supplied = ""
        return bool(PROBE_TOKEN and supplied and hmac.compare_digest(str(supplied), PROBE_TOKEN))
    def forward(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(n) if n else None
            headers = {k:v for k,v in self.headers.items()
                       if k.lower() not in ("host","connection","content-length","transfer-encoding")}
            req = urllib.request.Request(INNER + self.path, data=body, headers=headers, method=self.command)
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    raw = r.read()
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in ("connection","transfer-encoding","content-length"):
                            self.send_header(k,v)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    if raw:
                        self.wfile.write(raw)
            except urllib.error.HTTPError as e:
                raw = e.read()
                self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() not in ("connection","transfer-encoding","content-length"):
                        self.send_header(k,v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)
        except Exception as e:
            self.send_json(502, {"ok": False, "error": "inner_forward_failed", "detail": clean(e)})
    def do_POST(self):
        if self.path.split("?",1)[0] == "/vedismm/qualify/connect":
            if not self.authorized():
                return self.send_json(403, {"ok": False, "error": "forbidden"})
            try:
                code, obj = qualify_connect()
                return self.send_json(code, obj)
            except Exception as e:
                return self.send_json(500, {"ok": False, "stage": "exception", "error": clean(e)})
        return self.forward()
    def do_GET(self):
        path = self.path.split("?",1)[0]
        if path == "/vedismm/qualify/connect":
            if not self.authorized():
                return self.send_json(403, {"ok": False, "error": "forbidden"})
            try:
                code, obj = qualify_connect()
                return self.send_json(code, obj)
            except Exception as e:
                return self.send_json(500, {"ok": False, "stage": "exception", "error": clean(e)})
        if path == "/vedismm/qualify/health":
            return self.send_json(200, {
                "ok": True,
                "service": "nd-vedismm-probe-front",
                "version": "0.1.0",
                "configured": bool(EMAIL and PASSWORD and VK_TOKEN and PROBE_TOKEN),
                "target_group_id": TARGET_GROUP_ID,
                "target_screen": TARGET_SCREEN,
            })
        return self.forward()
    def do_PUT(self): return self.forward()
    def do_PATCH(self): return self.forward()
    def do_DELETE(self): return self.forward()
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

print("ND_VEDISMM_PROBE_FRONT_V0_1_READY " + json.dumps({
    "port": PORT,
    "inner_port": INNER_PORT,
    "configured": bool(EMAIL and PASSWORD and VK_TOKEN and PROBE_TOKEN),
    "target_group_id": TARGET_GROUP_ID,
}, ensure_ascii=False), flush=True)
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
