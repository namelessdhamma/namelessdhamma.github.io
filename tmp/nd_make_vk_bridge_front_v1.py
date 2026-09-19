import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT=int(os.environ.get("PORT","3000"))
INNER_PORT=int(os.environ.get("ND_MAKE_VK_INNER_PORT","3992"))
BRIDGE_TOKEN=os.environ.get("ND_MAKE_VK_BRIDGE_TOKEN","").strip()
MCP_PATH_TOKEN=os.environ.get("ND_MAKE_VK_MCP_PATH_TOKEN","").strip()
MAKE_WEBHOOK=os.environ.get("ND_MAKE_VK_WEBHOOK_URL","").strip()
QUALIFY_NONCE=os.environ.get("ND_MAKE_VK_QUALIFY_NONCE","").strip()
CURRENT_FRONT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a7f53b5f351942838c6ea2e14280308529cefd5/tmp/nd_remotion_mcp_front_v1.py"
INNER_PATH="/tmp/nd_make_vk_inner_front.py"

urllib.request.urlretrieve(CURRENT_FRONT,INNER_PATH)
env=dict(os.environ)
env["PORT"]=str(INNER_PORT)
child=subprocess.Popen([sys.executable,"-u",INNER_PATH],env=env)
INNER="http://127.0.0.1:%d"%INNER_PORT

VERSION="1.1.0"
GITHUB_MCP_PATH="/make/vk/github-mcp"
GITHUB_OIDC_ISSUER="https://token.actions.githubusercontent.com"
GITHUB_OIDC_AUDIENCE="nd-make-vk"
GITHUB_OIDC_REPOSITORY="namelessdhamma/nameless-dhamma-vault"
GITHUB_OIDC_WORKFLOW="namelessdhamma/nameless-dhamma-vault/.github/workflows/nd-make-vk-mcp.yml@refs/heads/main"

def redact(value):
    s=str(value)
    for secret in (BRIDGE_TOKEN,MCP_PATH_TOKEN,MAKE_WEBHOOK,QUALIFY_NONCE):
        if secret:
            s=s.replace(secret,"[REDACTED]")
    return s[:4000]

def b64url_decode(value):
    s=str(value)
    s += "="*((4-len(s)%4)%4)
    return base64.urlsafe_b64decode(s.encode("ascii"))

def verify_github_oidc(token):
    parts=str(token or "").split(".")
    if len(parts)!=3:
        raise RuntimeError("github_oidc_invalid_jwt")
    header=json.loads(b64url_decode(parts[0]).decode("utf-8"))
    claims=json.loads(b64url_decode(parts[1]).decode("utf-8"))
    if header.get("alg")!="RS256" or not header.get("kid"):
        raise RuntimeError("github_oidc_alg_or_kid_invalid")
    with urllib.request.urlopen(GITHUB_OIDC_ISSUER+"/.well-known/jwks",timeout=15) as r:
        jwks=json.loads(r.read().decode("utf-8"))
    key=next((k for k in (jwks.get("keys") or []) if k.get("kid")==header.get("kid")),None)
    if not key or key.get("kty")!="RSA":
        raise RuntimeError("github_oidc_signing_key_not_found")
    n=int.from_bytes(b64url_decode(key["n"]),"big")
    e=int.from_bytes(b64url_decode(key["e"]),"big")
    sig=int.from_bytes(b64url_decode(parts[2]),"big")
    klen=(n.bit_length()+7)//8
    em=pow(sig,e,n).to_bytes(klen,"big")
    digest=hashlib.sha256((parts[0]+"."+parts[1]).encode("ascii")).digest()
    digest_info=bytes.fromhex("3031300d060960864801650304020105000420")+digest
    pad_len=klen-len(digest_info)-3
    if pad_len<8:
        raise RuntimeError("github_oidc_signature_encoding_invalid")
    expected=b"\x00\x01"+(b"\xff"*pad_len)+b"\x00"+digest_info
    if not hmac.compare_digest(em,expected):
        raise RuntimeError("github_oidc_signature_invalid")
    now=int(time.time())
    if claims.get("iss")!=GITHUB_OIDC_ISSUER:
        raise RuntimeError("github_oidc_issuer_invalid")
    aud=claims.get("aud")
    auds=aud if isinstance(aud,list) else [aud]
    if GITHUB_OIDC_AUDIENCE not in auds:
        raise RuntimeError("github_oidc_audience_invalid")
    if claims.get("repository")!=GITHUB_OIDC_REPOSITORY:
        raise RuntimeError("github_oidc_repository_invalid")
    if claims.get("ref")!="refs/heads/main":
        raise RuntimeError("github_oidc_ref_invalid")
    if claims.get("job_workflow_ref")!=GITHUB_OIDC_WORKFLOW:
        raise RuntimeError("github_oidc_workflow_invalid")
    if claims.get("actor")!="namelessdhamma":
        raise RuntimeError("github_oidc_actor_invalid")
    if int(claims.get("exp") or 0)<now-30:
        raise RuntimeError("github_oidc_expired")
    if int(claims.get("iat") or 0)>now+60:
        raise RuntimeError("github_oidc_iat_invalid")
    if claims.get("nbf") is not None and int(claims.get("nbf") or 0)>now+30:
        raise RuntimeError("github_oidc_nbf_invalid")
    return {
        "repository":claims.get("repository"),
        "ref":claims.get("ref"),
        "workflow":claims.get("job_workflow_ref"),
        "run_id":claims.get("run_id"),
        "actor":claims.get("actor"),
    }

