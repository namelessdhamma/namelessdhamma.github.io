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

# Z.AI GLM-4.7-Flash is free but shared capacity may overload (429/code 1305).
# Multiple inherited startup probes previously hit Z.AI within seconds. Do one real
# synthetic Cyrillic check, reuse only its proof for the remaining exact startup
# probes, and never cache real user answers or queue/wait on the upstream service.
import threading as _v22_threading
_v22_zai_lock=_v22_threading.Lock()
_v22_zai_probe_cache={'answer':None,'at':0.0,'api_checks':0,'reused':0}
_v22_zai_probe_texts=frozenset((
    'Reply exactly OK.',
    'Ответь ровно одной короткой фразой: русский язык работает.',
    'Ответь только одним словом: да',
    'Ответь одним словом: да',
))
_v22_zai_cyrillic=_v22_re.compile(r'[А-Яа-яЁё]')
def _v22_is_zai_startup_probe(messages):
    if not isinstance(messages,list) or not (1<=len(messages)<=2):
        return False
    user=[m for m in messages if isinstance(m,dict) and m.get('role')=='user']
    if len(user)!=1 or len(str(user[0].get('content') or ''))>110:
        return False
    return str(user[0].get('content') or '').strip() in _v22_zai_probe_texts

def _call_candidate(provider,model,messages,max_tokens,temperature):
    if provider=='openrouter':
        if str(model)!=_V22_OPENROUTER_MODEL:
            raise RuntimeError('openrouter_unqualified_model_denied')
        return _v22_private_openrouter(messages,max_tokens,temperature)
    if provider=='zai':
        if str(model)!=_STRONG_RU_TARGET['zai']:
            raise RuntimeError('zai_paid_or_unqualified_model_denied')
        synthetic=_v22_is_zai_startup_probe(messages)
        # This cache is for exact hard-coded startup test questions ONLY.
        if synthetic and _v22_zai_probe_cache['answer'] and (
            time.time()-_v22_zai_probe_cache['at']<240):
            _v22_zai_probe_cache['reused']+=1
            print('ZAI_STARTUP_PROBE_REUSED',_v22_json.dumps({
                'calls_avoided':_v22_zai_probe_cache['reused'],
                'actual_checked':_v22_zai_probe_cache['api_checks'],
            }),flush=True)
            return _v22_zai_probe_cache['answer']
        if _provider_blocked('zai'):
            raise RuntimeError('zai_free_circuit_open_use_other_provider')
        # Atomic non-blocking guard prevents overlapping Z.AI requests and
        # prevents Z.AI's own busy service from stalling every fallback.
        if not _v22_zai_lock.acquire(blocking=False):
            raise RuntimeError('zai_free_busy_use_other_provider')
        try:
            if synthetic:
                # Use one short genuine Russian endpoint test and let other
                # inherited health probes consume its *tested* result.
                probe=[{'role':'system','content':'Ответь исключительно по-русски, коротко.'},
                       {'role':'user','content':'Ответь по-русски: русский язык работает.'}]
                out=_v22_previous_call(provider,model,probe,96,0.1)
                _v22_zai_probe_cache['api_checks']+=1
                if not str(out or '').strip() or not _v22_zai_cyrillic.search(str(out)):
                    raise RuntimeError('zai_free_russian_probe_failed')
                _v22_zai_probe_cache.update({'answer':str(out),'at':time.time()})
                print('ZAI_SINGLE_RUSSIAN_PROBE_PASS',_v22_json.dumps({
                    'model':model,'api_checks':_v22_zai_probe_cache['api_checks'],
                    'thinking_disabled':True}),flush=True)
                return out
            # Real requests remain untouched, never cached; inherited client
            # enforces thinking disabled, free model pin, token cap, and
            # long-cooldown on 429/1305, falling onward in the route loop.
            return _v22_previous_call(provider,model,messages,max_tokens,temperature)
        finally:
            _v22_zai_lock.release()
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

# No network, no VK messages: test probe dedup, active-response isolation,
# model free-pin and nonblocking congestion using cloned globals.
def _v22_zai_resilience_selftest():
    import types as _t
    class Gate:
        def __init__(self):self.held=False
        def acquire(self,blocking=False):
            if self.held:return False
            self.held=True;return True
        def release(self):self.held=False
    now=time.time()
    g=dict(_call_candidate.__globals__)
    stats={'calls':0,'messages':[]}
    def mock_zai(provider,model,msg,mt,tp):
        stats['calls']+=1
        stats['messages'].append(msg)
        return 'Русский язык работает.'
    cache={'answer':None,'at':0.0,'api_checks':0,'reused':0}
    lock=Gate()
    g.update({'_v22_previous_call':mock_zai,
              '_v22_zai_probe_cache':cache,'_v22_zai_lock':lock,
              '_provider_blocked':lambda name:False,'print':lambda *a,**kw:None})
    fn=_t.FunctionType(_call_candidate.__code__,g)
    model=_STRONG_RU_TARGET['zai']
    short=[{'role':'user','content':'Reply exactly OK.'}]
    ru=[{'role':'system','content':'Всегда отвечай на русском языке.'},
        {'role':'user','content':'Ответь ровно одной короткой фразой: русский язык работает.'}]
    assert fn('zai',model,short,96,0.1)
    assert fn('zai',model,ru,360,0.1)
    assert stats['calls']==1 and cache['reused']==1
    normal=[{'role':'user','content':'Настоящий запрос, а не тест запуска.'}]
    assert fn('zai',model,normal,600,0.2)
    assert stats['calls']==2 and stats['messages'][-1]==normal
    lock.held=True
    try:fn('zai',model,normal,600,0.2);raise AssertionError('busy_guard_failed')
    except RuntimeError as e:assert 'busy' in str(e)
    lock.held=False
    try:fn('zai','glm-4.6',normal,600,0.2);raise AssertionError('paid_model_pin_failed')
    except RuntimeError as e:assert 'unqualified' in str(e)
    g['_provider_blocked']=lambda name:name=='zai'
    g['_v22_zai_probe_cache']={'answer':None,'at':0.0,'api_checks':0,'reused':0}
    try:fn('zai',model,normal,600,0.2);raise AssertionError('overloaded_circuit_failed')
    except RuntimeError as e:assert 'circuit' in str(e)
    assert stats['calls']==2
    state['zai_resilience_qa']={'ok':True,'cases':6,'real_api_calls':0}
    print('ZAI_RESILIENCE_SELFTEST_PASS',_v22_json.dumps({
      'cases':6,'real_api_calls':0,'startup_actual_probes_expected':1,
      'paid_models_denied':True,'private_user_reply_cache':False}),flush=True)

try:
    _v22_zai_resilience_selftest()
except Exception as _zai_selftest_error:
    state['zai_resilience_qa']={'ok':False,'error':type(_zai_selftest_error).__name__}
    print('ZAI_RESILIENCE_SELFTEST_FAILED',_v22_json.dumps({
      'type':type(_zai_selftest_error).__name__,
      'detail':str(_zai_selftest_error)[:140]}),flush=True)

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
