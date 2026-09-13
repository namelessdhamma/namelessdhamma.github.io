import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c617c9b200cb1637fca544985d35ab2a1b8d9e08/tmp/nd_vk_gateway_v9_free_router.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

src=src.replace("OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','')","OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','') or os.environ.get('OpenRouter','')",1)
src=src.replace("OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')","OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')",1)
src=src.replace('ND_VK_GATEWAY_V9_FREE_ROUTER_START','ND_VK_GATEWAY_V13_INDEPENDENT_WEB_START',1)

marker='def routed_response(uid,text):\n'
web_code=r'''
def independent_web_research(query):
    import html as _html
    import urllib.parse as _up
    import datetime as _dt
    ua={'User-Agent':'Mozilla/5.0 (compatible; ND-VK-WebResearch/1.0)','Accept':'text/html,application/json;q=0.9,*/*;q=0.8'}
    results=[]; errors=[]

    def add(url,title='',snippet=''):
        try:
            u=_up.urlparse(url)
            host=(u.hostname or '').lower()
            if u.scheme not in ('http','https') or not host or host in ('localhost','127.0.0.1','::1') or host.endswith('.local'):
                return
            if any(x['url']==url for x in results): return
            results.append({'url':url,'title':title[:500],'snippet':snippet[:1600]})
        except Exception: return

    # First choice: public SearXNG JSON endpoints. They are independent from model-provider quotas.
    for base in ('https://searx.be/search','https://search.sapti.me/search','https://searx.tiekoetter.com/search','https://search.bus-hit.me/search'):
        try:
            url=base+'?'+_up.urlencode({'q':query[:500],'format':'json','language':'auto','safesearch':'0'})
            req=Request(url,headers=ua)
            with urlopen(req,timeout=12) as r: j=json.loads(r.read(1500000).decode('utf-8','replace'))
            for it in (j.get('results') or [])[:10]:
                add(str(it.get('url') or ''),str(it.get('title') or ''),str(it.get('content') or ''))
            if len(results)>=5:
                print('WEB_SEARCH_BACKEND',json.dumps({'backend':'searxng','base':base,'results':len(results)}),flush=True)
                break
        except Exception as e:
            errors.append('searx:'+cleanerr(e)[:180])

    # Fallback: DuckDuckGo HTML. No API key and independent of Groq/OpenRouter model quotas.
    if len(results)<5:
        try:
            url='https://html.duckduckgo.com/html/?'+_up.urlencode({'q':query[:500]})
            req=Request(url,headers=ua)
            with urlopen(req,timeout=15) as r: body=r.read(1800000).decode('utf-8','replace')
            pat=re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',re.I|re.S)
            for href,title_html in pat.findall(body)[:12]:
                href=_html.unescape(href)
                if href.startswith('//'): href='https:'+href
                pu=_up.urlparse(href)
                qs=_up.parse_qs(pu.query)
                if 'uddg' in qs: href=qs['uddg'][0]
                title=re.sub(r'<[^>]+>',' ',title_html)
                add(href,_html.unescape(re.sub(r'\s+',' ',title)).strip(),'')
            print('WEB_SEARCH_BACKEND',json.dumps({'backend':'duckduckgo_html','results':len(results)}),flush=True)
        except Exception as e:
            errors.append('ddg:'+cleanerr(e)[:180])

    if not results:
        raise RuntimeError('independent web search returned no results; '+' | '.join(errors[-5:]))

    # Visit several result pages to give the synthesizer actual source text, not just search snippets.
    enriched=[]
    for it in results[:7]:
        excerpt=''
        try:
            req=Request(it['url'],headers=ua)
            with urlopen(req,timeout=12) as r:
                ct=(r.headers.get('Content-Type') or '').lower()
                raw=r.read(700000)
            if 'html' in ct or not ct:
                txt=raw.decode('utf-8','replace')
                txt=re.sub(r'(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>',' ',txt)
                txt=re.sub(r'(?s)<[^>]+>',' ',txt)
                txt=_html.unescape(txt)
                txt=re.sub(r'\s+',' ',txt).strip()
                excerpt=txt[:5000]
        except Exception as e:
            errors.append('visit:'+cleanerr(e)[:140])
        enriched.append({'url':it['url'],'title':it['title'],'snippet':it['snippet'],'excerpt':excerpt})

    lines=['INDEPENDENT WEB RESEARCH', 'UTC_NOW: '+_dt.datetime.now(_dt.timezone.utc).isoformat()]
    for i,it in enumerate(enriched,1):
        lines.append('\nSOURCE %d\nURL: %s\nTITLE: %s\nSEARCH_SNIPPET: %s\nPAGE_EXCERPT: %s' % (i,it['url'],it['title'],it['snippet'],it['excerpt']))
    print('WEB_RESEARCH_OK',json.dumps({'results':len(results),'visited':sum(1 for x in enriched if x['excerpt'])}),flush=True)
    return '\n'.join(lines)[:30000]

'''
if marker not in src: raise RuntimeError('routed_response marker missing')
src=src.replace(marker,web_code+marker,1)

old="""        if route=='research':
            evidence=groq_chat([
                {'role':'system','content':'Research the request using web/tools when useful. Return factual findings, source names/URLs when available, disagreements and uncertainty. Do not fabricate citations.'},
                {'role':'user','content':text[:10000]}
            ],GROQ_RESEARCH_MODEL,'medium',3800)
            if OPENROUTER_API_KEY:
                synth='User request:\\n'+text[:9000]+'\\n\\nResearch material gathered by Groq Compound:\\n'+evidence[:24000]+'\\n\\nProduce a rigorous synthesis. Preserve useful source references exactly as supplied. Do not invent sources.'
                return save(openrouter_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',4800,0.25),'openrouter-nemotron+groq-compound')
            return save(evidence,'groq-compound')
"""
new="""        if route=='research':
            evidence=independent_web_research(text)
            synth='User request:\\n'+text[:7000]+'\\n\\nFresh web material gathered independently of the model provider:\\n'+evidence[:28000]+'\\n\\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'
            if OPENROUTER_API_KEY:
                try:
                    return save(openrouter_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',4200,0.2),'openrouter-free+independent-web')
                except Exception as oe:
                    print('RESEARCH_OPENROUTER_ERROR',cleanerr(oe),flush=True)
            return save(groq_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],GROQ_MODEL,'medium',3200),'groq-gpt-oss+independent-web')
"""
if old not in src: raise RuntimeError('V9 research block missing')
src=src.replace(old,new,1)

old_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')
"""
new_outer="""    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        if route=='research':
            return save('Не удалось получить независимые веб-источники для этого запроса. Ошибка уже зарегистрирована; актуальные факты не буду подменять памятью.','research-error-no-fabrication')
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')
"""
if old_outer in src: src=src.replace(old_outer,new_outer,1)

exec(compile(src,'nd_vk_gateway_v13_independent_web.py','exec'))