def github_oidc_from_headers(headers):
    auth=str(headers.get("Authorization") or "")
    if not auth.lower().startswith("bearer "):
        raise RuntimeError("github_oidc_bearer_required")
    return verify_github_oidc(auth[7:].strip())

def health():
    return {
        "ok":bool(MAKE_WEBHOOK and BRIDGE_TOKEN and MCP_PATH_TOKEN),
        "service":"nd-make-vk-railway-bridge",
        "version":VERSION,
        "make_webhook_configured":bool(MAKE_WEBHOOK),
        "http_auth_configured":bool(BRIDGE_TOKEN),
        "mcp_path_configured":bool(MCP_PATH_TOKEN),
        "github_oidc_mcp":GITHUB_MCP_PATH,
        "github_oidc_audience":GITHUB_OIDC_AUDIENCE,
        "inner_runtime":"nd-remotion-mcp-front-v1",
        "route":"Railway -> Make webhook -> VK Video",
    }

def validate_upload(args):
    if not isinstance(args,dict):
        raise RuntimeError("body_must_be_object")
    try:
        group_id=int(args.get("group_id") or 228330620)
    except Exception:
        raise RuntimeError("group_id_invalid")
    title=str(args.get("title") or "").strip()
    description=str(args.get("description") or "")
    file_url=str(args.get("file_url") or "").strip()
    if group_id<=0:
        raise RuntimeError("group_id_invalid")
    if not title or len(title)>200:
        raise RuntimeError("title_required_max_200")
    if len(description)>10000:
        raise RuntimeError("description_too_long")
    if not file_url.startswith("https://"):
        raise RuntimeError("file_url_must_be_https")
    return {
        "group_id":group_id,
        "title":title,
        "description":description,
        "file_url":file_url,
    }

def make_upload(args):
    if not MAKE_WEBHOOK:
        raise RuntimeError("make_webhook_not_configured")
    payload=validate_upload(args)
    url=MAKE_WEBHOOK+"?"+urllib.parse.urlencode({
        "group_id":str(payload["group_id"]),
        "title":payload["title"],
        "description":payload["description"],
        "file_url":payload["file_url"],
    })
    req=urllib.request.Request(url,headers={"User-Agent":"ND-Make-VK-Railway-Bridge/1.0"},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=600) as r:
            raw=r.read().decode("utf-8","replace")
            try:
                body=json.loads(raw) if raw else {}
            except Exception:
                body={"raw":raw[:8000]}
            return {"ok":200<=r.status<300,"make_status":r.status,"result":body}
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try:
            body=json.loads(raw) if raw else {}
        except Exception:
            body={"raw":redact(raw)}
        return {"ok":False,"make_status":e.code,"result":body}

TOOLS=[
    {
        "name":"vk_video_health",
        "description":"Check the Railway-to-Make VK Video bridge configuration without publishing anything.",
        "inputSchema":{"type":"object","properties":{},"additionalProperties":False},
    },
    {
        "name":"vk_video_upload",
        "description":"Upload an MP4 to the Nameless Dhamma VK Video community through the Railway -> Make -> VK route. Requires an HTTPS source URL.",
        "inputSchema":{
            "type":"object",
            "properties":{
                "group_id":{"type":"integer","default":228330620},
                "title":{"type":"string","minLength":1,"maxLength":200},
                "description":{"type":"string","maxLength":10000},
                "file_url":{"type":"string","minLength":8},
            },
            "required":["title","file_url"],
            "additionalProperties":False,
        },
    },
]

def tool_call(name,args):
    if name=="vk_video_health":
        return health()
    if name=="vk_video_upload":
        return make_upload(args or {})
    raise RuntimeError("unknown_tool:"+str(name))

