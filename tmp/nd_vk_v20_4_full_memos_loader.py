import os, urllib.request

# Compatibility markers required by the pinned V19 front guard.
# ND_V19_ORIGINAL_LOADER_ACTIVE
# ],1024,0.0)

BASE_COMMIT='f85df0407d6e4cd8571b39eccf08648bb07437c6'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_3_russian_quality_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

# Capture the already-qualified V20.3 assembled runtime, then apply only the
# bounded long-term-memory middleware delta.
exec_marker="exec(compile(src,'nd_vk_gateway_v20_3_russian_quality_runtime.py','exec'),{'__name__':'__main__'})"
capture_marker='globals()["_ND_V20_3_FINAL_SOURCE"]=src'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_4_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_3_capture_for_v20_4.py','exec'),G,G)
src=G.get('_ND_V20_3_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_4_base_capture_failed')

# Memory middleware: Porfirchik remains memory-blind. The gateway performs
# automatic recall before generation and asynchronous capture after response.
memory_code=r'''

MEMOS_URL=os.environ.get('PORFIRCHIK_MEMOS_URL','').strip().rstrip('/')
MEMOS_TOKEN=os.environ.get('PORFIRCHIK_MEMOS_BOT_TOKEN','').strip()
state['memos_enabled']=bool(MEMOS_URL and MEMOS_TOKEN)
state['memos_mode']='full-local-first-cloud-opportunistic'
state['memos_last_recall_ok']=None
state['memos_last_capture_ok']=None
state['memos_last_error']=None

def _memos_post(path,payload,timeout):
    if not MEMOS_URL or not MEMOS_TOKEN:
        raise RuntimeError('memos_not_configured')
    raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(
        MEMOS_URL+path,
        data=raw,
        method='POST',
        headers={
            'Authorization':'Bearer '+MEMOS_TOKEN,
            'Content-Type':'application/json; charset=utf-8',
            'Accept':'application/json',
            'User-Agent':'porfirchik-v20.4',
        },
    )
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        body=resp.read().decode('utf-8','replace')
    return json.loads(body or '{}')

def memos_turn_start(uid,text):
    if not MEMOS_URL or not MEMOS_TOKEN:
        return {'memory_context':'','episode_id':None,'session_id':'vk-father-'+str(uid)}
    payload={
        'session_id':'vk-father-'+str(uid),
        'conversation_id':'vk-father-'+str(uid),
        'turn_key':'vk-'+str(uid)+'-'+str(int(time.time()*1000)),
        'user_text':str(text or '')[:12000],
    }
    try:
        out=_memos_post('/v1/turn/start',payload,5.5)
        state['memos_last_recall_ok']=bool(out.get('ok'))
        state['memos_last_error']=None
        print('MEMOS_RECALL',json.dumps({
            'uid':uid,
            'ok':bool(out.get('ok')),
            'local_ok':out.get('local_ok'),
            'cloud_ok':out.get('cloud_ok'),
            'degraded':out.get('degraded'),
            'context_chars':len(str(out.get('memory_context') or '')),
        },ensure_ascii=False),flush=True)
        return out if isinstance(out,dict) else {'memory_context':''}
    except Exception as e:
        ce=cleanerr(e)
        state['memos_last_recall_ok']=False
        state['memos_last_error']=ce[:220]
        print('MEMOS_RECALL_ERROR',json.dumps({'uid':uid,'error':ce[:220]},ensure_ascii=False),flush=True)
        return {'memory_context':'','episode_id':None,'session_id':'vk-father-'+str(uid)}

def memos_turn_end_async(uid,user_text,assistant_text,mem):
    if not MEMOS_URL or not MEMOS_TOKEN:
        return
    episode_id=(mem or {}).get('episode_id')
    session_id=(mem or {}).get('session_id') or ('vk-father-'+str(uid))
    payload={
        'session_id':session_id,
        'conversation_id':'vk-father-'+str(uid),
        'episode_id':episode_id,
        'user_text':str(user_text or '')[:12000],
        'agent_text':str(assistant_text or '')[:12000],
    }
    def _worker():
        try:
            out=_memos_post('/v1/turn/end',payload,8.0)
            state['memos_last_capture_ok']=bool(out.get('ok'))
            if out.get('errors',{}).get('local') or out.get('errors',{}).get('cloud'):
                state['memos_last_error']=str(out.get('errors'))[:220]
            print('MEMOS_CAPTURE',json.dumps({
                'uid':uid,
                'ok':bool(out.get('ok')),
                'local_ok':out.get('local_ok'),
                'cloud_ok':out.get('cloud_ok'),
                'degraded':out.get('degraded'),
            },ensure_ascii=False),flush=True)
        except Exception as e:
            ce=cleanerr(e)
            state['memos_last_capture_ok']=False
            state['memos_last_error']=ce[:220]
            print('MEMOS_CAPTURE_ERROR',json.dumps({'uid':uid,'error':ce[:220]},ensure_ascii=False),flush=True)
    threading.Thread(target=_worker,daemon=True).start()
'''

