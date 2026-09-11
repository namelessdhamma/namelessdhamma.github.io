import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py'
loader=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

old_exec="exec(compile(src,'nd_vk_gateway_v42_father_handoff_loader.py','exec'))"
if old_exec not in loader:
    raise RuntimeError('V43 V42 exec marker not found')

patch = r'''
# V43 strong-only pool: explicit client-side fallback because some OpenRouter
# upstream failures can arrive as a 200 JSON error with no choices.
# Every model below is independently current-qualified as a strong free answer model.
OPENROUTER_STRONG_MODELS = [
    'nvidia/nemotron-3-ultra-550b-a55b:free',
    'z-ai/glm-5.2:free',
    'minimax/minimax-m3:free',
]

# Replace OpenRouter answer function in the fully materialized runtime.
_or_start = src.find('def openrouter_chat(')
_or_end = src.find('\ndef heuristic_route(', _or_start)
if _or_start < 0 or _or_end < 0:
    raise RuntimeError('V43 openrouter function boundary not found')
_or_fn = r'''def openrouter_chat(messages,effort='high',max_tokens=4200,temperature=0.45):
    if not OPENROUTER_API_KEY:raise RuntimeError('OPENROUTER_API_KEY missing')
    extra={'HTTP-Referer':'https://namelessdhamma.org','X-Title':'Nameless Dhamma VK Gateway'}
    failures=[]
    for model in OPENROUTER_STRONG_MODELS:
        payload={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,
                 'reasoning':{'effort':effort,'exclude':True}}
        try:
            try:
                j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
            except Exception as e:
                if 'HTTP 400' not in str(e):raise
                payload.pop('reasoning',None)
                j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
            if j.get('error'):
                raise RuntimeError('OpenRouter model error: '+cleanerr(j.get('error')))
            ch=j.get('choices') or []
            if not ch:
                raise RuntimeError('OpenRouter returned no choices: '+cleanerr(j))
            msg=ch[0].get('message') or {}
            out=(msg.get('content') or '').strip()
            if not out:
                raise RuntimeError('OpenRouter returned empty content')
            actual=j.get('model') or model
            print('STRONG_MODEL_USED',json.dumps({'provider':'openrouter','requested_model':model,'actual_model':actual},ensure_ascii=False),flush=True)
            state['last_provider']='openrouter:'+str(actual)
            return out
        except Exception as e:
            failures.append({'model':model,'error':cleanerr(e)})
            print('STRONG_MODEL_FAIL',json.dumps({'provider':'openrouter','model':model,'error':cleanerr(e)},ensure_ascii=False),flush=True)
    raise RuntimeError('all OpenRouter strong-free models unavailable: '+cleanerr(failures))
'''
src = src[:_or_start] + _or_fn + src[_or_end:]

# Replace the route-level terminal fallback so failures rotate across independent
# strong providers rather than retrying the same failed route or degrading quality.
_old_fallback = """    except Exception as e:\n        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)\n        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]\n        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')"""
_new_fallback = """    except Exception as e:\n        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)\n        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]\n        # fast normally starts on Groq, so rotate to OpenRouter first. Other answer routes\n        # normally start on OpenRouter, so rotate to Groq gpt-oss-120b first.\n        if route=='fast':\n            if OPENROUTER_API_KEY:\n                try:return save(openrouter_chat(fallback,'medium',3000,0.35),'openrouter-strong-fallback')\n                except Exception as e2:print('STRONG_CROSS_PROVIDER_FAIL',cleanerr(e2),flush=True)\n            try:return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-gpt-oss-fallback')\n            except Exception as e3:print('STRONG_CROSS_PROVIDER_FAIL',cleanerr(e3),flush=True)\n        else:\n            try:return save(groq_chat(fallback,GROQ_MODEL,'high',3400),'groq-gpt-oss-fallback')\n            except Exception as e2:print('STRONG_CROSS_PROVIDER_FAIL',cleanerr(e2),flush=True)\n            if OPENROUTER_API_KEY:\n                try:return save(openrouter_chat(fallback,'high',3400,0.35),'openrouter-strong-fallback')\n                except Exception as e3:print('STRONG_CROSS_PROVIDER_FAIL',cleanerr(e3),flush=True)\n        state['last_error']='all strong free answer routes unavailable'\n        return 'Сейчас все сильные бесплатные AI-маршруты временно недоступны или исчерпали лимит. Попробуйте ещё раз позже.'"""
if _old_fallback not in src:
    raise RuntimeError('V43 route fallback marker not found')
src=src.replace(_old_fallback,_new_fallback,1)

# Father-facing fast mode must explicitly preserve model quality.
src=src.replace("mode_by_uid[uid]='fast';send(peer,'Режим: быстро.');return",
                "mode_by_uid[uid]='fast';send(peer,'Режим: быстро — короткий ответ сильной моделью; качество модели не снижается.');return",1)

# Expose auditable version marker without changing authority/write boundaries.
src=src.replace('v42-father-handoff','v43-strong-pool',1)
print('ND_V43_STRONG_POOL_PATCHED',flush=True)
'''

loader=loader.replace(old_exec,patch+"\n"+old_exec,1)
print('ND_V43_LOADER_READY',flush=True)
exec(compile(loader,'nd_vk_gateway_v43_strong_pool_loader.py','exec'))
