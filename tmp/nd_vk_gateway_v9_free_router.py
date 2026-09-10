import os,json,threading,time,hashlib,random,re
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
TOKEN=os.environ.get('VK_GROUP_TOKEN','')
GROQ_API_KEY=os.environ.get('GROQ_API_KEY','')
GROQ_MODEL=os.environ.get('GROQ_MODEL','openai/gpt-oss-120b')
GROQ_RESEARCH_MODEL=os.environ.get('GROQ_RESEARCH_MODEL','groq/compound')
OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','')
OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')
V=os.environ.get('VK_API_VERSION','5.199')
SCREEN=os.environ.get('VK_GROUP_SCREEN_NAME','namelessdhamma').lstrip('@')
PUBLIC_BASE=os.environ.get('VK_PUBLIC_BASE_URL','').rstrip('/')
if not PUBLIC_BASE:
    d=os.environ.get('RAILWAY_PUBLIC_DOMAIN','').strip()
    if d: PUBLIC_BASE='https://'+d
PATH_KEY=hashlib.sha256(('nd-vk-path:'+TOKEN).encode()).hexdigest()[:32] if TOKEN else 'missing'
CALLBACK_PATH='/vk/callback/'+PATH_KEY
CALLBACK_URL=PUBLIC_BASE+CALLBACK_PATH if PUBLIC_BASE else ''
ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}

state={
    'ok':True,'phase':'starting','group_id':None,'callback_server_id':None,'callback_configured':False,
    'groq_present':bool(GROQ_API_KEY),'openrouter_present':bool(OPENROUTER_API_KEY),
    'groq_model':GROQ_MODEL,'research_model':GROQ_RESEARCH_MODEL,'openrouter_model':OPENROUTER_MODEL,
    'groq_probe':None,'openrouter_probe':None,'last_route':None,'last_provider':None,'last_error':None,
    'last_event_at':None,'ai_calls':0
}
history_by_uid={}
mode_by_uid={}
seen=set();seen_order=[];last_call={};lock=threading.Lock()

BASE_SYSTEM='''You are the VK interface of Nameless Dhamma (ND), an independent Buddhist research and creative project. Respond in the user's language; default to Russian. Be concise for simple questions and rigorous for serious work. Do not claim access to the user's ChatGPT account, ChatGPT memory, private chats, files, or current ND project state unless that context is explicitly supplied through this gateway. Full ND connected-state access is a separate layer.'''
WRITE_SYSTEM=BASE_SYSTEM+'''\nFor literary work: preserve the author's voice, intent and ambiguity. Avoid generic AI phrasing, moralizing, over-explanation and stylistic homogenization. Prefer concrete imagery, exact rhythm and the smallest justified revision. When critiquing, distinguish material weaknesses from subjective preference.'''
RESEARCH_SYSTEM=BASE_SYSTEM+'''\nFor research: distinguish evidence from inference, preserve source names and URLs present in supplied research material, identify uncertainty and disagreements, and synthesize rather than merely summarize. Never invent sources.'''
DEEP_SYSTEM=BASE_SYSTEM+'''\nFor difficult analysis: reason carefully, test assumptions, consider competing explanations, identify what would falsify the conclusion, and give a compact final synthesis.'''


def cleanerr(x):
    s=str(x)
    for secret in (TOKEN,GROQ_API_KEY,OPENROUTER_API_KEY,PATH_KEY):
        if secret:s=s.replace(secret,'[redacted]')
    return s[:1800]

def http_json(url,payload,key,timeout=150,headers_extra=None):
    headers={'Content-Type':'application/json','Authorization':'Bearer '+key,'Accept':'application/json','User-Agent':'nd-vk-gateway/1.0'}
    if headers_extra:headers.update(headers_extra)
    req=Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),method='POST',headers=headers)
    try:
        with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        try:body=e.read().decode('utf-8','replace')
        except Exception:body=''
        raise RuntimeError('HTTP %s: %s'%(e.code,cleanerr(body)))
    except Exception as e:raise RuntimeError(cleanerr(e))

def vk(method,p=None,timeout=20):
    if not TOKEN:raise RuntimeError('VK_GROUP_TOKEN missing')
    q=dict(p or {});q['access_token']=TOKEN;q['v']=V
    req=Request('https://api.vk.com/method/'+method,data=urlencode({k:str(v) for k,v in q.items() if v is not None}).encode(),method='POST',headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'nd-vk-gateway/1.0'})
    with urlopen(req,timeout=timeout) as r:j=json.loads(r.read().decode())
    if 'error' in j:
        e=j['error'];raise RuntimeError('VK %s error %s: %s'%(method,e.get('error_code'),e.get('error_msg')))
    return j.get('response')

