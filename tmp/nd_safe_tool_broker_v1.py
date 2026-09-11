import os,json,time,re,base64,zipfile,io,html,random
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.parse import urlencode,quote,parse_qs,urlparse
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
BROKER_TOKEN=os.environ.get('BROKER_TOKEN','')
GOOGLE_GATEWAY_URL=os.environ.get('ND_GOOGLE_GATEWAY_URL','').rstrip('/')
GOOGLE_GATEWAY_TOKEN=os.environ.get('GOOGLE_GATEWAY_TOKEN','')
GITHUB_TOKEN=os.environ.get('ND_GITHUB_PAT_RO','')
YANDEX_TOKEN=os.environ.get('YANDEX_DISK_TOKEN','')
GROQ_API_KEY=os.environ.get('GROQ_API_KEY','')
GROQ_RESEARCH_MODEL=os.environ.get('GROQ_RESEARCH_MODEL','groq/compound')
ALLOWED_REPOS={'namelessdhamma/nameless-dhamma-vault','namelessdhamma/namelessdhamma.github.io'}

CATALOG={
  'policy':{
    'mode':'READ_ONLY',
    'mutations':False,
    'model_receives_credentials':False,
    'unknown_tool_behavior':'DENY'
  },
  'broker_executable':[
    {'name':'nd_authority','description':'Read current ND StateHead, Capability Registry, durable-memory summary, and relevant canonical components from Google Drive authority layer.'},
    {'name':'google_drive_search','description':'Read-only search across Google Drive project files through the authority gateway.'},
    {'name':'github_read','description':'Read-only search/read in allowlisted ND GitHub repositories. No commit/update/delete operations exist.'},
    {'name':'yandex_read','description':'Read-only search/read of ND book documents on Yandex Disk. No upload/edit/delete operations exist.'},
    {'name':'web_current','description':'Current web research through Groq Compound with web search/website tools and source URLs.'},
    {'name':'tool_catalog','description':'Return this capability catalog and execution boundaries.'}
  ],
  'chatgpt_only_not_executable_here':[
    'Scholar Gateway','SciSpace','Undermind','Academic Writing Toolkit','Docs AI',
    'Google Drive connector','GitHub connector','Soluvery'
  ]
}

def cleanerr(e):
    s=str(e)
    for secret in (BROKER_TOKEN,GOOGLE_GATEWAY_TOKEN,GITHUB_TOKEN,YANDEX_TOKEN,GROQ_API_KEY):
        if secret:s=s.replace(secret,'[REDACTED]')
    return s[:700]

def get_bytes(url,headers=None,timeout=40,max_bytes=8000000):
    h={'User-Agent':'nd-safe-tool-broker/1.0'}
    if headers:h.update(headers)
    req=Request(url,method='GET',headers=h)
    with urlopen(req,timeout=timeout) as r:return r.read(max_bytes+1)[:max_bytes]

def get_json(url,headers=None,timeout=40):
    return json.loads(get_bytes(url,headers,timeout,1500000).decode('utf-8','replace'))

def post_json(url,payload,headers=None,timeout=120):
    data=json.dumps(payload,ensure_ascii=False).encode()
    h={'Content-Type':'application/json','Accept':'application/json','User-Agent':'nd-safe-tool-broker/1.0'}
    if headers:h.update(headers)
    req=Request(url,data=data,method='POST',headers=h)
    try:
        with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
    except HTTPError as e:
        body=e.read().decode('utf-8','replace')
        raise RuntimeError('HTTP %s: %s'%(e.code,body[:700]))

def terms(q):
    stop={'это','как','что','для','или','при','над','под','про','мне','тебе','можно','нужно','хочу','есть','the','and','for','with','from','this','that','have','what','about','into','your'}
    out=[]
    for w in re.findall(r'[A-Za-zА-Яа-яЁё0-9_-]{3,}',(q or '').lower()):
        if w not in stop and w not in out:out.append(w)
    return out[:12]

def docx_text(data):
    try:
        import xml.etree.ElementTree as ET
        chunks=[]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in [n for n in z.namelist() if n=='word/document.xml' or n.startswith('word/header') or n.startswith('word/footer') or n in ('word/footnotes.xml','word/endnotes.xml','word/comments.xml')]:
                try:root=ET.fromstring(z.read(name))
                except Exception:continue
                for p in root.iter():
                    if p.tag.rsplit('}',1)[-1]!='p':continue
                    xs=[]
                    for el in p.iter():
                        local=el.tag.rsplit('}',1)[-1]
                        if local=='t' and el.text:xs.append(el.text)
                        elif local=='tab':xs.append('\t')
                        elif local in ('br','cr'):xs.append('\n')
                    t=''.join(xs).strip()
                    if t:chunks.append(t)
        return '\n'.join(chunks).strip()
    except Exception:return ''

