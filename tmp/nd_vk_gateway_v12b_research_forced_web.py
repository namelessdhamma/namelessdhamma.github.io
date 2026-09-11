import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/8100fde7de32c3e6d873c55d0894c484e2639120/tmp/nd_vk_gateway_v12_research_integrity.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="exec(compile(src,'nd_vk_gateway_v12_research_integrity.py','exec'))"
if marker not in outer: raise RuntimeError('V12 exec marker not found')
addon=r'''
insert_before="def heuristic_route(text):\n"
if insert_before not in src: raise RuntimeError('heuristic route marker not found for research patch')
research_fn=r"""
def groq_research_web(user_text):
    if not GROQ_API_KEY: raise RuntimeError('GROQ_API_KEY missing')
    today=time.strftime('%Y-%m-%d',time.gmtime())
    payload={
        'model':GROQ_RESEARCH_MODEL,
        'messages':[
            {'role':'system','content':'You are the evidence-gathering stage of ND research. Today is '+today+'. For current or time-sensitive claims you MUST use web search. Prefer official/primary sources and, when useful, visit the source pages. Return a compact source-backed brief with direct URLs, dates, disagreements, and uncertainty. Never substitute model memory for current facts.'},
            {'role':'user','content':user_text}
        ],
        'max_completion_tokens':2800,
        'compound_custom':{'tools':{'enabled_tools':['web_search','visit_website']}}
    }
    j=http_json('https://api.groq.com/openai/v1/chat/completions',payload,GROQ_API_KEY,180,{'Groq-Model-Version':'latest'})
    ch=j.get('choices') or []
    if not ch: raise RuntimeError('Compound research returned no choices')
    msg=ch[0].get('message') or {}
    out=(msg.get('content') or '').strip()
    tools=msg.get('executed_tools') or []
    if not tools: raise RuntimeError('Compound research used no web tools')
    raw=json.dumps(tools,ensure_ascii=False)
    urls=[]
    for u in re.findall(r'https?://[^\\s"\\\\<>]+',raw):
        u=u.rstrip(').,;]')
        if u not in urls: urls.append(u)
        if len(urls)>=16: break
    print('RESEARCH_WEB_TOOLS',json.dumps({'count':len(tools),'url_count':len(urls)},ensure_ascii=False),flush=True)
    if not out: raise RuntimeError('Compound research returned empty content')
    if urls:
        out += '\\n\\nTool-verified source URLs:\\n'+'\\n'.join('- '+u for u in urls)
    return out

"""
src=src.replace(insert_before,research_fn+insert_before,1)
old="""            evidence=groq_chat([
                {'role':'system','content':'Research the request using web/tools when useful. Produce a compact source-backed research brief. Include current dates when relevant, source names and direct URLs in the answer, disagreements and uncertainty. Prefer primary/official sources. Do not fabricate citations. Keep the brief under about 1800 words so it can be passed safely to a second model.'},
                {'role':'user','content':text[:9000]}
            ],GROQ_RESEARCH_MODEL,'medium',2800)
"""
new="""            evidence=groq_research_web(text[:9000])
"""
if old not in src: raise RuntimeError('V12 research evidence block not found')
src=src.replace(old,new,1)
src=src.replace("ND_VK_GATEWAY_V12_RESEARCH_INTEGRITY_START","ND_VK_GATEWAY_V24_RESEARCH_FORCED_WEB_START",1)
'''
outer=outer.replace(marker,addon+"\nexec(compile(src,'nd_vk_gateway_v12b_research_forced_web.py','exec'))",1)
print('ND_V12B_RESEARCH_PATCH_LOADED',flush=True)
exec(compile(outer,'nd_vk_gateway_v12b_outer.py','exec'))
