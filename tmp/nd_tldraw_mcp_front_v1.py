import hashlib, json, os, subprocess, sys, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_TLDRAW_MCP_INNER_PORT','3400'))
PATH_TOKEN=os.environ.get('ND_TLDRAW_MCP_PATH_TOKEN','').strip()
QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()

TLDRAW_MCP='https://tldraw-mcp-app.tldraw.workers.dev/mcp'
CURRENT_V12='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/52eae2e57468cc39b5d1e7bfd375abb494b45a4f/tmp/nd_meta_vk_multiplex_front_v12_gemini_drive_semantic_fix.py'

inner_path='/tmp/nd_current_v12.py'
urllib.request.urlretrieve(CURRENT_V12,inner_path)
env=dict(os.environ)
env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)
INNER='http://127.0.0.1:%d' % INNER_PORT

for _ in range(45):
    if child.poll() is not None:
        raise RuntimeError('v12_child_exited_'+str(child.returncode))
    try:
        with urllib.request.urlopen(INNER+'/gemini/drive/health',timeout=3) as r:
            if r.status==200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise RuntimeError('v12_local_health_timeout')

if not QSTASH_TOKEN:
    raise RuntimeError('qstash_token_missing')

def semantic_broker_probe():
    payload={'tool':'nd_authority','query':'Report current ND StateHead status, Capability Registry version, and component count.'}
    req=urllib.request.Request(
        'http://127.0.0.1:3302/invoke',
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={
            'Authorization':'Bearer '+QSTASH_TOKEN,
            'Content-Type':'application/json',
            'Accept':'application/json',
            'User-Agent':'ND-Gemini-v12-Semantic-Probe/1.0'
        }
    )
    status=0
    body=''
    try:
        with urllib.request.urlopen(req,timeout=150) as r:
            status=r.status
            body=r.read().decode('utf-8','replace')
    except urllib.error.HTTPError as e:
        status=e.code
        body=e.read().decode('utf-8','replace')
    except Exception as e:
        status=-1
        body=json.dumps({'error':type(e).__name__+':'+str(e)})
    print('ND_GEMINI_V12_SEMANTIC_BROKER_PROBE '+json.dumps({'status':status,'body':body[:6000]},ensure_ascii=False),flush=True)

threading.Thread(target=semantic_broker_probe,daemon=True).start()

def clean(x):
    z=str(x)
    if PATH_TOKEN:
        z=z.replace(PATH_TOKEN,'[REDACTED]')
    return z[:4000]

def copy_request_headers(h):
    out={}
    allowed={
        'accept','content-type','mcp-protocol-version','mcp-session-id',
        'last-event-id','user-agent'
    }
    for k,v in h.items():
        if k.lower() in allowed:
            out[k]=v
    out['User-Agent']='ND-Tldraw-MCP-Relay/1.2'
    return out

def send_upstream_response(handler, response, stream=False):
    ctype=str(response.headers.get('Content-Type') or '')
    is_stream=stream or ctype.lower().startswith('text/event-stream')
    handler.send_response(response.status)
    for k,v in response.headers.items():
        if k.lower() in ('content-type','mcp-session-id','cache-control','retry-after'):
            handler.send_header(k,v)
    handler.send_header('X-ND-MCP-Relay','tldraw-v1.2')
    if is_stream:
        handler.send_header('Connection','close')
        handler.end_headers()
        handler.close_connection=True
        while True:
            chunk=response.read(8192)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    else:
        raw=response.read()
        handler.send_header('Content-Length',str(len(raw)))
        handler.end_headers()
        if raw:
            handler.wfile.write(raw)

QUALIFICATION={
    'ok':False,
    'stage':'not_started',
    'full_dynamic_passthrough':True,
    'allowlist':False,
    'tools_paginated_to_exhaustion':False,
    'tools_count':0,
    'tools':[],
    'tool_surface_sha256':None,
    'serverInfo':{},
    'capabilities':{},
    'error':None,
}
QUAL_LOCK=threading.Lock()

