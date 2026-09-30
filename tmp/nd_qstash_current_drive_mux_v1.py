import json, os, subprocess, sys, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3100'))
GATEWAY_PORT=int(os.environ.get('ND_DRIVE_MUX_GATEWAY_PORT','3310'))
GATEWAY_INNER_PORT=int(os.environ.get('ND_DRIVE_MUX_GATEWAY_INNER_PORT','3311'))
DRIVE_PORT=int(os.environ.get('ND_DRIVE_MUX_DRIVE_PORT','3312'))

CURRENT_FRONT_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f0240dcb6afd7abbbd73aded1b886862de108851/tmp/nd_github_mcp_front_v6_search_fixed.py'
DRIVE_SOURCE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/b3ca0b410839c85ecdc07505370e298a97a5bfcf/tmp/nd_drive_full_user_qstash_v2.mjs'

urllib.request.urlretrieve(CURRENT_FRONT_URL,'/tmp/nd-current-gateway.py')
urllib.request.urlretrieve(DRIVE_SOURCE_URL,'/tmp/nd-drive-reserve.mjs')
subprocess.run(['apk','add','--no-cache','nodejs'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

g_env=dict(os.environ)
g_env['PORT']=str(GATEWAY_PORT)
g_env['ND_GITHUB_INNER_HTTP_PORT']=str(GATEWAY_INNER_PORT)
gateway=subprocess.Popen([sys.executable,'-u','/tmp/nd-current-gateway.py'],env=g_env)

d_env=dict(os.environ)
d_env['PORT']=str(DRIVE_PORT)
drive=subprocess.Popen(['node','/tmp/nd-drive-reserve.mjs'],env=d_env)

GATEWAY='http://127.0.0.1:%d'%GATEWAY_PORT
DRIVE='http://127.0.0.1:%d'%DRIVE_PORT

def clean(e):
    s=str(e)
    tok=os.environ.get('ND_DRIVE_BRIDGE_TOKEN','')
    if tok: s=s.replace(tok,'[REDACTED]')
    return s[:1200]

def proxy(req,target):
    n=int(req.headers.get('Content-Length','0') or 0)
    body=req.rfile.read(n) if n else None
    headers={k:v for k,v in req.headers.items() if k.lower() not in ('host','connection','content-length','transfer-encoding')}
    out=urllib.request.Request(target+(req.path or '/'),data=body,headers=headers,method=req.command)
    try:
        with urllib.request.urlopen(out,timeout=180) as r:
            raw=r.read(); req.send_response(r.status)
            for k,v in r.headers.items():
                if k.lower() not in ('connection','transfer-encoding','content-length'): req.send_header(k,v)
            req.send_header('Content-Length',str(len(raw))); req.end_headers(); req.wfile.write(raw)
    except HTTPError as e:
        raw=e.read(); req.send_response(e.code)
        for k,v in e.headers.items():
            if k.lower() not in ('connection','transfer-encoding','content-length'): req.send_header(k,v)
        req.send_header('Content-Length',str(len(raw))); req.end_headers(); req.wfile.write(raw)
    except Exception as e:
        raw=json.dumps({'ok':False,'error':'mux_upstream_unavailable','detail':clean(e)}).encode()
        req.send_response(503); req.send_header('Content-Type','application/json'); req.send_header('Content-Length',str(len(raw))); req.end_headers(); req.wfile.write(raw)

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def target(self):
        p=self.path.split('?',1)[0]
        return DRIVE if p.startswith('/drive/') else GATEWAY
    def do_GET(self): proxy(self,self.target())
    def do_POST(self): proxy(self,self.target())
    def do_PUT(self): proxy(self,self.target())
    def do_PATCH(self): proxy(self,self.target())
    def do_DELETE(self): proxy(self,self.target())
    def do_HEAD(self): proxy(self,self.target())

print('ND_QSTASH_CURRENT_DRIVE_MUX_READY '+json.dumps({'port':PORT,'gateway_port':GATEWAY_PORT,'gateway_inner_port':GATEWAY_INNER_PORT,'drive_port':DRIVE_PORT,'drive_mcp':'/drive/mcp'}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
