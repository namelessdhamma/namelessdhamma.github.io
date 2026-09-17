import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/bd211fd66784d31a4a5c3d07044465dcd3756d87/tmp/nd_meta_vk_multiplex_front_v02.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

anchor="VK_ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}\n"
inject=anchor+"GEMINI_DRIVE_TOKEN=os.environ.get('ND_GEMINI_DRIVE_BRIDGE_TOKEN','').strip()\nQSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\n"
if src.count(anchor)!=1:
    raise RuntimeError('gemini drive env anchor mismatch')
src=src.replace(anchor,inject,1)

method_anchor="    def forward(self):\n"
methods=r'''    def gemini_drive(self):
        if not GEMINI_DRIVE_TOKEN or self.headers.get('X-ND-Gemini-Drive-Key','')!=GEMINI_DRIVE_TOKEN:
            self.send_json(401,{'ok':False,'error':'unauthorized'}); return
        if not QSTASH_TOKEN:
            self.send_json(503,{'ok':False,'error':'internal_broker_auth_unconfigured'}); return
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576: raise RuntimeError('request_too_large')
            body=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            tool=str(body.get('tool') or '').strip()
            query=str(body.get('query') or '').strip()[:9000]
            if tool not in ('nd_authority','google_drive_search'):
                self.send_json(403,{'ok':False,'error':'tool_denied'}); return
            if not query: raise RuntimeError('query_required')
            raw=json.dumps({'tool':tool,'query':query},ensure_ascii=False).encode('utf-8')
            req=urllib.request.Request(
                META+'/invoke',data=raw,method='POST',
                headers={
                    'Authorization':'Bearer '+QSTASH_TOKEN,
                    'Content-Type':'application/json',
                    'Accept':'application/json',
                    'User-Agent':'ND-Gemini-Drive-Bridge/1.0'
                })
            with urllib.request.urlopen(req,timeout=120) as r:
                obj=json.loads(r.read().decode('utf-8','replace') or '{}')
            if not isinstance(obj,dict) or 'result' not in obj:
                raise RuntimeError('invalid_internal_broker_response')
            self.send_json(200,{
                'ok':True,
                'provider':'google_drive',
                'transport':'gemini_to_existing_railway_drive_broker',
                'tool':tool,
                'result':obj.get('result'),
                'mutations':False
            }); return
        except HTTPError as e:
            detail=e.read().decode('utf-8','replace')[:700]
            self.send_json(502,{'ok':False,'error':'internal_broker_http_'+str(e.code),'detail':detail}); return
        except Exception as e:
            self.send_json(502,{'ok':False,'error':'bridge_failed','detail':clean(e)}); return

'''
if src.count(method_anchor)!=1:
    raise RuntimeError('gemini drive method anchor mismatch')
src=src.replace(method_anchor,methods+method_anchor,1)

old_post="    def do_POST(self):\n        if self.is_vk_mcp(): self.vk_mcp(); return\n        self.forward()\n"
new_post="    def do_POST(self):\n        if self.path.split('?',1)[0]=='/gemini/drive/invoke': self.gemini_drive(); return\n        if self.is_vk_mcp(): self.vk_mcp(); return\n        self.forward()\n"
if src.count(old_post)!=1:
    raise RuntimeError('gemini drive POST anchor mismatch')
src=src.replace(old_post,new_post,1)

health_anchor="        if path=='/vk/health':\n"
health_inject="        if path=='/gemini/drive/health':\n            self.send_json(200,{'ok':True,'service':'nd-gemini-drive-bridge','configured':bool(GEMINI_DRIVE_TOKEN and QSTASH_TOKEN),'mode':'READ_ONLY','tools':['nd_authority','google_drive_search']}); return\n"+health_anchor
if src.count(health_anchor)!=1:
    raise RuntimeError('gemini drive health anchor mismatch')
src=src.replace(health_anchor,health_inject,1)

print('ND_GEMINI_DRIVE_FRONT_V03_READY '+json.dumps({'endpoint':'/gemini/drive/invoke','health':'/gemini/drive/health','read_only':True}),flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v03_gemini_drive_runtime.py','exec'))
