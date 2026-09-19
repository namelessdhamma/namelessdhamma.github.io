import base64
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT=int(os.environ.get("PORT","3000"))
INNER_PORT=int(os.environ.get("ND_REMOTION_INNER_PORT","3988"))
PATH_TOKEN=os.environ.get("ND_REMOTION_MCP_PATH_TOKEN","").strip()
GITHUB_PAT=os.environ.get("ND_GITHUB_PAT","").strip()
REPO=os.environ.get("ND_REMOTION_GITHUB_REPO","namelessdhamma/nameless-dhamma-vault").strip()
BRANCH=os.environ.get("ND_REMOTION_GITHUB_BRANCH","main").strip()
CURRENT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/437a52b8b998c2d1033563a9497610403dc105f7/tmp/nd_runtime_resilience_entry_v9.py"
INNER_PATH="/tmp/nd_current_production_entry_remotion_inner.py"

urllib.request.urlretrieve(CURRENT,INNER_PATH)
env=dict(os.environ)
env["PORT"]=str(INNER_PORT)
child=subprocess.Popen([sys.executable,"-u",INNER_PATH],env=env)
INNER="http://127.0.0.1:%d"%INNER_PORT

def clean(x):
    s=str(x)
    for secret in (PATH_TOKEN,GITHUB_PAT):
        if secret:
            s=s.replace(secret,"[REDACTED]")
    return s[:4000]