def groq_chat(messages,model=None,reasoning='medium',max_tokens=2400):
    if not GROQ_API_KEY:raise RuntimeError('GROQ_API_KEY missing')
    model=model or GROQ_MODEL
    payload={'model':model,'messages':messages,'max_completion_tokens':max_tokens}
    if model.startswith('openai/'):
        payload['reasoning_effort']=reasoning;payload['include_reasoning']=False
    j=http_json('https://api.groq.com/openai/v1/chat/completions',payload,GROQ_API_KEY)
    ch=j.get('choices') or []
    if not ch:raise RuntimeError('Groq returned no choices')
    out=((ch[0].get('message') or {}).get('content') or '').strip()
    if not out:raise RuntimeError('Groq returned empty content')
    return out

def openrouter_chat(messages,effort='high',max_tokens=4200,temperature=0.45):
    if not OPENROUTER_API_KEY:raise RuntimeError('OPENROUTER_API_KEY missing')
    payload={'model':OPENROUTER_MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,
             'reasoning':{'effort':effort,'exclude':True}}
    extra={'HTTP-Referer':'https://namelessdhamma.org','X-Title':'Nameless Dhamma VK Gateway'}
    try:
        j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
    except Exception as e:
        # Some upstream free providers can reject optional reasoning controls. Retry once without them.
        if 'HTTP 400' not in str(e):raise
        payload.pop('reasoning',None)
        j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
    ch=j.get('choices') or []
    if not ch:raise RuntimeError('OpenRouter returned no choices')
    msg=ch[0].get('message') or {}
    out=(msg.get('content') or '').strip()
    if not out:raise RuntimeError('OpenRouter returned empty content')
    return out

def heuristic_route(text):
    t=text.lower()
    if any(x in t for x in ('исслед','источник','проверь в интернете','актуальн','последние','новост','сравни данные','найди информацию','research','source','latest','web search')):return 'research'
    if any(x in t for x in ('рассказ','глава','книга','текст','редакт','перепиши','стиль','литератур','сцена','диалог','проза','рукопис','write','rewrite','chapter')):return 'write'
    if len(text)>1400 or any(x in t for x in ('проанализируй глубоко','сложный анализ','разбери подробно','критически','докажи','опроверг','deep analysis')):return 'deep'
    return 'fast'

def classify_route(text):
    try:
        prompt='''Classify the request for an AI router. Return exactly one word: fast, write, research, or deep.\nfast = ordinary conversation/simple Q&A.\nwrite = book/prose/editing/literary criticism/rewrite.\nresearch = current facts, sources, web investigation, evidence comparison.\ndeep = difficult non-current reasoning/analysis/planning.\nRequest:\n'''+text[:3000]
        out=groq_chat([{'role':'user','content':prompt}],GROQ_MODEL,'low',96).lower()
        for k in ('research','write','deep','fast'):
            if re.search(r'\b'+k+r'\b',out):return k
    except Exception as e:print('ROUTER_CLASSIFY_FALLBACK',cleanerr(e),flush=True)
    return heuristic_route(text)

