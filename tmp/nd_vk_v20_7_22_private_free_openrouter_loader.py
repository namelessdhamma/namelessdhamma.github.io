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

# Keep all providers' circuit keys consistent with their outbound API calls.
# The old adaptive loop queried "zai" but the actual Z.AI API opened "zai:<model>".
_v22_old_circuit_blocked=_provider_blocked
def _provider_blocked(name):
    if name=='zai':
        name='zai:'+_STRONG_RU_TARGET['zai']
    return _v22_old_circuit_blocked(name)

def _v22_private_openrouter(messages,max_tokens=1800,temperature=0.3):
    if not OPENROUTER_API_KEY:
        raise RuntimeError('openrouter_key_unavailable')
    circuit='openrouter:'+_V22_OPENROUTER_MODEL
    if _provider_blocked(circuit):
        raise RuntimeError('openrouter_strict_privacy_circuit_open')
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
        choices=ans.get('choices') or []
        msg=(choices[0].get('message') or {}) if choices else {}
        content=msg.get('content') or ''
        if isinstance(content,list):
            content=''.join(str(x.get('text') or '') for x in content if isinstance(x,dict))
        if not isinstance(content,str) or not content.strip():
            raise RuntimeError('openrouter_strict_privacy_empty')
        _provider_success(circuit)
        return content.strip()
    except _v22_http_error.HTTPError as exc:
        code=int(exc.code)
        reason=('HTTP '+str(code)+' '+('rate limit' if code==429 else
                 'payment required' if code==402 else
                 'privacy-compliant free route unavailable' if code==404 else
                 'OpenRouter strict privacy endpoint refused request'))
        err=RuntimeError(reason)
        _provider_fail(circuit,err)
        # 404 indicates missing free/ZDR-compliant endpoint: avoid repeated requests.
        if code==404:
            _provider_down_until[circuit]=max(float(_provider_down_until.get(circuit,0) or 0),time.time()+3600)
        raise err from None
    except Exception as exc:
        _provider_fail(circuit,exc)
        raise


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

# In-memory fault-injection only: clone code objects into private globals so
# these tests cannot alter live callbacks, global router state, or spend API quota.
def _v22_failover_qualification():
    import types as _v22_types
    actual=list(_adaptive_candidates('write'))
    models={p:m for p,m in actual}
    assert set(models)=={'groq','cloudflare','zai','openrouter'},'missing_provider_in_active_pool'
    tests=[
      ('normal',set(),set(),'groq'),
      ('groq_429',set(),{'groq'},'cloudflare'),
      ('groq_and_cloudflare_limit',set(),{'groq','cloudflare'},'zai'),
      ('three_provider_limit',set(),{'groq','cloudflare','zai'},'openrouter'),
      ('open_circuits',{'groq','cloudflare','zai'},set(),'openrouter'),
      ('all_unavailable',set(),{'groq','cloudflare','zai','openrouter'},None),
      ('recovered_primary',set(),set(),'groq')
    ]
    passed=0
    for label,blocked,fail,expected in tests:
        attempts=[]
        def mock_call(provider,model,messages,max_tokens,temperature):
            attempts.append(provider)
            if provider in fail:raise RuntimeError('HTTP 429 synthetic quota')
            return 'Синтетический ответ'
        def mock_blocked(name):
            return name.split(':',1)[0] in blocked
        private=dict(adaptive_chat.__globals__)
        private.update({
            '_adaptive_candidates':lambda route:list(actual),
            '_call_candidate':mock_call,
            '_provider_blocked':mock_blocked,
            'state':{},'cleanerr':lambda e:str(e),
            'print':lambda *a,**kw:None
        })
        fn=_v22_types.FunctionType(adaptive_chat.__code__,private)
        result=None
        try:result=fn([{'role':'user','content':'synthetic only'}],'write',96,0.1)
        except RuntimeError:pass
        success=attempts[-1] if result else None
        assert success==expected,(label,success,expected)
        if expected is not None:
            assert result=='Синтетический ответ'
        passed+=1
    # Test emergency route order and fallback, using private function globals.
    emergency=list(_emergency_candidates())
    assert [p for p,m in emergency]==['cloudflare','zai','openrouter','groq']
    seq=[]
    def em_mock_call(provider,model,messages,max_tokens,temperature):
        seq.append(provider)
        if provider in ('cloudflare','zai'):raise RuntimeError('HTTP 429 synthetic')
        return 'Синтетический аварийный ответ'
    eg=dict(emergency_reserve_chat.__globals__)
    eg.update({'_emergency_candidates':lambda:list(emergency),
               '_call_candidate':em_mock_call,
               '_provider_blocked':lambda n:False,
               'state':{},'cleanerr':lambda e:str(e),
               'print':lambda *a,**kw:None})
    ef=_v22_types.FunctionType(emergency_reserve_chat.__code__,eg)
    assert ef([],96,0.1)=='Синтетический аварийный ответ' and seq==['cloudflare','zai','openrouter']
    passed+=1
    # Z.AI circuit opened under "zai:model" must be detected by "zai" precheck.
    bg=dict(_provider_blocked.__globals__)
    bg['_v22_old_circuit_blocked']=lambda key:key=='zai:'+models['zai']
    bf=_v22_types.FunctionType(_provider_blocked.__code__,bg)
    assert bf('zai') and not bf('groq')
    passed+=1
    state['model_failover_selftest']={'ok':True,'scenarios':passed}
    print('ND_V20_7_22_FAILOVER_SELFTEST_PASS',_v22_json.dumps(
        {'cases':passed,'production_calls':0,'private_state':True,
         'normal_priority':['groq','cloudflare','zai','openrouter']},
        ensure_ascii=False),flush=True)
try:
    _v22_failover_qualification()
except Exception as _v22_test_err:
    state['model_failover_selftest']={'ok':False,'error_type':type(_v22_test_err).__name__}
    print('ND_V20_7_22_FAILOVER_SELFTEST_FAILED',
          _v22_json.dumps({'error_type':type(_v22_test_err).__name__,
                           'detail':str(_v22_test_err)[:190]},ensure_ascii=False),flush=True)

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
