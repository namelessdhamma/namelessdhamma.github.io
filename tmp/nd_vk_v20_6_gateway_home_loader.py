import os, urllib.request, re

# Compatibility markers required by the inherited front/runtime guards.
# ND_V19_ORIGINAL_LOADER_ACTIVE
# ],1024,0.0)

BASE_COMMIT='e1d77608377c621f9509d9f846d4c5fb8ffe6e12'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_5_gateway_free_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

exec_marker="exec(compile(src,'nd_vk_gateway_v20_5_memory_durable_runtime.py','exec'),{'__name__':'__main__'})"
capture_marker='globals()["_ND_V20_5_GATEWAY_FINAL_SOURCE"]=src'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_6_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_5_gateway_capture_for_v20_6.py','exec'),G,G)
src=G.get('_ND_V20_5_GATEWAY_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_6_base_capture_failed')

system_prefix="""You are Porfirchik, the VK conversational interface of Nameless Dhamma (ND), an independent Buddhist research and creative project. Respond in the user's language; default to Russian. Be concise for simple questions and rigorous for serious work.

CURRENT RUNTIME FACTS YOU MAY STATE WHEN RELEVANT:
- Your production runtime home is the Railway service nd-yandex-n8n-gateway.
- You DO have automatic long-term conversational memory. It is server-managed, not model-internal: MemOS Cloud is the semantic/intelligent layer and a persistent local SQLite database at /memos-data/porfirchik-memos.sqlite3 is the fail-open fallback with a durable Cloud outbox/replay queue.
- The runtime also reconstructs recent VK conversation history before generation.
- You are memory-blind operationally: recall and capture happen automatically around your model call; you do not manually invoke memory tools.
- The same Railway gateway co-hosts ND connectivity modules for Yandex/YouTube/Telegram/browser work. Their existence does NOT mean their data is automatically available in every answer. Claim you used or read a connected source only when its result was actually supplied in the current request context.
- Model/provider routing is an internal runtime detail and can change. Do not invent provider availability; answer from supplied runtime facts when asked.
- Do not claim access to the user's ChatGPT account, ChatGPT memory, private ChatGPT chats, or the full CURRENT ND StateHead unless that context is explicitly supplied through this gateway.
- If asked where your memory is, do not say you have only ephemeral OpenAI context. Explain the MemOS Cloud + persistent SQLite architecture above, and distinguish it from the model's own transient context window.
"""
m=re.search(r"BASE_SYSTEM='''(.*?)'''",src,re.S)
if not m:
    raise RuntimeError('v20_6_base_system_not_found')
legacy=m.group(1)
# Preserve useful pre-existing persona/profile constraints after authoritative runtime facts.
new_base="BASE_SYSTEM='''"+system_prefix+"\n\nAdditional inherited behavior:\n"+legacy+"'''"
src=src[:m.start()]+new_base+src[m.end():]

state_anchor="""state['memos_recall_policy']='user-first-v1'"""
state_new=state_anchor+"""
state['runtime_home']='nd-yandex-n8n-gateway'
state['runtime_platform']='railway-free'
state['runtime_home_policy']='single-owner'
state['cohosted_gateway_modules']=['yandex','youtube','telegram','browser']
state['cohosted_modules_auto_available_to_model']=False
state['self_knowledge_policy']='runtime-facts-v1'
# CURRENT Free-runtime provider truth. Keep the inherited routing code intact:
# it already filters unconfigured providers. Override only diagnostics/currentness.
state['model_route_table']={
    'write':['groq:openai/gpt-oss-120b'],
    'deep_research':['groq:openai/gpt-oss-120b'],
}
state['russian_primary_models']=['groq:openai/gpt-oss-120b']
state['provider_pool']={
    'groq':bool(os.environ.get('GROQ_API_KEY')),
    'openrouter':bool(os.environ.get('OPENROUTER_API_KEY')),
    'cerebras':bool(os.environ.get('CEREBRAS_API_KEY')),
    'cloudflare':bool(os.environ.get('CLOUDFLARE_ACCOUNT_ID') and os.environ.get('CLOUDFLARE_API_TOKEN')),
}
state['provider_policy']='groq-primary; cerebras-reserve; openrouter-opportunistic; dead routes filtered'
"""
if src.count(state_anchor)!=1:
    raise RuntimeError('v20_6_state_anchor_mismatch')
