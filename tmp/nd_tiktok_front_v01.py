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
SANDBOX_CLIENT_KEY = os.environ.get("ND_TIKTOK_SANDBOX_CLIENT_KEY", "").strip()
SANDBOX_CLIENT_SECRET = os.environ.get("ND_TIKTOK_SANDBOX_CLIENT_SECRET", "").strip()
SANDBOX_REDIRECT_URI = os.environ.get("ND_TIKTOK_SANDBOX_REDIRECT_URI", "").strip() or REDIRECT_URI
SETUP_TOKEN = os.environ.get("ND_TIKTOK_SETUP_TOKEN", "").strip()
MCP_PATH_TOKEN = os.environ.get("ND_TIKTOK_MCP_PATH_TOKEN", "").strip()
ACCESS_TOKEN_ENV = os.environ.get("ND_TIKTOK_ACCESS_TOKEN", "").strip()
REFRESH_TOKEN_ENV = os.environ.get("ND_TIKTOK_REFRESH_TOKEN", "").strip()
OPEN_ID_ENV = os.environ.get("ND_TIKTOK_OPEN_ID", "").strip()
SCOPE_ENV = os.environ.get("ND_TIKTOK_SCOPE", "").strip()
CREDENTIAL_MODE_ENV = os.environ.get("ND_TIKTOK_CREDENTIAL_MODE", "").strip().lower()
OAUTH_SCOPES = "user.info.basic,user.info.profile,user.info.stats,video.list,video.upload,video.publish"
WEBHOOK_LOG_PATH = "/tmp/nd_tiktok_webhooks.jsonl"

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
    for secret in (CLIENT_SECRET, SANDBOX_CLIENT_SECRET, SETUP_TOKEN, MCP_PATH_TOKEN, ACCESS_TOKEN_ENV, REFRESH_TOKEN_ENV):
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
            "credential_mode": CREDENTIAL_MODE_ENV or "production",
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
    mode = str(tok.get("credential_mode") or CREDENTIAL_MODE_ENV or "production").strip().lower()
    if mode == "sandbox":
        refresh_key = SANDBOX_CLIENT_KEY
        refresh_secret = SANDBOX_CLIENT_SECRET
    else:
        refresh_key = CLIENT_KEY
        refresh_secret = CLIENT_SECRET
        mode = "production"
    if not (refresh_key and refresh_secret):
        raise RuntimeError("tiktok_refresh_credentials_missing:" + mode)
    obj = token_form({
        "client_key": refresh_key,
        "client_secret": refresh_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    })
    if not obj.get("refresh_token"):
        obj["refresh_token"] = refresh
    obj["credential_mode"] = mode
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

