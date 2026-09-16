import urllib.request, json

print('ND_SOCIAL_RAILWAY_WRAPPER_BOOT {"version":"v0.1"}',flush=True)

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py'
SOCIAL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/acf4450217188038f8c8416dc973a671197799d5/tmp/nd_social_provider_runtime_v01.py'

wrapper=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
target="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
assert wrapper.count(target)==1

inject=r"""
# ---- ND Social Railway provider layer v0.1 ----
import types
_social_src=urllib.request.urlopen(SOCIAL,timeout=30).read().decode('utf-8')
_social=types.ModuleType('nd_social_provider_runtime_v01')
exec(compile(_social_src,'nd_social_provider_runtime_v01.py','exec'),_social.__dict__)

def social_provider_health():
    states={}
    required={
        'youtube':['ND_YOUTUBE_CLIENT_ID','ND_YOUTUBE_CLIENT_SECRET','ND_YOUTUBE_REFRESH_TOKEN'],
        'telegram':['ND_TELEGRAM_BOT_TOKEN'],
        'instagram':['ND_META_USER_ACCESS_TOKEN','ND_INSTAGRAM_USER_ID'],
        'facebook':['ND_META_USER_ACCESS_TOKEN'],
        'tiktok':['ND_TIKTOK_ACCESS_TOKEN','ND_TIKTOK_REFRESH_TOKEN'],
        'vk':['VK_GROUP_TOKEN'],
        'line':['ND_LINE_CHANNEL_ACCESS_TOKEN'],
        'dzen':['ND_DZEN_SESSION_BUNDLE'],
    }
    for p,names in required.items():
        present=[n for n in names if os.environ.get(n,'').strip()]
        states[p]={'configured':bool(present),'present_secret_names':present}
    return {
        'ok':True,'provider':'nd-social-railway','version':'0.1',
        'route':'railway','writes_enabled':bool(_social.WRITES_ENABLED),
        'providers':states,
        'host_reuse_first':True,'service':'nd-qstash-control-v2'
    }

_get_anchor="    def do_GET(self):\n        if self.path.split('?',1)[0]=='/nd/linear/status':\n"
_get_repl="    def do_GET(self):\n        _sp=self.path.split('?',1)[0]\n        if _sp=='/nd/social/provider/health':\n            self.send_json(200,social_provider_health()); return\n        if self.path.split('?',1)[0]=='/nd/linear/status':\n"
assert s.count(_get_anchor)==1
s=s.replace(_get_anchor,_get_repl,1)

_post_anchor="        if p=='/nd/linear/invoke':\n"
_post_repl='''        if p=='/nd/social/provider/invoke':
            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return
            try:
                n=int(self.headers.get('Content-Length','0') or 0)
                if n>262144: raise RuntimeError('request_too_large')
                q=json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
                provider=str(q.get('provider') or '').strip().lower()
                cmd={'operation':str(q.get('operation') or 'status'),'arguments':q.get('arguments') or {}}
                out=_social.route_social(provider,cmd)
                self.send_json(200,{'ok':True,'provider':provider,'route':'railway','result':out}); return
            except Exception as e:
                err=_social._redact(e) if hasattr(_social,'_redact') else str(e)[:1000]
                if err.startswith('AWAITING_AUTH:'):
                    self.send_json(428,{'ok':False,'route':'railway','status':'AWAITING_AUTH','error':err}); return
                if err=='WRITE_NOT_QUALIFIED':
                    self.send_json(409,{'ok':False,'route':'railway','status':'WRITE_NOT_QUALIFIED','error':err}); return
                self.send_json(502,{'ok':False,'route':'railway','status':'FAILED','error':err}); return
        if p=='/nd/linear/invoke':
'''
assert s.count(_post_anchor)==1
s=s.replace(_post_anchor,_post_repl,1)

print('ND_SOCIAL_RAILWAY_PATCH_READY '+json.dumps({
    'providers':list(_social.SOCIAL_PROVIDERS),
    'writes_enabled':bool(_social.WRITES_ENABLED),
    'endpoint':'/nd/social/provider/invoke'
},ensure_ascii=False),flush=True)

exec(compile(s,'nd_social_railway_wrapper_v01_runtime.py','exec'))
"""
wrapper=wrapper.replace(target,inject,1)
exec(compile(wrapper,'nd_social_railway_wrapper_v01_outer.py','exec'))
