import urllib.request
u='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/2d27b8f0221b1693ef038be2414f0143d69dde18/tmp/nd_vk_v20_7_8_provider_router_loader.py'
s=urllib.request.urlopen(u,timeout=30).read().decode('utf-8')
patch=r"""
# Historical free providers are enabled ONLY following a live tiny probe.
_v2079_live={'cerebras':False,'cloudflare':False,'mistral':False}
_v2079_old_candidates=_adaptive_candidates
def _adaptive_candidates(route):
    # Old large Cloudflare candidates and paid/obsolete models are excluded.
    out=[x for x in _v2079_old_candidates(route) if x[0] in ('groq','openrouter')]
    if _v2079_live['cerebras']: out.append(('cerebras','gpt-oss-120b'))
    if _v2079_live['cloudflare']: out.append(('cloudflare','@cf/meta/llama-3.1-8b-instruct-fp8'))
    if _v2079_live['mistral']: out.append(('mistral','mistral-small-latest'))
    return list(dict.fromkeys(out))

EMERGENCY_RESERVE_TABLE=[]
state['provider_router_patch']='v20.7.10-historical-free-qualified'
state['provider_pool']={
  'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),
  'cerebras_connected':bool(CEREBRAS_API_KEY),
  'cloudflare_connected':bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
  'mistral_connected':bool(MISTRAL_API_KEY),
}
state['provider_live_probes']=dict(_v2079_live)
# Prevent inherited startup probes from calling heavy or unqualified models.
_safe_base=[]
for _p,_m in [('groq',GROQ_MODEL or 'openai/gpt-oss-120b'),
              ('openrouter',OPENROUTER_MODEL or 'openrouter/free')]:
    if _configured(_p) and (_p!='openrouter' or _m.endswith(':free') or _m=='openrouter/free'):
        _safe_base.append((_p,_m))
MODEL_ROUTE_TABLE['write']=list(_safe_base)
MODEL_ROUTE_TABLE['deep_research']=list(_safe_base)
def _v2079_probe():
    time.sleep(2)
    tiny=[{'role':'user','content':'Ответь одним словом: да'}]
    checks=[
      ('cerebras',bool(CEREBRAS_API_KEY) and os.environ.get('PORFIRCHIK_CEREBRAS_FREE_VERIFIED')=='1',
        lambda:cerebras_chat(tiny,'gpt-oss-120b',max_tokens=96,temperature=0.1)),
      ('cloudflare',bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
        lambda:cloudflare_chat(tiny,'@cf/meta/llama-3.1-8b-instruct-fp8',max_tokens=40,temperature=0.1)),
      ('mistral',bool(MISTRAL_API_KEY) and os.environ.get('PORFIRCHIK_MISTRAL_FREE_VERIFIED')=='1',
        lambda:mistral_chat(tiny,max_tokens=40,temperature=0.1)),
    ]
    for name,permitted,fn in checks:
        if not permitted:
            print('ND_PROVIDER_PROBE_SKIPPED',name,flush=True)
            continue
        try:
            result=fn()
            if not result or not str(result).strip():
                raise RuntimeError('empty_response')
            _v2079_live[name]=True
            print('ND_PROVIDER_PROBE_OK',name,flush=True)
        except Exception as ex:
            print('ND_PROVIDER_PROBE_FAILED',name,cleanerr(ex)[:250],flush=True)
    EMERGENCY_RESERVE_TABLE.clear()
    for name,model in [('cerebras','gpt-oss-120b'),
                       ('cloudflare','@cf/meta/llama-3.1-8b-instruct-fp8'),
                       ('mistral','mistral-small-latest')]:
        if _v2079_live[name]: EMERGENCY_RESERVE_TABLE.append((name,model))
    state['provider_live_probes']=dict(_v2079_live)
    for _r in ('write','deep_research'):
        MODEL_ROUTE_TABLE[_r]=_adaptive_candidates(_r)
    state['model_route_table']={
        k:[p+':'+m for p,m in _adaptive_candidates(k)]
        for k in ('write','deep_research')
    }
    print('ND_V20_7_10_POOL_QUALIFIED',
          json.dumps({'live':_v2079_live,'routes':state['model_route_table']},
                     ensure_ascii=False),flush=True)
threading.Thread(target=_v2079_probe,daemon=True).start()
print('ND_V20_7_11_FREE_POOL_INITIALIZED',flush=True)
"""
patch += "\n\n# V20.7.11: exact no-charge model variants only; no second callback or server.\n_v20711_live={'groq20':False,'orqwen':False,'cf3':False,'zai':False}\n_v20711_previous_candidates=_adaptive_candidates\ndef _adaptive_candidates(route):\n    base=list(_v20711_previous_candidates(route))\n    if _v20711_live['groq20']:\n        base.insert(1,('groq','openai/gpt-oss-20b'))\n    if _v20711_live['orqwen']:\n        base.append(('openrouter','qwen/qwen3.8-27b:free'))\n    if _v20711_live['cf3']:\n        base.append(('cloudflare','@cf/meta/llama-3.2-3b-instruct'))\n    if _v20711_live['zai']:\n        base.append(('zai','glm-4.7-flash'))\n    return list(dict.fromkeys(base))\n\n_v20711_original_candidate_call=_call_candidate\ndef _call_candidate(provider,model,messages,max_tokens,temperature):\n    if provider=='zai':\n        if model!='glm-4.7-flash' or not ZAI_API_KEY:\n            raise RuntimeError('zai_nonfree_model_disallowed')\n        payload={'model':'glm-4.7-flash','messages':messages,\n                 'max_tokens':min(1024,max(32,int(max_tokens))),\n                 'temperature':temperature,'stream':False}\n        return _direct_post('zai:glm-4.7-flash',\n                            'https://api.z.ai/api/paas/v4/chat/completions',\n                            payload,ZAI_API_KEY,60)\n    if provider=='openrouter':\n        if model!='openrouter/free' and not str(model).endswith(':free'):\n            raise RuntimeError('openrouter_nonfree_model_disallowed')\n        max_tokens=min(1400,max(32,int(max_tokens)))\n    elif provider=='cloudflare':\n        if model not in ('@cf/meta/llama-3.1-8b-instruct-fp8',\n                         '@cf/meta/llama-3.2-3b-instruct'):\n            raise RuntimeError('cloudflare_unqualified_model_disallowed')\n        max_tokens=min(900,max(32,int(max_tokens)))\n    return _v20711_original_candidate_call(provider,model,messages,max_tokens,temperature)\n\ndef _v20711_probe():\n    # Inherited startup probes finish against the original 3-model table first.\n    time.sleep(24)\n    day=time.strftime('%Y-%m-%d',time.gmtime())\n    cache_path='/memos-data/porfirchik-extra-router-probes-'+day+'.json'\n    try:\n        with open(cache_path,'r',encoding='utf-8') as f:\n            saved=json.load(f)\n        if isinstance(saved,dict):\n            for k in _v20711_live:\n                _v20711_live[k]=saved.get(k) is True\n    except (OSError,ValueError,TypeError):\n        pass\n    tiny=[{'role':'user','content':'Ответь только одним словом: да'}]\n    tests=[\n        ('groq20',bool(GROQ_API_KEY),\n         lambda:_call_candidate('groq','openai/gpt-oss-20b',tiny,48,0.1)),\n        ('orqwen',bool(OPENROUTER_API_KEY),\n         lambda:_call_candidate('openrouter','qwen/qwen3.8-27b:free',tiny,70,0.1)),\n        ('cf3',bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),\n         lambda:_call_candidate('cloudflare','@cf/meta/llama-3.2-3b-instruct',tiny,48,0.1)),\n        ('zai',bool(ZAI_API_KEY),\n         lambda:_call_candidate('zai','glm-4.7-flash',tiny,70,0.1)),\n    ]\n    for name,available,fn in tests:\n        if not available:\n            print('ND_EXTRA_ROUTER_SKIPPED',name,'no_key',flush=True)\n            continue\n        if _v20711_live[name]:\n            print('ND_EXTRA_ROUTER_CACHED',name,flush=True)\n            continue\n        try:\n            result=fn()\n            if not result or not str(result).strip():\n                raise RuntimeError('empty_response')\n            _v20711_live[name]=True\n            print('ND_EXTRA_ROUTER_OK',name,flush=True)\n        except Exception as e:\n            print('ND_EXTRA_ROUTER_FAILED',name,cleanerr(e)[:220],flush=True)\n    try:\n        with open(cache_path,'w',encoding='utf-8') as f:\n            json.dump(_v20711_live,f)\n    except OSError:\n        pass\n    for route in ('write','deep_research'):\n        MODEL_ROUTE_TABLE[route]=_adaptive_candidates(route)\n    state['extra_router_probes']=dict(_v20711_live)\n    state['model_route_table']={\n       route:[p+':'+m for p,m in _adaptive_candidates(route)]\n       for route in ('write','deep_research')\n    }\n    print('ND_V20_7_11_POOL_READY',\n          json.dumps({'extra_live':_v20711_live,\n                      'routes':state['model_route_table']},ensure_ascii=False),\n          flush=True)\n\nthreading.Thread(target=_v20711_probe,daemon=True).start()\nstate['router_expansion']='v20.7.11-seven-free-model-candidates'\nprint('ND_V20_7_11_EXPANSION_INITIALIZED',flush=True)\n"
anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(anchor)!=1: raise RuntimeError('v2079_patch_anchor_missing')
s=s.replace(anchor,"router_patch_code += "+repr(patch)+"\n"+anchor,1)
end="exec(compile(outer,'v20_7_8_outer_loader.py','exec'),{'__name__':'__main__'})"
if s.count(end)!=1: raise RuntimeError('v2079_outer_exec_anchor_missing')
s=s.replace(end,"print('ND_V20_7_11_PROVIDER_WRAPPER_READY',flush=True)\n"+end,1)
compile(s,'nd_v2079_free_provider_wrapper.py','exec')
exec(compile(s,'nd_v2079_free_provider_wrapper.py','exec'),{'__name__':'__main__'})