def make_sandbox_state():
    if not SANDBOX_CLIENT_SECRET:
        raise RuntimeError("tiktok_sandbox_client_secret_missing")
    ts_s = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    payload = "sandbox." + ts_s + "." + nonce
    sig = hmac.new(SANDBOX_CLIENT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return payload + "." + sig

def valid_sandbox_state(state):
    try:
        mode, ts_s, nonce, sig = state.split(".", 3)
        if mode != "sandbox" or abs(int(time.time()) - int(ts_s)) > 900:
            return False
        payload = mode + "." + ts_s + "." + nonce
        want = hmac.new(SANDBOX_CLIENT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
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

def mcp_tools():
    return [
        {"name":"tiktok_status","description":"Read Nameless Dhamma TikTok authorization/configuration status without returning secrets.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
        {"name":"tiktok_user","description":"Read the authorized TikTok account profile and statistics using the granted user.info scopes.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
        {"name":"tiktok_list_videos","description":"List public videos for the authorized TikTok account.","inputSchema":{"type":"object","properties":{"max_count":{"type":"integer","minimum":1,"maximum":20},"cursor":{"type":"integer"}},"additionalProperties":False}},
        {"name":"tiktok_creator_info","description":"Read Content Posting creator capabilities including allowed privacy levels and maximum video duration.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
        {"name":"tiktok_publish_status","description":"Read Content Posting processing status for a publish_id.","inputSchema":{"type":"object","properties":{"publish_id":{"type":"string"}},"required":["publish_id"],"additionalProperties":False}},
        {"name":"tiktok_webhook_events","description":"Read the most recent verified TikTok webhook events accepted by the ND gateway.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
        {"name":"tiktok_upload_draft_url","description":"Download an MP4/WebM/MOV from an approved Nameless Dhamma source URL and upload it to TikTok as a user-reviewable draft. Does not publish publicly.","inputSchema":{"type":"object","properties":{"video_url":{"type":"string"}},"required":["video_url"],"additionalProperties":False}},
        {"name":"tiktok_direct_post_video_url","description":"Download an approved Nameless Dhamma video URL and Direct Post it to the authorized TikTok account. Defaults to SELF_ONLY; set privacy_level explicitly for broader visibility.","inputSchema":{"type":"object","properties":{"video_url":{"type":"string"},"title":{"type":"string"},"privacy_level":{"type":"string","enum":["SELF_ONLY","MUTUAL_FOLLOW_FRIENDS","PUBLIC_TO_EVERYONE"]},"disable_duet":{"type":"boolean"},"disable_comment":{"type":"boolean"},"disable_stitch":{"type":"boolean"}},"required":["video_url"],"additionalProperties":False}},
        {"name":"tiktok_publish_photos","description":"Publish or upload a TikTok photo post using HTTPS images hosted under the verified namelessdhamma.org prefix.","inputSchema":{"type":"object","properties":{"photo_images":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":35},"post_mode":{"type":"string","enum":["MEDIA_UPLOAD","DIRECT_POST"]},"title":{"type":"string"},"description":{"type":"string"},"privacy_level":{"type":"string","enum":["SELF_ONLY","MUTUAL_FOLLOW_FRIENDS","PUBLIC_TO_EVERYONE"]},"disable_comment":{"type":"boolean"},"auto_add_music":{"type":"boolean"},"brand_content_toggle":{"type":"boolean"},"brand_organic_toggle":{"type":"boolean"},"is_aigc":{"type":"boolean"},"photo_cover_index":{"type":"integer","minimum":0}},"required":["photo_images"],"additionalProperties":False}}
    ]

def mcp_local(path, method="GET", raw=None, content_type="application/json"):
    headers={"X-ND-TikTok-Setup-Token":SETUP_TOKEN,"User-Agent":"ND-TikTok-MCP/1.0"}
    data=raw
    if data is not None:
        headers["Content-Type"]=content_type
    req=urllib.request.Request("http://127.0.0.1:%d%s"%(PORT,path),data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=180) as r:
            b=r.read()
            return json.loads(b.decode("utf-8","replace") or "{}") if b else {}
    except urllib.error.HTTPError as e:
        b=e.read().decode("utf-8","replace")
        try:
            obj=json.loads(b or "{}")
        except Exception:
            obj={"raw":clean_error(b or e.reason)}
        raise RuntimeError("local_http_%s:%s"%(e.code,clean_error(obj)))

def mcp_download_media(url, max_bytes=70*1024*1024):
    u=str(url or "").strip()
    allowed=("https://namelessdhamma.org/","https://www.namelessdhamma.org/","https://raw.githubusercontent.com/namelessdhamma/")
    if not any(u.startswith(p) for p in allowed):
        raise RuntimeError("media_url_not_in_approved_nd_sources")
    req=urllib.request.Request(u,headers={"User-Agent":"ND-TikTok-MCP/1.0"})
    with urllib.request.urlopen(req,timeout=120) as r:
        ctype=(r.headers.get("Content-Type") or "application/octet-stream").split(";",1)[0].strip().lower()
        total=0
        chunks=[]
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>max_bytes: raise RuntimeError("media_too_large")
            chunks.append(chunk)
    return b"".join(chunks),ctype

def mcp_call(name,a):
    a=a or {}
    if not isinstance(a,dict): raise RuntimeError("arguments_must_be_object")
    if name=="tiktok_status":
        return mcp_local("/tiktok/oauth/status")
    if name=="tiktok_user":
        return mcp_local("/tiktok/user")
    if name=="tiktok_list_videos":
        qv={"max_count":max(1,min(20,int(a.get("max_count") or 10)))}
        if a.get("cursor") is not None: qv["cursor"]=int(a.get("cursor"))
        return mcp_local("/tiktok/videos?"+urllib.parse.urlencode(qv))
    if name=="tiktok_creator_info":
        return mcp_local("/tiktok/creator")
    if name=="tiktok_publish_status":
        pid=str(a.get("publish_id") or "").strip()
        if not pid: raise RuntimeError("publish_id_required")
        return mcp_local("/tiktok/upload/status?"+urllib.parse.urlencode({"publish_id":pid}))
    if name=="tiktok_webhook_events":
        return mcp_local("/tiktok/webhooks/status")
    if name=="tiktok_upload_draft_url":
        body,ctype=mcp_download_media(a.get("video_url"))
        if ctype not in ("video/mp4","video/quicktime","video/webm","application/octet-stream"):
            raise RuntimeError("unsupported_video_type:"+ctype)
        if ctype=="application/octet-stream":
            ctype="video/mp4"
        return mcp_local("/tiktok/upload","POST",body,ctype)
    if name=="tiktok_direct_post_video_url":
        body,ctype=mcp_download_media(a.get("video_url"))
        if ctype not in ("video/mp4","video/quicktime","video/webm","application/octet-stream"):
            raise RuntimeError("unsupported_video_type:"+ctype)
        if ctype=="application/octet-stream": ctype="video/mp4"
        qv={
            "title":str(a.get("title") or ""),
            "privacy_level":str(a.get("privacy_level") or "SELF_ONLY"),
            "disable_duet":"true" if bool(a.get("disable_duet",False)) else "false",
            "disable_comment":"true" if bool(a.get("disable_comment",False)) else "false",
            "disable_stitch":"true" if bool(a.get("disable_stitch",False)) else "false",
        }
        return mcp_local("/tiktok/direct/video?"+urllib.parse.urlencode(qv),"POST",body,ctype)
    if name=="tiktok_publish_photos":
        payload=dict(a)
        payload["post_mode"]=str(payload.get("post_mode") or "MEDIA_UPLOAD")
        raw=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        return mcp_local("/tiktok/photo","POST",raw,"application/json")
    raise RuntimeError("unknown_tiktok_tool")

class Handler(BaseHTTPRequestHandler):
    server_version = "ND-TikTok-Front/1.2"

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

    def is_tiktok_mcp(self):
        expected=("/nd/tiktok/mcp/"+MCP_PATH_TOKEN) if MCP_PATH_TOKEN else ""
        return bool(expected and urllib.parse.urlsplit(self.path).path==expected)

    def handle_tiktok_mcp(self):
        try:
            n=int(self.headers.get("Content-Length","0") or "0")
            if n<0 or n>1048576: raise RuntimeError("request_too_large")
            msg=json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if not isinstance(msg,dict): raise RuntimeError("invalid_jsonrpc")
        except Exception as e:
            self.send_json(400,{"jsonrpc":"2.0","error":{"code":-32700,"message":clean_error(e)},"id":None})
            return
        mid=msg.get("id")
        method=str(msg.get("method") or "")
        if method=="notifications/initialized":
            self.send_response(204); self.end_headers(); return
        if method=="initialize":
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"nd-tiktok-direct-mcp","version":"1.0.0"},"instructions":"Direct Nameless Dhamma TikTok MCP. Full qualified read/write surface for the authorized ND TikTok account. Public posting requires an explicit tool call with the desired privacy level; draft upload does not publish publicly."}})
            return
        if method=="ping":
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":{}})
            return
        if method=="tools/list":
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":{"tools":mcp_tools()}})
            return
        if method=="tools/call":
            p=msg.get("params") or {}
            try:
                obj=mcp_call(str(p.get("name") or ""),p.get("arguments") or {})
                err=False
            except Exception as e:
                obj={"ok":False,"error":clean_error(e)}
                err=True
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":json.dumps(obj,ensure_ascii=False)}],"structuredContent":obj,"isError":err}})
            return
        self.send_json(200,{"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"Method not found"}})

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
            "version": "1.2.0",
            "configured": bool(CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI),
            "requested_scopes": OAUTH_SCOPES,
            "setup_protected": bool(SETUP_TOKEN),
            "mcp_configured": bool(MCP_PATH_TOKEN),
            "sandbox_configured": bool(SANDBOX_CLIENT_KEY and SANDBOX_CLIENT_SECRET and SANDBOX_REDIRECT_URI),
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
            "scope": OAUTH_SCOPES,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": state,
        }
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)
        cookie = "nd_tiktok_oauth_state=%s; Max-Age=900; Path=/tiktok/oauth/; Secure; HttpOnly; SameSite=Lax" % urllib.parse.quote(state, safe="")
        self.redirect(url, cookie)

    def sandbox_oauth_start(self):
        if not (SANDBOX_CLIENT_KEY and SANDBOX_CLIENT_SECRET and SANDBOX_REDIRECT_URI):
            self.send_json(503, {"ok": False, "error": "tiktok_sandbox_not_configured"})
            return
        state = make_sandbox_state()
        params = {
            "client_key": SANDBOX_CLIENT_KEY,
            "scope": OAUTH_SCOPES,
            "response_type": "code",
            "redirect_uri": SANDBOX_REDIRECT_URI,
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
        if not state or not cookie_state or state != cookie_state:
            self.send_json(400, {"ok": False, "error": "state_invalid"})
            return
        sandbox_mode = state.startswith("sandbox.")
        if sandbox_mode:
            if not valid_sandbox_state(state):
                self.send_json(400, {"ok": False, "error": "state_invalid"})
                return
            exchange_key = SANDBOX_CLIENT_KEY
            exchange_secret = SANDBOX_CLIENT_SECRET
            exchange_redirect = SANDBOX_REDIRECT_URI
        else:
            if not valid_state(state):
                self.send_json(400, {"ok": False, "error": "state_invalid"})
                return
            exchange_key = CLIENT_KEY
            exchange_secret = CLIENT_SECRET
            exchange_redirect = REDIRECT_URI
        try:
            tok = token_form({
                "client_key": exchange_key,
                "client_secret": exchange_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": exchange_redirect,
            })
            tok["credential_mode"] = "sandbox" if sandbox_mode else "production"
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
        url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,avatar_large_url,display_name,username,bio_description,profile_deep_link,is_verified,follower_count,following_count,likes_count,video_count"
        status, obj = api_json(url, "GET", token=tok["access_token"])
        self.send_json(status, obj)

    def video_list(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        try:
            max_count = max(1, min(20, int((query.get("max_count") or ["10"])[0])))
        except Exception:
            max_count = 10
        body = {"max_count": max_count}
        cursor = (query.get("cursor") or [""])[0]
        if cursor:
            try:
                body["cursor"] = int(cursor)
            except Exception:
                pass
        fields = "id,title,video_description,duration,cover_image_url,embed_link,create_time"
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/video/list/?fields=" + urllib.parse.quote(fields, safe=","),
            "POST",
            body,
            tok["access_token"],
        )
        self.send_json(status, obj)

    def creator_info(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            "POST",
            {},
            tok["access_token"],
        )
        self.send_json(status, obj)

    def webhook_receive(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            n = 0
        if n <= 0 or n > 1024 * 1024:
            self.send_json(400, {"ok": False, "error": "invalid_body_size"})
            return
        raw = self.rfile.read(n)
        sig_header = self.headers.get("TikTok-Signature", "") or self.headers.get("Tiktok-Signature", "")
        parts = {}
        for item in sig_header.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                parts[k.strip()] = v.strip()
        ts = parts.get("t", "")
        supplied = parts.get("s", "")
        valid = False
        try:
            if ts and supplied and abs(int(time.time()) - int(ts)) <= 300:
                signed = ts.encode("utf-8") + b"." + raw
                candidates = [x for x in (CLIENT_SECRET, SANDBOX_CLIENT_SECRET) if x]
                valid = any(hmac.compare_digest(hmac.new(sec.encode("utf-8"), signed, hashlib.sha256).hexdigest(), supplied) for sec in candidates)
        except Exception:
            valid = False
        if not valid:
            self.send_json(401, {"ok": False, "error": "invalid_webhook_signature"})
            return
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            self.send_json(400, {"ok": False, "error": "invalid_json"})
            return
        event_id = hashlib.sha256(raw).hexdigest()
        rec = {
            "received_at": int(time.time()),
            "event_id": event_id,
            "client_key": obj.get("client_key"),
            "event": obj.get("event"),
            "create_time": obj.get("create_time"),
            "user_openid": obj.get("user_openid"),
            "content": obj.get("content"),
        }
        try:
            with open(WEBHOOK_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        self.send_json(200, {"ok": True})

    def webhook_status(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        rows = []
        try:
            with open(WEBHOOK_LOG_PATH, "r", encoding="utf-8") as f:
                rows = [json.loads(x) for x in f.read().splitlines()[-20:] if x.strip()]
        except Exception:
            rows = []
        self.send_json(200, {"ok": True, "events": rows})

    def direct_video(self, query):
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
        privacy = (query.get("privacy_level") or ["SELF_ONLY"])[0]
        title = (query.get("title") or [""])[0][:2200]
        post_info = {
            "privacy_level": privacy,
            "title": title,
            "disable_duet": (query.get("disable_duet") or ["false"])[0].lower() == "true",
            "disable_comment": (query.get("disable_comment") or ["false"])[0].lower() == "true",
            "disable_stitch": (query.get("disable_stitch") or ["false"])[0].lower() == "true",
        }
        init_body = {
            "post_info": post_info,
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": n,
                "chunk_size": n,
                "total_chunk_count": 1,
            },
        }
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
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
                "User-Agent": "Nameless-Dhamma-TikTok/1.1",
            },
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                upload_status = r.status
                r.read()
        except urllib.error.HTTPError as e:
            raw_err = e.read().decode("utf-8", "replace")
            self.send_json(e.code, {"ok": False, "stage": "upload", "error": clean_error(raw_err or e.reason), "publish_id": publish_id})
            return
        self.send_json(200, {"ok": True, "publish_id": publish_id, "upload_status": upload_status})

    def photo_publish(self, query):
        if not authorized_setup(self.headers, query):
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            n = 0
        if n <= 0 or n > 1024 * 1024:
            self.send_json(400, {"ok": False, "error": "invalid_body_size"})
            return
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            self.send_json(400, {"ok": False, "error": "invalid_json"})
            return
        images = payload.get("photo_images") or []
        if not isinstance(images, list) or not images or len(images) > 35:
            self.send_json(400, {"ok": False, "error": "photo_images_required"})
            return
        for u in images:
            if not isinstance(u, str) or not u.startswith("https://namelessdhamma.org/"):
                self.send_json(400, {"ok": False, "error": "photo_url_must_use_verified_nd_prefix"})
                return
        mode = str(payload.get("post_mode") or "MEDIA_UPLOAD").upper()
        if mode not in ("MEDIA_UPLOAD", "DIRECT_POST"):
            self.send_json(400, {"ok": False, "error": "invalid_post_mode"})
            return
        try:
            tok = get_token()
        except Exception as e:
            self.send_json(401, {"ok": False, "error": clean_error(e)})
            return
        post_info = {
            "title": str(payload.get("title") or "")[:90],
            "description": str(payload.get("description") or "")[:4000],
        }
        if mode == "DIRECT_POST":
            post_info.update({
                "privacy_level": str(payload.get("privacy_level") or "SELF_ONLY"),
                "disable_comment": bool(payload.get("disable_comment", False)),
                "auto_add_music": bool(payload.get("auto_add_music", False)),
                "brand_content_toggle": bool(payload.get("brand_content_toggle", False)),
                "brand_organic_toggle": bool(payload.get("brand_organic_toggle", False)),
            })
        body = {
            "media_type": "PHOTO",
            "post_mode": mode,
            "post_info": post_info,
            "source_info": {
                "source": "PULL_FROM_URL",
                "photo_images": images,
                "photo_cover_index": int(payload.get("photo_cover_index") or 0),
            },
            "is_aigc": bool(payload.get("is_aigc", False)),
        }
        status, obj = api_json(
            "https://open.tiktokapis.com/v2/post/publish/content/init/",
            "POST",
            body,
            tok["access_token"],
        )
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
        if path == "/tiktok/oauth/sandbox/start":
            return self.sandbox_oauth_start()
        if path == "/tiktok/oauth/callback":
            return self.oauth_callback(query)
        if path == "/tiktok/oauth/status":
            return self.oauth_status()
        if path == "/tiktok/token/export":
            return self.token_export(query)
        if path == "/tiktok/user":
            return self.user_info(query)
        if path == "/tiktok/videos":
            return self.video_list(query)
        if path == "/tiktok/creator":
            return self.creator_info(query)
        if path == "/tiktok/webhooks/status":
            return self.webhook_status(query)
        if path == "/tiktok/upload/status":
            return self.upload_status(query)
        return self.forward()

    def do_POST(self):
        if self.is_tiktok_mcp():
            return self.handle_tiktok_mcp()
        path, query = self.parse()
        if path == "/tiktok/webhooks":
            return self.webhook_receive()
        if path == "/tiktok/upload":
            return self.upload_video(query)
        if path == "/tiktok/direct/video":
            return self.direct_video(query)
        if path == "/tiktok/photo":
            return self.photo_publish(query)
        return self.forward()

    def do_PUT(self):
        return self.forward()

    def do_PATCH(self):
        return self.forward()

    def do_DELETE(self):
        return self.forward()

print("ND_TIKTOK_FRONT_V1_2_READY " + json.dumps({
    "port": PORT,
    "inner_port": INNER_PORT,
    "configured": bool(CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI),
    "setup_protected": bool(SETUP_TOKEN),
    "mcp_configured": bool(MCP_PATH_TOKEN),
}, ensure_ascii=False), flush=True)

ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()