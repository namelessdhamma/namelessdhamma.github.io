import os, json, threading, time, random, urllib.request, urllib.error, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PUBLIC_PORT=int(os.environ.get("PORT","3000"))
LEGACY_PORT=int(os.environ.get("ND_VK_LEGACY_PORT","3001"))
LEGACY_URL=f"http://127.0.0.1:{LEGACY_PORT}"
TOKEN=os.environ.get("VK_GROUP_TOKEN","")
V=os.environ.get("VK_API_VERSION","5.199")
ROUTE_TOKEN=os.environ.get("ND_VK_MCP_ROUTE_TOKEN","").strip()
MCP_PATH="/vk/mcp/"+ROUTE_TOKEN if ROUTE_TOKEN else ""
ALLOWED={int(x.strip()) for x in os.environ.get("VK_ALLOWED_USER_IDS","").replace(";",",").split(",") if x.strip().isdigit()}
LEGACY_SOURCE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py"

def cleanerr(e):
    s=str(e)
    for secret in (TOKEN,ROUTE_TOKEN):
        if secret: s=s.replace(secret,"[redacted]")
    return s[:1200]

def vk(method, params=None, timeout=25):
    if not TOKEN: raise RuntimeError("VK_GROUP_TOKEN missing")
    p=dict(params or {})
    p["access_token"]=TOKEN
    p["v"]=V
    data=urllib.parse.urlencode({k:str(v) for k,v in p.items() if v is not None}).encode()
    req=urllib.request.Request("https://api.vk.com/method/"+method,data=data,method="POST",
                               headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"nd-vk-mcp/1.1"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=json.loads(r.read().decode())
    if "error" in body:
        e=body["error"]
        raise RuntimeError("VK %s error %s: %s"%(method,e.get("error_code"),e.get("error_msg")))
    return body.get("response")

def require_peer(value):
    try: peer=int(value)
    except Exception: raise RuntimeError("peer_id must be an integer")
    if not ALLOWED: raise RuntimeError("VK_ALLOWED_USER_IDS is empty; access is fail-closed")
    if peer not in ALLOWED: raise RuntimeError("peer_id is outside VK_ALLOWED_USER_IDS")
    return peer

def tools():
    ro={"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True}
    wr={"readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":True}
    return [
      {"name":"vk_status","description":"Verify direct VK API reachability and community identity without returning message contents.",
       "inputSchema":{"type":"object","properties":{},"additionalProperties":False},"annotations":ro},
      {"name":"vk_get_users","description":"Read basic VK profile data for allow-listed users.",
       "inputSchema":{"type":"object","properties":{"user_ids":{"type":"array","items":{"type":"integer"}}},"additionalProperties":False},"annotations":ro},
      {"name":"vk_get_conversations","description":"Read recent direct VK conversations, filtered to allow-listed users.",
       "inputSchema":{"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":100,"default":20},"offset":{"type":"integer","minimum":0,"default":0},"unread_only":{"type":"boolean","default":False}},"additionalProperties":False},"annotations":ro},
      {"name":"vk_get_history","description":"Read message history for one allow-listed VK peer.",
       "inputSchema":{"type":"object","properties":{"peer_id":{"type":"integer"},"count":{"type":"integer","minimum":1,"maximum":100,"default":30},"offset":{"type":"integer","minimum":0,"default":0}},"required":["peer_id"],"additionalProperties":False},"annotations":ro},
      {"name":"vk_send_message","description":"Send a plain-text VK message to one allow-listed peer.",
       "inputSchema":{"type":"object","properties":{"peer_id":{"type":"integer"},"message":{"type":"string","minLength":1,"maxLength":3500},"reply_to":{"type":"integer"}},"required":["peer_id","message"],"additionalProperties":False},"annotations":wr},
      {"name":"vk_mark_as_read","description":"Mark messages from one allow-listed VK peer as read.",
       "inputSchema":{"type":"object","properties":{"peer_id":{"type":"integer"}},"required":["peer_id"],"additionalProperties":False},"annotations":wr},
    ]

def call_tool(name,args):
    args=args or {}
    if name=="vk_status":
        r=vk("groups.getById")
        return {"ok":True,"transport":"DIRECT_VK_API","api_version":V,"allowed_peer_count":len(ALLOWED),"group":r}
    if name=="vk_get_users":
        ids=args.get("user_ids")
        ids=sorted(ALLOWED) if ids is None else [require_peer(x) for x in ids]
        if not ids:return {"ok":True,"response":[]}
        return {"ok":True,"response":vk("users.get",{"user_ids":",".join(str(x) for x in ids),"fields":"first_name,last_name,screen_name"})}
    if name=="vk_get_conversations":
        count=max(1,min(int(args.get("count",20)),100)); offset=max(0,int(args.get("offset",0)))
        filt="unread" if bool(args.get("unread_only",False)) else "all"
        resp=vk("messages.getConversations",{"count":count,"offset":offset,"filter":filt,"extended":0}) or {}
        items=(resp.get("items") or []) if isinstance(resp,dict) else []
        filtered=[]
        for item in items:
            try: pid=int((((item.get("conversation") or {}).get("peer") or {}).get("id")))
            except Exception: continue
            if pid in ALLOWED: filtered.append(item)
        return {"ok":True,"response":{"count":len(filtered),"items":filtered}}
    if name=="vk_get_history":
        peer=require_peer(args.get("peer_id"))
        return {"ok":True,"response":vk("messages.getHistory",{"peer_id":peer,"count":max(1,min(int(args.get("count",30)),100)),"offset":max(0,int(args.get("offset",0))),"rev":0})}
    if name=="vk_send_message":
        peer=require_peer(args.get("peer_id")); message=str(args.get("message") or "").strip()
        if not message: raise RuntimeError("message must not be empty")
        if len(message)>3500: raise RuntimeError("message exceeds 3500-character MCP limit")
        p={"peer_id":peer,"random_id":random.randint(1,2000000000),"message":message}
        if args.get("reply_to") is not None:p["reply_to"]=int(args["reply_to"])
        return {"ok":True,"response":vk("messages.send",p)}
    if name=="vk_mark_as_read":
        peer=require_peer(args.get("peer_id"))
        return {"ok":True,"response":vk("messages.markAsRead",{"peer_id":peer})}
    raise RuntimeError("unknown tool: "+str(name))

