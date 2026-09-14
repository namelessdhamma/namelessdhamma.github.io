import json, os, subprocess, sys, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_INNER_GATEWAY_PORT','3001'))
RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BROWSERLESS_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
if BROWSERLESS_TOKEN.lower().startswith('bearer '): BROWSERLESS_TOKEN=BROWSERLESS_TOKEN[7:].strip()
INNER_URL='http://127.0.0.1:%d' % INNER_PORT
GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'

inner_path='/tmp/nd_inner_gateway.py'
src=urllib.request.urlopen(GATEWAY_URL,timeout=30).read()
open(inner_path,'wb').write(src)
env=dict(os.environ)
env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)

def clean_error(x):
    s=str(x)
    if BROWSERLESS_TOKEN:
        s=s.replace(BROWSERLESS_TOKEN,'[REDACTED]')
        s=s.replace(urllib.parse.quote(BROWSERLESS_TOKEN,safe=''),'[REDACTED]')
    return s[:1200]

def parse_sse(raw):
    text=raw.decode('utf-8','replace')
    vals=[]
    for line in text.splitlines():
        if line.startswith('data: '):
            try: vals.append(json.loads(line[6:]))
            except Exception: pass
    if not vals: raise RuntimeError('Browserless MCP returned no parsable SSE data')
    return vals[-1]

def post_mcp(payload,session_id=None):
    if not BROWSERLESS_TOKEN:
        raise RuntimeError('browserless_not_configured')
    headers={
        'Authorization':'Bearer '+BROWSERLESS_TOKEN,
        'Accept':'application/json, text/event-stream',
        'Content-Type':'application/json',
        'User-Agent':'ND-True-Doctor-Railway-Relay/2.0'
    }
    if session_id:
        headers['Mcp-Session-Id']=session_id
        headers['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request(
        'https://mcp.browserless.io/mcp',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('Browserless MCP HTTP %s: %s'%(e.code,clean_error(body)))

ALLOWED_BL_TOOLS={
    'browserless_export','browserless_skill','browserless_agent','browserless_search',
    'browserless_performance','browserless_account','browserless_usage',
    'browserless_sessions','browserless_logs','browserless_smartscraper',
    'browserless_function','browserless_map','browserless_crawl','browserless_profiles'
}

def browserless_tool_call(name,args=None):
    if name not in ALLOWED_BL_TOOLS:
        raise RuntimeError('tool is not allowlisted')
    init={
        'jsonrpc':'2.0','id':1,'method':'initialize',
        'params':{
            'protocolVersion':'2025-06-18',
            'capabilities':{},
            'clientInfo':{'name':'ND True Doctor Railway Relay','version':'2.0'}
        }
    }
    status,headers,raw=post_mcp(init)
    if status!=200: raise RuntimeError('initialize failed')
    init_msg=parse_sse(raw)
    sid=headers.get('Mcp-Session-Id') or headers.get('mcp-session-id')
    if not sid: raise RuntimeError('Browserless MCP did not return a session id')
    post_mcp({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},sid)
    status,_,raw=post_mcp({
        'jsonrpc':'2.0','id':2,'method':'tools/call',
        'params':{'name':name,'arguments':args or {}}
    },sid)
    if status!=200: raise RuntimeError('tools/call failed')
    return {
        'ok':True,
        'provider':'Browserless',
        'serverInfo':((init_msg.get('result') or {}).get('serverInfo') or {}),
        'tool':name,
        'response':parse_sse(raw)
    }

def browserless_profiles():
    try:
        out=browserless_tool_call('browserless_profiles',{
            'limit':20,'offset':0,
            '_prompt':'ND Doctor Railway relay verification: list Browserless profiles only; no mutation.'
        })
        return 200,out
    except Exception as e:
        print('BROWSERLESS_RAILWAY_RELAY_ERROR',clean_error(e),flush=True)
        return 502,{'ok':False,'provider':'Browserless','error':clean_error(e)}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):
        pass

    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def relay_browserless(self):
        expected=('/browserless/profiles/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            code,obj=browserless_profiles()
            self.send_json(code,obj)
            return True
        return False

    def forward(self):
        n=int(self.headers.get('Content-Length','0') or 0)
        body=self.rfile.read(n) if n else None
        url=INNER_URL+self.path
        headers={}
        for k,v in self.headers.items():
            lk=k.lower()
            if lk in ('host','connection','content-length','transfer-encoding'):
                continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read()
                self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() in ('connection','transfer-encoding','content-length'):
                        continue
                    self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read()
            self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'):
                    continue
                self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{'error':'inner_gateway_unavailable','detail':clean_error(e)})

    def do_GET(self):
        if self.relay_browserless():
            return
        self.forward()

    def bootstrap_browserless(self):
        global BROWSERLESS_TOKEN
        expected=('/browserless/bootstrap/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if not expected or self.path.split('?',1)[0]!=expected:
            return False
        if BROWSERLESS_TOKEN:
            self.send_json(409,{'ok':False,'error':'browserless_already_configured'})
            return True
        auth=(self.headers.get('Authorization') or '').strip()
        if not auth.startswith('Bearer '):
            self.send_json(401,{'ok':False,'error':'missing_bearer'})
            return True
        token=auth[7:].strip()
        if len(token)<20:
            self.send_json(400,{'ok':False,'error':'invalid_token_shape'})
            return True
        BROWSERLESS_TOKEN=token
        self.send_json(200,{'ok':True,'configured':True,'persistence':'process_memory'})
        return True

    def do_POST(self):
        if self.bootstrap_browserless():
            return
        expected=('/browserless/call/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            try:
                n=int(self.headers.get('Content-Length','0') or 0)
                body=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                name=str(body.get('tool') or '')
                args=body.get('arguments') or {}
                if not isinstance(args,dict): raise RuntimeError('arguments must be an object')
                self.send_json(200,browserless_tool_call(name,args));return
            except Exception as e:
                self.send_json(400,{'ok':False,'error':clean_error(e)});return
        self.forward()

print('ND_BROWSERLESS_FRONT_PROXY_V4_START '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'relay_path_configured':bool(RELAY_TOKEN),'bootstrap_path_configured':bool(RELAY_TOKEN),'browserless_configured':bool(BROWSERLESS_TOKEN)}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
