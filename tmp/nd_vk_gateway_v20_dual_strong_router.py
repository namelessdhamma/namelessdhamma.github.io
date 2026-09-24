import ast
import urllib.request

V18 = 'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/tmp/nd_vk_gateway_v18_adaptive_router.py'
source = urllib.request.urlopen(V18, timeout=30).read().decode('utf-8')

def literal_assignment(src, name):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value), node
    raise RuntimeError(name + ' assignment missing')

def replace_assignment(src, name, value):
    _, node = literal_assignment(src, name)
    lines = src.splitlines(True)
    if node.lineno != node.end_lineno:
        raise RuntimeError(name + ' assignment unexpectedly multiline')
    old = lines[node.lineno - 1]
    indent = old[:len(old) - len(old.lstrip())]
    newline = '\n' if old.endswith('\n') else ''
    lines[node.lineno - 1] = indent + name + '=' + repr(value) + newline
    return ''.join(lines)

patch, _ = literal_assignment(source, 'v18_patch_code')
adaptive, _ = literal_assignment(patch, '_adaptive_code')

# Make provider availability mean availability of the canonical strong-only pool.
start = adaptive.index('def _any_adaptive_provider():\n')
end = adaptive.index('def _adaptive_candidates(route):\n', start)
strong_header = '''def _any_adaptive_provider():
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

'''
adaptive = adaptive[:start] + strong_header + adaptive[end:]

# Replace broad adaptive candidate construction with the explicit two-route table only.
start = adaptive.index('def _adaptive_candidates(route):\n')
end = adaptive.index('def _call_candidate(', start)
strong_candidates = '''def _adaptive_candidates(route):
    key='write' if route=='write' else 'deep_research'
    out=[]
    for provider,model in MODEL_ROUTE_TABLE[key]:
        if _configured(provider):
            out.append((provider,model))
    return out

'''
adaptive = adaptive[:start] + strong_candidates + adaptive[end:]

# Deep/research is now one canonical route.
adaptive = adaptive.replace("def adaptive_chat(messages,route='deep',max_tokens=4200,temperature=0.3):", "def adaptive_chat(messages,route='deep_research',max_tokens=4200,temperature=0.3):", 1)

# Replace state metadata with the canonical dual strong-router state.
start = adaptive.index("state['adaptive_router']='v18'\n")
end = adaptive.index("def adaptive_startup_probe():\n", start)
state_block = '''state['adaptive_router']='v20-dual-strong'
state['strong_only']=True
state['semantic_routes']=['write','deep_research']
state['model_route_table']={
    k:[p+':'+m for p,m in v] for k,v in MODEL_ROUTE_TABLE.items()
}
state['provider_pool']={
    'openrouter':bool(OPENROUTER_API_KEY),
    'cloudflare':bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
    'groq':bool(GROQ_API_KEY),
}
state['provider_probes']={}
state['last_adaptive_provider']=None

'''
adaptive = adaptive[:start] + state_block + adaptive[end:]

# Startup probes only the exact production strong pool; no unrelated provider can become fallback.
start = adaptive.index('def adaptive_startup_probe():\n')
probe = '''def adaptive_startup_probe():
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
                out=_call_candidate(provider,model,[{'role':'user','content':'Reply exactly OK.'}],48,0.0)
                ok=bool(out)
                state['provider_probes'][key]={'ok':ok,'model':model}
                print('STRONG_PROVIDER_PROBE',json.dumps(
                    {'provider':provider,'model':model,'ok':ok},ensure_ascii=False
                ),flush=True)
            except Exception as e:
                state['provider_probes'][key]={'ok':False,'model':model,'error':cleanerr(e)[:220]}
                print('STRONG_PROVIDER_PROBE',json.dumps(
                    {'provider':provider,'model':model,'ok':False,'error':cleanerr(e)[:220]},ensure_ascii=False
                ),flush=True)
'''
adaptive = adaptive[:start] + probe
patch = replace_assignment(patch, '_adaptive_code', adaptive)

new_rr = '''def routed_response(uid,text):
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
    print('AI_ROUTE',json.dumps({
        'uid':uid,'route':route,'raw_route':raw_route,
        'web_retrieval':use_web,'strong_only':True
    },ensure_ascii=False),flush=True)
    def save(out,provider=None):
        history_by_uid[uid]=(hist+[{'role':'user','content':text[:12000]},{'role':'assistant','content':out[:18000]}])[-10:]
        state['ai_calls']+=1
        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        return out
    if route=='write':
        try:
            msgs=[{'role':'system','content':WRITE_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]
            out=adaptive_chat(msgs,'write',5200,0.65)
            return save(out,state.get('last_adaptive_provider'))
        except Exception as e:
            print('STRONG_ROUTE_ERROR',cleanerr(e),flush=True)
            state['last_error']=cleanerr(e)
    else:
        if use_web:
            try:
                evidence=independent_web_research(text)
            except Exception as e:
                print('WEB_RETRIEVAL_ERROR',cleanerr(e),flush=True)
                state['last_error']=cleanerr(e)
                return save('Не удалось получить независимые веб-источники для этого запроса. Актуальные факты не буду подменять памятью модели.','research-error-no-fabrication')
            synth='User request:\n'+text[:7000]+'\n\nFresh web material gathered independently of the model provider:\n'+evidence[:28000]+'\n\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'
            msgs=[{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}]
        else:
            msgs=[{'role':'system','content':DEEP_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]
        try:
            out=adaptive_chat(msgs,'deep_research',5600,0.25)
            return save(out,state.get('last_adaptive_provider'))
        except Exception as e:
            print('STRONG_ROUTE_ERROR',cleanerr(e),flush=True)
            state['last_error']=cleanerr(e)
    print('ALL_STRONG_ROUTES_UNAVAILABLE',state.get('last_error','unknown'),flush=True)
    degraded=('Сейчас все сильные ИИ-маршруты временно недоступны или исчерпали лимиты. '
              'Я не буду переключаться на более слабую модель. Контекст последних сообщений сохраняется в VK; '
              'следующий запрос снова проверит сильные маршруты.')
    return save(degraded,'degraded-no-strong-provider')
'''
patch = replace_assignment(patch, '_new_rr', new_rr)
patch = patch.replace('ND_VK_GATEWAY_V18_ADAPTIVE_ROUTER_START', 'ND_VK_GATEWAY_V20_DUAL_STRONG_ROUTER_START')
source = replace_assignment(source, 'v18_patch_code', patch)
source = source.replace("print('ND_V18_ADAPTIVE_ROUTER_WRAPPER_READY',flush=True)", "print('ND_V20_DUAL_STRONG_ROUTER_WRAPPER_READY',flush=True)")
source = source.replace("exec(compile(outer,'nd_vk_gateway_v18_adaptive_router.py','exec'))", "exec(compile(outer,'nd_vk_gateway_v20_dual_strong_router.py','exec'))")

print('ND_V20_CANDIDATE_PATCH_READY', flush=True)
exec(compile(source, 'nd_vk_gateway_v20_dual_strong_router_wrapper.py', 'exec'))