def gh(path,method="GET",body=None):
    if not GITHUB_PAT:
        raise RuntimeError("github_pat_missing")
    url="https://api.github.com/repos/%s/%s"%(REPO,path.lstrip("/"))
    data=None if body is None else json.dumps(body).encode("utf-8")
    headers={
        "Authorization":"Bearer "+GITHUB_PAT,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"ND-Remotion-Railway-MCP/1.0",
    }
    if data is not None:
        headers["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            raw=r.read().decode("utf-8","replace")
            return r.status,(json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: obj=json.loads(raw or "{}")
        except Exception: obj={"raw":clean(raw)}
        return e.code,obj

def new_request_id():
    return time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+secrets.token_hex(6)

def submit(args):
    calls=args.get("calls") or []
    if not isinstance(calls,list) or len(calls)>20:
        raise RuntimeError("calls_must_be_array_max_20")
    for c in calls:
        if not isinstance(c,dict) or not str(c.get("tool") or ""):
            raise RuntimeError("each_call_requires_tool")
    rid=str(args.get("request_id") or "").strip() or new_request_id()
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:" for ch in rid) or len(rid)>120:
        raise RuntimeError("invalid_request_id")
    payload={
        "request_id":rid,
        "purpose":str(args.get("purpose") or "Railway Remotion MCP fallback"),
        "submitted_via":"railway-remotion-mcp",
        "submitted_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "calls":calls,
    }
    path=".nd-runtime/remotion/commands/%s.json"%rid
    content=base64.b64encode(json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8")).decode("ascii")
    status,obj=gh("contents/"+urllib.parse.quote(path,safe="/"),"PUT",{
        "message":"remotion fallback command: "+rid,
        "content":content,
        "branch":BRANCH,
    })
    if status not in (200,201):
        raise RuntimeError("github_command_write_%s:%s"%(status,clean(obj)))
    return {
        "ok":True,
        "state":"SUBMITTED",
        "request_id":rid,
        "command_path":path,
        "result_path":".nd-runtime/remotion/results/%s.json"%rid,
        "transport":"Railway MCP -> GitHub command/result -> GitHub Actions Remotion worker",
        "independence":"CONTROL_SURFACE_ONLY; render compute depends on GitHub Actions",
    }

def result(args):
    rid=str(args.get("request_id") or "").strip()
    if not rid:
        raise RuntimeError("request_id_required")
    path=".nd-runtime/remotion/results/%s.json"%rid
    status,obj=gh("contents/"+urllib.parse.quote(path,safe="/")+"?ref="+urllib.parse.quote(BRANCH,safe=""))
    if status==404:
        return {"ok":True,"state":"PENDING","request_id":rid,"result_path":path}
    if status!=200:
        raise RuntimeError("github_result_read_%s:%s"%(status,clean(obj)))
    raw=base64.b64decode(str(obj.get("content") or "").replace("\n","")).decode("utf-8","replace")
    parsed=json.loads(raw)
    return {"ok":True,"state":"COMPLETE","request_id":rid,"result":parsed}

def status():
    code,obj=gh("contents")
    return {
        "ok":code==200,
        "service":"nd-remotion-railway-mcp-relay",
        "version":"1.0.2",
        "github_status":code,
        "repository":REPO,
        "branch":BRANCH,
        "path_token_configured":bool(PATH_TOKEN),
        "github_pat_configured":bool(GITHUB_PAT),
        "render_worker":"GitHub Actions",
        "railway_role":"MCP/control relay; not heavy render compute",
        "failure_domain_note":"Railway endpoint remains callable independently, but submitted renders depend on GitHub availability.",
    }

def selftest():
    repo_status,_=gh("contents")
    runs_status,runs_obj=gh("actions/workflows/nd-remotion-fallback.yml/runs?per_page=5")
    runs=[]
    if runs_status==200 and isinstance(runs_obj,dict):
        for row in (runs_obj.get("workflow_runs") or [])[:5]:
            runs.append({
                "id":row.get("id"),
                "event":row.get("event"),
                "status":row.get("status"),
                "conclusion":row.get("conclusion"),
                "head_sha":row.get("head_sha"),
                "created_at":row.get("created_at"),
                "updated_at":row.get("updated_at"),
            })
    return {
        "ok":repo_status==200 and runs_status==200,
        "service":"nd-remotion-railway-mcp-relay",
        "version":"1.0.1",
        "mcp_surface":{
            "serverInfo":{"name":"nd-remotion-railway-mcp","version":"1.0.1"},
            "tools":[t["name"] for t in TOOLS],
            "tools_count":len(TOOLS),
        },
        "github_actions":{
            "status":runs_status,
            "workflow":"nd-remotion-fallback.yml",
            "runs":runs,
        },
        "secrets_exposed":False,
    }

TOOLS=[
    {"name":"remotion_selftest","description":"Run a non-mutating self-test of the Railway Remotion MCP control surface and inspect recent GitHub Actions fallback runs without exposing credentials.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"remotion_status","description":"Check the ND Remotion fallback MCP control route and GitHub worker reachability. Does not render.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"remotion_submit","description":"Submit one bounded sequence of operational Remotion MCP tool calls to the GitHub Actions render worker. Returns request_id immediately; poll remotion_result.","inputSchema":{"type":"object","properties":{"request_id":{"type":"string"},"purpose":{"type":"string"},"calls":{"type":"array","maxItems":20,"items":{"type":"object","properties":{"tool":{"type":"string"},"arguments":{"type":"object"},"timeout_ms":{"type":"integer","minimum":1000,"maximum":1200000}},"required":["tool"],"additionalProperties":False}}},"required":["calls"],"additionalProperties":False}},
    {"name":"remotion_result","description":"Read the durable result of a previously submitted ND Remotion GitHub Actions job.","inputSchema":{"type":"object","properties":{"request_id":{"type":"string"}},"required":["request_id"],"additionalProperties":False}},
]

def tool_call(name,args):
    if name=="remotion_selftest": return selftest()
    if name=="remotion_status": return status()
    if name=="remotion_submit": return submit(args or {})
    if name=="remotion_result": return result(args or {})
    raise RuntimeError("unknown_tool:"+str(name))

class H(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,*a): pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        if raw: self.wfile.write(raw)
    def forward(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0)
            body=self.rfile.read(n) if n else None
            headers={k:v for k,v in self.headers.items() if k.lower() not in ("host","connection","content-length","transfer-encoding")}
            req=urllib.request.Request(INNER+self.path,data=body,headers=headers,method=self.command)
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read()
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in ("connection","transfer-encoding","content-length"):
                            self.send_header(k,v)
                    self.send_header("Content-Length",str(len(raw)))
                    self.end_headers()
                    if raw: self.wfile.write(raw)
            except urllib.error.HTTPError as e:
                raw=e.read()
                self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() not in ("connection","transfer-encoding","content-length"):
                        self.send_header(k,v)
                self.send_header("Content-Length",str(len(raw)))
                self.end_headers()
                if raw: self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{"ok":False,"error":"inner_forward_failed","detail":clean(e)})
    def is_mcp(self):
        expected="/remotion/mcp/"+PATH_TOKEN if PATH_TOKEN else ""
        return bool(expected and self.path.split("?",1)[0]==expected)
    def handle_mcp(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0)
            if n<=0 or n>1024*1024: raise RuntimeError("invalid_body_size")
            msg=json.loads(self.rfile.read(n).decode("utf-8","replace"))
            method=str(msg.get("method") or "")
            mid=msg.get("id")
            if method=="initialize":
                p=msg.get("params") or {}
                result_obj={"protocolVersion":p.get("protocolVersion") or "2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"nd-remotion-railway-mcp","version":"1.0.2"}}
            elif method=="notifications/initialized":
                self.send_response(204); self.send_header("Content-Length","0"); self.end_headers(); return
            elif method=="tools/list":
                result_obj={"tools":TOOLS}
            elif method=="tools/call":
                p=msg.get("params") or {}
                data=tool_call(str(p.get("name") or ""),p.get("arguments") or {})
                result_obj={"content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],"structuredContent":data,"isError":False}
            else:
                self.send_json(200,{"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"Method not found"}}); return
            self.send_json(200,{"jsonrpc":"2.0","id":mid,"result":result_obj})
        except Exception as e:
            self.send_json(200,{"jsonrpc":"2.0","id":None,"error":{"code":-32000,"message":clean(e)}})
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path=="/remotion/health":
            try: self.send_json(200,status())
            except Exception as e: self.send_json(503,{"ok":False,"error":clean(e)})
            return
        if path=="/remotion/selftest":
            try: self.send_json(200,selftest())
            except Exception as e: self.send_json(503,{"ok":False,"error":clean(e)})
            return
        return self.forward()
    def do_POST(self):
        if self.is_mcp(): return self.handle_mcp()
        return self.forward()
    def do_PUT(self): return self.forward()
    def do_PATCH(self): return self.forward()
    def do_DELETE(self): return self.forward()
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Content-Length","0"); self.end_headers()

print("ND_REMOTION_RAILWAY_MCP_V1_0_2_READY "+json.dumps({
    "port":PORT,
    "inner_port":INNER_PORT,
    "path_token_configured":bool(PATH_TOKEN),
    "github_pat_configured":bool(GITHUB_PAT),
    "repo":REPO,
},ensure_ascii=False),flush=True)
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
