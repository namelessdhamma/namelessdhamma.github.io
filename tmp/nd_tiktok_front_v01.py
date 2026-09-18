import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "3000"))
INNER_PORT = int(os.environ.get("ND_TIKTOK_INNER_PORT", "3999"))
CLIENT_KEY = os.environ.get("ND_TIKTOK_CLIENT_KEY", "").strip()
CLIENT_SECRET = os.environ.get("ND_TIKTOK_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.environ.get("ND_TIKTOK_REDIRECT_URI", "").strip()
SETUP_TOKEN = os.environ.get("ND_TIKTOK_SETUP_TOKEN", "").strip()
ACCESS_TOKEN_ENV = os.environ.get("ND_TIKTOK_ACCESS_TOKEN", "").strip()
REFRESH_TOKEN_ENV = os.environ.get("ND_TIKTOK_REFRESH_TOKEN", "").strip()
OPEN_ID_ENV = os.environ.get("ND_TIKTOK_OPEN_ID", "").strip()
SCOPE_ENV = os.environ.get("ND_TIKTOK_SCOPE", "").strip()

TOKEN_PATH = "/tmp/nd_tiktok_token.json"
UPSTREAM = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/aa37a2083e1abf56768e6cb59e4bd583122ae3b6/tmp/nd_tldraw_mcp_front_v2_resources.py"
UPSTREAM_PATH = "/tmp/nd_existing_gateway_tiktok_inner.py"

urllib.request.urlretrieve(UPSTREAM, UPSTREAM_PATH)
child_env = dict(os.environ)
child_env["PORT"] = str(INNER_PORT)
child = subprocess.Popen([sys.executable, "-u", UPSTREAM_PATH], env=child_env)
INNER = "http://127.0.0.1:%d" % INNER_PORT

def clean_error(value):
    text = str(value)
    for secret in (CLIENT_SECRET, SETUP_TOKEN, ACCESS_TOKEN_ENV, REFRESH_TOKEN_ENV):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:2000]

def save_token(obj):
    if not isinstance(obj, dict):
        raise RuntimeError("invalid_token_response")
    now = int(time.time())
    out = dict(obj)
    out["obtained_at"] = now
    try:
        out["expires_at"] = now + int(out.get("expires_in") or 0)
    except Exception:
        out["expires_at"] = now
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except Exception:
        pass
    return out

def load_token_raw():
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    if ACCESS_TOKEN_ENV or REFRESH_TOKEN_ENV:
        return {
            "access_token": ACCESS_TOKEN_ENV,
            "refresh_token": REFRESH_TOKEN_ENV,
            "open_id": OPEN_ID_ENV,
            "scope": SCOPE_ENV,
            "expires_at": 0,
        }
    return {}

