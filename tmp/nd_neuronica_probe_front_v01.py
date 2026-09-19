import html
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT=int(os.environ.get("PORT","3000"))
INNER_PORT=int(os.environ.get("ND_NEURONICA_INNER_PORT","3977"))
EMAIL=os.environ.get("ND_NEURONICA_EMAIL","").strip()
PASSWORD=os.environ.get("ND_NEURONICA_PASSWORD","")
PROBE_TOKEN=os.environ.get("ND_VEDISMM_PROBE_TOKEN","").strip()
VK_TOKEN=os.environ.get("VK_GROUP_TOKEN","").strip()
VK_VERSION=os.environ.get("VK_API_VERSION","5.199").strip() or "5.199"
BASE="https://neironica.ru"

UPSTREAM="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a7f53b5f351942838c6ea2e14280308529cefd5/tmp/nd_remotion_mcp_front_v1.py"
UPSTREAM_PATH="/tmp/nd_existing_gateway_neuronica_inner.py"
urllib.request.urlretrieve(UPSTREAM,UPSTREAM_PATH)
child_env=dict(os.environ); child_env["PORT"]=str(INNER_PORT)
child=subprocess.Popen([sys.executable,"-u",UPSTREAM_PATH],env=child_env)
INNER="http://127.0.0.1:%d"%INNER_PORT
SECRETS=[EMAIL,PASSWORD,PROBE_TOKEN,VK_TOKEN]

def clean(v):
    s=str(v)
    for sec in SECRETS:
        if sec: s=s.replace(sec,"[REDACTED]")
    return s[:6000]

