import urllib.request

BASE_COMMIT='edb2cacd6fa522bf3cf38c5c8c9333b5f57a7ef4'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_18_strongest_russian_models_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')
old="exec(compile(s,'v20718_strong_ru_wrapper.py','exec'),{'__name__':'__main__'})"
if base.count(old)!=1:
    raise RuntimeError('v20719_capture_anchor_missing')
G={'__name__':'__main__'}
exec(compile(base.replace(old,"globals()['_V20719_S']=s",1),'v20719_capture.py','exec'),G,G)
s=G.get('_V20719_S','')
if not s:
    raise RuntimeError('v20719_base_capture_failed')
v20719_patch="\n# V20.7.19: Cloudflare 120B direct path + hard runtime Russian-language quarantine.\n_STRONG_RU_LANGUAGE_BLOCKED=set()\n_v20719_call=_call_candidate\ndef _call_candidate(provider,model,messages,max_tokens,temperature):\n    expected=_STRONG_RU_TARGET.get(provider)\n    if expected is None:\n        raise RuntimeError('provider_not_in_strong_ru_policy:'+str(provider))\n    if provider in _STRONG_RU_DISABLED:\n        raise RuntimeError('strong_provider_disabled:'+provider+':'+_STRONG_RU_DISABLED[provider])\n    if str(model)!=expected:\n        raise RuntimeError('weaker_model_blocked:'+provider+':'+str(model))\n    # The inherited V20.7.13 Cloudflare gate only knew the old small Llama IDs.\n    # Bypass that stale gate but retain the exact model pin in cloudflare_chat().\n    if provider=='cloudflare':\n        return cloudflare_chat(messages,expected,max_tokens,temperature)\n    return _v20719_call(provider,expected,messages,max_tokens,temperature)\n\n_v20719_candidates=_adaptive_candidates\ndef _adaptive_candidates(route):\n    return [(p,m) for p,m in _v20719_candidates(route)\n            if p not in _STRONG_RU_LANGUAGE_BLOCKED]\n\ndef _v20719_language_enforcer():\n    time.sleep(11)\n    probe=state.get('strongest_ru_probe') or {}\n    for provider,rec in probe.items():\n        if isinstance(rec,dict) and rec.get('ok') is False and not rec.get('error'):\n            _STRONG_RU_LANGUAGE_BLOCKED.add(provider)\n            print('STRONG_RU_PROVIDER_QUARANTINED',\n                  json.dumps({'provider':provider,'reason':'russian_probe_failed'},ensure_ascii=False),\n                  flush=True)\n    for route in ('write','deep_research'):\n        MODEL_ROUTE_TABLE[route]=_adaptive_candidates(route)\n    state['strongest_ru_language_blocked']=sorted(_STRONG_RU_LANGUAGE_BLOCKED)\n    state['model_route_table']={\n      r:[p+':'+m for p,m in _adaptive_candidates(r)]\n      for r in ('write','deep_research')\n    }\n    print('ND_V20_7_19_RUSSIAN_LANGUAGE_GATE_READY',\n          json.dumps({'routes':state['model_route_table'],\n                      'blocked':state['strongest_ru_language_blocked']},\n                     ensure_ascii=False),flush=True)\n\nthreading.Thread(target=_v20719_language_enforcer,daemon=True).start()\nprint('ND_V20_7_19_CLOUDFLARE_120B_GATE_FIXED',flush=True)\n"
anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(anchor)!=1:
    raise RuntimeError('v20719_patch_anchor_missing')
s=s.replace(anchor,'router_patch_code += '+repr(v20719_patch)+'\n'+anchor,1)
compile(s,'v20719_wrapper.py','exec')
print('ND_V20_7_19_WRAPPER_READY',flush=True)
exec(compile(s,'v20719_wrapper.py','exec'),{'__name__':'__main__'})
