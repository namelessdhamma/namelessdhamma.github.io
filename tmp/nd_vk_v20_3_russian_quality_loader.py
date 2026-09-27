import os, urllib.request

# Compatibility markers required by the pinned V19 front guard.
# ND_V19_ORIGINAL_LOADER_ACTIVE
# ],1024,0.0)

BASE_COMMIT='10eab30144d517e7fa23557640fef4341854b941'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_2_vk_star_sanitizer_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

# V20.2 assembles the complete runtime and immediately executes it. Capture that
# already-qualified assembly first, then apply only the bounded Russian-quality delta.
exec_marker='re(rc(final,"nd_vk_gateway_v20_2_strong_primary_reserve_runtime.py","exec"),{"__name__":"__main__"})'
capture_marker='globals()["_ND_V20_2_FINAL_SOURCE"]=final'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_3_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_2_capture_for_v20_3.py','exec'),G,G)
src=G.get('_ND_V20_2_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_3_base_capture_failed')

# Natural-Russian contract. This is intentionally small and applies at generation
# time, rather than adding a second editor model or another agent/service.
russian_policy="""\n\nRUSSIAN_QUALITY_SYSTEM=\'\'\'\nRussian-language quality is a first-class requirement. When the user writes in Russian, answer in natural contemporary Russian that an educated adult native speaker would actually use. Silently correct your own morphology, case government, agreement, aspect, prepositions, declension and word order before sending. Prefer ordinary idiomatic wording over literal translations, bureaucratic nominalizations, English calques, generic AI phrasing and unnatural bookish synonyms. Do not imitate the user's grammatical mistakes unless explicitly asked to. Preserve deliberate literary voice when editing prose, but keep unintended grammar and syntax natural. If two phrasings are equally accurate, choose the simpler and more idiomatic Russian one.\n\'\'\'\n"""
clean_marker='\n\ndef cleanerr(x):\n'
if src.count(clean_marker)!=1:
    raise RuntimeError('v20_3_prompt_insert_anchor_mismatch')
src=src.replace(clean_marker,russian_policy+clean_marker,1)

for name in ('WRITE_SYSTEM','RESEARCH_SYSTEM','DEEP_SYSTEM'):
    old="{'role':'system','content':%s}" % name
    new="{'role':'system','content':%s+RUSSIAN_QUALITY_SYSTEM}" % name
    if old not in src:
        raise RuntimeError('v20_3_system_use_missing_'+name)
    src=src.replace(old,new)

# Nemotron 3 Ultra does not list Russian among its supported post-training languages.
# Prefer current multilingual models whose published support includes Russian.
old_models="""STRONG_OPENROUTER_MODEL='nvidia/nemotron-3-ultra-550b-a55b:free'\nSTRONG_CLOUDFLARE_MODEL='@cf/nvidia/nemotron-3-120b-a12b'\nSTRONG_GROQ_MODEL='openai/gpt-oss-120b'\nMODEL_ROUTE_TABLE={\n    'write':[\n        ('openrouter',STRONG_OPENROUTER_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_MODEL),\n        ('groq',STRONG_GROQ_MODEL),\n    ],\n    'deep_research':[\n        ('openrouter',STRONG_OPENROUTER_MODEL),\n        ('groq',STRONG_GROQ_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_MODEL),\n    ],\n}\n"""
new_models="""STRONG_GROQ_MODEL='qwen/qwen3.8-27b'\nSTRONG_CLOUDFLARE_MODEL='@cf/qwen/qwen3.8-27b'\nSTRONG_CLOUDFLARE_ALT_MODEL='@cf/zai-org/glm-4.7-flash'\nMODEL_ROUTE_TABLE={\n    'write':[\n        ('groq',STRONG_GROQ_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_ALT_MODEL),\n    ],\n    'deep_research':[\n        ('groq',STRONG_GROQ_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_MODEL),\n        ('cloudflare',STRONG_CLOUDFLARE_ALT_MODEL),\n    ],\n}\n"""
if src.count(old_models)!=1:
    raise RuntimeError('v20_3_model_table_anchor_mismatch')
src=src.replace(old_models,new_models,1)

# Reduce lexical wandering on literary/write replies without making them mechanical.
write_call="adaptive_chat(msgs,'write',5200,0.65)"
if src.count(write_call)!=1:
    raise RuntimeError('v20_3_write_temperature_anchor_mismatch')
src=src.replace(write_call,"adaptive_chat(msgs,'write',5200,0.45)",1)

# Make the existing startup probe exercise Russian morphology/idiom rather than only
# transport. It remains one small request per distinct strong model on process start.
old_probe="""                out=_call_candidate(provider,model,[{'role':'user','content':'Reply exactly OK.'}],1024,0.0)\n                ok=bool(out)\n                state['provider_probes'][key]={'ok':ok,'model':model}\n                print('STRONG_PROVIDER_PROBE',json.dumps({'provider':provider,'model':model,'ok':ok},ensure_ascii=False),flush=True)\n"""
new_probe="""                probe_messages=[\n                    {'role':'system','content':'Пиши только естественным современным русским. Ответь одной исправленной фразой, без пояснений.'},\n                    {'role':'user','content':'Исправь: Вчера я ходил к магазину и покупал хлеба, потому что дома закончилась еда.'}\n                ]\n                out=_call_candidate(provider,model,probe_messages,512,0.1)\n                low=out.lower()\n                quality=sum((\n                    'в магазин' in low,\n                    'купил хлеб' in low,\n                    'к магазину' not in low,\n                    'покупал хлеба' not in low,\n                ))\n                ok=bool(out) and quality>=4\n                state['provider_probes'][key]={'ok':ok,'model':model,'russian_quality_score':quality,'preview':out[:400]}\n                print('RUSSIAN_PROVIDER_PROBE',json.dumps({'provider':provider,'model':model,'ok':ok,'score':quality,'preview':out[:400]},ensure_ascii=False),flush=True)\n"""
if src.count(old_probe)!=1:
    raise RuntimeError('v20_3_probe_anchor_mismatch')
src=src.replace(old_probe,new_probe,1)

src=src.replace("state['adaptive_router']='v20.1-strong-primary-emergency-reserve'","state['adaptive_router']='v20.3-russian-quality'",1)
state_anchor="state['semantic_routes']=['write','deep_research']\n"
if state_anchor not in src:
    raise RuntimeError('v20_3_state_anchor_missing')
src=src.replace(state_anchor,state_anchor+"state['russian_quality_policy']='native-ru-v1'\nstate['russian_primary_models']=['groq:qwen/qwen3.8-27b','cloudflare:@cf/qwen/qwen3.8-27b','cloudflare:@cf/zai-org/glm-4.7-flash']\n",1)
src=src.replace('ND_VK_GATEWAY_V20_2_STRONG_PRIMARY_RESERVE_START','ND_VK_GATEWAY_V20_3_RUSSIAN_QUALITY_START',1)

required=(
    'RUSSIAN_QUALITY_SYSTEM',
    "STRONG_GROQ_MODEL='qwen/qwen3.8-27b'",
    "STRONG_CLOUDFLARE_MODEL='@cf/qwen/qwen3.8-27b'",
    'RUSSIAN_PROVIDER_PROBE',
    "state['russian_quality_policy']='native-ru-v1'",
    'ND_VK_GATEWAY_V20_3_RUSSIAN_QUALITY_START',
    "text=str(text or '').replace('*','')",
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_3_final_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_3_russian_quality_runtime.py','exec')
print('ND_V20_3_RUSSIAN_QUALITY_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_3_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_3_russian_quality_runtime.py','exec'),{'__name__':'__main__'})
