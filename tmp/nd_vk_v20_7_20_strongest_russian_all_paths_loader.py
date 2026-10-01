import urllib.request
BASE_COMMIT='dd14892153a438c569a966749e51e35f5592c1c7'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_19_strongest_russian_models_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')
old="exec(compile(s,'v20719_wrapper.py','exec'),{'__name__':'__main__'})"
if base.count(old)!=1: raise RuntimeError('v20720_capture_anchor_missing')
G={'__name__':'__main__'}
exec(compile(base.replace(old,"globals()['_V20720_S']=s",1),'v20720_capture.py','exec'),G,G)
s=G.get('_V20720_S','')
if not s: raise RuntimeError('v20720_base_capture_failed')
v20720_patch="\n# V20.7.20: close legacy emergency/model-metadata bypasses.\nos.environ['GROQ_MODEL']=_STRONG_RU_TARGET['groq']\nos.environ['OPENROUTER_MODEL']=_STRONG_RU_TARGET['openrouter']\nos.environ['GROQ_RESEARCH_MODEL']=_STRONG_RU_TARGET['groq']\n\ndef _emergency_candidates():\n    # Same exact allowlist; different order only for provider independence.\n    preferred=('cloudflare','zai','openrouter','groq')\n    current=dict(_adaptive_candidates('write'))\n    return [(p,current[p]) for p in preferred if p in current]\n\ndef emergency_reserve_chat(messages,max_tokens=3200,temperature=0.35):\n    errors=[]\n    for provider,model in _emergency_candidates():\n        circuit=(provider+':'+model) if provider in ('groq','openrouter','cloudflare') else provider\n        try:\n            if _provider_blocked(circuit):\n                errors.append(provider+':circuit_open')\n                continue\n        except Exception:\n            pass\n        try:\n            out=_call_candidate(provider,model,messages,max_tokens,temperature)\n            if out and str(out).strip():\n                state['last_emergency_provider']=provider+':'+model\n                return out\n            errors.append(provider+':empty')\n        except Exception as err:\n            errors.append(provider+':'+cleanerr(err)[:140])\n    raise RuntimeError('strong_ru_emergency_unavailable: '+' | '.join(errors[-4:]))\n\nstate['strong_only']=True\nstate['provider_policy']='exact-strongest-russian-model-per-provider'\nstate['groq_model']=_STRONG_RU_TARGET['groq']\nstate['research_model']=_STRONG_RU_TARGET['groq']\nstate['openrouter_model']=_STRONG_RU_TARGET['openrouter']\nstate['russian_primary_models']=[p+':'+m for p,m in _adaptive_candidates('write')]\nstate['emergency_reserve_table']=[p+':'+m for p,m in _emergency_candidates()]\nstate['extra_router_probes']={}\nprint('ND_V20_7_20_STRONG_ONLY_ALL_PATHS_READY',json.dumps({\n  'primary':state['russian_primary_models'],\n  'emergency':state['emergency_reserve_table'],\n},ensure_ascii=False),flush=True)\n"
anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(anchor)!=1: raise RuntimeError('v20720_patch_anchor_missing')
s=s.replace(anchor,'router_patch_code += '+repr(v20720_patch)+'\n'+anchor,1)
compile(s,'v20720_wrapper.py','exec')
print('ND_V20_7_20_WRAPPER_READY',flush=True)
exec(compile(s,'v20720_wrapper.py','exec'),{'__name__':'__main__'})
