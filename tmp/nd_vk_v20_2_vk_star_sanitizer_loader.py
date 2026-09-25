print("ND_V19_ORIGINAL_LOADER_ACTIVE",flush=True)
import ast,builtins,urllib.request
V17="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/23b4b0e95652355f3e8a01473fe944e899c87ace/tmp/nd_vk_gateway_v17_omniroute_reserve.py"
V18="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/tmp/nd_vk_gateway_v18_adaptive_router.py"
v17=urllib.request.urlopen(V17,timeout=30).read().decode("utf-8")
v18=urllib.request.urlopen(V18,timeout=30).read().decode("utf-8")
patch=None
for n in ast.parse(v18).body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="v18_patch_code" for t in n.targets):
        patch=ast.literal_eval(n.value);break
if not patch: raise RuntimeError("v18_patch_literal_missing")
cap={}
rc=builtins.compile
re=builtins.exec
G={"__name__":"__main__"}
def cp(source,filename,mode,*a,**k):
    if filename=="nd_vk_gateway_v13_independent_web.py":
        cap["src"]=source.decode("utf-8") if isinstance(source,(bytes,bytearray)) else source
    return rc(source,filename,mode,*a,**k)
def ep(obj,gl=None,lo=None):
    if getattr(obj,"co_filename","")=="nd_vk_gateway_v13_independent_web.py":
        cap["blocked"]=True;return None
    return re(obj,G,G)
G["compile"]=cp;G["exec"]=ep
re(rc(v17,"nd_v17_capture_entry.py","exec"),G,G)
if not cap.get("blocked") or not cap.get("src"): raise RuntimeError("v17_final_source_capture_failed")
P={"src":cap["src"]}
re(rc(patch,"nd_v18_patch_only.py","exec"),P,P)
P["_adaptive_code"]=P["_adaptive_code"].replace("],48,0.0)", "],1024,0.0)",1)

# V20 canonical dual strong-router delta: mutate the already-extracted V18 patch only.
_a=P["_adaptive_code"]
_s=_a.index("def _any_adaptive_provider():\n")
_e=_a.index("def _call_candidate(",_s)
_strong='''def _any_adaptive_provider():
    return any(_configured(x) for x in ('openrouter','cloudflare','groq'))

STRONG_OPENROUTER_MODEL='nvidia/nemotron-3-ultra-550b-a55b:free'
STRONG_CLOUDFLARE_MODEL='@cf/nvidia/nemotron-3-120b-a12b'
STRONG_GROQ_MODEL='openai/gpt-oss-120b'
MODEL_ROUTE_TABLE={
    'write':[
        ('openrouter',STRONG_OPENROUTER_MODEL),
        ('cloudflare',STRONG_CLOUDFLARE_MODEL),
        ('groq',STRONG_GROQ_MODEL),
    ],
    'deep_research':[
        ('openrouter',STRONG_OPENROUTER_MODEL),
        ('groq',STRONG_GROQ_MODEL),
        ('cloudflare',STRONG_CLOUDFLARE_MODEL),
    ],
}

def _adaptive_candidates(route):
    key='write' if route=='write' else 'deep_research'
    return [(p,m) for p,m in MODEL_ROUTE_TABLE[key] if _configured(p)]

EMERGENCY_RESERVE_TABLE=[
    ('cloudflare','@cf/zai-org/glm-4.7-flash'),
    ('cerebras','zai-glm-4.7'),
    ('cerebras','gpt-oss-120b'),
    ('omniroute',OMNIROUTE_MODEL),
    ('mistral',MISTRAL_MODEL),
    ('openai',OPENAI_MODEL),
    ('zai',ZAI_MODEL),
]

def _emergency_candidates():
    strong={(p,m) for rows in MODEL_ROUTE_TABLE.values() for p,m in rows}
    base=list(EMERGENCY_RESERVE_TABLE)
    if OPENROUTER_MODEL and ('openrouter',OPENROUTER_MODEL) not in strong:
        base.append(('openrouter',OPENROUTER_MODEL))
    out=[];seen=set()
    for p,m in base:
        k=(p,str(m or ''))
        if not m or k in strong or k in seen or not _configured(p):
            continue
        seen.add(k);out.append(k)
    return out

def emergency_reserve_chat(messages,max_tokens=3200,temperature=0.35):
    errs=[]
    candidates=_emergency_candidates()
    if not candidates:
        raise RuntimeError('no emergency reserve providers configured')
    for provider,model in candidates:
        circuit_name=(provider+':'+model) if provider in ('openrouter','cerebras','cloudflare','groq') else provider
        if _provider_blocked(circuit_name):
            errs.append(provider+':'+model+':circuit_open')
            continue
        try:
            out=_call_candidate(provider,model,messages,max_tokens,temperature)
            selected=provider+':'+model
            state['last_emergency_provider']=selected
            state['last_provider']=selected
            print('AI_EMERGENCY_RESERVE_SELECTED',json.dumps(
                {'provider':provider,'model':model},ensure_ascii=False
            ),flush=True)
            return out
        except Exception as e:
            ce=cleanerr(e)
            errs.append(provider+':'+model+':'+ce)
            print('AI_EMERGENCY_RESERVE_ERROR',json.dumps(
                {'provider':provider,'model':model,'error':ce},ensure_ascii=False
            ),flush=True)
    raise RuntimeError('emergency reserve providers unavailable: '+' | '.join(errs[-8:]))

'''
_a=_a[:_s]+_strong+_a[_e:]
_a=_a.replace("def adaptive_chat(messages,route='deep',max_tokens=4200,temperature=0.3):","def adaptive_chat(messages,route='deep_research',max_tokens=4200,temperature=0.3):",1)

