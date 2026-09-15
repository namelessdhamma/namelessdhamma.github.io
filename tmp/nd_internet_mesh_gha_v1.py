import json, os, sys, time, urllib.parse, urllib.request
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
    h={"Accept":"application/json, text/event-stream","Content-Type":"application/json","User-Agent":"ND-GitHub-Failover/1.1"}
    h[cfg["header"]]=cfg["prefix"]+cfg["token"]
    if provider=="tinyfish":h.update({"X-TF-Request-Origin":"nd-github-failover","X-TF-Client-Name":"nd-github-failover","X-TF-Client-Version":"1.1.0"})
    if sid:h.update({"Mcp-Session-Id":sid,"MCP-Protocol-Version":"2025-06-18"})
    req=urllib.request.Request(cfg["url"],data=json.dumps(payload).encode(),headers=h,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        body=e.read().decode("utf-8","replace");raise RuntimeError(f"{provider}_http_{e.code}:{clean(body)}")
    except URLError as e:raise RuntimeError(f"{provider}_network:{clean(e)}")

def initialize(provider):
    status,h,raw=post(provider,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ND GitHub Failover","version":"1.1.0"}}},timeout=45)
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

def tool_value(msg):
    r=(msg or {}).get("result") or {}
    if r.get("isError"):
        raise RuntimeError("provider_tool_error:"+clean(r.get("content") or r))
    sc=r.get("structuredContent")
    if isinstance(sc,dict):return sc
    for c in r.get("content") or []:
        if isinstance(c,dict) and c.get("type")=="text":
            t=str(c.get("text") or "")
            try:return json.loads(t)
            except Exception:return {"text":t}
    return r

def call_tool(provider,tool,args,timeout=120):
    _,msg=request(provider,"tools/call",{"name":tool,"arguments":args},timeout)
    return tool_value(msg)

def deep_find(obj,key):
    if isinstance(obj,dict):
        if key in obj and obj[key] not in (None,""):return obj[key]
        for v in obj.values():
            z=deep_find(v,key)
            if z not in (None,""):return z
    elif isinstance(obj,list):
        for v in obj:
            z=deep_find(v,key)
            if z not in (None,""):return z
    return None

def kernel_smoke(request_key):
    if not request_key:raise RuntimeError("request_key_required_for_smoke")
    name="nd-gh-smoke-"+request_key[-18:]
    created=call_tool("kernel","manage_browsers",{"action":"create","name":name,"start_url":"https://example.com","headless":True,"timeout_seconds":120,"telemetry_enabled":False,"context":"Creating a temporary browser for independent GitHub failover qualification with deterministic cleanup and no persistent user state."})
    sid=deep_find(created,"session_id")
    if not sid:raise RuntimeError("kernel_smoke_missing_session_id:"+clean(created))
    check=None; cleanup=None
    try:
        check=call_tool("kernel","execute_playwright_code",{"session_id":sid,"code":"return { url: page.url(), title: await page.title(), heading: await page.locator('h1').textContent() };","context":"Reading the public Example Domain page through the failover-created browser to verify navigation and remote execution end to end."})
        text=json.dumps(check,ensure_ascii=False)
        ok=("Example Domain" in text)
        if not ok:raise RuntimeError("kernel_smoke_content_mismatch:"+clean(check))
        return {"ok":True,"provider":"kernel","scenario":"create_read_delete","session_id_present":True,"content_verified":True}
    finally:
        try:
            cleanup=call_tool("kernel","manage_browsers",{"action":"delete","session_id":sid,"context":"Deleting the temporary failover qualification browser immediately after verification so no orphan browser session remains."})
        except Exception as e:
            raise RuntimeError("kernel_smoke_cleanup_failed:"+clean(e))

def tinyfish_smoke(request_key):
    if not request_key:raise RuntimeError("request_key_required_for_smoke")
    started=call_tool("tinyfish","run_web_automation",{
        "url":"https://example.com",
        "goal":"Open the page and report the page title and main heading. Do not click external links or submit anything.",
        "browser_profile":"lite",
        "agent_config":{"mode":"strict","max_steps":10,"max_duration_seconds":60},
        "capture_config":{"elements":True,"snapshots":True,"screenshots":False,"recording":False,"html":False}
    },120)
    run_id=deep_find(started,"run_id") or deep_find(started,"id")
    if not run_id:raise RuntimeError("tinyfish_smoke_missing_run_id:"+clean(started))
    last=None
    for _ in range(12):
        last=call_tool("tinyfish","wait_for_run",{"run_id":run_id},90)
        state=str(deep_find(last,"status") or deep_find(last,"state") or "").lower()
        text=json.dumps(last,ensure_ascii=False)
        if any(x in state for x in ("completed","success","succeeded","done")):
            if "Example Domain" not in text:raise RuntimeError("tinyfish_smoke_content_mismatch:"+clean(last))
            return {"ok":True,"provider":"tinyfish","scenario":"single_run_wait","run_id_present":True,"content_verified":True}
        if any(x in state for x in ("failed","error","cancelled","canceled")):
            raise RuntimeError("tinyfish_smoke_terminal_"+state+":"+clean(last))
        time.sleep(2)
    try:call_tool("tinyfish","cancel_run",{"run_id":run_id},45)
    except Exception:pass
    raise RuntimeError("tinyfish_smoke_timeout:"+clean(last))

def main():
    provider=os.getenv("ND_PROVIDER","status").strip().lower();tool=os.getenv("ND_TOOL","").strip()
    args=json.loads(os.getenv("ND_ARGUMENTS_JSON","{}") or "{}");request_key=os.getenv("ND_REQUEST_KEY","").strip()
    if provider=="status":
        out={"ok":True,"service":"ND GitHub Internet Failover","version":"1.1.0-qualification","providers":{k:{"configured":bool(v["token"]),"upstream":v["url"],"allowlisted_tools":len(v["allow"])} for k,v in PROVIDERS.items()},"secrets_returned":False}
    else:
        if provider not in PROVIDERS:raise RuntimeError("unknown_provider")
        if tool=="__smoke__":
            if provider=="kernel":out=kernel_smoke(request_key)
            elif provider=="tinyfish":out=tinyfish_smoke(request_key)
            else:raise RuntimeError("smoke_supported_for_kernel_or_tinyfish")
            out["request_key"]=request_key
            out["retry_policy"]="NO_AUTOMATIC_RETRY_ON_AMBIGUOUS_OR_LOST_RESPONSE"
        elif tool in ("","__tools__"):
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
