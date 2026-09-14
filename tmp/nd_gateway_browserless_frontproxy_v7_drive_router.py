import json, os, subprocess, sys, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_INNER_GATEWAY_PORT','3001'))
RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BROWSERLESS_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
ROUTER_TOKEN=os.environ.get('ND_VK_MCP_ROUTE_TOKEN','').strip()
GROQ_API_KEY=os.environ.get('GROQ_API_KEY','').strip()
GROQ_MODEL=os.environ.get('GROQ_MODEL','openai/gpt-oss-120b').strip()
OPENROUTER_API_KEY=(os.environ.get('OpenRouter','') or os.environ.get('OPENROUTER_API_KEY','')).strip()
OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()
if BROWSERLESS_TOKEN.lower().startswith('bearer '): BROWSERLESS_TOKEN=BROWSERLESS_TOKEN[7:].strip()
INNER_URL='http://127.0.0.1:%d' % INNER_PORT
GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'

inner_path='/tmp/nd_inner_gateway.py'
src=urllib.request.urlopen(GATEWAY_URL,timeout=30).read()
open(inner_path,'wb').write(src)
env=dict(os.environ); env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)
probe_last={}

# V7: restore the previously qualified Drive bridge as an internal child.
# Credentials remain in Railway environment; this front only proxies /drive/*.
DRIVE_PORT=int(os.environ.get('ND_DRIVE_BRIDGE_PORT','3002'))
DRIVE_URL='http://127.0.0.1:%d' % DRIVE_PORT
DRIVE_FRONT_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1bb27fa0c61e24d373cb170c2edea61e5d3f3cbd/tmp/nd_safe_tool_broker_v14_enable_docs_front.js'
drive_child=None
try:
    subprocess.run(['apk','add','--no-cache','nodejs'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    urllib.request.urlretrieve(DRIVE_FRONT_URL,'/tmp/nd-drive-front.mjs')
    drive_env=dict(os.environ); drive_env['PORT']=str(DRIVE_PORT)
    drive_child=subprocess.Popen(['node','/tmp/nd-drive-front.mjs'],env=drive_env)
    print('ND_DRIVE_CHILD_LAUNCHED '+json.dumps({'port':DRIVE_PORT}),flush=True)
except Exception as e:
    print('ND_DRIVE_CHILD_START_ERROR '+json.dumps({'error':str(e)[:500]}),flush=True)

def clean_error(x):
    s=str(x)
    for token in (BROWSERLESS_TOKEN,ROUTER_TOKEN,GROQ_API_KEY,OPENROUTER_API_KEY):
        if token:
            s=s.replace(token,'[REDACTED]')
            s=s.replace(urllib.parse.quote(token,safe=''),'[REDACTED]')
    return s[:1200]

def parse_sse(raw):
    text=raw.decode('utf-8','replace'); vals=[]
    for line in text.splitlines():
        if line.startswith('data: '):
            try: vals.append(json.loads(line[6:]))
            except Exception: pass
    if not vals: raise RuntimeError('Browserless MCP returned no parsable SSE data')
    return vals[-1]

def post_mcp(payload,session_id=None):
    if not BROWSERLESS_TOKEN: raise RuntimeError('browserless_not_configured')
    headers={'Authorization':'Bearer '+BROWSERLESS_TOKEN,'Accept':'application/json, text/event-stream','Content-Type':'application/json','User-Agent':'ND-True-Doctor-Railway-Relay/2.0'}
    if session_id:
        headers['Mcp-Session-Id']=session_id; headers['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request('https://mcp.browserless.io/mcp',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=90) as r: return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('Browserless MCP HTTP %s: %s'%(e.code,clean_error(body)))

ALLOWED_BL_TOOLS={'browserless_export','browserless_skill','browserless_agent','browserless_search','browserless_performance','browserless_account','browserless_usage','browserless_sessions','browserless_logs','browserless_smartscraper','browserless_function','browserless_map','browserless_crawl','browserless_profiles'}

def browserless_tool_call(name,args=None):
    if name not in ALLOWED_BL_TOOLS: raise RuntimeError('tool is not allowlisted')
    init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'ND True Doctor Railway Relay','version':'2.0'}}}
    status,headers,raw=post_mcp(init)
    if status!=200: raise RuntimeError('initialize failed')
    init_msg=parse_sse(raw); sid=headers.get('Mcp-Session-Id') or headers.get('mcp-session-id')
    if not sid: raise RuntimeError('Browserless MCP did not return a session id')
    post_mcp({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},sid)
    status,_,raw=post_mcp({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args or {}}},sid)
    if status!=200: raise RuntimeError('tools/call failed')
    return {'ok':True,'provider':'Browserless','serverInfo':((init_msg.get('result') or {}).get('serverInfo') or {}),'tool':name,'response':parse_sse(raw)}

def browserless_profiles():
    try:
        out=browserless_tool_call('browserless_profiles',{'limit':20,'offset':0,'_prompt':'ND Doctor Railway relay verification: list Browserless profiles only; no mutation.'}); return 200,out
    except Exception as e:
        print('BROWSERLESS_RAILWAY_RELAY_ERROR',clean_error(e),flush=True); return 502,{'ok':False,'provider':'Browserless','error':clean_error(e)}

def auth_ok(headers):
    if not ROUTER_TOKEN: return False
    return (headers.get('Authorization') or '').strip() == 'Bearer '+ROUTER_TOKEN

def inner_health():
    try:
        with urllib.request.urlopen(INNER_URL+'/health',timeout=8) as r:
            raw=r.read();
            try: body=json.loads(raw.decode('utf-8','replace'))
            except Exception: body={'raw':raw.decode('utf-8','replace')[:600]}
            return r.status,body
    except Exception as e: return 502,{'ok':False,'error':clean_error(e)}