def result(i,r): return {"jsonrpc":"2.0","id":i,"result":r}
def error(i,c,m): return {"jsonrpc":"2.0","id":i,"error":{"code":c,"message":m}}

def dispatch(req):
    if not isinstance(req,dict): return 400,error(None,-32600,"Invalid Request")
    rid=req.get("id"); method=req.get("method"); params=req.get("params") or {}
    if method=="initialize":
        ver=params.get("protocolVersion") or "2025-06-18"
        return 200,result(rid,{"protocolVersion":ver,"capabilities":{"tools":{"listChanged":False}},
                              "serverInfo":{"name":"ND VK","version":"1.1.0"},
                              "instructions":"Direct bounded VK access. Make remains an independent fallback."})
    if method in ("notifications/initialized","notifications/cancelled"):
        return 202,None
    if method=="ping": return 200,result(rid,{})
    if method=="tools/list": return 200,result(rid,{"tools":tools()})
    if method=="tools/call":
        try:
            data=call_tool(params.get("name"),params.get("arguments") or {})
            return 200,result(rid,{"content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],"structuredContent":data,"isError":False})
        except Exception as e:
            msg=cleanerr(e)
            return 200,result(rid,{"content":[{"type":"text","text":msg}],"isError":True})
    return 404,error(rid,-32601,"Method not found")

def start_legacy():
    os.environ["PORT"]=str(LEGACY_PORT)
    try:
        src=urllib.request.urlopen(LEGACY_SOURCE,timeout=30).read().decode("utf-8")
        exec(compile(src,"nd_vk_gateway_v14_web_recovery.py","exec"),{"__name__":"__main__"})
    except Exception as e:
        print("LEGACY_START_ERROR",cleanerr(e),flush=True)

class Gateway(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,*a): pass
    def send_json(self,status,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.end_headers()
        if raw:self.wfile.write(raw)
    def is_mcp(self):
        return bool(MCP_PATH) and self.path.split("?",1)[0]==MCP_PATH
    def check_origin(self):
        origin=(self.headers.get("Origin") or "").strip()
        if not origin:return True
        return origin in ("https://chatgpt.com","https://chat.openai.com")
    def do_GET(self):
        if self.is_mcp():
            if not self.check_origin(): self.send_json(403,error(None,-32000,"Forbidden origin")); return
            self.send_response(405); self.send_header("Allow","POST"); self.send_header("Content-Length","0"); self.end_headers(); return
        self.proxy()
    def do_DELETE(self):
        if self.is_mcp():
            self.send_response(405); self.send_header("Allow","POST"); self.send_header("Content-Length","0"); self.end_headers(); return
        self.proxy()
    def do_POST(self):
        if self.is_mcp():
            if not self.check_origin(): self.send_json(403,error(None,-32000,"Forbidden origin")); return
            try:
                n=int(self.headers.get("Content-Length","0")); req=json.loads(self.rfile.read(n).decode() or "{}")
                status,body=dispatch(req)
                if body is None:
                    self.send_response(status); self.send_header("Content-Length","0"); self.end_headers()
                else:self.send_json(status,body)
            except Exception as e:self.send_json(400,error(None,-32700,cleanerr(e)))
            return
        self.proxy()
    def proxy(self):
        try:
            n=int(self.headers.get("Content-Length","0") or "0"); body=self.rfile.read(n) if n else None
            target=LEGACY_URL+self.path
            headers={k:v for k,v in self.headers.items() if k.lower() not in ("host","content-length","connection")}
            req=urllib.request.Request(target,data=body,method=self.command,headers=headers)
            try:
                with urllib.request.urlopen(req,timeout=190) as r:
                    data=r.read(); status=r.status; rh=r.headers
            except urllib.error.HTTPError as e:
                data=e.read(); status=e.code; rh=e.headers
            self.send_response(status)
            for k,v in rh.items():
                if k.lower() not in ("transfer-encoding","connection","content-length"): self.send_header(k,v)
            self.send_header("Content-Length",str(len(data))); self.end_headers()
            if data:self.wfile.write(data)
        except Exception as e:self.send_json(502,{"error":"legacy_proxy_failed","detail":cleanerr(e)})

print("ND_VK_DIRECT_MCP_GATEWAY_START",json.dumps({"public_port":PUBLIC_PORT,"legacy_port":LEGACY_PORT,"mcp_configured":bool(MCP_PATH),"tool_count":len(tools()),"allowed_count":len(ALLOWED)}),flush=True)
threading.Thread(target=start_legacy,daemon=True).start()
for _ in range(50):
    try:
        urllib.request.urlopen(LEGACY_URL+"/health",timeout=1).read()
        print("ND_VK_LEGACY_READY",flush=True); break
    except Exception: time.sleep(0.2)
os.environ["PORT"]=str(PUBLIC_PORT)
ThreadingHTTPServer(("0.0.0.0",PUBLIC_PORT),Gateway).serve_forever()
