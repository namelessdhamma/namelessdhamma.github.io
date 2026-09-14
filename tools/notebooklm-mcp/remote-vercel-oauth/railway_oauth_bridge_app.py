from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error
from http.cookiejar import CookieJar
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.railway_deployment import build_railway_app_from_environ

PROVIDER = "https://nd-notebooklm-oauth-mcp.vercel.app"
MCP_URL = PROVIDER + "/mcp"
TOKEN_PATH = Path("/data/nd-notebooklm/doctor-provider-oauth.json")
RELAY_TOKEN = os.environ.get("ND_NOTEBOOKLM_DOCTOR_RELAY_TOKEN", "").strip()
PASSWORD_CANDIDATES = []
for _name in ("NOTEBOOKLM_MCP_OAUTH_PASSWORD", "ND_NOTEBOOKLM_OAUTH_LOGIN_PASSWORD"):
    _v = os.environ.get(_name, "").strip()
    if _v and _v not in PASSWORD_CANDIDATES:
        PASSWORD_CANDIDATES.append(_v)

mcp_app = build_railway_app_from_environ()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _opener():
    return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(CookieJar()))

def _request(url, *, method="GET", headers=None, data=None, opener=None, timeout=60):
    op = opener or _opener()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()

def _json_request(url, payload, *, headers=None, opener=None, timeout=60):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(headers or {})
    return _request(
        url,
        method="POST",
        headers=h,
        data=json.dumps(payload).encode("utf-8"),
        opener=opener,
        timeout=timeout,
    )

def _form_request(url, payload, *, headers=None, opener=None, timeout=60):
    h = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    h.update(headers or {})
    return _request(
        url,
        method="POST",
        headers=h,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        opener=opener,
        timeout=timeout,
    )

def _safe_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None

def _load_token():
    try:
        obj = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None

def _save_token(obj):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    TOKEN_PATH.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)

def _register_client(opener):
    payload = {
        "client_name": "ND True Doctor Railway Relay",
        "redirect_uris": ["https://nd-doctor.invalid/notebooklm/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }
    status, _, raw = _json_request(PROVIDER + "/register", payload, opener=opener)
    obj = _safe_json(raw)
    if status not in (200, 201) or not isinstance(obj, dict) or not obj.get("client_id"):
        raise RuntimeError("dcr_failed_status_%s" % status)
    return obj

def _pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge

def _authorize_with_password(opener, client, password):
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    redirect_uri = client["redirect_uris"][0]
    query = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": MCP_URL,
    }
    status, headers, raw = _request(
        PROVIDER + "/authorize?" + urllib.parse.urlencode(query),
        opener=opener,
    )
    if status not in (302, 303, 307, 308):
        raise RuntimeError("authorize_failed_status_%s" % status)
    loc = headers.get("Location") or headers.get("location") or ""
    parsed = urllib.parse.urlparse(urllib.parse.urljoin(PROVIDER + "/", loc))
    sid = urllib.parse.parse_qs(parsed.query).get("sid", [""])[0]
    if not sid:
        raise RuntimeError("authorize_missing_sid")

    status, headers, raw = _form_request(
        PROVIDER + "/login",
        {"sid": sid, "password": password},
        opener=opener,
    )
    if status not in (302, 303, 307, 308):
        raise RuntimeError("login_failed_status_%s" % status)
    loc = headers.get("Location") or headers.get("location") or ""
    callback = urllib.parse.urlparse(loc)
    params = urllib.parse.parse_qs(callback.query)
    code = params.get("code", [""])[0]
    got_state = params.get("state", [""])[0]
    if not code or got_state != state:
        raise RuntimeError("login_missing_code_or_state")

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "client_id": client["client_id"],
    }
    if client.get("client_secret"):
        token_payload["client_secret"] = client["client_secret"]

    status, _, raw = _form_request(PROVIDER + "/token", token_payload, opener=opener)
    tok = _safe_json(raw)
    if status != 200 or not isinstance(tok, dict) or not tok.get("access_token"):
        raise RuntimeError("token_exchange_failed_status_%s" % status)

    now = int(time.time())
    return {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "token_type": tok.get("token_type", "Bearer"),
        "expires_at": now + int(tok.get("expires_in") or 3600) - 60,
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "redirect_uri": redirect_uri,
    }

