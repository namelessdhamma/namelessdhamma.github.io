import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a54578258a88d06e579f46367ac316f1a83d313/tmp/nd_vk_gateway_v38_e2e_qualified.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

marker='code=code.replace("ND_VK_GATEWAY_V13_ND_READONLY_START","ND_VK_GATEWAY_V38_SAFE_TOOL_BROKER_START",1)'
if marker not in src:
    raise RuntimeError('V38 strong-only injection marker not found')

patch = r'''
# V39 strong-only user-answer invariant.
# Explicit OpenRouter pool contains only currently qualified large/frontier free candidates.
old_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
new_models="OPENROUTER_MODELS=[OPENROUTER_MODEL,'minimax/minimax-m3:free','z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"
if old_models in code:
    code=code.replace(old_models,new_models,1)

# All route failures remain strong-to-strong: Groq GPT-OSS-120B <-> explicit OpenRouter strong-free pool.
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
    raise RuntimeError('V39 fallback marker not found')
code=code.replace(old_fallback,new_fallback,1)

# Fast means brevity/latency, never a weaker answer model.
old_fast="send(peer,'Режим: быстро.');return"
new_fast="send(peer,'Режим: быстро — короткий и быстрый ответ сильной моделью. Качество модели не снижается.');return"
if old_fast in code:
    code=code.replace(old_fast,new_fast,1)

# User status exposes policy without technical noise.
old_status="AI: Groq + резерв OpenRouter."
new_status="AI: только сильные бесплатные модели; Groq + резерв OpenRouter."
if old_status in code:
    code=code.replace(old_status,new_status,1)

# Make telemetry explicitly auditable.
start_tag="ND_VK_GATEWAY_V38_SAFE_TOOL_BROKER_START"
if start_tag in code:
    code=code.replace(start_tag,"ND_VK_GATEWAY_V39_STRONG_ONLY_START",1)
'''

src=src.replace(marker,patch+'\n'+marker,1)
src=src.replace("ND_V38_WRAPPER_READY","ND_V39_WRAPPER_READY",1)
src=src.replace("nd_vk_gateway_v38_loader.py","nd_vk_gateway_v39_loader.py",1)
print('ND_V39_OUTER_READY',flush=True)
exec(compile(src,'nd_vk_gateway_v39_outer.py','exec'))
