import json, os, subprocess, sys, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_INNER_GATEWAY_PORT','3001'))
RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BROWSERLESS_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
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

def browserless_profiles():
    if not BROWSERLESS_TOKEN:
        return 503, {'ok':False,'provider':'Browserless','error':'browserless_not_configured'}
    url='https://production-sfo.browserless.io/profiles?limit=20&offset=0&token='+urllib.parse.quote(BROWSERLESS_TOKEN,safe='')
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'ND-True-Doctor-Railway-Relay/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read().decode('utf-8','replace')
            data=json.loads(raw)
            return 200, {'ok':True,'provider':'Browserless','operation':'profiles_list','data':data}
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        return 502, {'ok':False,'provider':'Browserless','error':'HTTP %s: %s'%(e.code,clean_error(body))}
    except Exception as e:
        return 502, {'ok':False,'provider':'Browserless','error':clean_error(e)}

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

    def do_POST(self):
        self.forward()

print('ND_BROWSERLESS_FRONT_PROXY_START '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'relay_path_configured':bool(RELAY_TOKEN),'browserless_configured':bool(BROWSERLESS_TOKEN)}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