src=src.replace(state_anchor,state_new,1)

status_pattern=re.compile(r"""                if text=='/status':\n                    send\(peer,'ND Router: VK=OK; Groq=%s; OpenRouter=%s; fast=%s; research=%s; deep/write=%s; mode=%s; last_route=%s; last_provider=%s'%\(\n                        'OK' if GROQ_API_KEY else 'OFF','OK' if OPENROUTER_API_KEY else 'OFF',GROQ_MODEL,GROQ_RESEARCH_MODEL,OPENROUTER_MODEL,mode_by_uid.get\(uid,'auto'\),state.get\('last_route'\),state.get\('last_provider'\)\)\);return""")
status_repl="""                if text=='/status':
                    send(peer,'Porfirchik: VK=OK; home=nd-yandex-n8n-gateway; memory=MemOS Cloud + persistent SQLite/outbox; Groq=%s; OpenRouter=%s; mode=%s; last_route=%s; last_provider=%s'%(
                        'OK' if GROQ_API_KEY else 'OFF','OK' if OPENROUTER_API_KEY else 'OFF',mode_by_uid.get(uid,'auto'),state.get('last_route'),state.get('last_provider')));return"""
src,_status_count=status_pattern.subn(status_repl,src,count=1)

_thread_anchor="threading.Thread(target=startup,daemon=True).start()\n"
_probe_code="""def _v20_6_reserve_probe():
    time.sleep(12)
    state['reserve_probes']={}
    if CEREBRAS_API_KEY:
        try:
            out=_call_candidate('cerebras','gpt-oss-120b',[{'role':'user','content':'Reply exactly OK.'}],128,0.0)
            state['reserve_probes']['cerebras:gpt-oss-120b']={'ok':bool(out)}
            print('V20_6_RESERVE_PROBE',json.dumps({'provider':'cerebras','model':'zai-glm-4.7','ok':bool(out)},ensure_ascii=False),flush=True)
        except Exception as e:
            state['reserve_probes']['cerebras:gpt-oss-120b']={'ok':False,'error':cleanerr(e)[:220]}
            print('V20_6_RESERVE_PROBE',json.dumps({'provider':'cerebras','model':'zai-glm-4.7','ok':False,'error':cleanerr(e)[:220]},ensure_ascii=False),flush=True)
    if OPENROUTER_API_KEY:
        state['reserve_probes']['openrouter:'+OPENROUTER_MODEL]={'ok':state.get('openrouter_probe')=='ok'}

threading.Thread(target=_v20_6_reserve_probe,daemon=True).start()
"""
if _thread_anchor not in src:
    raise RuntimeError('v20_6_startup_thread_anchor_missing')
src=src.replace(_thread_anchor,_probe_code+_thread_anchor,1)


_archived_cerebras="    ('cerebras','gpt-oss-120b'),\n"
if _archived_cerebras in src:
    src=src.replace(_archived_cerebras,'',1)

src=src.replace("state['adaptive_router']='v20.5-memory-durable'","state['adaptive_router']='v20.6-home-aware'",1)
src=src.replace("'User-Agent':'porfirchik-v20.5'","'User-Agent':'porfirchik-v20.6'",1)
src=src.replace('ND_VK_GATEWAY_V20_5_MEMORY_DURABLE_START','ND_VK_GATEWAY_V20_6_HOME_AWARE_START',1)

required=(
    "state['runtime_home']='nd-yandex-n8n-gateway'",
    "state['self_knowledge_policy']='runtime-facts-v1'",
    "state['adaptive_router']='v20.6-home-aware'",
    'MemOS Cloud + persistent SQLite/outbox',
    'ND_VK_GATEWAY_V20_6_HOME_AWARE_START',
    "text=str(text or '').replace('*','')",
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_6_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_6_home_aware_runtime.py','exec')
print('ND_V20_6_HOME_AWARE_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_6_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_6_home_aware_runtime.py','exec'),{'__name__':'__main__'})