def token_form(fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
            "User-Agent": "Nameless-Dhamma-TikTok/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            obj = json.loads(raw or "{}")
            if not isinstance(obj, dict):
                raise RuntimeError("invalid_token_json")
            if obj.get("error"):
                raise RuntimeError("tiktok_token_error:" + clean_error(obj))
            return obj
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise RuntimeError("tiktok_token_http_%s:%s" % (e.code, clean_error(raw or e.reason)))

def refresh_access_token(tok):
    refresh = str(tok.get("refresh_token") or "").strip()
    if not refresh:
        return tok
    obj = token_form({
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    })
    if not obj.get("refresh_token"):
        obj["refresh_token"] = refresh
    return save_token(obj)

def get_token():
    tok = load_token_raw()
    if not tok.get("access_token"):
        raise RuntimeError("tiktok_not_authorized")
    expires_at = int(tok.get("expires_at") or 0)
    if expires_at and expires_at <= int(time.time()) + 120 and tok.get("refresh_token"):
        tok = refresh_access_token(tok)
    return tok

def make_state():
    if not CLIENT_SECRET:
        raise RuntimeError("tiktok_client_secret_missing")
    payload = "%d.%s" % (int(time.time()), secrets.token_urlsafe(24))
    sig = hmac.new(CLIENT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return payload + "." + sig

def valid_state(state):
    try:
        ts_s, nonce, sig = state.split(".", 2)
        if abs(int(time.time()) - int(ts_s)) > 900:
            return False
        payload = ts_s + "." + nonce
        want = hmac.new(CLIENT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, want)
    except Exception:
        return False

def api_json(url, method="GET", body=None, token=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "User-Agent": "Nameless-Dhamma-TikTok/1.0",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json; charset=UTF-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw or "{}") if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            obj = json.loads(raw or "{}")
        except Exception:
            obj = {"raw": clean_error(raw)}
        return e.code, obj

def authorized_setup(headers, query):
    if not SETUP_TOKEN:
        return False
    supplied = headers.get("X-ND-TikTok-Setup-Token", "")
    if not supplied:
        supplied = (query.get("setup") or [""])[0]
    return hmac.compare_digest(str(supplied), SETUP_TOKEN)

class Handler(BaseHTTPRequestHandler):
    server_version = "ND-TikTok-Front/1.0"

    def log_message(self, *args):
        pass

    def send_bytes(self, status, raw, content_type="application/octet-stream", extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def send_json(self, status, obj):
        self.send_bytes(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def send_html(self, status, html):
        self.send_bytes(status, html.encode("utf-8"), "text/html; charset=utf-8")

    def redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def parse(self):
        p = urllib.parse.urlsplit(self.path)
        return p.path, urllib.parse.parse_qs(p.query, keep_blank_values=True)

    def cookie_value(self, name):
        c = cookies.SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
            return c[name].value if name in c else ""
        except Exception:
            return ""

    def tiktok_health(self):
        tok = load_token_raw()
        self.send_json(200, {
            "ok": True,
            "service": "nd-tiktok-front",
            "version": "1.0.0",
            "configured": bool(CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI),
            "setup_protected": bool(SETUP_TOKEN),
            "authorized": bool(tok.get("access_token")),
            "scope": tok.get("scope") or "",
            "open_id_present": bool(tok.get("open_id")),
        })

    def oauth_start(self):
        if not (CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI):
            self.send_json(503, {"ok": False, "error": "tiktok_not_configured"})
            return
        state = make_state()
        params = {
            "client_key": CLIENT_KEY,
            "scope": "user.info.basic,video.upload",
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": state,
        }
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)
        cookie = "nd_tiktok_oauth_state=%s; Max-Age=900; Path=/tiktok/oauth/; Secure; HttpOnly; SameSite=Lax" % urllib.parse.quote(state, safe="")
        self.redirect(url, cookie)

    def oauth_callback(self, query):
        if query.get("error"):
            self.send_html(400, "<h1>TikTok authorization failed</h1><p>%s</p>" % clean_error((query.get("error_description") or query.get("error") or [""])[0]))
            return
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        cookie_state = urllib.parse.unquote(self.cookie_value("nd_tiktok_oauth_state") or "")
        if not code:
            self.send_json(400, {"ok": False, "error": "code_missing"})
            return
        if not state or not cookie_state or state != cookie_state or not valid_state(state):
            self.send_json(400, {"ok": False, "error": "state_invalid"})
            return
        try:
            tok = token_form({
                "client_key": CLIENT_KEY,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            })
            tok = save_token(tok)
        except Exception as e:
            self.send_json(502, {"ok": False, "error": clean_error(e)})
            return
        scope = str(tok.get("scope") or "")
        html = """<!doctype html><html><head><meta charset="utf-8"><title>Nameless Dhamma — TikTok connected</title></head>
<body style="background:#000;color:#eee;font-family:system-ui;padding:48px;line-height:1.6">
<h1>TikTok connected</h1><p>Authorization completed successfully.</p>
<p>Granted scopes: <code>%s</code></p><p>You may close this tab.</p></body></html>""" % scope.replace("<", "&lt;")
        self.send_html(200, html)

    def oauth_status(self):
        tok = load_token_raw()
        self.send_json(200, {
            "ok": True,
            "authorized": bool(tok.get("access_token")),
            "open_id": tok.get("open_id") or "",
            "scope": tok.get("scope") or "",
            "expires_at": tok.get("expires_at") or 0,
            "refresh_token_present": bool(tok.get("refresh_token")),
        })

    def token_export(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        tok = load_token_raw()
        if not tok.get("access_token"):
            self.send_json(404, {"ok": False, "error": "tiktok_not_authorized"})
            return
        self.send_json(200, {"ok": True, "token": tok})

    def user_info(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,avatar_url,display_name"
        status, obj = api_json(url, "GET", token=tok["access_token"])
        self.send_json(status, obj)

    def upload_video(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            n = 0
        if n <= 0 or n > 70 * 1024 * 1024:
            self.send_json(400, {"ok": False, "error": "invalid_video_size", "max_bytes": 70 * 1024 * 1024})
            return
        ctype = (self.headers.get("Content-Type") or "video/mp4").split(";", 1)[0].strip().lower()
        if ctype not in ("video/mp4", "video/quicktime", "video/webm"):
            self.send_json(415, {"ok": False, "error": "unsupported_video_type"})
            return
        body = self.rfile.read(n)
        if len(body) != n:
            self.send_json(400, {"ok": False, "error": "short_video_body"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        init_body = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": n,
                "chunk_size": n,
                "total_chunk_count": 1,
            }
        }
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            "POST",
            init_body,
            tok["access_token"],
        )
        if status < 200 or status >= 300 or ((obj.get("error") or {}).get("code") not in (None, "", "ok")):
            self.send_json(status, {"ok": False, "stage": "init", "response": obj})
            return
        data = obj.get("data") or {}
        upload_url = str(data.get("upload_url") or "")
        publish_id = str(data.get("publish_id") or "")
        if not upload_url:
            self.send_json(502, {"ok": False, "stage": "init", "error": "upload_url_missing", "response": obj})
            return
        req = urllib.request.Request(
            upload_url,
            data=body,
            headers={
                "Content-Type": ctype,
                "Content-Length": str(n),
                "Content-Range": "bytes 0-%d/%d" % (n - 1, n),
                "User-Agent": "Nameless-Dhamma-TikTok/1.0",
            },
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                upload_status = r.status
                r.read()
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            self.send_json(e.code, {"ok": False, "stage": "upload", "error": clean_error(raw or e.reason), "publish_id": publish_id})
            return
        self.send_json(200, {"ok": True, "publish_id": publish_id, "upload_status": upload_status})

    def upload_status(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        publish_id = (query.get("publish_id") or [""])[0]
        if not publish_id:
            self.send_json(400, {"ok": False, "error": "publish_id_required"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            "POST",
            {"publish_id": publish_id},
            tok["access_token"],
        )
        self.send_json(status, obj)

    def forward(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            n = 0
        body = self.rfile.read(n) if n else None
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length", "transfer-encoding")
        }
        req = urllib.request.Request(INNER + self.path, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() not in ("connection", "transfer-encoding", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("connection", "transfer-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception as e:
            self.send_json(502, {"ok": False, "error": "existing_gateway_unavailable", "detail": clean_error(e)})

    def do_GET(self):
        path, query = self.parse()
        if path == "/tiktok/health":
            return self.tiktok_health()
        if path == "/tiktok/oauth/start":
            return self.oauth_start()
        if path == "/tiktok/oauth/callback":
            return self.oauth_callback(query)
        if path == "/tiktok/oauth/status":
            return self.oauth_status()
        if path == "/tiktok/token/export":
            return self.token_export(query)
        if path == "/tiktok/user":
            return self.user_info(query)
        if path == "/tiktok/upload/status":
            return self.upload_status(query)
        return self.forward()

    def do_POST(self):
        path, query = self.parse()
        if path == "/tiktok/upload":
            return self.upload_video(query)
        return self.forward()

    def do_PUT(self):
        return self.forward()

    def do_PATCH(self):
        return self.forward()

    def do_DELETE(self):
        return self.forward()

print("ND_TIKTOK_FRONT_V1_READY " + json.dumps({
    "port": PORT,
    "inner_port": INNER_PORT,
    "configured": bool(CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI),
    "setup_protected": bool(SETUP_TOKEN),
}, ensure_ascii=False), flush=True)

ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
