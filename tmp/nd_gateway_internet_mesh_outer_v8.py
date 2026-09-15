import importlib.util, json, os, subprocess, sys, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get("PORT","3000"))
CHILD_PORT=int(os.environ.get("ND_MESH_CHILD_PORT","3003"))
CHILD_URL="http://127.0.0.1:%d"%CHILD_PORT
RELAY_TOKEN=(os.environ.get("ND_INTERNET_MESH_ROUTE_TOKEN") or os.environ.get("ND_BROWSERLESS_RELAY_TOKEN") or "").strip()
V7_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c84304463f06241f806b8e51947c6aed3b623829/tmp/nd_gateway_browserless_frontproxy_v7_drive_router.py"
LIB_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/785b394e1290bc394dfcaa88dc4a0864b38dde27/tmp/nd_internet_mesh_gha_v1.py"

def fetch(url,path):
    raw=urllib.request.urlopen(url,timeout=30).read()
    open(path,"wb").write(raw)
    return raw

v7=fetch(V7_URL,"/tmp/nd_current_v7.py").decode("utf-8")
needle="threading.Thread(target=drive_qualify_once,daemon=True).start()"
if v7.count(needle)!=1: raise RuntimeError("unexpected_drive_qualification_invocation_count")
v7=v7.replace(needle,"# Drive startup qualification invocation disabled after Generation 8.1 adoption",1)
open("/tmp/nd_current_v7.py","w",encoding="utf-8").write(v7)
env=dict(os.environ);env["PORT"]=str(CHILD_PORT)
child=subprocess.Popen([sys.executable,"-u","/tmp/nd_current_v7.py"],env=env)

fetch(LIB_URL,"/tmp/nd_mesh_provider_lib.py")
spec=importlib.util.spec_from_file_location("nd_mesh_provider_lib","/tmp/nd_mesh_provider_lib.py")
mesh=importlib.util.module_from_spec(spec);spec.loader.exec_module(mesh)

DEDUPE={}
MAX_DEDUPE=256
PROBES={"started_at":time.time(),"providers":{}}

def clean(x):
    s=mesh.clean(x)
    if RELAY_TOKEN:
        s=s.replace(RELAY_TOKEN,"[REDACTED]").replace(urllib.parse.quote(RELAY_TOKEN,safe=""),"[REDACTED]")
    return s[:5000]

def child_health():
    try:
        with urllib.request.urlopen(CHILD_URL+"/health",timeout=8) as r:
            raw=r.read()
            try:body=json.loads(raw.decode("utf-8","replace"))
            except Exception:body={"raw":raw.decode("utf-8","replace")[:500]}
            return r.status,body
    except Exception as e:return 502,{"ok":False,"error":clean(e)}

def provider_tools(provider):
    init,msg=mesh.request(provider,"tools/list",{},45)
    allow=mesh.PROVIDERS[provider]["allow"]
    tools=[x for x in ((msg.get("result") or {}).get("tools") or []) if x.get("name") in allow]
    return {"ok":True,"provider":provider,"serverInfo":((init.get("result") or {}).get("serverInfo") or {}),"tools":tools,"count":len(tools)}

def run_startup_probes():
    time.sleep(3)
    for p,cfg in mesh.PROVIDERS.items():
        rec={"configured":bool(cfg["token"])}
        if rec["configured"]:
            try:
                out=provider_tools(p);rec.update({"reachable":True,"tool_count":out["count"],"serverInfo":out.get("serverInfo") or {}})
            except Exception as e:rec.update({"reachable":False,"error":clean(e)})
        PROBES["providers"][p]=rec
    PROBES["finished_at"]=time.time()
threading.Thread(target=run_startup_probes,daemon=True).start()

def list_kernel_by_name(name):
    out=mesh.call_tool("kernel","manage_browsers",{"action":"list","status":"active","query":name,"limit":50,"offset":0,"context":"Checking for an existing request-key-bound browser before failover creation to prevent duplicate material browser starts."},60)
    items=mesh.deep_find(out,"items")
    if not isinstance(items,list):return None
    for item in items:
        if isinstance(item,dict) and item.get("name")==name:return item
    return None