class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'

    def log_message(self,*a):
        pass

    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(raw)

    def tldraw_path(self):
        expected=('/tldraw/mcp/'+PATH_TOKEN) if PATH_TOKEN else ''
        return bool(expected and self.path.split('?',1)[0]==expected)

    def tldraw_proxy(self):
        if not PATH_TOKEN:
            self.send_json(503,{'ok':False,'error':'tldraw_path_token_unconfigured'})
            return
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>8*1024*1024:
                raise RuntimeError('request_too_large')
            body=self.rfile.read(n) if n else None
            req=urllib.request.Request(
                TLDRAW_MCP,
                data=body,
                headers=copy_request_headers(self.headers),
                method=self.command
            )
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    send_upstream_response(self,r,stream=(self.command=='GET'))
            except HTTPError as e:
                raw=e.read()
                self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() in ('content-type','mcp-session-id','cache-control','retry-after'):
                        self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{'ok':False,'error':'tldraw_proxy_failed','detail':clean(e)})

    def forward_inner(self):
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            body=self.rfile.read(n) if n else None
            headers={k:v for k,v in self.headers.items()
                     if k.lower() not in ('host','connection','content-length','transfer-encoding')}
            req=urllib.request.Request(INNER+self.path,data=body,headers=headers,method=self.command)
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read()
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in ('connection','transfer-encoding','content-length'):
                            self.send_header(k,v)
                    self.send_header('Content-Length',str(len(raw)))
                    self.end_headers()
                    if raw:
                        self.wfile.write(raw)
            except HTTPError as e:
                raw=e.read()
                self.send_response(e.code)
                for k,v in e.headers.items():
                    if k.lower() not in ('connection','transfer-encoding','content-length'):
                        self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)
        except Exception as e:
            self.send_json(502,{'ok':False,'error':'inner_forward_failed','detail':clean(e)})

    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/tldraw/health':
            with QUAL_LOCK:
                q=dict(QUALIFICATION)
            self.send_json(200,{
                'ok':True,
                'service':'nd-tldraw-mcp-relay',
                'version':'1.2.0',
                'provider':'official-tldraw-mcp-app',
                'upstream':TLDRAW_MCP,
                'transport':'streamable-http-relay',
                'path_token_configured':bool(PATH_TOKEN),
                'inner_runtime':'nd-qstash-control-v2-v12',
                'semantic_broker_probe_preserved':True,
                'full_dynamic_passthrough':True,
                'allowlist':False,
                'qualification':q
            })
            return
        if path=='/tldraw/qualification':
            with QUAL_LOCK:
                q=dict(QUALIFICATION)
            self.send_json(200,q)
            return
        if self.tldraw_path():
            self.tldraw_proxy()
            return
        self.forward_inner()

    def do_POST(self):
        if self.tldraw_path():
            self.tldraw_proxy()
            return
        self.forward_inner()

    def do_DELETE(self):
        if self.tldraw_path():
            self.tldraw_proxy()
            return
        self.forward_inner()

def decode_mcp(raw,ctype):
    text=raw.decode('utf-8','replace')
    if 'text/event-stream' in str(ctype).lower():
        vals=[]
        for line in text.splitlines():
            if line.startswith('data:'):
                s=line[5:].strip()
                if s:
                    vals.append(s)
        if not vals:
            return None
        return json.loads(vals[-1])
    if not text.strip():
        return None
    return json.loads(text)

def local_mcp_call(payload,session_id=None,expect_body=True):
    if not PATH_TOKEN:
        raise RuntimeError('path_token_unconfigured')
    url='http://127.0.0.1:%d/tldraw/mcp/%s' % (PORT,PATH_TOKEN)
    headers={
        'Content-Type':'application/json',
        'Accept':'application/json, text/event-stream',
        'MCP-Protocol-Version':'2025-06-18',
        'User-Agent':'ND-Tldraw-Full-Surface-Qualifier/1.0'
    }
    if session_id:
        headers['MCP-Session-Id']=session_id
    req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    with urllib.request.urlopen(req,timeout=90) as r:
        raw=r.read()
        sid=str(r.headers.get('Mcp-Session-Id') or r.headers.get('MCP-Session-Id') or session_id or '').strip()
        obj=decode_mcp(raw,r.headers.get('Content-Type')) if (expect_body or raw) else None
        return obj,sid,r.status