def call_google(path,query):
    if not GOOGLE_GATEWAY_URL or not GOOGLE_GATEWAY_TOKEN:raise RuntimeError('Google gateway unavailable')
    u=GOOGLE_GATEWAY_URL+path+'?q='+quote((query or '')[:5000],safe='')
    return get_json(u,{'Authorization':'Bearer '+GOOGLE_GATEWAY_TOKEN,'Accept':'application/json'},45)

def nd_authority(q):
    j=call_google('/nd/context',q)
    return {'summary':{k:j.get(k) for k in ('statehead_status','registry_version','component_count','selected_components')},
            'pieces':(j.get('pieces') or [])[:8]}

def google_drive_search(q):
    try:
        j=call_google('/nd/search',q)
        return j
    except Exception:
        # Fallback: authority gateway discovery embedded in context remains read-only.
        j=call_google('/nd/context',q+' plugin tool agent automation connector')
        return {'fallback':True,'pieces':(j.get('pieces') or [])[-5:]}

def safe_path(p):
    low=(p or '').lower()
    if not low.endswith(('.md','.txt','.json','.yaml','.yml','.docx','.py','.js','.ts','.tsx')):return False
    if any(x in low for x in ('/.git','/.obsidian','secret','credential','.env','token','password','private_key','api_key')):return False
    return True

def github_read(q):
    if not GITHUB_TOKEN:raise RuntimeError('GitHub read token unavailable')
    ts=terms(q)
    repo='namelessdhamma/nameless-dhamma-vault'
    low=(q or '').lower()
    if 'github.io' in low or 'website' in low or 'сайт' in low:repo='namelessdhamma/namelessdhamma.github.io'
    if repo not in ALLOWED_REPOS:raise RuntimeError('repo denied')
    headers={'Authorization':'Bearer '+GITHUB_TOKEN,'Accept':'application/vnd.github+json'}
    paths=[]
    if ts:
        try:
            sq=' '.join(ts[:4])+' repo:'+repo
            j=get_json('https://api.github.com/search/code?q='+quote(sq,safe=''),headers,30)
            for it in j.get('items') or []:
                p=it.get('path') or ''
                if safe_path(p) and p not in paths:paths.append(p)
                if len(paths)>=4:break
        except Exception as e:
            print('BROKER_GITHUB_SEARCH_ERROR',cleanerr(e),flush=True)
    if not paths and repo.endswith('nameless-dhamma-vault'):
        paths=['00 СЕЙЧАС.md','01 ТЕМЫ.md','02 РЕШЕНИЯ.md','03 ИЗМЕНЕНИЯ.md']
    out=[]
    for p in paths[:4]:
        try:
            j=get_json('https://api.github.com/repos/'+repo+'/contents/'+quote(p,safe='/')+'?ref=main',headers,30)
            raw=base64.b64decode((j.get('content') or '').replace('\n',''))
            if p.lower().endswith('.docx'):txt=docx_text(raw)
            else:txt=raw.decode('utf-8','replace')
            if txt.strip():out.append({'repo':repo,'path':p,'text':txt[:6000]})
        except Exception as e:
            print('BROKER_GITHUB_FILE_ERROR',json.dumps({'path':p,'error':cleanerr(e)},ensure_ascii=False),flush=True)
    return {'repo':repo,'results':out,'mutations':False}

def yandex_read(q):
    if not YANDEX_TOKEN:raise RuntimeError('Yandex token unavailable')
    headers={'Authorization':'OAuth '+YANDEX_TOKEN,'Accept':'application/json'}
    j=get_json('https://cloud-api.yandex.net/v1/disk/resources/files?limit=1000&media_type=document',headers,45)
    ts=terms(q)
    cand=[]
    for it in j.get('items') or []:
        p=it.get('path') or '';name=(it.get('name') or p.rsplit('/',1)[-1]);low=(name+' '+p).lower()
        if not name.lower().endswith(('.docx','.txt','.md')):continue
        score=0
        nums={n.lstrip('0') or '0' for n in re.findall(r'[0-9]+',name)}
        for t in ts:
            if t.isdigit():
                if (t.lstrip('0') or '0') in nums:score+=40
            elif t in name.lower():score+=7
            elif t in low:score+=1
        if 'черновик' in ts and 'черновик' in low:score+=10
        cand.append((score,p,it))
    cand.sort(key=lambda x:(x[0],x[1]),reverse=True)
    out=[]
    for score,p,it in cand[:3]:
        if score<=0 and out:break
        try:
            dj=get_json('https://cloud-api.yandex.net/v1/disk/resources/download?path='+quote(p,safe=''),headers,30)
            href=dj.get('href')
            if not href:continue
            raw=get_bytes(href,None,60,9000000)
            if p.lower().endswith('.docx'):txt=docx_text(raw)
            else:txt=raw.decode('utf-8','replace')
            if txt.strip():out.append({'path':p,'score':score,'text':txt[:7000]})
        except Exception as e:
            print('BROKER_YANDEX_FILE_ERROR',json.dumps({'path':p,'error':cleanerr(e)},ensure_ascii=False),flush=True)
    return {'results':out,'mutations':False}