def sensitive_call(provider,tool,args,request_key):
    if not request_key:raise RuntimeError("request_key_required_for_sensitive_start")
    key="%s:%s:%s"%(provider,tool,request_key)
    if key in DEDUPE:return DEDUPE[key]
    if provider=="kernel" and tool=="manage_browsers" and str((args or {}).get("action") or "")=="create":
        args=dict(args or {})
        name=str(args.get("name") or ("nd-mesh-"+mesh.hashlib.sha256(request_key.encode()).hexdigest()[:18]))
        args["name"]=name
        existing=list_kernel_by_name(name)
        if existing:out={"ok":True,"reused":True,"provider_result":existing}
        else:out={"ok":True,"reused":False,"provider_result":mesh.call_tool(provider,tool,args,120)}
    elif provider=="tinyfish" and tool=="run_web_automation":
        args=dict(args or {});args.setdefault("session_id",mesh.request_uuid(request_key))
        out={"ok":True,"provider_result":mesh.call_tool(provider,tool,args,180),"session_id":args["session_id"]}
    else:out={"ok":True,"provider_result":mesh.call_tool(provider,tool,args,150)}
    if len(DEDUPE)>=MAX_DEDUPE:
        try:DEDUPE.pop(next(iter(DEDUPE)))
        except Exception:DEDUPE.clear()
    DEDUPE[key]=out
    return out

def kernel_smoke(request_key):
    name="nd-rw-smoke-"+mesh.hashlib.sha256(request_key.encode()).hexdigest()[:16]
    created=sensitive_call("kernel","manage_browsers",{"action":"create","name":name,"start_url":"https://example.com","headless":True,"timeout_seconds":120,"telemetry_enabled":False,"context":"Creating a temporary browser through Railway failover qualification with request-key recovery and guaranteed cleanup."},request_key)
    obj=created.get("provider_result") or {}
    sid=mesh.deep_find(obj,"session_id") or mesh.deep_find(obj,"id")
    if not sid:raise RuntimeError("kernel_smoke_missing_session_id:"+clean(obj))
    try:
        check=mesh.call_tool("kernel","execute_playwright_code",{"session_id":sid,"code":"return { url: page.url(), title: await page.title(), heading: await page.locator('h1').textContent() };","context":"Reading Example Domain through the failover-created browser to verify end-to-end Railway browser execution."},120)
        if "Example Domain" not in json.dumps(check,ensure_ascii=False):raise RuntimeError("kernel_smoke_content_mismatch:"+clean(check))
        return {"ok":True,"provider":"kernel","scenario":"create_read_delete","reused_start":bool(created.get("reused")),"content_verified":True}
    finally:
        mesh.call_tool("kernel","manage_browsers",{"action":"delete","session_id":sid,"context":"Deleting the temporary Railway failover qualification browser so no orphan browser session remains."},60)

def tinyfish_smoke(request_key):
    return mesh.tinyfish_smoke(request_key)

def status(live=False):
    c,body=child_health()
    out={"ok":c==200,"service":"ND Internet Access Mesh","version":"1.0.0-qualification","child_v7_health":c,"route_auth_configured":bool(RELAY_TOKEN),"startup_probes":PROBES,"providers":{}}
    for p,cfg in mesh.PROVIDERS.items():
        rec={"configured":bool(cfg["token"]),"allowlisted_tools":len(cfg["allow"])}
        if live and rec["configured"]:
            try:
                x=provider_tools(p);rec.update({"reachable":True,"tool_count":x["count"],"serverInfo":x.get("serverInfo") or {}})
            except Exception as e:rec.update({"reachable":False,"error":clean(e)})
        out["providers"][p]=rec
    return out

def dispatch(name,args):
    args=args or {}
    if name=="internet_status":return status(bool(args.get("live")))
    if name=="internet_provider_tools":return provider_tools(str(args.get("provider") or "").lower())
    if name=="internet_smoke":
        p=str(args.get("provider") or "").lower();rk=str(args.get("request_key") or "")
        if p=="kernel":return kernel_smoke(rk)
        if p=="tinyfish":return tinyfish_smoke(rk)
        raise RuntimeError("smoke_provider_must_be_kernel_or_tinyfish")
    if name=="internet_call":
        p=str(args.get("provider") or "").lower();tool=str(args.get("tool") or "");a=args.get("arguments") or {};rk=str(args.get("request_key") or "")
        if p not in mesh.PROVIDERS:raise RuntimeError("unknown_provider")
        if tool not in mesh.PROVIDERS[p]["allow"]:raise RuntimeError("tool_not_allowlisted")
        sens=(p=="tinyfish" and tool=="run_web_automation") or (p=="kernel" and tool=="manage_browsers" and str(a.get("action") or "")=="create")
        if sens:return sensitive_call(p,tool,a,rk)
        return {"ok":True,"provider":p,"tool":tool,"provider_result":mesh.call_tool(p,tool,a,150)}
    raise RuntimeError("unknown_mesh_tool")