def routed_response(uid,text):
    hist=history_by_uid.get(uid,[])[-10:]
    forced=mode_by_uid.get(uid,'auto')
    route=classify_route(text) if forced=='auto' else forced
    state['last_route']=route
    print('AI_ROUTE',json.dumps({'uid':uid,'route':route,'openrouter':bool(OPENROUTER_API_KEY)}),flush=True)
    def save(out,provider):
        history_by_uid[uid]=(hist+[{'role':'user','content':text[:12000]},{'role':'assistant','content':out[:18000]}])[-10:]
        state['ai_calls']+=1;state['last_provider']=provider
        return out
    try:
        if route=='research':
            evidence=groq_chat([
                {'role':'system','content':'Research the request using web/tools when useful. Return factual findings, source names/URLs when available, disagreements and uncertainty. Do not fabricate citations.'},
                {'role':'user','content':text[:10000]}
            ],GROQ_RESEARCH_MODEL,'medium',3800)
            if OPENROUTER_API_KEY:
                synth='User request:\n'+text[:9000]+'\n\nResearch material gathered by Groq Compound:\n'+evidence[:24000]+'\n\nProduce a rigorous synthesis. Preserve useful source references exactly as supplied. Do not invent sources.'
                return save(openrouter_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',4800,0.25),'openrouter-nemotron+groq-compound')
            return save(evidence,'groq-compound')
        if route=='write':
            msgs=[{'role':'system','content':WRITE_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]
            if OPENROUTER_API_KEY:return save(openrouter_chat(msgs,'high',5200,0.7),'openrouter-nemotron')
            return save(groq_chat(msgs,GROQ_MODEL,'high',3600),'groq-gpt-oss')
        if route=='deep':
            msgs=[{'role':'system','content':DEEP_SYSTEM}]+hist+[{'role':'user','content':text[:14000]}]
            if OPENROUTER_API_KEY:return save(openrouter_chat(msgs,'high',5000,0.3),'openrouter-nemotron')
            return save(groq_chat(msgs,GROQ_MODEL,'high',3600),'groq-gpt-oss')
        msgs=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(msgs,GROQ_MODEL,'medium',2600),'groq-gpt-oss')
    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True);state['last_error']=cleanerr(e)
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',3000),'groq-fallback')

def resolve_gid():
    r=vk('groups.getById',{'group_ids':SCREEN})
    if isinstance(r,list) and r:return int(r[0]['id'])
    if isinstance(r,dict):
        a=r.get('groups') or []
        if a:return int(a[0]['id'])
        if 'id' in r:return int(r['id'])
    raise RuntimeError('community id not resolved')

def servers(gid):
    r=vk('groups.getCallbackServers',{'group_id':gid})
    if isinstance(r,dict):return r.get('items') or []
    return r if isinstance(r,list) else []

