import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/05476fbb7bd64f6d4598d5f843cccf9446611e84/tmp/nd_vk_gateway_v13_independent_web.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
src=src.replace('ND_VK_GATEWAY_V13_INDEPENDENT_WEB_START','ND_VK_GATEWAY_V14_WEB_RECOVERY_START',1)

old="""    # Fallback: DuckDuckGo HTML. No API key and independent of Groq/OpenRouter model quotas.
    if len(results)<5:
        try:
            url='https://html.duckduckgo.com/html/?'+_up.urlencode({'q':query[:500]})
            req=Request(url,headers=ua)
            with urlopen(req,timeout=15) as r: body=r.read(1800000).decode('utf-8','replace')
            pat=re.compile(r'<a[^>]+class=\"[^\"]*result__a[^\"]*\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>',re.I|re.S)
            for href,title_html in pat.findall(body)[:12]:
                href=_html.unescape(href)
                if href.startswith('//'): href='https:'+href
                pu=_up.urlparse(href)
                qs=_up.parse_qs(pu.query)
                if 'uddg' in qs: href=qs['uddg'][0]
                title=re.sub(r'<[^>]+>',' ',title_html)
                add(href,_html.unescape(re.sub(r'\\s+',' ',title)).strip(),'')
            print('WEB_SEARCH_BACKEND',json.dumps({'backend':'duckduckgo_html','results':len(results)}),flush=True)
        except Exception as e:
            errors.append('ddg:'+cleanerr(e)[:180])
"""
new="""    # Deterministic no-key news fallback for fresh/current queries.
    if len(results)<5:
        try:
            import xml.etree.ElementTree as _ET
            url='https://news.google.com/rss/search?'+_up.urlencode({'q':query[:400],'hl':'en-US','gl':'US','ceid':'US:en'})
            req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/rss+xml,application/xml,text/xml'})
            with urlopen(req,timeout=15) as r: root=_ET.fromstring(r.read(1200000))
            for it in root.findall('.//item')[:12]:
                add((it.findtext('link') or '').strip(),(it.findtext('title') or '').strip(),(it.findtext('description') or '').strip())
            print('WEB_SEARCH_BACKEND',json.dumps({'backend':'google_news_rss','results':len(results)}),flush=True)
        except Exception as e:
            errors.append('gnews:'+cleanerr(e)[:180])

    # DuckDuckGo no-JS endpoints expect browser-like POST form submission.
    if len(results)<5:
        for endpoint,name in (('https://html.duckduckgo.com/html/','duckduckgo_html_post'),('https://lite.duckduckgo.com/lite/','duckduckgo_lite_post')):
            try:
                data=_up.urlencode({'q':query[:500]}).encode()
                hdr={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36','Accept':'text/html,application/xhtml+xml','Content-Type':'application/x-www-form-urlencoded','Referer':endpoint,'Origin':'https://duckduckgo.com','Sec-Fetch-Site':'same-origin','Sec-Fetch-Mode':'navigate'}
                req=Request(endpoint,data=data,headers=hdr,method='POST')
                with urlopen(req,timeout=15) as r: body=r.read(1800000).decode('utf-8','replace')
                patterns=[r'<a[^>]+class=\"[^\"]*result__a[^\"]*\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>',r'<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>']
                for patx in patterns:
                    for href,title_html in re.findall(patx,body,re.I|re.S)[:20]:
                        href=_html.unescape(href)
                        if href.startswith('//'): href='https:'+href
                        pu=_up.urlparse(href); qs=_up.parse_qs(pu.query)
                        if 'uddg' in qs: href=qs['uddg'][0]
                        title=_html.unescape(re.sub(r'\\s+',' ',re.sub(r'<[^>]+>',' ',title_html))).strip()
                        if title and not href.startswith('javascript:'): add(href,title,'')
                print('WEB_SEARCH_BACKEND',json.dumps({'backend':name,'results':len(results)}),flush=True)
                if len(results)>=5: break
            except Exception as e:
                errors.append(name+':'+cleanerr(e)[:180])

    # Bing HTML fallback gives a second independent index without an API key.
    if len(results)<5:
        try:
            url='https://www.bing.com/search?'+_up.urlencode({'q':query[:500],'count':'10','setlang':'en-US'})
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36','Accept':'text/html,application/xhtml+xml'})
            with urlopen(req,timeout=15) as r: body=r.read(1800000).decode('utf-8','replace')
            for block in re.findall(r'<li[^>]+class=\"b_algo\"[^>]*>(.*?)</li>',body,re.I|re.S)[:12]:
                m=re.search(r'<h2[^>]*>.*?<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>',block,re.I|re.S)
                if not m: continue
                href=_html.unescape(m.group(1)); title=_html.unescape(re.sub(r'\\s+',' ',re.sub(r'<[^>]+>',' ',m.group(2)))).strip()
                sn=re.search(r'<p[^>]*>(.*?)</p>',block,re.I|re.S)
                snippet=_html.unescape(re.sub(r'\\s+',' ',re.sub(r'<[^>]+>',' ',sn.group(1) if sn else ''))).strip()
                add(href,title,snippet)
            print('WEB_SEARCH_BACKEND',json.dumps({'backend':'bing_html','results':len(results)}),flush=True)
        except Exception as e:
            errors.append('bing:'+cleanerr(e)[:180])
"""
if old not in src: raise RuntimeError('V13 DDG block not found')
src=src.replace(old,new,1)

old_visit="""            req=Request(it['url'],headers=ua)
            with urlopen(req,timeout=12) as r:
                ct=(r.headers.get('Content-Type') or '').lower()
                raw=r.read(700000)
            if 'html' in ct or not ct:
                txt=raw.decode('utf-8','replace')
                txt=re.sub(r'(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>',' ',txt)
                txt=re.sub(r'(?s)<[^>]+>',' ',txt)
                txt=_html.unescape(txt)
                txt=re.sub(r'\\s+',' ',txt).strip()
                excerpt=txt[:5000]
"""
new_visit="""            # Jina Reader is a free no-key extraction fallback (rate-limited), then direct fetch.
            try:
                ju='https://r.jina.ai/'+it['url']
                req=Request(ju,headers={'User-Agent':'ND-VK-WebResearch/1.0','Accept':'text/plain'})
                with urlopen(req,timeout=18) as r: excerpt=r.read(450000).decode('utf-8','replace')[:5000]
            except Exception:
                req=Request(it['url'],headers=ua)
                with urlopen(req,timeout=12) as r:
                    ct=(r.headers.get('Content-Type') or '').lower(); raw=r.read(700000)
                if 'html' in ct or not ct:
                    txt=raw.decode('utf-8','replace')
                    txt=re.sub(r'(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>',' ',txt)
                    txt=re.sub(r'(?s)<[^>]+>',' ',txt); txt=_html.unescape(txt); txt=re.sub(r'\\s+',' ',txt).strip(); excerpt=txt[:5000]
"""
if old_visit not in src: raise RuntimeError('V13 visit block not found')
src=src.replace(old_visit,new_visit,1)

exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))
