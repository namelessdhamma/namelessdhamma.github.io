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
INNER_PORT=int(os.environ.get("ND_VEDISMM_MEDIA_INNER_PORT","3977"))
BASE=os.environ.get("ND_VEDISMM_BASE_URL","https://vedismm.ru/api/v1").rstrip("/")
EMAIL=os.environ.get("ND_VEDISMM_EMAIL","").strip()
PASSWORD=os.environ.get("ND_VEDISMM_PASSWORD","")
PROBE_TOKEN=os.environ.get("ND_VEDISMM_PROBE_TOKEN","").strip()
ACCOUNT_ID=160
TARGET_GROUP_ID="228330620"
SAMPLE_URL="https://filesamples.com/samples/video/mp4/sample_640x360.mp4"
SESSION_PATH="/tmp/nd_vedismm_media_session.json"

UPSTREAM="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a7f53b5f351942838c6ea2e14280308529cefd5/tmp/nd_remotion_mcp_front_v1.py"
UPSTREAM_PATH="/tmp/nd_existing_gateway_vedismm_media_inner.py"
urllib.request.urlretrieve(UPSTREAM,UPSTREAM_PATH)
child_env=dict(os.environ)
child_env["PORT"]=str(INNER_PORT)
child=subprocess.Popen([sys.executable,"-u",UPSTREAM_PATH],env=child_env)
INNER="http://127.0.0.1:%d"%INNER_PORT

SECRETS=[EMAIL,PASSWORD,PROBE_TOKEN]
def clean(v):
    s=str(v)
    for sec in SECRETS:
        if sec: s=s.replace(sec,"[REDACTED]")
    return s[:3000]

def api_json(path,method="GET",body=None,bearer=None,extra_headers=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
    headers={"Accept":"application/json","User-Agent":"ND-VediSMM-Media-Probe/0.1"}
    if data is not None: headers["Content-Type"]="application/json; charset=utf-8"
    if bearer: headers["Authorization"]="Bearer "+bearer
    if isinstance(extra_headers,dict): headers.update({str(k):str(v) for k,v in extra_headers.items()})
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read().decode("utf-8","replace")
            return r.status,(json.loads(raw or "{}") if raw else {}),dict(r.headers)
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: obj=json.loads(raw or "{}")
        except Exception: obj={"raw":clean(raw)}
        return e.code,obj,dict(e.headers)

def save_session(data):
    if not isinstance(data,dict): return
    now=int(time.time())
    out=dict(data)
    out["expires_at"]=now+int(out.get("expires_in") or 0)
    out["refresh_expires_at"]=now+int(out.get("refresh_expires_in") or 0)
    with open(SESSION_PATH,"w",encoding="utf-8") as f: json.dump(out,f)
    try: os.chmod(SESSION_PATH,0o600)
    except Exception: pass

def load_session():
    try:
        with open(SESSION_PATH,"r",encoding="utf-8") as f: obj=json.load(f)
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}

def get_access():
    now=int(time.time())
    s=load_session()
    tok=str(s.get("access_token") or "").strip()
    if tok and int(s.get("expires_at") or 0)>now+60:
        return tok,"cache"
    ref=str(s.get("refresh_token") or "").strip()
    if ref and int(s.get("refresh_expires_at") or 0)>now+60:
        code,obj,_=api_json("/auth/refresh","POST",{"refresh_token":ref})
        if code==200:
            data=obj.get("data") or {}
            tok=str(data.get("access_token") or "").strip()
            if tok:
                save_session(data); return tok,"refresh"
    code,obj,_=api_json("/auth/login","POST",{"email":EMAIL,"password":PASSWORD,"client_name":"ND VediSMM media qualification"})
    if code!=200:
        raise RuntimeError("login_http_%s:%s"%(code,clean(obj)))
    data=obj.get("data") or {}
    tok=str(data.get("access_token") or "").strip()
    if not tok: raise RuntimeError("login_access_missing")
    save_session(data)
    return tok,"login"

def account_readback(token):
    code,obj,_=api_json("/accounts/%d"%ACCOUNT_ID,bearer=token)
    if code!=200:
        raise RuntimeError("account_http_%s:%s"%(code,clean(obj)))
    row=obj.get("data") or {}
    safe={k:row.get(k) for k in ("id","network","connection_mode","target_type","external_id","title","username","status","attention_required","has_error")}
    ext=str(row.get("external_id") or "").lstrip("-")
    match=(str(row.get("network") or "")=="vk" and ext==TARGET_GROUP_ID)
    return safe,match