def register():
    gid=resolve_gid();state['group_id']=gid
    if not CALLBACK_URL:raise RuntimeError('public callback URL missing')
    sid=None
    for s in servers(gid):
        if (s.get('url') or '').rstrip('/')==CALLBACK_URL.rstrip('/'):
            sid=int(s['id']);break
    if sid is None:
        r=vk('groups.addCallbackServer',{'group_id':gid,'url':CALLBACK_URL,'title':'ND Free Adaptive Router'})
        sid=int(r.get('server_id') if isinstance(r,dict) else r)
    state['callback_server_id']=sid
    time.sleep(1);vk('groups.setCallbackSettings',{'group_id':gid,'server_id':sid,'api_version':V,'message_new':1})
    state['callback_configured']=True
    print('VK_READY',json.dumps({'group_id':gid,'server_id':sid,'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'allowed_count':len(ALLOWED)}),flush=True)

def startup():
    if not TOKEN:state['phase']='waiting_for_token';return
    for wait in (1,3,8,15,30):
        time.sleep(wait)
        try:
            register();state['phase']='ready';state['last_error']=None
            try:
                groq_chat([{'role':'user','content':'Reply exactly OK.'}],GROQ_MODEL,'low',256);state['groq_probe']='ok';print('GROQ_PROBE_OK',flush=True)
            except Exception as e:state['groq_probe']='error';print('GROQ_PROBE_ERROR',cleanerr(e),flush=True)
            if OPENROUTER_API_KEY:
                try:
                    openrouter_chat([{'role':'user','content':'Reply exactly OK.'}],'low',256,0.0);state['openrouter_probe']='ok';print('OPENROUTER_PROBE_OK',flush=True)
                except Exception as e:state['openrouter_probe']='error';state['last_error']=cleanerr(e);print('OPENROUTER_PROBE_ERROR',cleanerr(e),flush=True)
            else:state['openrouter_probe']='not_configured'
            return
        except Exception as e:state['last_error']=cleanerr(e);state['phase']='retrying';print('VK_RETRY',cleanerr(e),flush=True)
    state['phase']='error'

def send(peer,text):
    text=str(text or '')
    parts=[]
    while len(text)>3900:
        cut=text.rfind('\n',0,3900)
        if cut<2500:cut=text.rfind(' ',0,3900)
        if cut<2000:cut=3900
        parts.append(text[:cut].strip());text=text[cut:].strip()
    if text:parts.append(text)
    if not parts:parts=['(пустой ответ)']
    results=[]
    for part in parts[:10]:
        r=vk('messages.send',{'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':part});results.append(r)
    print('VK_SENT',json.dumps({'peer_id':peer,'parts':len(results),'last_result':results[-1] if results else None}),flush=True)
    return results

def remember_event(eid):
    if not eid:return True
    with lock:
        if eid in seen:return False
        seen.add(eid);seen_order.append(eid)
        if len(seen_order)>1000:
            old=seen_order.pop(0);seen.discard(old)
    return True

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def out(self,code,body,ctype='application/json; charset=utf-8'):
        raw=(json.dumps(body,ensure_ascii=False) if isinstance(body,(dict,list)) else str(body)).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        p=self.path.split('?',1)[0]
        if p=='/health':self.out(200,state);return
        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL});return
        self.out(404,{'error':'not_found'})
    def do_POST(self):
        if self.path.split('?',1)[0]!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
            n=int(self.headers.get('Content-Length','0'));b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:self.out(400,'bad request','text/plain; charset=utf-8');return
        typ=b.get('type');gid=b.get('group_id');eid=b.get('event_id');state['last_event_at']=int(time.time())
        if state.get('group_id') and gid and int(gid)!=int(state['group_id']):self.out(403,'forbidden','text/plain; charset=utf-8');return
        if typ=='confirmation':
            try:
                r=vk('groups.getCallbackConfirmationCode',{'group_id':int(gid or state['group_id'])});code=r.get('code') if isinstance(r,dict) else r;self.out(200,code,'text/plain; charset=utf-8')
            except Exception as e:state['last_error']=cleanerr(e);self.out(500,'error','text/plain; charset=utf-8')
            return
        self.out(200,'ok','text/plain; charset=utf-8')
        if typ!='message_new' or not remember_event(eid):return
        obj=b.get('object') or {};m=obj.get('message') or obj
        if not isinstance(m,dict):return
        peer=m.get('peer_id');uid=m.get('from_id');text=(m.get('text') or '').strip()
        print('VK_MESSAGE',json.dumps({'from_id':uid,'peer_id':peer,'kind':'command' if text.startswith('/') else 'text'}),flush=True)
        if not peer or not uid:return
        def reply():
            try:
                if text=='/whoami':send(peer,'VK user id: %s'%uid);return
                if text=='/nd-test':send(peer,'ND VK Gateway: связь с Nameless Dhamma работает.');return
                if text=='/reset':history_by_uid.pop(uid,None);send(peer,'Контекст диалога сброшен.');return
                if text.startswith('/mode'):
                    parts=text.split(None,1);mode=(parts[1].strip().lower() if len(parts)>1 else 'auto')
                    if mode not in ('auto','fast','write','research','deep'):send(peer,'Режимы: auto, fast, write, research, deep');return
                    mode_by_uid[uid]=mode;send(peer,'Режим: '+mode);return
                if text=='/status':
                    send(peer,'ND Router: VK=OK; Groq=%s; OpenRouter=%s; fast=%s; research=%s; deep/write=%s; mode=%s; last_route=%s; last_provider=%s'%(
                        'OK' if GROQ_API_KEY else 'OFF','OK' if OPENROUTER_API_KEY else 'OFF',GROQ_MODEL,GROQ_RESEARCH_MODEL,OPENROUTER_MODEL,mode_by_uid.get(uid,'auto'),state.get('last_route'),state.get('last_provider')));return
                if ALLOWED and int(uid) not in ALLOWED:send(peer,'Доступ к AI-контуру ND для этого аккаунта пока не разрешён. Ваш VK ID: %s'%uid);return
                if not GROQ_API_KEY:send(peer,'AI-контур временно недоступен: GROQ_API_KEY не настроен.');return
                now=time.time();last=last_call.get(uid,0)
                if now-last<2:time.sleep(2-(now-last))
                last_call[uid]=time.time();send(peer,routed_response(uid,text or 'Продолжи.'))
            except Exception as e:
                state['last_error']=cleanerr(e);print('VK_MESSAGE_ERROR',state['last_error'],flush=True)
                try:send(peer,'Ошибка AI-контура. Событие зарегистрировано; повторите сообщение позднее.')
                except Exception:pass
        threading.Thread(target=reply,daemon=True).start()

print('ND_VK_GATEWAY_V9_FREE_ROUTER_START',json.dumps({'port':PORT,'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'groq_model':GROQ_MODEL,'research_model':GROQ_RESEARCH_MODEL,'openrouter_model':OPENROUTER_MODEL,'allowed_count':len(ALLOWED)}),flush=True)
threading.Thread(target=startup,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
