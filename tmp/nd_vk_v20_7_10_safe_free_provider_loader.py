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
      ('cerebras',bool(CEREBRAS_API_KEY),
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
print('ND_V20_7_10_FREE_POOL_INITIALIZED',flush=True)
"""
anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(anchor)!=1: raise RuntimeError('v2079_patch_anchor_missing')
s=s.replace(anchor,"router_patch_code += "+repr(patch)+"\n"+anchor,1)
end="exec(compile(outer,'v20_7_8_outer_loader.py','exec'),{'__name__':'__main__'})"
if s.count(end)!=1: raise RuntimeError('v2079_outer_exec_anchor_missing')
s=s.replace(end,"print('ND_V20_7_10_PROVIDER_WRAPPER_READY',flush=True)\n"+end,1)
compile(s,'nd_v2079_free_provider_wrapper.py','exec')
exec(compile(s,'nd_v2079_free_provider_wrapper.py','exec'),{'__name__':'__main__'})