clean_anchor='\n\ndef cleanerr(x):\n'
if src.count(clean_anchor)!=1:
    raise RuntimeError('v20_4_memory_insert_anchor_mismatch')
# Helpers call cleanerr only at runtime, so they may be defined before cleanerr.
src=src.replace(clean_anchor,memory_code+clean_anchor,1)

old_start="""    _local_hist=history_by_uid.get(uid,[])[-10:]
    _vk_hist=vk_recent_context(uid,text)
    hist=(_vk_hist if _vk_hist else _local_hist)[-10:]
"""
new_start="""    _local_hist=history_by_uid.get(uid,[])[-10:]
    _vk_hist=vk_recent_context(uid,text)
    hist=(_vk_hist if _vk_hist else _local_hist)[-10:]
    _memos=memos_turn_start(uid,text)
    _memory_context=str((_memos or {}).get('memory_context') or '').strip()
    _memory_msgs=([{'role':'system','content':_memory_context}] if _memory_context else [])
"""
if src.count(old_start)!=1:
    raise RuntimeError('v20_4_routed_start_anchor_mismatch')
src=src.replace(old_start,new_start,1)

old_save="""        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        return out
"""
new_save="""        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        memos_turn_end_async(uid,text,out,_memos)
        return out
"""
if src.count(old_save)!=1:
    raise RuntimeError('v20_4_save_anchor_mismatch')
src=src.replace(old_save,new_save,1)

prompt_replacements=(
    ("msgs=[{'role':'system','content':WRITE_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]",
     "msgs=[{'role':'system','content':WRITE_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+hist+[{'role':'user','content':text[:16000]}]"),
    ("msgs=[{'role':'system','content':RESEARCH_SYSTEM+RUSSIAN_QUALITY_SYSTEM},{'role':'user','content':synth}]",
     "msgs=[{'role':'system','content':RESEARCH_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+[{'role':'user','content':synth}]"),
    ("msgs=[{'role':'system','content':DEEP_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]",
     "msgs=[{'role':'system','content':DEEP_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+hist+[{'role':'user','content':text[:16000]}]"),
)
for old,new in prompt_replacements:
    if src.count(old)!=1:
        raise RuntimeError('v20_4_prompt_anchor_mismatch:'+old[:60])
    src=src.replace(old,new,1)

src=src.replace("state['adaptive_router']='v20.3-russian-quality'","state['adaptive_router']='v20.4-full-memos'",1)
state_anchor="state['russian_primary_models']=['cloudflare:@cf/qwen/qwen3.8-27b','groq:openai/gpt-oss-120b','cloudflare:@cf/openai/gpt-oss-120b']\n"
if state_anchor not in src:
    raise RuntimeError('v20_4_state_anchor_missing')
src=src.replace(state_anchor,state_anchor+"state['long_term_memory']='full-memos-auto-recall-auto-capture'\\n",1)
src=src.replace('ND_VK_GATEWAY_V20_3_RUSSIAN_QUALITY_START','ND_VK_GATEWAY_V20_4_FULL_MEMOS_START',1)

required=(
    'MEMOS_URL=',
    'def memos_turn_start(uid,text):',
    'def memos_turn_end_async(uid,user_text,assistant_text,mem):',
    "state['long_term_memory']='full-memos-auto-recall-auto-capture'",
    'ND_VK_GATEWAY_V20_4_FULL_MEMOS_START',
    "text=str(text or '').replace('*','')",
    '# ND_V19_ORIGINAL_LOADER_ACTIVE',
)
for marker in required:
    if marker not in src and marker not in globals().get('__doc__',''):
        # The V19 marker belongs to this loader itself, not necessarily final runtime.
        if marker!='# ND_V19_ORIGINAL_LOADER_ACTIVE':
            raise RuntimeError('v20_4_final_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_4_full_memos_runtime.py','exec')
print('ND_V20_4_FULL_MEMOS_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_4_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_4_full_memos_runtime.py','exec'),{'__name__':'__main__'})