def multipart_upload(token,blob,filename="nd-vedismm-qualification.mp4"):
    boundary="----NDVediSMMBoundary7MA4YWxkTrZu0gW"
    head=(
        "--"+boundary+"\r\n"
        'Content-Disposition: form-data; name="file"; filename="'+filename+'"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8")
    tail=("\r\n--"+boundary+"--\r\n").encode("utf-8")
    data=head+blob+tail
    headers={
        "Accept":"application/json",
        "Authorization":"Bearer "+token,
        "Content-Type":"multipart/form-data; boundary="+boundary,
        "Content-Length":str(len(data)),
        "User-Agent":"ND-VediSMM-Media-Probe/0.1",
    }
    req=urllib.request.Request(BASE+"/media",data=data,headers=headers,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=120) as r:
            raw=r.read().decode("utf-8","replace")
            return r.status,(json.loads(raw or "{}") if raw else {})
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: obj=json.loads(raw or "{}")
        except Exception: obj={"raw":clean(raw)}
        return e.code,obj

def run_preflight_probe():
    if not (EMAIL and PASSWORD and PROBE_TOKEN):
        return 503,{"ok":False,"stage":"config"}
    token,source=get_access()
    acct,match=account_readback(token)
    if not match:
        return 409,{"ok":False,"stage":"account_mismatch","account":acct}
    body={
        "title":"ND VediSMM qualification — temporary",
        "content":"Temporary qualification video for Nameless Dhamma. This post is not published by this probe.",
        "account_ids":[ACCOUNT_ID],
        "media_ids":[426],
        "append_signature":False,
        "content_overrides":{},
        "first_comment":""
    }
    pcode,pobj,pheaders=api_json("/posts","POST",body,token,{"Idempotency-Key":"nd-vk-video-draft-account160-media426-v1"})
    if pcode!=201:
        return 502,{"ok":False,"stage":"draft_create","http":pcode,"detail":clean(pobj),"account":acct}
    post=(pobj.get("data") or {}) if isinstance(pobj,dict) else {}
    draft_safe={k:post.get(k) for k in ("id","title","status","version","scheduled_at","published_at")}
    constraint_body={
        "account_ids":[ACCOUNT_ID],
        "media_ids":[426],
        "content":"Temporary qualification video for Nameless Dhamma. This post is not published by this probe.",
        "append_signature":False,
        "content_overrides":{},
        "first_comment":""
    }
    ccode,cobj,_=api_json("/posts/constraints","POST",constraint_body,token)
    if ccode!=200:
        return 502,{"ok":False,"stage":"constraints","http":ccode,"detail":clean(cobj),"draft":draft_safe,"account":acct}
    return 200,{
        "ok":True,
        "stage":"draft_and_constraints_only",
        "token_source":source,
        "account":acct,
        "draft":draft_safe,
        "constraints":cobj,
        "vk_publication_performed":False,
        "secrets_exposed":False,
    }

def run_media_probe():
    if not (EMAIL and PASSWORD and PROBE_TOKEN):
        return 503,{"ok":False,"stage":"config"}
    token,source=get_access()
    acct,match=account_readback(token)
    if not match:
        return 409,{"ok":False,"stage":"account_mismatch","account":acct}
    req=urllib.request.Request(SAMPLE_URL,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        blob=r.read(2*1024*1024)
        ctype=str(r.headers.get("Content-Type") or "")
    if len(blob)<1000 or len(blob)>=2*1024*1024:
        return 502,{"ok":False,"stage":"sample_download","bytes":len(blob),"content_type":ctype}
    code,obj=multipart_upload(token,blob)
    if code not in (200,201):
        return 502,{"ok":False,"stage":"media_upload","http":code,"detail":clean(obj),"account":acct}
    row=obj.get("data") or {}
    safe_media={k:row.get(k) for k in ("id","type","original_name","mime","extension","size","width","height","duration","status","created_at","updated_at")}
    return 200,{
        "ok":True,
        "stage":"media_uploaded_only",
        "token_source":source,
        "account":acct,
        "account_target_match":match,
        "sample_bytes":len(blob),
        "sample_content_type":ctype,
        "media":safe_media,
        "vk_publication_performed":False,
        "secrets_exposed":False,
    }

class H(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,*a): pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(raw))); self.end_headers()
        if raw: self.wfile.write(raw)
    def authorized(self):
        supplied=self.headers.get("X-ND-VediSMM-Probe-Token","")
        if not supplied:
            try: supplied=(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token") or [""])[0]
            except Exception: supplied=""
        return bool(PROBE_TOKEN and supplied and hmac.compare_digest(str(supplied),PROBE_TOKEN))
    def forward(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0); body=self.rfile.read(n) if n else None
            headers={k:v for k,v in self.headers.items() if k.lower() not in ("host","connection","content-length","transfer-encoding")}
            req=urllib.request.Request(INNER+self.path,data=body,headers=headers,method=self.command)
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read(); self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in ("connection","transfer-encoding","content-length"): self.send_header(k,v)
                    self.send_header("Content-Length",str(len(raw))); self.end_headers()
                    if raw: self.wfile.write(raw)
            except urllib.error.HTTPError as e:
                raw=e.read(); self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() not in ("connection","transfer-encoding","content-length"): self.send_header(k,v)
                self.send_header("Content-Length",str(len(raw))); self.end_headers()
                if raw: self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{"ok":False,"error":"inner_forward_failed","detail":clean(e)})
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path=="/vedismm/qualify/preflight":
            if not self.authorized(): return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                code,obj=run_preflight_probe()
                print("ND_VEDISMM_PREFLIGHT "+json.dumps({"http":code,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(code,obj)
            except Exception as e:
                obj={"ok":False,"stage":"exception","error":clean(e)}
                print("ND_VEDISMM_PREFLIGHT "+json.dumps({"http":500,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(500,obj)
        if path=="/vedismm/qualify/media":
            if not self.authorized(): return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                code,obj=run_media_probe()
                print("ND_VEDISMM_MEDIA_PROBE "+json.dumps({"http":code,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(code,obj)
            except Exception as e:
                obj={"ok":False,"stage":"exception","error":clean(e)}
                print("ND_VEDISMM_MEDIA_PROBE "+json.dumps({"http":500,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(500,obj)
        if path=="/vedismm/qualify/media/health":
            return self.send_json(200,{"ok":True,"service":"nd-vedismm-media-probe","configured":bool(EMAIL and PASSWORD and PROBE_TOKEN),"account_id":ACCOUNT_ID})
        return self.forward()
    def do_POST(self): return self.forward()
    def do_PUT(self): return self.forward()
    def do_PATCH(self): return self.forward()
    def do_DELETE(self): return self.forward()
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Content-Length","0"); self.end_headers()

print("ND_VEDISMM_MEDIA_PROBE_V0_1_READY "+json.dumps({"port":PORT,"inner_port":INNER_PORT,"account_id":ACCOUNT_ID},ensure_ascii=False),flush=True)
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
