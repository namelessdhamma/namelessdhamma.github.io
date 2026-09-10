import os,json,threading,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request,urlopen

PORT=int(os.environ.get("PORT","3000"))
TOKEN=os.environ.get("VK_GROUP_TOKEN","")
V=os.environ.get("VK_API_VERSION","5.199")
state={"ok":True,"token_present":bool(TOKEN),"group_id":None,"vk_error":None}

def vk(method,p):
    q=dict(p);q["access_token"]=TOKEN;q["v"]=V
    req=Request("https://api.vk.com/method/"+method,data=urlencode(q).encode(),method="POST")
    with urlopen(req,timeout=20) as r:j=json.loads(r.read().decode())
    if "error" in j:
        e=j["error"];raise RuntimeError("VK error %s: %s"%(e.get("error_code"),e.get("error_msg")))
    return j.get("response")

def init():
    time.sleep(1)
    try:
        r=vk("groups.getById",{"group_ids":"namelessdhamma"})
        if isinstance(r,list) and r: state["group_id"]=r[0].get("id")
        elif isinstance(r,dict):
            a=r.get("groups") or []
            if a: state["group_id"]=a[0].get("id")
        print("VK_RESOLVE",json.dumps({"group_id":state["group_id"]}),flush=True)
    except Exception as e:
        state["vk_error"]=(str(e).replace(TOKEN,"[redacted]") if TOKEN else str(e))[:500]
        print("VK_RESOLVE_ERROR",state["vk_error"],flush=True)

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        if self.path.split("?",1)[0]!="/health":
            self.send_response(404);self.end_headers();return
        b=json.dumps(state).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)

print("ND_VK_GATEWAY_MINI_START",json.dumps({"port":PORT,"token_present":bool(TOKEN)}),flush=True)
threading.Thread(target=init,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