def tool_defs():
    return [
      {"name":"internet_status","description":"Read shared Internet Access Mesh and current provider health.","inputSchema":{"type":"object","properties":{"live":{"type":"boolean","default":False}},"additionalProperties":False}},
      {"name":"internet_provider_tools","description":"List current allow-listed tools for one upstream provider.","inputSchema":{"type":"object","properties":{"provider":{"type":"string","enum":["browserless","kernel","tinyfish"]}},"required":["provider"],"additionalProperties":False}},
      {"name":"internet_call","description":"Call one allow-listed provider tool. Sensitive starts require request_key.","inputSchema":{"type":"object","properties":{"provider":{"type":"string","enum":["browserless","kernel","tinyfish"]},"tool":{"type":"string"},"arguments":{"type":"object"},"request_key":{"type":"string"}},"required":["provider","tool"],"additionalProperties":False}},
      {"name":"internet_smoke","description":"Run bounded Kernel or TinyFish end-to-end failover smoke.","inputSchema":{"type":"object","properties":{"provider":{"type":"string","enum":["kernel","tinyfish"]},"request_key":{"type":"string","minLength":1}},"required":["provider","request_key"],"additionalProperties":False}},
    ]

def auth(headers):
    if not RELAY_TOKEN:return False
    return (headers.get("Authorization") or "").strip()=="Bearer "+RELAY_TOKEN or (headers.get("X-ND-Bridge-Key") or "").strip()==RELAY_TOKEN

def rpc_ok(rid,obj):
    return {"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":json.dumps(obj,ensure_ascii=False)}],"structuredContent":obj}}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8");self.send_response(code);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def read_json(self):
        n=int(self.headers.get("Content-Length","0") or 0);return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
    def forward(self):
        n=int(self.headers.get("Content-Length","0") or 0);body=self.rfile.read(n) if n else None;headers={}
        for k,v in self.headers.items():
            if k.lower() not in ("host","connection","content-length","transfer-encoding"):headers[k]=v
        req=urllib.request.Request(CHILD_URL+self.path,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read();self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() not in ("connection","transfer-encoding","content-length"):self.send_header(k,v)
                self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read();self.send_response(e.code);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        except Exception as e:self.send_json(502,{"error":"mesh_child_unavailable","detail":clean(e)})
    def do_GET(self):
        p=self.path.split("?",1)[0]
        if p=="/internet/health":self.send_json(200,status(False));return
        if p=="/internet/status":
            if not auth(self.headers):self.send_json(403,{"ok":False,"error":"forbidden"});return
            self.send_json(200,status(True));return
        self.forward()
    def do_POST(self):
        p=self.path.split("?",1)[0]
        if p=="/mcp":
            if not auth(self.headers):self.send_json(401,{"jsonrpc":"2.0","id":None,"error":{"code":-32001,"message":"unauthorized"}});return
            try:req=self.read_json()
            except Exception:self.send_json(400,{"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"parse error"}});return
            rid=req.get("id");method=req.get("method")
            try:
                if method=="initialize":
                    pv=((req.get("params") or {}).get("protocolVersion") or "2025-06-18")
                    self.send_json(200,{"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":pv,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"ND Internet Access Mesh","version":"1.0.0-qualification"}}});return
                if method=="notifications/initialized":self.send_response(202);self.send_header("Content-Length","0");self.end_headers();return
                if method=="ping":self.send_json(200,{"jsonrpc":"2.0","id":rid,"result":{}});return
                if method=="tools/list":self.send_json(200,{"jsonrpc":"2.0","id":rid,"result":{"tools":tool_defs()}});return
                if method=="tools/call":
                    q=req.get("params") or {};self.send_json(200,rpc_ok(rid,dispatch(str(q.get("name") or ""),q.get("arguments") or {})));return
                self.send_json(200,{"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"method not found"}})
            except Exception as e:self.send_json(200,{"jsonrpc":"2.0","id":rid,"error":{"code":-32000,"message":clean(e)}})
            return
        if p in ("/internet/call","/internet/smoke"):
            if not auth(self.headers):self.send_json(403,{"ok":False,"error":"forbidden"});return
            try:
                b=self.read_json();out=dispatch("internet_smoke" if p.endswith("smoke") else "internet_call",b);self.send_json(200,out)
            except Exception as e:self.send_json(502,{"ok":False,"error":clean(e)})
            return
        self.forward()

print("ND_INTERNET_MESH_OUTER_V8_START "+json.dumps({"port":PORT,"child_port":CHILD_PORT,"route_auth":bool(RELAY_TOKEN),"providers":{k:bool(v["token"]) for k,v in mesh.PROVIDERS.items()}}),flush=True)
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
