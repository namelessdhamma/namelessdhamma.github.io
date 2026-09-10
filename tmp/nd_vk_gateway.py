import os,json,threading,time,hashlib,random
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request,urlopen

PORT=int(os.environ.get("PORT","3000"))
TOKEN=os.environ.get("VK_GROUP_TOKEN","")
V=os.environ.get("VK_API_VERSION","5.199")
SCREEN=os.environ.get("VK_GROUP_SCREEN_NAME","namelessdhamma").lstrip("@")
PUBLIC_BASE=os.environ.get("VK_PUBLIC_BASE_URL","").rstrip("/")
if not PUBLIC_BASE:
    d=os.environ.get("RAILWAY_PUBLIC_DOMAIN","").strip()
    if d: PUBLIC_BASE="https://"+d
CALLBACK_PATH="/vk/callback"
CALLBACK_URL=PUBLIC_BASE+CALLBACK_PATH if PUBLIC_BASE else ""
SECRET=hashlib.sha256(("nd-vk-callback:"+TOKEN).encode()).hexdigest()[:32] if TOKEN else ""

state={
 "ok":True,"phase":"starting","token_present":bool(TOKEN),"public_base_present":bool(PUBLIC_BASE),
 "group_id":None,"callback_url":CALLBACK_URL or None,"callback_server_id":None,
 "callback_registered":False,"callback_configured":False,"last_error":None,
 "last_event_type":None,"last_event_at":None,"startup_attempts":0
}

def cleanerr(e):
    s=str(e)
    if TOKEN:s=s.replace(TOKEN,"[redacted]")
    return s[:600]

def vk(method,p=None,timeout=20):
    if not TOKEN: raise RuntimeError("VK_GROUP_TOKEN missing")
    q=dict(p or {});q["access_token"]=TOKEN;q["v"]=V
    req=Request("https://api.vk.com/method/"+method,data=urlencode({k:str(v) for k,v in q.items() if v is not None}).encode(),method="POST",headers={"Content-Type":"application/x-www-form-urlencoded"})
    with urlopen(req,timeout=timeout) as r:j=json.loads(r.read().decode())
    if "error" in j:
        e=j["error"];raise RuntimeError("VK %s error %s: %s"%(method,e.get("error_code"),e.get("error_msg")))
    return j.get("response")

def resolve_gid():
    r=vk("groups.getById",{"group_ids":SCREEN})
    if isinstance(r,list) and r:return int(r[0]["id"])
    if isinstance(r,dict):
        a=r.get("groups") or []
        if a:return int(a[0]["id"])
        if "id" in r:return int(r["id"])
    raise RuntimeError("community id not resolved")

def servers(gid):
    r=vk("groups.getCallbackServers",{"group_id":gid})
    if isinstance(r,dict):return r.get("items") or []
    return r if isinstance(r,list) else []

def register():
    state["startup_attempts"]+=1
    state["phase"]="resolving_group"
    gid=resolve_gid();state["group_id"]=gid
    if not CALLBACK_URL:raise RuntimeError("public callback URL missing")
    state["phase"]="checking_callback"
    sid=None
    for s in servers(gid):
        if (s.get("url") or "").rstrip("/")==CALLBACK_URL.rstrip("/"):
            sid=int(s["id"]);break
    if sid is None:
        state["phase"]="adding_callback"
        r=vk("groups.addCallbackServer",{"group_id":gid,"url":CALLBACK_URL,"title":"ND Gateway","secret_key":SECRET})
        sid=int((r.get("server_id") if isinstance(r,dict) else r))
    else:
        state["phase"]="securing_callback"
        vk("groups.editCallbackServer",{"group_id":gid,"server_id":sid,"url":CALLBACK_URL,"title":"ND Gateway","secret_key":SECRET})
    state["callback_server_id"]=sid;state["callback_registered"]=True
    time.sleep(1)
    state["phase"]="configuring_callback"
    vk("groups.setCallbackSettings",{"group_id":gid,"server_id":sid,"api_version":V,"message_new":1})
    state["callback_configured"]=True;state["phase"]="ready";state["last_error"]=None
    print("VK_READY",json.dumps({"group_id":gid,"server_id":sid,"callback_configured":True}),flush=True)

def startup():
    if not TOKEN:state["phase"]="waiting_for_token";return
    for wait in (1,3,8,15,30):
        time.sleep(wait)
        try:register();return
        except Exception as e:
            state["last_error"]=cleanerr(e);state["phase"]="retrying"
            print("VK_RETRY",json.dumps({"attempt":state["startup_attempts"],"error":state["last_error"]}),flush=True)
    state["phase"]="error"

def send(peer,text):
    return vk("messages.send",{"peer_id":int(peer),"random_id":random.randint(1,2000000000),"message":text[:3900]})

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def out(self,code,body,ctype="application/json; charset=utf-8"):
        if isinstance(body,(dict,list)):raw=json.dumps(body,ensure_ascii=False).encode()
        else:raw=str(body).encode()
        self.send_response(code);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        p=self.path.split("?",1)[0]
        if p=="/health":self.out(200,state);return
        if p=="/":self.out(200,{"service":"ND VK Gateway","qualification":True,"health":"/health"});return
        self.out(404,{"error":"not_found"})
    def do_POST(self):
        if self.path.split("?",1)[0]!=CALLBACK_PATH:self.out(404,{"error":"not_found"});return
        try:
            n=int(self.headers.get("Content-Length","0"));b=json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:self.out(400,"bad request","text/plain; charset=utf-8");return
        typ=b.get("type");gid=b.get("group_id");state["last_event_type"]=typ;state["last_event_at"]=int(time.time())
        if typ=="confirmation":
            if state.get("group_id") and gid and int(gid)!=int(state["group_id"]):self.out(403,"forbidden","text/plain; charset=utf-8");return
            try:
                r=vk("groups.getCallbackConfirmationCode",{"group_id":int(gid or state["group_id"])})
                code=r.get("code") if isinstance(r,dict) else r
                self.out(200,code,"text/plain; charset=utf-8")
            except Exception as e:
                state["last_error"]=cleanerr(e);self.out(500,"error","text/plain; charset=utf-8")
            return
        if not SECRET or b.get("secret")!=SECRET:self.out(403,"forbidden","text/plain; charset=utf-8");return
        self.out(200,"ok","text/plain; charset=utf-8")
        if typ!="message_new":return
        obj=b.get("object") or {};m=obj.get("message") or obj
        if not isinstance(m,dict):return
        peer=m.get("peer_id");uid=m.get("from_id");text=(m.get("text") or "").strip()
        print("VK_MESSAGE",json.dumps({"from_id":uid,"peer_id":peer,"command":text if text.startswith("/") else "text"},ensure_ascii=False),flush=True)
        if not peer:return
        def reply():
            try:
                if text=="/whoami":send(peer,"VK user id: %s"%uid)
                elif text=="/nd-test":send(peer,"ND VK Gateway: связь с Nameless Dhamma работает.")
                else:send(peer,"ND VK Gateway подключён. GPT-контур ещё не активирован. Для проверки отправьте /nd-test или /whoami.")
            except Exception as e:
                state["last_error"]=cleanerr(e);print("VK_MESSAGE_ERROR",state["last_error"],flush=True)
        threading.Thread(target=reply,daemon=True).start()

print("ND_VK_GATEWAY_START",json.dumps({"port":PORT,"token_present":bool(TOKEN),"callback_url_present":bool(CALLBACK_URL)}),flush=True)
threading.Thread(target=startup,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
