import json, os, sys, urllib.parse, urllib.request
from urllib.error import HTTPError, URLError

PROVIDERS = {
    "browserless": {"url": os.getenv("ND_BROWSERLESS_MCP_URL","https://mcp.browserless.io/mcp"),"token":os.getenv("BROWSERLESS_API_TOKEN","").strip(),"header":"Authorization","prefix":"Bearer ","allow":{"browserless_export","browserless_skill","browserless_agent","browserless_search","browserless_performance","browserless_account","browserless_usage","browserless_sessions","browserless_logs","browserless_smartscraper","browserless_function","browserless_map","browserless_crawl","browserless_profiles"}},
    "kernel": {"url": os.getenv("ND_KERNEL_MCP_URL","https://mcp.onkernel.com/mcp"),"token":os.getenv("KERNEL_API_KEY","").strip(),"header":"Authorization","prefix":"Bearer ","allow":{"get_connection_context","search_docs","manage_profiles","manage_browsers","browser_curl","computer_action","execute_playwright_code","webmcp","manage_replays"}},
    "tinyfish": {"url": os.getenv("ND_TINYFISH_MCP_URL","https://agent.tinyfish.ai/mcp"),"token":os.getenv("TINYFISH_API_KEY","").strip(),"header":"X-API-Key","prefix":"","allow":{"search","fetch_content","run_web_automation","wait_for_run","get_run","list_runs","cancel_run","get_wallet"}},
}
SENSITIVE={("tinyfish","run_web_automation"),("kernel","manage_browsers")}
def clean(x):
    s=str(x)
    for cfg in PROVIDERS.values():
        tok=cfg["token"]
        if tok:s=s.replace(tok,"[REDACTED]").replace(urllib.parse.quote(tok,safe=""),"[REDACTED]")
    return s[:4000]
def parse(raw,ctype=""):
    txt=raw.decode("utf-8","replace")
    if "text/event-stream" in ctype.lower() or txt.lstrip().startswith("data:"):
        vals=[]
        for line in txt.splitlines():
            if line.startswith("data:"):
                p=line[5:].strip()
                if not p or p=="[DONE]":continue
                try:vals.append(json.loads(p))
                except Exception:pass
        if not vals:raise RuntimeError("no_parsable_sse_data")
        return vals[-1]
    return json.loads(txt)
def post(provider,payload,sid=None,timeout=100):
    cfg=PROVIDERS[provider]
    if not cfg["token"]:raise RuntimeError(provider+"_not_configured")
    h={"Accept":"application/json, text/event-stream","Content-Type":"application/json","User-Agent":"ND-GitHub-Failover/1.0"}
    h[cfg["header"]]=cfg["prefix"]+cfg["token"]
    if provider=="tinyfish":h.update({"X-TF-Request-Origin":"nd-github-failover","X-TF-Client-Name":"nd-github-failover","X-TF-Client-Version":"1.0.0"})
    if sid:h.update({"Mcp-Session-Id":sid,"MCP-Protocol-Version":"2025-06-18"})
    req=urllib.request.Request(cfg["url"],data=json.dumps(payload).encode(),headers=h,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        body=e.read().decode("utf-8","replace");raise RuntimeError(f"{provider}_http_{e.code}:{clean(body)}")
    except URLError as e:raise RuntimeError(f"{provider}_network:{clean(e)}")
def initialize(provider):
    status,h,raw=post(provider,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ND GitHub Failover","version":"1.0.0"}}},timeout=45)
    if status!=200:raise RuntimeError("initialize_failed")
    msg=parse(raw,h.get("Content-Type",""));sid=h.get("Mcp-Session-Id") or h.get("mcp-session-id")
    if sid:
        try:post(provider,{"jsonrpc":"2.0","method":"notifications/initialized","params":{}},sid,30)
        except Exception:pass
    return sid,msg
def request(provider,method,params=None,timeout=100):
    sid,init=initialize(provider);payload={"jsonrpc":"2.0","id":2,"method":method}
    if params is not None:payload["params"]=params
    status,h,raw=post(provider,payload,sid,timeout)
    if status!=200:raise RuntimeError(method+"_failed")
    return init,parse(raw,h.get("Content-Type",""))
def main():
    provider=os.getenv("ND_PROVIDER","status").strip().lower();tool=os.getenv("ND_TOOL","").strip()
    args=json.loads(os.getenv("ND_ARGUMENTS_JSON","{}") or "{}");request_key=os.getenv("ND_REQUEST_KEY","").strip()
    if provider=="status":
        out={"ok":True,"service":"ND GitHub Internet Failover","version":"1.0.0-qualification","providers":{k:{"configured":bool(v["token"]),"upstream":v["url"],"allowlisted_tools":len(v["allow"])} for k,v in PROVIDERS.items()},"secrets_returned":False}
    else:
        if provider not in PROVIDERS:raise RuntimeError("unknown_provider")
        if tool in ("","__tools__"):
            init,msg=request(provider,"tools/list",{},45);allow=PROVIDERS[provider]["allow"]
            tools=[x for x in ((msg.get("result") or {}).get("tools") or []) if x.get("name") in allow]
            out={"ok":True,"provider":provider,"serverInfo":((init.get("result") or {}).get("serverInfo") or {}),"tools":tools,"count":len(tools)}
        else:
            if tool not in PROVIDERS[provider]["allow"]:raise RuntimeError("tool_not_allowlisted")
            sensitive=(provider,tool) in SENSITIVE
            if provider=="kernel" and tool=="manage_browsers":sensitive=str(args.get("action") or "")=="create"
            if sensitive and not request_key:raise RuntimeError("request_key_required_for_sensitive_start")
            init,msg=request(provider,"tools/call",{"name":tool,"arguments":args},120)
            out={"ok":True,"provider":provider,"tool":tool,"serverInfo":((init.get("result") or {}).get("serverInfo") or {}),"response":msg,"request_key":request_key or None,"retry_policy":"NO_AUTOMATIC_RETRY_ON_AMBIGUOUS_OR_LOST_RESPONSE" if sensitive else "BOUNDED_RETRY_AFTER_STATUS_CHECK"}
    raw=json.dumps(out,ensure_ascii=False);print(raw);open("nd-internet-failover-result.json","w",encoding="utf-8").write(raw+"\n")
if __name__=="__main__":
    try:main()
    except Exception as e:
        raw=json.dumps({"ok":False,"error":clean(e)},ensure_ascii=False);print(raw,file=sys.stderr);open("nd-internet-failover-result.json","w",encoding="utf-8").write(raw+"\n");sys.exit(1)