_s=_a.index("state['adaptive_router']='v18'\n")
_e=_a.index("def adaptive_startup_probe():\n",_s)
_state='''state['adaptive_router']='v20.1-strong-primary-emergency-reserve'
state['strong_only']=False
state['strong_primary']=True
state['emergency_reserve_enabled']=True
state['semantic_routes']=['write','deep_research']
state['model_route_table']={k:[p+':'+m for p,m in v] for k,v in MODEL_ROUTE_TABLE.items()}
state['emergency_reserve_table']=[p+':'+str(m) for p,m in EMERGENCY_RESERVE_TABLE]
state['provider_pool']={
    'openrouter':bool(OPENROUTER_API_KEY),
    'cloudflare':bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
    'groq':bool(GROQ_API_KEY),
}
state['provider_probes']={}
state['last_adaptive_provider']=None
state['last_emergency_provider']=None

'''
_probe='''def adaptive_startup_probe():
    time.sleep(10)
    seen=set()
    for route in ('write','deep_research'):
        for provider,model in MODEL_ROUTE_TABLE[route]:
            key=provider+':'+model
            if key in seen:
                continue
            seen.add(key)
            if not _configured(provider):
                state['provider_probes'][key]={'ok':False,'stage':'not_configured','model':model}
                continue
            try:
                out=_call_candidate(provider,model,[{'role':'user','content':'Reply exactly OK.'}],1024,0.0)
                ok=bool(out)
                state['provider_probes'][key]={'ok':ok,'model':model}
                print('STRONG_PROVIDER_PROBE',json.dumps({'provider':provider,'model':model,'ok':ok},ensure_ascii=False),flush=True)
            except Exception as e:
                ce=cleanerr(e)
                state['provider_probes'][key]={'ok':False,'model':model,'error':ce[:220]}
                print('STRONG_PROVIDER_PROBE',json.dumps({'provider':provider,'model':model,'ok':False,'error':ce[:220]},ensure_ascii=False),flush=True)
'''
_a=_a[:_s]+_state+_probe
P["_adaptive_code"]=_a

