import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
v14=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

needle="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if needle not in v14:
    raise RuntimeError('V14 terminal exec marker missing')

inject=r'''src='import hmac\n'+src

old_post="""    def do_POST(self):
        if self.path.split('?',1)[0]!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
            n=int(self.headers.get('Content-Length','0'));b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:self.out(400,'bad request','text/plain; charset=utf-8');return
"""
new_post="""    def do_POST(self):
        p=self.path.split('?',1)[0]
        if p=='/nd/control/provider-probe':
            # Qualification-only control plane. Disabled unless explicitly configured.
            if os.environ.get('ND_ROUTER_CONTROL_ENABLED','0')!='1':
                self.out(404,{'error':'not_found'});return
            try:
                n=int(self.headers.get('Content-Length','0'))
                b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            except Exception:
                self.out(400,{'error':'bad_request'});return
            expected=os.environ.get('ND_ROUTER_CONTROL_TOKEN','')
            supplied=str(b.get('token') or '')
            if not expected or not supplied or not hmac.compare_digest(supplied,expected):
                self.out(403,{'error':'forbidden'});return
            provider=str(b.get('provider') or '').strip().lower()
            if provider not in ('groq','openrouter'):
                self.out(400,{'error':'provider_must_be_groq_or_openrouter'});return
            now=time.time()
            key='_control_probe_last_'+provider
            last=float(state.get(key) or 0)
            if now-last<15:
                self.out(429,{'error':'rate_limited','retry_after_sec':max(1,int(15-(now-last)))});return
            state[key]=now
            t0=time.time()
            try:
                prompt=[{'role':'user','content':'Reply exactly ND_ROUTER_PROBE_OK.'}]
                if provider=='groq':
                    out=groq_chat(prompt,GROQ_MODEL,'low',64)
                    model=GROQ_MODEL
                else:
                    out=openrouter_chat(prompt,'low',64,0.0)
                    model=OPENROUTER_MODEL
                reply=str(out or '').strip()
                self.out(200,{
                    'ok':reply=='ND_ROUTER_PROBE_OK',
                    'provider':provider,
                    'model':model,
                    'reply':reply[:120],
                    'latency_ms':int((time.time()-t0)*1000)
                });return
            except Exception as e:
                state['last_error']=cleanerr(e)
                self.out(502,{
                    'ok':False,
                    'provider':provider,
                    'error':cleanerr(e)
                });return
        if p!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
            n=int(self.headers.get('Content-Length','0'));b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:self.out(400,'bad request','text/plain; charset=utf-8');return
"""
if old_post not in src:
    raise RuntimeError('V14/V9 Handler POST block not found')
src=src.replace(old_post,new_post,1)
src=src.replace('ND_VK_GATEWAY_V14_WEB_RECOVERY_START','ND_VK_GATEWAY_V15_MCP_PROVIDER_PROBE_START',1)

exec(compile(src,'nd_vk_gateway_v15_mcp_provider_probe.py','exec'))
'''
v14=v14.replace(needle,inject,1)
exec(compile(v14,'nd_vk_gateway_v15_mcp_provider_probe_loader.py','exec'))