class H(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,*a):
        pass

    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def authorized_http(self):
        if not BRIDGE_TOKEN:
            return False
        auth=str(self.headers.get("Authorization") or "")
        candidate=auth[7:].strip() if auth.lower().startswith("bearer ") else str(self.headers.get("X-ND-Bridge-Token") or "").strip()
        return bool(candidate and hmac.compare_digest(candidate,BRIDGE_TOKEN))

    def is_mcp(self):
        expected="/make/vk/mcp/"+MCP_PATH_TOKEN if MCP_PATH_TOKEN else ""
        return bool(expected and self.path.split("?",1)[0]==expected)

    def handle_mcp(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0)
            if n<=0 or n>1024*1024:
                raise RuntimeError("invalid_body_size")
            msg=json.loads(self.rfile.read(n).decode("utf-8","replace"))
            method=str(msg.get("method") or "")
            mid=msg.get("id")
            if method=="initialize":
                p=msg.get("params") or {}
                result_obj={
                    "protocolVersion":p.get("protocolVersion") or "2025-06-18",
                    "capabilities":{"tools":{}},
                    "serverInfo":{"name":"nd-make-vk-railway-mcp","version":VERSION},
                }
            elif method=="notifications/initialized":
                self.send_response(204)
                self.send_header("Content-Length","0")
                self.end_headers()
                return
            elif method=="tools/list":
                result_obj={"tools":TOOLS}
            elif method=="tools/call":
                p=msg.get("params") or {}
                data=tool_call(str(p.get("name") or ""),p.get("arguments") or {})
                result_obj={
                    "content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],
                    "structuredContent":data,
                    "isError":not bool(data.get("ok",True)) if isinstance(data,dict) else False,
                }
            else:
                self.send_json(200,{"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"Method not found"}})
                return
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":result_obj})
        except Exception as e:
            self.send_json(200,{"jsonrpc":"2.0","id":None,"error":{"code":-32000,"message":redact(e)}})

    def forward(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0)
            body=self.rfile.read(n) if n else None
            headers={k:v for k,v in self.headers.items() if k.lower() not in ("host","connection","content-length","transfer-encoding")}
            req=urllib.request.Request(INNER+self.path,data=body,headers=headers,method=self.command)
            try:
                with urllib.request.urlopen(req,timeout=600) as r:
                    raw=r.read()
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in ("connection","transfer-encoding","content-length"):
                            self.send_header(k,v)
                    self.send_header("Content-Length",str(len(raw)))
                    self.end_headers()
                    if raw:
                        self.wfile.write(raw)
            except urllib.error.HTTPError as e:
                raw=e.read()
                self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() not in ("connection","transfer-encoding","content-length"):
                        self.send_header(k,v)
                self.send_header("Content-Length",str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{"ok":False,"error":"inner_forward_failed","detail":redact(e)})

    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path=="/make/vk/health":
            self.send_json(200 if health()["ok"] else 503,health())
            return
        if path=="/make/vk/qualify":
            if not QUALIFY_NONCE:
                return self.send_json(404,{"ok":False,"error":"qualification_disabled"})
            q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            nonce=str((q.get("nonce") or [""])[0])
            if not nonce or not hmac.compare_digest(nonce,QUALIFY_NONCE):
                return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                out=make_upload({
                    "group_id":228330620,
                    "title":"ND Railway Make bridge qualification — temporary",
                    "description":"Temporary Railway -> Make -> VK qualification. Delete after verification.",
                    "file_url":"https://filesamples.com/samples/video/mp4/sample_640x360.mp4",
                })
                return self.send_json(200 if out.get("ok") else 502,out)
            except Exception as e:
                return self.send_json(500,{"ok":False,"error":redact(e)})
        return self.forward()

    def do_POST(self):
        path=self.path.split("?",1)[0]
        if self.is_mcp():
            return self.handle_mcp()
        if path==GITHUB_MCP_PATH:
            try:
                github_oidc_from_headers(self.headers)
            except Exception as e:
                return self.send_json(403,{"ok":False,"error":redact(e)})
            return self.handle_mcp()
        if path=="/make/vk/video":
            if not self.authorized_http():
                return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                n=int(self.headers.get("Content-Length","0") or 0)
                if n<=0 or n>1024*1024:
                    raise RuntimeError("invalid_body_size")
                args=json.loads(self.rfile.read(n).decode("utf-8","replace"))
                out=make_upload(args)
                return self.send_json(200 if out.get("ok") else 502,out)
            except Exception as e:
                return self.send_json(400,{"ok":False,"error":redact(e)})
        return self.forward()

    def do_PUT(self):
        return self.forward()
    def do_PATCH(self):
        return self.forward()
    def do_DELETE(self):
        return self.forward()
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length","0")
        self.end_headers()

print("ND_MAKE_VK_RAILWAY_BRIDGE_READY "+json.dumps({
    "version":VERSION,
    "port":PORT,
    "inner_port":INNER_PORT,
    "make_webhook_configured":bool(MAKE_WEBHOOK),
    "http_auth_configured":bool(BRIDGE_TOKEN),
    "mcp_path_configured":bool(MCP_PATH_TOKEN),
    "github_oidc_mcp":GITHUB_MCP_PATH,
},ensure_ascii=False),flush=True)

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