P["_new_rr"]='''def routed_response(uid,text):
    _local_hist=history_by_uid.get(uid,[])[-10:]
    _vk_hist=vk_recent_context(uid,text)
    hist=(_vk_hist if _vk_hist else _local_hist)[-10:]
    forced=mode_by_uid.get(uid,'auto')
    raw_route=classify_route(text) if forced=='auto' else forced
    route='write' if raw_route=='write' else 'deep_research'
    use_web=(raw_route=='research')
    state['last_route']=route
    state['last_raw_route']=raw_route
    state['last_web_retrieval']=use_web
    print('AI_ROUTE',json.dumps({'uid':uid,'route':route,'web_retrieval':use_web,'strong_primary':True,'emergency_reserve':True},ensure_ascii=False),flush=True)
    def save(out,provider=None):
        history_by_uid[uid]=(hist+[{'role':'user','content':text[:12000]},{'role':'assistant','content':out[:18000]}])[-10:]
        state['ai_calls']+=1
        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        return out
    if route=='write':
        try:
            msgs=[{'role':'system','content':WRITE_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]
            return save(adaptive_chat(msgs,'write',5200,0.65),state.get('last_adaptive_provider'))
        except Exception as e:
            state['last_error']=cleanerr(e)
            print('STRONG_ROUTE_ERROR',state['last_error'],flush=True)
    else:
        if use_web:
            try:
                evidence=independent_web_research(text)
            except Exception as e:
                state['last_error']=cleanerr(e)
                print('WEB_RETRIEVAL_ERROR',state['last_error'],flush=True)
                return save('Не удалось получить независимые веб-источники для этого запроса. Актуальные факты не буду подменять памятью модели.','research-error-no-fabrication')
            synth='User request:\\n'+text[:7000]+'\\n\\nFresh web material gathered independently of the model provider:\\n'+evidence[:28000]+'\\n\\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'
            msgs=[{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}]
        else:
            msgs=[{'role':'system','content':DEEP_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]
        try:
            return save(adaptive_chat(msgs,'deep_research',5600,0.25),state.get('last_adaptive_provider'))
        except Exception as e:
            state['last_error']=cleanerr(e)
            print('STRONG_ROUTE_ERROR',state['last_error'],flush=True)
    print('ALL_STRONG_ROUTES_UNAVAILABLE',state.get('last_error','unknown'),flush=True)
    try:
        reserve_tokens=4200 if route=='write' else 3600
        reserve_temp=0.55 if route=='write' else 0.3
        out=emergency_reserve_chat(msgs,reserve_tokens,reserve_temp)
        return save(out,state.get('last_emergency_provider') or 'emergency-reserve')
    except Exception as reserve_e:
        state['last_error']=cleanerr(reserve_e)
        print('ALL_AI_ROUTES_UNAVAILABLE',state['last_error'],flush=True)
    return save('Сейчас недоступны и сильные модели, и аварийные резервные маршруты. Контекст последних сообщений сохраняется в VK; следующий запрос автоматически снова начнёт с сильных моделей.','degraded-no-provider')
'''
print("ND_V20_2_STRONG_PRIMARY_RESERVE_DELTA_APPLIED",flush=True)
rr=P.get("_new_rr","")
bad="synth='User request:\n'+text[:7000]+'\n\nFresh web material gathered independently of the model provider:\n'+evidence[:28000]+'\n\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'"
good="synth='User request:\\n'+text[:7000]+'\\n\\nFresh web material gathered independently of the model provider:\\n'+evidence[:28000]+'\\n\\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'"
if bad in rr:
    rr=rr.replace(bad,good,1)
elif good not in rr:
    raise RuntimeError("v20_new_rr_escape_state_invalid")
final=P["_pre"]+P["_adaptive_code"]+rr+P["_rr_end"]+P["_post"]
if P["_groq_gate"] not in final: raise RuntimeError("v18_final_groq_gate_missing")
final=final.replace(P["_groq_gate"],P["_adaptive_gate"],1)
if P["_thread_marker"] not in final: raise RuntimeError("v18_final_thread_marker_missing")
final=final.replace(P["_thread_marker"],"threading.Thread(target=adaptive_startup_probe,daemon=True).start()\n"+P["_thread_marker"],1)
final=final.replace("ND_VK_GATEWAY_V15B_FATHER_MIN_PROFILE_START","ND_VK_GATEWAY_V20_2_STRONG_PRIMARY_RESERVE_START",1)
if "adaptive_startup_probe" not in final: raise RuntimeError("v18_final_assembly_failed")

# V20.2: VK does not render Markdown emphasis. Strip all asterisks at the final outbound send boundary.
_send_marker="def send(peer,text):\n    text=str(text or '')\n"
_send_patched="def send(peer,text):\n    text=str(text or '').replace('*','')\n"
if _send_marker not in final:
    raise RuntimeError("v20_2_vk_send_sanitizer_anchor_missing")
final=final.replace(_send_marker,_send_patched,1)
if _send_patched not in final:
    raise RuntimeError("v20_2_vk_send_sanitizer_patch_failed")
if "**Жирный** и *курсив*".replace("*","")!="Жирный и курсив":
    raise RuntimeError("v20_2_vk_send_sanitizer_selftest_failed")
print("ND_V20_2_VK_STAR_SANITIZER_READY",flush=True)
print("ND_V20_2_STRONG_PRIMARY_RESERVE_ASSEMBLY_READY",flush=True)
re(rc(final,"nd_vk_gateway_v20_2_strong_primary_reserve_runtime.py","exec"),{"__name__":"__main__"})
