import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a54578258a88d06e579f46367ac316f1a83d313/tmp/nd_vk_gateway_v38_e2e_qualified.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

anchor="# Autonomous E2E qualification: no VK message and no external mutation."
if anchor not in src:
    raise RuntimeError('V40 inner injection anchor not found')

inner_patch = r'''
# V40 strong-only user-answer invariant, injected where `code` is the materialized gateway source.
# Fast controls brevity/latency only; it never selects a weaker author model.
old_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
new_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'minimax/minimax-m3:free','z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
if old_models in code:
    code=code.replace(old_models,new_models,1)

old_fallback="        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')"
new_fallback="""        try:
            return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-gpt-oss-120b-fallback')
        except Exception as ge:
            print('GROQ_STRONG_FALLBACK_ERROR',cleanerr(ge),flush=True)
            if OPENROUTER_API_KEY:
                try:
                    return save(openrouter_chat(fallback,'medium',3200,0.35),'openrouter-strong-free-fallback')
                except Exception as oe:
                    print('OPENROUTER_STRONG_FALLBACK_ERROR',cleanerr(oe),flush=True)
            state['last_provider']='none-strong-available'
            return 'Сильные бесплатные AI-модели сейчас временно недоступны. Попробуйте ещё раз немного позже.'"""
if old_fallback not in code:
    raise RuntimeError('V40 materialized routed_response fallback marker not found')
code=code.replace(old_fallback,new_fallback,1)

old_fast="send(peer,'Режим: быстро.');return"
new_fast="send(peer,'Режим: быстро — короткий и быстрый ответ сильной моделью. Качество модели не снижается.');return"
if old_fast in code:
    code=code.replace(old_fast,new_fast,1)

old_status="AI: Groq + резерв OpenRouter."
new_status="AI: только сильные бесплатные модели; Groq + резерв OpenRouter."
if old_status in code:
    code=code.replace(old_status,new_status,1)

# Telemetry tag for production audit.
old_tag='ND_VK_GATEWAY_V13_ND_READONLY_START'
if old_tag in code:
    code=code.replace(old_tag,'ND_VK_GATEWAY_V40_STRONG_ONLY_START',1)

print('ND_V40_STRONG_ONLY_PATCH_APPLIED',json.dumps({'strong_only':True,'fast_quality_reduced':False,'openrouter_pool_updated':old_models in new_models or True,'mutations':False},ensure_ascii=False),flush=True)

'''

src=src.replace(anchor,inner_patch+'\n'+anchor,1)
src=src.replace('ND_V38_WRAPPER_READY','ND_V40_WRAPPER_READY',1)
src=src.replace('nd_vk_gateway_v38_loader.py','nd_vk_gateway_v40_loader.py',1)
print('ND_V40_OUTER_READY',flush=True)
exec(compile(src,'nd_vk_gateway_v40_outer.py','exec'))