def vk_method(method, params=None):
    form=dict(params or {})
    form["access_token"]=VK_TOKEN
    form["v"]=VK_VERSION
    data=urllib.parse.urlencode(form).encode("utf-8")
    req=urllib.request.Request("https://api.vk.com/method/"+method,data=data,headers={"User-Agent":"ND-VK-ShortVideo-Probe/0.1"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            raw=r.read().decode("utf-8","replace")
            return r.status,json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: obj=json.loads(raw or "{}")
        except Exception: obj={"raw":clean(raw)}
        return e.code,obj

def session_opener():
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders=[("User-Agent","ND-Neuronica-Probe/0.1"),("Accept","text/html,application/xhtml+xml,application/json")]
    return opener,jar

def fetch(opener,path,method="GET",form=None,body=None,headers=None,timeout=45):
    url=path if path.startswith("http") else BASE+path
    data=None
    h=dict(headers or {})
    if form is not None:
        data=urllib.parse.urlencode(form).encode("utf-8")
        h["Content-Type"]="application/x-www-form-urlencoded"
    elif body is not None:
        data=json.dumps(body,ensure_ascii=False).encode("utf-8")
        h["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    try:
        with opener.open(req,timeout=timeout) as r:
            raw=r.read()
            return r.status,r.geturl(),raw.decode("utf-8","replace"),dict(r.headers)
    except urllib.error.HTTPError as e:
        raw=e.read()
        return e.code,e.geturl(),raw.decode("utf-8","replace"),dict(e.headers)

def login():
    opener,jar=session_opener()
    gcode,gurl,gtext,gheaders=fetch(opener,"/login.php")
    code,url,text,headers=fetch(opener,"/login.php","POST",form={
        "email":EMAIL,
        "password":PASSWORD,
        "website":"",
        "phone_number":"",
        "remember":"1",
    })
    dcode,durl,dtext,dheaders=fetch(opener,"/dashboard.php")
    authenticated=(dcode==200 and "/login.php" not in durl and ("Выйти" in dtext or "dashboard" in dtext.lower() or "Токен" in dtext))
    err=None
    if not authenticated:
        m=re.search(r'<div[^>]+class=["\'][^"\']*error-message[^"\']*["\'][^>]*>(.*?)</div>',text,re.I|re.S)
        if m:
            err=re.sub(r'<[^>]+>',' ',m.group(1))
            err=html.unescape(re.sub(r'\s+',' ',err)).strip()[:500]
    return opener,jar,{"prefetch_http":gcode,"login_http":code,"login_final":url,"dashboard_http":dcode,"dashboard_final":durl,"authenticated":authenticated,"login_error":err},dtext

def extract_surface(text):
    # Keep only endpoint-ish strings, never page content or credentials.
    vals=set()
    patterns=[
        r"""fetch\(\s*['"]([^'"]+)['"]""",
        r"""(?:href|action)=['"]([^'"]+)['"]""",
        r"""['"]((?:/api/|/ajax/|/oauth/|/integrations/|/auto-publish|/social|/vk/)[^'"]*)['"]""",
        r"""['"]([^'"]*(?:vk|vkontakte|publish|media|oauth)[^'"]*)['"]""",
    ]
    for p in patterns:
        for m in re.findall(p,text,re.I):
            s=html.unescape(str(m)).strip()
            if not s or len(s)>500: continue
            if EMAIL.lower() in s.lower(): continue
            if PASSWORD and PASSWORD in s: continue
            vals.add(s)
    out=[]
    for s in sorted(vals):
        low=s.lower()
        if any(k in low for k in ("vk","vkontakte","publish","media","oauth","social","integration","api/")):
            out.append(s)
    return out[:120]

def discover():
    if not EMAIL or not PASSWORD:
        return 503,{"ok":False,"stage":"config"}
    opener,jar,auth,dashboard=login()
    if not auth["authenticated"]:
        return 502,{"ok":False,"stage":"login","auth":auth}
    pages=["/auto-publishing.php","/media_manager.php","/dashboard.php"]
    results={}
    all_endpoints=set()
    for p in pages:
        code,url,text,headers=fetch(opener,p)
        eps=extract_surface(text)
        results[p]={"http":code,"final_url":url,"chars":len(text),"endpoints":eps}
        all_endpoints.update(eps)
    cookies=[{"name":c.name,"domain":c.domain,"secure":c.secure,"expires":c.expires is not None} for c in jar]
    return 200,{
        "ok":True,
        "stage":"authenticated_surface_discovery",
        "auth":auth,
        "cookies":cookies,
        "pages":results,
        "candidate_endpoints":sorted(all_endpoints)[:160],
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
        supplied=self.headers.get("X-ND-Probe-Token","")
        if not supplied:
            try: supplied=(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token") or [""])[0]
            except Exception: supplied=""
        return bool(PROBE_TOKEN and supplied==PROBE_TOKEN)
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
        if path=="/vk/qualify/shortvideo-read":
            if not self.authorized(): return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                code,obj=vk_method("shortVideo.getOwnerVideos",{"owner_id":-228330620,"count":1})
                safe={"http":code}
                if isinstance(obj,dict) and obj.get("error"):
                    err=obj.get("error") or {}
                    safe.update({"ok":False,"error_code":err.get("error_code"),"error_msg":err.get("error_msg")})
                else:
                    resp=(obj or {}).get("response") if isinstance(obj,dict) else None
                    safe.update({"ok":True,"response_type":type(resp).__name__,"count":(resp or {}).get("count") if isinstance(resp,dict) else None})
                print("ND_VK_SHORTVIDEO_READ "+json.dumps(safe,ensure_ascii=False),flush=True)
                return self.send_json(200,safe)
            except Exception as e:
                return self.send_json(500,{"ok":False,"stage":"exception","error":clean(e)})
        if path=="/neuronica/qualify/discover":
            if not self.authorized(): return self.send_json(403,{"ok":False,"error":"forbidden"})
            try:
                code,obj=discover()
                print("ND_NEURONICA_DISCOVER "+json.dumps({"http":code,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(code,obj)
            except Exception as e:
                obj={"ok":False,"stage":"exception","error":clean(e)}
                print("ND_NEURONICA_DISCOVER "+json.dumps({"http":500,"result":obj},ensure_ascii=False),flush=True)
                return self.send_json(500,obj)
        if path=="/neuronica/qualify/health":
            return self.send_json(200,{"ok":True,"service":"nd-neuronica-probe","configured":bool(EMAIL and PASSWORD and PROBE_TOKEN)})
        return self.forward()
    def do_POST(self): return self.forward()
    def do_PUT(self): return self.forward()
    def do_PATCH(self): return self.forward()
    def do_DELETE(self): return self.forward()
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Content-Length","0"); self.end_headers()

print("ND_NEURONICA_PROBE_V0_1_READY "+json.dumps({"port":PORT,"inner_port":INNER_PORT,"configured":bool(EMAIL and PASSWORD and PROBE_TOKEN)},ensure_ascii=False),flush=True)
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