def _refresh_token(saved):
    refresh = saved.get("refresh_token")
    if not refresh:
        return None
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": saved.get("client_id", ""),
    }
    if saved.get("client_secret"):
        payload["client_secret"] = saved["client_secret"]
    status, _, raw = _form_request(PROVIDER + "/token", payload)
    tok = _safe_json(raw)
    if status != 200 or not isinstance(tok, dict) or not tok.get("access_token"):
        return None
    now = int(time.time())
    out = dict(saved)
    out.update(
        {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token") or refresh,
            "token_type": tok.get("token_type", "Bearer"),
            "expires_at": now + int(tok.get("expires_in") or 3600) - 60,
        }
    )
    _save_token(out)
    return out

def _ensure_token():
    saved = _load_token()
    if saved and saved.get("access_token") and int(saved.get("expires_at") or 0) > int(time.time()):
        return saved
    if saved:
        refreshed = _refresh_token(saved)
        if refreshed:
            return refreshed

    last_error = None
    for password in PASSWORD_CANDIDATES:
        try:
            opener = _opener()
            client = _register_client(opener)
            token = _authorize_with_password(opener, client, password)
            _save_token(token)
            return token
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "no_oauth_password_candidate")

def _parse_mcp(raw):
    text = raw.decode("utf-8", "replace")
    obj = _safe_json(raw)
    if isinstance(obj, dict):
        return obj
    vals = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                vals.append(json.loads(line[6:]))
            except Exception:
                pass
    if vals:
        return vals[-1]
    raise RuntimeError("mcp_unparseable_response")

def _mcp_post(token, payload, session_id=None):
    headers = {
        "Authorization": "Bearer " + token["access_token"],
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
        headers["MCP-Protocol-Version"] = "2025-06-18"
    status, response_headers, raw = _request(
        MCP_URL,
        method="POST",
        headers=headers,
        data=json.dumps(payload).encode("utf-8"),
        timeout=90,
    )
    if status == 401:
        raise RuntimeError("mcp_unauthorized")
    if status not in (200, 202):
        raise RuntimeError("mcp_http_%s" % status)
    return status, response_headers, raw

def _mcp_call(tool, arguments):
    token = _ensure_token()
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ND True Doctor Railway Relay", "version": "1.0"},
        },
    }
    status, headers, raw = _mcp_post(token, init)
    init_obj = _parse_mcp(raw)
    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    if session_id:
        _mcp_post(
            token,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            session_id,
        )
    status, _, raw = _mcp_post(
        token,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        },
        session_id,
    )
    return {
        "ok": True,
        "provider": "NotebookLM",
        "serverInfo": ((init_obj.get("result") or {}).get("serverInfo") or {}),
        "tool": tool,
        "response": _parse_mcp(raw),
    }

def _authorized_path(request: Request, prefix: str) -> bool:
    if len(RELAY_TOKEN) < 24:
        return False
    return request.url.path == prefix + "/" + RELAY_TOKEN

async def doctor_health(request: Request):
    return JSONResponse(
        {
            "ok": True,
            "service": "nd-notebooklm-oauth-bridge",
            "version": "1.0.0",
            "provider": "NotebookLM",
            "oauth_password_candidate_count": len(PASSWORD_CANDIDATES),
            "cached_provider_token": bool(_load_token()),
            "relay_configured": len(RELAY_TOKEN) >= 24,
            "native_backup_mcp_preserved": True,
        }
    )

async def doctor_notebooks(request: Request):
    if not _authorized_path(request, "/doctor/notebooks"):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    try:
        return JSONResponse(_mcp_call("notebook_list", {"limit": 20}))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:1000]}, status_code=502)

async def doctor_server_info(request: Request):
    if not _authorized_path(request, "/doctor/server-info"):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    try:
        return JSONResponse(_mcp_call("server_info", {"include_account": True}))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:1000]}, status_code=502)

routes = [
    Route("/doctor/health", doctor_health, methods=["GET"]),
    Route("/doctor/notebooks/{token}", doctor_notebooks, methods=["GET"]),
    Route("/doctor/server-info/{token}", doctor_server_info, methods=["GET"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes)
