import urllib.request, json

print('ND_SOCIAL_GATEWAY_WRAPPER_BOOT {"version":"v0.1"}',flush=True)

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py'
CORE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/7317ae127e22173fa710ac77e6f9b9ff041a18fe/tmp/nd_social_gateway_core_v01.py'

wrapper=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
target="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
assert wrapper.count(target)==1

inject=r"""
# ---- ND Social Gateway v0.1 qualification layer ----
import types
_social_core_src=urllib.request.urlopen(CORE,timeout=30).read().decode('utf-8')
_social_core=types.ModuleType('nd_social_gateway_core_v01')
exec(compile(_social_core_src,'nd_social_gateway_core_v01.py','exec'),_social_core.__dict__)

ND_SOCIAL_ROUTE_HEALTH_JSON=os.environ.get('ND_SOCIAL_ROUTE_HEALTH_JSON','').strip()

def social_route_health():
    if not ND_SOCIAL_ROUTE_HEALTH_JSON:
        return {}
    try:
        obj=json.loads(ND_SOCIAL_ROUTE_HEALTH_JSON)
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}

def social_health_payload():
    st=_social_core.structural_selftest()
    return {
        'ok':bool(st.get('ok')),
        'provider':'nd-social-gateway',
        'version':_social_core.GATEWAY_VERSION,
        'mode':'qualification_no_provider_writes',
        'providers':len(_social_core.PROVIDERS),
        'routes_per_provider':len(_social_core.ROUTE_ORDER),
        'route_order':list(_social_core.ROUTE_ORDER),
        'host_reuse_first':True,
        'new_railway_service_allowed':False,
        'browserless_enabled':False,
        'tinyfish_enabled':False
    }

_get_anchor="    def do_GET(self):\n        if self.path.split('?',1)[0]=='/nd/linear/status':\n"
_get_repl="    def do_GET(self):\n        _sp=self.path.split('?',1)[0]\n        if _sp=='/nd/social/health':\n            self.send_json(200,social_health_payload()); return\n        if _sp=='/nd/social/capabilities':\n            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return\n            self.send_json(200,_social_core.capability_contract()); return\n        if _sp=='/nd/social/status':\n            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return\n            self.send_json(200,{'ok':True,'health':social_health_payload(),'route_health':_social_core.validate_route_state(social_route_health())}); return\n        if self.path.split('?',1)[0]=='/nd/linear/status':\n"
assert s.count(_get_anchor)==1
s=s.replace(_get_anchor,_get_repl,1)

_post_anchor="        if p=='/nd/linear/invoke':\n"
_post_repl="""        if p=='/nd/social/resolve':
            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return
            try:
                n=int(self.headers.get('Content-Length','0') or 0)
                if n>262144: raise RuntimeError('request_too_large')
                q=json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
                req=_social_core.validate_request(q)
                out=_social_core.resolve_route(req['provider'],req['operation'],social_route_health())
                out['request_id']=req.get('request_id') or ''
                self.send_json(200 if out.get('ok') else 503,out); return
            except Exception as e:
                self.send_json(400,{'ok':False,'provider':'nd-social-gateway','error':str(e)[:800]}); return
        if p=='/nd/linear/invoke':
"""
assert s.count(_post_anchor)==1
s=s.replace(_post_anchor,_post_repl,1)

print('ND_SOCIAL_GATEWAY_PATCH_READY '+json.dumps({
    'version':_social_core.GATEWAY_VERSION,
    'providers':list(_social_core.PROVIDERS),
    'route_order':list(_social_core.ROUTE_ORDER),
    'write_actions_enabled':False
},ensure_ascii=False),flush=True)

exec(compile(s,'nd_gateway_social_wrapper_v01_runtime.py','exec'))
"""

wrapper=wrapper.replace(target,inject,1)
exec(compile(wrapper,'nd_gateway_social_wrapper_v01_outer.py','exec'))