def qualify_full_surface():
    time.sleep(1.0)
    try:
        with QUAL_LOCK:
            QUALIFICATION['stage']='initialize'
        hello,sid,_=local_mcp_call({
            'jsonrpc':'2.0','id':'nd-tldraw-init','method':'initialize','params':{
                'protocolVersion':'2025-06-18',
                'capabilities':{},
                'clientInfo':{'name':'ND tldraw full-surface qualifier','version':'1.0'}
            }
        })
        if not isinstance(hello,dict) or hello.get('error'):
            raise RuntimeError('initialize_failed:'+json.dumps(hello,ensure_ascii=False)[:1200])
        result=hello.get('result') or {}
        if sid:
            try:
                local_mcp_call({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},session_id=sid,expect_body=False)
            except Exception as e:
                print('ND_TLDRAW_INITIALIZED_NOTIFICATION_WARN '+clean(e),flush=True)

        all_tools=[]
        cursor=None
        pages=0
        while True:
            pages+=1
            if pages>100:
                raise RuntimeError('tools_pagination_guard_exceeded')
            params={} if cursor is None else {'cursor':cursor}
            obj,sid,_=local_mcp_call({'jsonrpc':'2.0','id':'nd-tldraw-tools-%d'%pages,'method':'tools/list','params':params},session_id=sid)
            if not isinstance(obj,dict) or obj.get('error'):
                raise RuntimeError('tools_list_failed:'+json.dumps(obj,ensure_ascii=False)[:1200])
            page=(obj.get('result') or {})
            tools=page.get('tools') or []
            if not isinstance(tools,list):
                raise RuntimeError('tools_not_list')
            all_tools.extend(tools)
            cursor=page.get('nextCursor')
            if not cursor:
                break

        canonical=json.dumps(all_tools,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        names=[str(t.get('name') or '') for t in all_tools]
        if not all_tools or not all(names):
            raise RuntimeError('empty_or_invalid_tool_surface')
        q={
            'ok':True,
            'stage':'complete',
            'full_dynamic_passthrough':True,
            'allowlist':False,
            'tools_paginated_to_exhaustion':True,
            'pages':pages,
            'tools_count':len(all_tools),
            'tool_names':names,
            'tools':all_tools,
            'tool_surface_sha256':digest,
            'serverInfo':result.get('serverInfo') or {},
            'capabilities':result.get('capabilities') or {},
            'protocolVersion':result.get('protocolVersion'),
            'session_established':bool(sid),
            'error':None,
        }
        with QUAL_LOCK:
            QUALIFICATION.clear(); QUALIFICATION.update(q)
        print('ND_TLDRAW_FULL_SURFACE_QUALIFICATION '+json.dumps(q,ensure_ascii=False),flush=True)
    except Exception as e:
        q={
            'ok':False,
            'stage':'failed',
            'full_dynamic_passthrough':True,
            'allowlist':False,
            'tools_paginated_to_exhaustion':False,
            'tools_count':0,
            'tools':[],
            'tool_surface_sha256':None,
            'serverInfo':{},
            'capabilities':{},
            'error':clean(e),
        }
        with QUAL_LOCK:
            QUALIFICATION.clear(); QUALIFICATION.update(q)
        print('ND_TLDRAW_FULL_SURFACE_QUALIFICATION '+json.dumps(q,ensure_ascii=False),flush=True)

print('ND_TLDRAW_MCP_RELAY_V1_2_READY '+json.dumps({
    'provider':'official-tldraw-mcp-app',
    'upstream':TLDRAW_MCP,
    'path_token_configured':bool(PATH_TOKEN),
    'inner_port':INNER_PORT,
    'semantic_broker_probe_preserved':True,
    'full_dynamic_passthrough':True,
    'allowlist':False
}),flush=True)

server=ThreadingHTTPServer(('0.0.0.0',PORT),H)
threading.Thread(target=qualify_full_surface,daemon=True).start()
server.serve_forever()
