import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a54578258a88d06e579f46367ac316f1a83d313/tmp/nd_vk_gateway_v38_e2e_qualified.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

anchor="# Autonomous E2E qualification: no VK message and no external mutation."
if anchor not in src:
    raise RuntimeError('V41 V38 anchor not found')

nested_patch = r'''
# V41: install strong-only patch into V13 addon so it executes on the materialized V12 gateway `src`.
v13_exec_marker="replacement=addon+\"\\nexec(compile(src,'nd_vk_gateway_v13_nd_readonly.py','exec'))\""
if v13_exec_marker not in code:
    raise RuntimeError('V41 V13 execution marker not found')
strong_addon = r"""
# V41 materialized gateway patch: only strong free models may author user-visible answers.
old_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
new_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'minimax/minimax-m3:free','z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
if old_models in src:
    src=src.replace(old_models,new_models,1)

old_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        if route=='research':
            return save('Исследовательский контур не смог надёжно завершить поиск. Я не буду подменять актуальное исследование ответом из памяти. Повторите запрос позже или переключитесь на другой режим.','research-error-no-fabrication')
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')
"""
new_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        if route=='research':
            return save('Исследовательский контур не смог надёжно завершить поиск. Я не буду подменять актуальное исследование ответом из памяти. Повторите запрос позже или переключитесь на другой режим.','research-error-no-fabrication')
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        try:
            return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-gpt-oss-120b-fallback')
        except Exception as ge:
            print('GROQ_STRONG_FALLBACK_ERROR',cleanerr(ge),flush=True)
            if OPENROUTER_API_KEY:
                try:
                    out=openrouter_chat(fallback,'medium',3200,0.35)
                    return save(out,'openrouter:'+str(state.get('last_openrouter_model') or 'strong-free-fallback'))
                except Exception as oe:
                    print('OPENROUTER_STRONG_FALLBACK_ERROR',cleanerr(oe),flush=True)
            state['last_provider']='none-strong-available'
            return 'Сильные бесплатные AI-модели сейчас временно недоступны. Попробуйте ещё раз немного позже.'
"""
if old_outer not in src:
    raise RuntimeError('V41 materialized research-integrity fallback block not found')
src=src.replace(old_outer,new_outer,1)
print('ND_V41_MATERIALIZED_STRONG_ONLY',json.dumps({'strong_only':True,'strong_to_strong_fallback':True,'mutations':False},ensure_ascii=False),flush=True)
"""
insert="addon=addon+"+repr(strong_addon)+"\n"+v13_exec_marker
code=code.replace(v13_exec_marker,insert,1)

# Father-facing semantics: fast = brief/low-latency, not weak model.
old_fast="send(peer,'Режим: быстро.');return"
new_fast="send(peer,'Режим: быстро — короткий и быстрый ответ сильной моделью. Качество модели не снижается.');return"
if old_fast in code:
    code=code.replace(old_fast,new_fast,1)
old_status="AI: Groq + резерв OpenRouter."
new_status="AI: только сильные бесплатные модели; Groq + резерв OpenRouter."
if old_status in code:
    code=code.replace(old_status,new_status,1)

'''

src=src.replace(anchor,nested_patch+'\n'+anchor,1)
src=src.replace('ND_V38_WRAPPER_READY','ND_V41_WRAPPER_READY',1)
src=src.replace('nd_vk_gateway_v38_loader.py','nd_vk_gateway_v41_loader.py',1)
print('ND_V41_OUTER_READY',flush=True)
exec(compile(src,'nd_vk_gateway_v41_outer.py','exec'))
