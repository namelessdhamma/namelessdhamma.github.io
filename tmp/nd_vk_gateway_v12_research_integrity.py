import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c617c9b200cb1637fca544985d35ab2a1b8d9e08/tmp/nd_vk_gateway_v9_free_router.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

repls=[
("OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','')","OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','') or os.environ.get('OpenRouter','')"),
("OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')","OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')\nOPENROUTER_MODELS=[OPENROUTER_MODEL,'z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"),
("'last_event_at':None,'ai_calls':0","'last_event_at':None,'ai_calls':0,'last_openrouter_model':None"),
("payload={'model':OPENROUTER_MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,","payload={'models':OPENROUTER_MODELS,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,"),
("if not ch:raise RuntimeError('OpenRouter returned no choices')","if not ch:raise RuntimeError('OpenRouter returned no choices: '+cleanerr(j))"),
("ND_VK_GATEWAY_V9_FREE_ROUTER_START","ND_VK_GATEWAY_V12_RESEARCH_INTEGRITY_START"),
("state['ai_calls']+=1;state['last_provider']=provider\n        return out","state['ai_calls']+=1;state['last_provider']=provider\n        print('AI_PROVIDER',json.dumps({'uid':uid,'route':route,'provider':provider},ensure_ascii=False),flush=True)\n        return out"),
]
for old,new in repls:
    if old not in src:
        raise RuntimeError('Expected V9 pattern not found: '+old[:120])
    src=src.replace(old,new,1)

old_or="""        j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
    ch=j.get('choices') or []
"""
new_or="""        j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
    used_model=str(j.get('model') or j.get('provider') or 'unknown')
    state['last_openrouter_model']=used_model
    print('OPENROUTER_MODEL_USED',json.dumps({'model':used_model},ensure_ascii=False),flush=True)
    ch=j.get('choices') or []
"""
if old_or not in src:
    raise RuntimeError('OpenRouter telemetry pattern not found')
src=src.replace(old_or,new_or,1)

old_research="""        if route=='research':
            evidence=groq_chat([
                {'role':'system','content':'Research the request using web/tools when useful. Return factual findings, source names/URLs when available, disagreements and uncertainty. Do not fabricate citations.'},
                {'role':'user','content':text[:10000]}
            ],GROQ_RESEARCH_MODEL,'medium',3800)
            if OPENROUTER_API_KEY:
                synth='User request:\\n'+text[:9000]+'\\n\\nResearch material gathered by Groq Compound:\\n'+evidence[:24000]+'\\n\\nProduce a rigorous synthesis. Preserve useful source references exactly as supplied. Do not invent sources.'
                return save(openrouter_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',4800,0.25),'openrouter-nemotron+groq-compound')
            return save(evidence,'groq-compound')
"""
new_research="""        if route=='research':
            evidence=groq_chat([
                {'role':'system','content':'Research the request using web/tools when useful. Produce a compact source-backed research brief. Include current dates when relevant, source names and direct URLs in the answer, disagreements and uncertainty. Prefer primary/official sources. Do not fabricate citations. Keep the brief under about 1800 words so it can be passed safely to a second model.'},
                {'role':'user','content':text[:9000]}
            ],GROQ_RESEARCH_MODEL,'medium',2800)
            if OPENROUTER_API_KEY:
                for cap in (9000,4500):
                    try:
                        synth='User request:\\n'+text[:6000]+'\\n\\nWEB RESEARCH MATERIAL FROM GROQ COMPOUND:\\n'+evidence[:cap]+'\\n\\nUsing only this research material for current factual claims, produce a rigorous synthesis. Preserve source names and URLs actually present. Do not invent sources, models, prices, limits or dates. If the material is insufficient, say so explicitly.'
                        out=openrouter_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',3200,0.2)
                        prov='openrouter:'+str(state.get('last_openrouter_model') or 'unknown')+'+groq-compound'
                        return save(out,prov)
                    except Exception as oe:
                        print('RESEARCH_OPENROUTER_SYNTH_ERROR',json.dumps({'cap':cap,'error':cleanerr(oe)},ensure_ascii=False),flush=True)
                try:
                    synth='User request:\\n'+text[:6000]+'\\n\\nWEB RESEARCH MATERIAL FROM GROQ COMPOUND:\\n'+evidence[:9000]+'\\n\\nSynthesize strictly from the supplied web research. Preserve actual URLs. Do not add remembered current facts not supported by the research material.'
                    out=groq_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],GROQ_MODEL,'high',3000)
                    return save(out,'groq-gpt-oss+groq-compound')
                except Exception as ge:
                    print('RESEARCH_GROQ_SYNTH_ERROR',cleanerr(ge),flush=True)
            return save(evidence,'groq-compound-direct')
"""
if old_research not in src:
    raise RuntimeError('Research block pattern not found')
src=src.replace(old_research,new_research,1)

old_write="""            if OPENROUTER_API_KEY:return save(openrouter_chat(msgs,'high',5200,0.7),'openrouter-nemotron')
"""
new_write="""            if OPENROUTER_API_KEY:
                out=openrouter_chat(msgs,'high',5200,0.7)
                return save(out,'openrouter:'+str(state.get('last_openrouter_model') or 'unknown'))
"""
if old_write not in src: raise RuntimeError('Write provider pattern not found')
src=src.replace(old_write,new_write,1)
old_deep="""            if OPENROUTER_API_KEY:return save(openrouter_chat(msgs,'high',5000,0.3),'openrouter-nemotron')
"""
new_deep="""            if OPENROUTER_API_KEY:
                out=openrouter_chat(msgs,'high',5000,0.3)
                return save(out,'openrouter:'+str(state.get('last_openrouter_model') or 'unknown'))
"""
if old_deep not in src: raise RuntimeError('Deep provider pattern not found')
src=src.replace(old_deep,new_deep,1)

old_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')
"""
new_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        if route=='research':
            return save('Исследовательский контур не смог надёжно завершить поиск. Я не буду подменять актуальное исследование ответом из памяти. Повторите запрос позже или переключитесь на другой режим.','research-error-no-fabrication')
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')
"""
if old_outer not in src: raise RuntimeError('Outer fallback pattern not found')
src=src.replace(old_outer,new_outer,1)

exec(compile(src,'nd_vk_gateway_v12_research_integrity.py','exec'))
