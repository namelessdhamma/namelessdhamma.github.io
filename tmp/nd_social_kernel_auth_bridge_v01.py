import base64, json, urllib.request

print('ND_SOCIAL_KERNEL_AUTH_WRAPPER_BOOT {"version":"v0.1"}', flush=True)

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py'
wrapper=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
target="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
assert wrapper.count(target)==1

inject=r"""
# ---- ND Social Kernel auth bootstrap v0.1 ----
import base64
ND_SOCIAL_KERNEL_BOOTSTRAP_TRIGGER=os.environ.get('ND_SOCIAL_KERNEL_BOOTSTRAP_TRIGGER','').strip()
ND_SOCIAL_KERNEL_PROVIDER=os.environ.get('ND_SOCIAL_KERNEL_PROVIDER','').strip().lower()
ND_SOCIAL_KERNEL_START_URL=os.environ.get('ND_SOCIAL_KERNEL_START_URL','').strip()
ND_SOCIAL_KERNEL_SESSION_ID=os.environ.get('ND_SOCIAL_KERNEL_SESSION_ID','').strip()
ND_SOCIAL_KERNEL_ACTION_B64=os.environ.get('ND_SOCIAL_KERNEL_ACTION_B64','').strip()
ND_SOCIAL_KERNEL_ACTION_REV=os.environ.get('ND_SOCIAL_KERNEL_ACTION_REV','').strip()

def social_kernel_bootstrap_once():
    if not KERNEL_API_KEY or not ND_SOCIAL_KERNEL_BOOTSTRAP_TRIGGER or not ND_SOCIAL_KERNEL_START_URL:
        return
    provider=(ND_SOCIAL_KERNEL_PROVIDER or 'generic')[:40]
    suffix=ND_SOCIAL_KERNEL_BOOTSTRAP_TRIGGER[-12:]
    name='nd-social-auth-'+provider+'-'+suffix
    try:
        _,obj=_kernel_json('/browsers','GET',None,timeout=30)
        items=obj if isinstance(obj,list) else ((obj or {}).get('data') or (obj or {}).get('browsers') or [])
        for b in (items or []):
            if not isinstance(b,dict) or b.get('deleted_at'):
                continue
            if str(b.get('name') or '')==name:
                live=str(b.get('browser_live_view_url') or '')
                sid=str(b.get('session_id') or b.get('id') or '')
                if live and sid:
                    print('ND_SOCIAL_KERNEL_AUTH_BOOTSTRAP '+json.dumps({
                        'ok':True,'reused':True,'provider':provider,'session_id':sid,
                        'browser_live_view_url':live,'start_url':b.get('start_url'),
                        'timeout_seconds':b.get('timeout_seconds')
                    },ensure_ascii=False),flush=True)
                    return
        payload={
            'stealth':True,
            'headless':False,
            'timeout_seconds':7200,
            'start_url':ND_SOCIAL_KERNEL_START_URL,
            'name':name
        }
        _,obj=_kernel_json('/browsers','POST',payload,timeout=60)
        print('ND_SOCIAL_KERNEL_AUTH_BOOTSTRAP '+json.dumps({
            'ok':True,'reused':False,'provider':provider,
            'session_id':obj.get('session_id') or obj.get('id'),
            'browser_live_view_url':obj.get('browser_live_view_url'),
            'start_url':obj.get('start_url') or ND_SOCIAL_KERNEL_START_URL,
            'timeout_seconds':obj.get('timeout_seconds')
        },ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_SOCIAL_KERNEL_AUTH_BOOTSTRAP '+json.dumps({
            'ok':False,'provider':provider,'error':clean_error(e)
        },ensure_ascii=False),flush=True)

def social_kernel_action_once():
    if not KERNEL_API_KEY or not ND_SOCIAL_KERNEL_SESSION_ID or not ND_SOCIAL_KERNEL_ACTION_B64:
        return
    time.sleep(2)
    try:
        raw=base64.b64decode(ND_SOCIAL_KERNEL_ACTION_B64.encode('ascii'),validate=True)
        if len(raw)>100000:
            raise RuntimeError('social_kernel_action_too_large')
        code=raw.decode('utf-8')
        result=_kernel_playwright(ND_SOCIAL_KERNEL_SESSION_ID,code,120)
        print('ND_SOCIAL_KERNEL_ACTION '+json.dumps({
            'ok':True,'rev':ND_SOCIAL_KERNEL_ACTION_REV,
            'session_id':ND_SOCIAL_KERNEL_SESSION_ID,'result':result
        },ensure_ascii=False)[:18000],flush=True)
    except Exception as e:
        print('ND_SOCIAL_KERNEL_ACTION '+json.dumps({
            'ok':False,'rev':ND_SOCIAL_KERNEL_ACTION_REV,
            'session_id':ND_SOCIAL_KERNEL_SESSION_ID,'error':clean_error(e)
        },ensure_ascii=False),flush=True)

threading.Thread(target=social_kernel_bootstrap_once,daemon=True).start()
threading.Thread(target=social_kernel_action_once,daemon=True).start()
# ---- end social kernel auth bootstrap ----

exec(compile(s,'nd_gateway_social_kernel_auth_v01_runtime.py','exec'))
"""
wrapper=wrapper.replace(target,inject,1)
exec(compile(wrapper,'nd_social_kernel_auth_bridge_v01_outer.py','exec'))
