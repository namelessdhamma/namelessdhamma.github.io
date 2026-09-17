import json, os, subprocess, sys, threading, time, urllib.error, urllib.request
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
    return z[:2000]

def copy_request_headers(h):
    out={}
    allowed={
        'accept','content-type','mcp-protocol-version','mcp-session-id',
        'last-event-id','user-agent'
    }
    for k,v in h.items():
        if k.lower() in allowed:
            out[k]=v
    out['User-Agent']='ND-Tldraw-MCP-Relay/1.1'
    return out

def send_upstream_response(handler, response, stream=False):
    ctype=str(response.headers.get('Content-Type') or '')
    is_stream=stream or ctype.lower().startswith('text/event-stream')
    handler.send_response(response.status)
    for k,v in response.headers.items():
        if k.lower() in ('content-type','mcp-session-id','cache-control','retry-after'):
            handler.send_header(k,v)
    handler.send_header('X-ND-MCP-Relay','tldraw-v1.1')
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
            self.send_json(200,{
                'ok':True,
                'service':'nd-tldraw-mcp-relay',
                'version':'1.1.0',
                'provider':'official-tldraw-mcp-app',
                'upstream':TLDRAW_MCP,
                'transport':'streamable-http-relay',
                'path_token_configured':bool(PATH_TOKEN),
                'inner_runtime':'nd-qstash-control-v2-v12',
                'semantic_broker_probe_preserved':True
            })
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

print('ND_TLDRAW_MCP_RELAY_V1_1_READY '+json.dumps({
    'provider':'official-tldraw-mcp-app',
    'upstream':TLDRAW_MCP,
    'path_token_configured':bool(PATH_TOKEN),
    'inner_port':INNER_PORT,
    'semantic_broker_probe_preserved':True
}),flush=True)

ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
