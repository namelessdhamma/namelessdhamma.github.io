# V20.7.22: restore strong free OpenRouter backup without collecting/retaining VK conversation content.
# Exact trusted predecessor remains V20.7.21. This wrapper injects only one bounded router patch.
import os
import urllib.request as _v20722_ur
_BASE_COMMIT='4c1453183601fc3fabc6bbb807a6ef66153078b2'
_BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+_BASE_COMMIT+'/tmp/nd_vk_v20_7_21_arbiter_fencing_loader.py'
_base=_v20722_ur.urlopen(_BASE_URL,timeout=30).read().decode('utf-8')
_old="exec(compile(s,'v20721_wrapper.py','exec'),{'__name__':'__main__','os':os})"
if _base.count(_old)!=1:raise RuntimeError('v20722_predecessor_capture_anchor_mismatch')
_cap={'__name__':'__main__','os':os}
exec(compile(_base.replace(_old,"globals()['_V20722_S']=s",1),'v20722_capture.py','exec'),_cap,_cap)
s=_cap.get('_V20722_S','')
if not s:raise RuntimeError('v20722_predecessor_capture_failed')

_private_free_patch=r'''
# V20.7.22: exactly one chosen strong OpenRouter model, no paid provider fallback.
import urllib.request as _v22_http
import urllib.error as _v22_http_error
import json as _v22_json
import re as _v22_re
_V22_OPENROUTER_MODEL='inclusionai/ling-3.1-flash'
_STRONG_RU_TARGET['openrouter']=_V22_OPENROUTER_MODEL
OPENROUTER_MODEL=_V22_OPENROUTER_MODEL
os.environ['OPENROUTER_MODEL']=_V22_OPENROUTER_MODEL
_v22_previous_call=_call_candidate

def _v22_private_openrouter(messages,max_tokens=1800,temperature=0.3):
    if not OPENROUTER_API_KEY:
        raise RuntimeError('openrouter_key_unavailable')
    body={
        'model':_V22_OPENROUTER_MODEL,
        'provider':{
            'zdr':True,
            'data_collection':'deny',
            'max_price':{'prompt':0,'completion':0}
        },
        'messages':messages,
        'max_tokens':min(2800,max(64,int(max_tokens))),
        'temperature':float(temperature)
    }
    headers={
        'Authorization':'Bearer '+OPENROUTER_API_KEY,
        'Content-Type':'application/json',
        'HTTP-Referer':'https://namelessdhamma.org',
        'X-Title':'ND Porfirchik private free fallback'
    }
    req=_v22_http.Request('https://openrouter.ai/api/v1/chat/completions',
                         data=_v22_json.dumps(body,ensure_ascii=False).encode('utf-8'),
                         headers=headers,method='POST')
    try:
        with _v22_http.urlopen(req,timeout=29) as rsp:
            if rsp.status!=200:raise RuntimeError('openrouter_http_'+str(rsp.status))
            ans=_v22_json.loads(rsp.read(1048576).decode('utf-8'))
    except _v22_http_error.HTTPError as exc:
        raise RuntimeError('openrouter_strict_privacy_http_'+str(exc.code)) from None
    choices=ans.get('choices') or []
    msg=(choices[0].get('message') or {}) if choices else {}
    content=msg.get('content') or ''
    if isinstance(content,list):
        content=''.join(str(x.get('text') or '') for x in content if isinstance(x,dict))
    if not isinstance(content,str) or not content.strip():
        raise RuntimeError('openrouter_strict_privacy_empty')
    return content.strip()

def openrouter_specific_chat(messages,model,max_tokens=1800,temperature=0.3):
    if str(model)!=_V22_OPENROUTER_MODEL:
        raise RuntimeError('openrouter_unqualified_model_denied')
    return _v22_private_openrouter(messages,max_tokens,temperature)

def _call_candidate(provider,model,messages,max_tokens,temperature):
    if provider=='openrouter':
        if str(model)!=_V22_OPENROUTER_MODEL:
            raise RuntimeError('openrouter_unqualified_model_denied')
        return _v22_private_openrouter(messages,max_tokens,temperature)
    return _v22_previous_call(provider,model,messages,max_tokens,temperature)

for _v22_route in ('write','deep_research'):
    MODEL_ROUTE_TABLE[_v22_route]=_adaptive_candidates(_v22_route)
state['strongest_ru_targets']=dict(_STRONG_RU_TARGET)
state['openrouter_model']=_V22_OPENROUTER_MODEL
state['russian_primary_models']=[p+':'+m for p,m in _adaptive_candidates('write')]
state['emergency_reserve_table']=[p+':'+m for p,m in _emergency_candidates()]
state['model_route_table']={r:[p+':'+m for p,m in _adaptive_candidates(r)]
                            for r in ('write','deep_research')}
state['openrouter_data_policy']='ZDR_REQUIRED;COLLECTION_DENY;ZERO_PRICE_ONLY'
state['provider_policy']='exact-strongest-russian-model-per-provider;private-free-openrouter-v22'
print('ND_V20_7_22_PRIVATE_FREE_ROUTER_READY',_v22_json.dumps({
 'openrouter':_V22_OPENROUTER_MODEL,
 'privacy':'zdr+data_collection_deny',
 'max_price_usd_per_million':0,
 'primary':state['russian_primary_models'],
 'emergency':state['emergency_reserve_table']
},ensure_ascii=False),flush=True)
'''
_anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(_anchor)!=1:raise RuntimeError('v20722_router_patch_anchor_mismatch')
s=s.replace(_anchor,'router_patch_code += '+repr(_private_free_patch)+'\n'+_anchor,1)
compile(s,'v20722_wrapper.py','exec')
print('ND_V20_7_22_WRAPPER_READY',flush=True)
if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_7_22_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(s,'v20722_wrapper.py','exec'),{'__name__':'__main__','os':os})