def web_current(q):
    if not GROQ_API_KEY:raise RuntimeError('Groq research unavailable')
    today=time.strftime('%Y-%m-%d',time.gmtime())
    payload={
      'model':GROQ_RESEARCH_MODEL,
      'messages':[
        {'role':'system','content':'Today is '+today+'. You are a read-only evidence retrieval tool. For current claims, use web search and visit websites. Prefer primary/official sources. Return a compact source-backed brief with direct URLs and dates. Do not rely on stale model memory when web verification is requested.'},
        {'role':'user','content':(q or '')[:9000]}
      ],
      'max_completion_tokens':2600,
      'compound_custom':{'tools':{'enabled_tools':['web_search','visit_website']}}
    }
    j=post_json('https://api.groq.com/openai/v1/chat/completions',payload,
                {'Authorization':'Bearer '+GROQ_API_KEY,'Groq-Model-Version':'latest'},180)
    ch=j.get('choices') or []
    if not ch:raise RuntimeError('no research choices')
    msg=ch[0].get('message') or {}
    tools=msg.get('executed_tools') or []
    if not tools:raise RuntimeError('web research used no tools')
    raw=json.dumps(tools,ensure_ascii=False)
    urls=[]
    for u in re.findall(r'https?://[^\\s"\\\\<>]+',raw):
        u=u.rstrip(').,;]')
        if u not in urls:urls.append(u)
        if len(urls)>=16:break
    return {'brief':(msg.get('content') or '').strip(),'source_urls':urls,'tool_calls':len(tools),'mutations':False}

def invoke(tool,q):
    if tool=='tool_catalog':return CATALOG
    if tool=='nd_authority':return nd_authority(q)
    if tool=='google_drive_search':return google_drive_search(q)
    if tool=='github_read':return github_read(q)
    if tool=='yandex_read':return yandex_read(q)
    if tool=='web_current':return web_current(q)
    raise PermissionError('tool denied')

class H(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def auth(self):
        return bool(BROKER_TOKEN) and self.headers.get('Authorization','')=='Bearer '+BROKER_TOKEN
    def sendj(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=='/health':
            return self.sendj({'ok':True,'service':'ND Safe Tool Broker','mode':'READ_ONLY','mutations':False})
        if not self.auth():return self.sendj({'error':'unauthorized'},401)
        if p.path=='/catalog':return self.sendj(CATALOG)
        return self.sendj({'error':'not_found'},404)
    def do_POST(self):
        if not self.auth():return self.sendj({'error':'unauthorized'},401)
        p=urlparse(self.path)
        if p.path!='/invoke':return self.sendj({'error':'not_found'},404)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>20000:raise ValueError('bad request size')
            j=json.loads(self.rfile.read(n).decode('utf-8','replace'))
            tool=str(j.get('tool') or '')[:80];q=str(j.get('query') or '')[:9000]
            t=time.time();res=invoke(tool,q)
            meta={'tool':tool,'ok':True,'elapsed_ms':int((time.time()-t)*1000),'mutations':False}
            print('BROKER_INVOKE',json.dumps({**meta,'result_chars':len(json.dumps(res,ensure_ascii=False))},ensure_ascii=False),flush=True)
            return self.sendj({'meta':meta,'result':res})
        except PermissionError as e:
            print('BROKER_DENY',str(e),flush=True);return self.sendj({'error':'tool_denied'},403)
        except Exception as e:
            print('BROKER_ERROR',cleanerr(e),flush=True);return self.sendj({'error':'tool_failed','detail':cleanerr(e)},502)

print('ND_SAFE_TOOL_BROKER_START',json.dumps({
  'port':PORT,'google':bool(GOOGLE_GATEWAY_URL and GOOGLE_GATEWAY_TOKEN),
  'github':bool(GITHUB_TOKEN),'yandex':bool(YANDEX_TOKEN),'web':bool(GROQ_API_KEY),
  'mutations':False},ensure_ascii=False),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