def provider_probe(provider):
    now=time.time(); last=probe_last.get(provider,0)
    if now-last<15: return 429,{'ok':False,'error':'rate_limited','retry_after_sec':max(1,int(15-(now-last)))}
    probe_last[provider]=now
    if provider=='groq':
        key=GROQ_API_KEY; model=GROQ_MODEL; url='https://api.groq.com/openai/v1/chat/completions'; headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    elif provider=='openrouter':
        key=OPENROUTER_API_KEY; model=OPENROUTER_MODEL; url='https://openrouter.ai/api/v1/chat/completions'; headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://namelessdhamma.org','X-Title':'ND Router Qualification'}
    else: return 400,{'ok':False,'error':'provider_must_be_groq_or_openrouter'}
    if not key: return 503,{'ok':False,'provider':provider,'error':'provider_not_configured'}
    payload={'model':model,'messages':[{'role':'user','content':'Reply exactly ND_ROUTER_PROBE_OK.'}],'max_tokens':32,'temperature':0}
    t0=time.time(); req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as r: data=json.loads(r.read().decode('utf-8','replace'))
        reply=str((((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '')).strip()
        return 200,{'ok':reply=='ND_ROUTER_PROBE_OK','provider':provider,'configured_model':model,'response_model':data.get('model'),'reply':reply[:120],'latency_ms':int((time.time()-t0)*1000),'channel':'railway'}
    except HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')[:800]
        except Exception: detail=''
        return e.code,{'ok':False,'provider':provider,'error':clean_error(detail),'channel':'railway'}
    except Exception as e: return 502,{'ok':False,'provider':provider,'error':clean_error(e),'channel':'railway'}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8'); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def relay_browserless(self):
        expected=('/browserless/profiles/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            code,obj=browserless_profiles(); self.send_json(code,obj); return True
        return False
    def router_get(self):
        p=self.path.split('?',1)[0]
        if p not in ('/nd/router/status','/nd/router/health'): return False
        if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        code,health=inner_health()
        if p.endswith('/status'):
            self.send_json(200,{'ok':code==200,'channel':'railway','proxy':'v6-router-control','inner_health_status':code,'inner_health':health,'providers':{'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'drive_port':DRIVE_PORT,'drive_child':bool(drive_child)}})
        else: self.send_json(code,{'ok':code==200,'channel':'railway','inner_health':health})
        return True
    def drive_forward(self):
        n=int(self.headers.get('Content-Length','0') or 0); body=self.rfile.read(n) if n else None
        url=DRIVE_URL+self.path; headers={}
        for k,v in self.headers.items():
            if k.lower() in ('host','connection','content-length','transfer-encoding'): continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read(); self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() in ('connection','transfer-encoding','content-length'): continue
                    self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read(); self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'): continue
                self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except Exception as e:
            self.send_json(503,{'ok':False,'error':'drive_bridge_unavailable','detail':clean_error(e)})

    def forward(self):
        n=int(self.headers.get('Content-Length','0') or 0); body=self.rfile.read(n) if n else None; url=INNER_URL+self.path; headers={}
        for k,v in self.headers.items():
            if k.lower() in ('host','connection','content-length','transfer-encoding'): continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read(); self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() in ('connection','transfer-encoding','content-length'): continue
                    self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read(); self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'): continue
                self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except Exception as e: self.send_json(502,{'error':'inner_gateway_unavailable','detail':clean_error(e)})
    def do_GET(self):
        if self.path.split('?',1)[0].startswith('/drive/'):
            self.drive_forward(); return
        if self.relay_browserless() or self.router_get(): return
        self.forward()
    def bootstrap_browserless(self):
        global BROWSERLESS_TOKEN
        expected=('/browserless/bootstrap/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if not expected or self.path.split('?',1)[0]!=expected: return False
        if BROWSERLESS_TOKEN: self.send_json(409,{'ok':False,'error':'browserless_already_configured'}); return True
        auth=(self.headers.get('Authorization') or '').strip()
        if not auth.startswith('Bearer '): self.send_json(401,{'ok':False,'error':'missing_bearer'}); return True
        token=auth[7:].strip()
        if len(token)<20: self.send_json(400,{'ok':False,'error':'invalid_token_shape'}); return True
        BROWSERLESS_TOKEN=token; self.send_json(200,{'ok':True,'configured':True,'persistence':'process_memory'}); return True
    def do_POST(self):
        p=self.path.split('?',1)[0]
        if p.startswith('/drive/'):
            self.drive_forward(); return
        if self.bootstrap_browserless(): return
        if p=='/nd/router/request':
            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return
            try:
                n=int(self.headers.get('Content-Length','0') or 0); b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            except Exception: self.send_json(400,{'ok':False,'error':'bad_request'}); return
            code,obj=provider_probe(str(b.get('provider') or '').strip().lower()); self.send_json(code,obj); return
        expected=('/browserless/call/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and p==expected:
            try:
                n=int(self.headers.get('Content-Length','0') or 0); body=json.loads(self.rfile.read(n).decode('utf-8') or '{}'); name=str(body.get('tool') or ''); args=body.get('arguments') or {}
                if not isinstance(args,dict): raise RuntimeError('arguments must be an object')
                self.send_json(200,browserless_tool_call(name,args)); return
            except Exception as e: self.send_json(400,{'ok':False,'error':clean_error(e)}); return
        self.forward()

print('ND_BROWSERLESS_FRONT_PROXY_V7_DRIVE_ROUTER_START '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'router_control':bool(ROUTER_TOKEN),'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY)}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
