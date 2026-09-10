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
MISTRAL_API_KEY=os.environ.get('MISTRAL_API_KEY','')
MISTRAL_MODEL=os.environ.get('MISTRAL_MODEL','mistral-medium-3-5')
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

state={'ok':True,'phase':'starting','group_id':None,'callback_server_id':None,'callback_configured':False,
       'groq_present':bool(GROQ_API_KEY),'mistral_present':bool(MISTRAL_API_KEY),
       'groq_model':GROQ_MODEL,'research_model':GROQ_RESEARCH_MODEL,'mistral_model':MISTRAL_MODEL,
       'groq_probe':None,'mistral_probe':None,'last_route':None,'last_error':None,'last_event_at':None,'ai_calls':0}
history_by_uid={}
mode_by_uid={}
seen=set();seen_order=[];last_call={};lock=threading.Lock()

BASE_SYSTEM='''You are the VK interface of Nameless Dhamma (ND), an independent Buddhist research and creative project. Respond in the user's language; default to Russian. Be concise when the user asks a simple question, but do not sacrifice depth for serious research or literary work. Do not claim access to the user's ChatGPT account, ChatGPT memory, private chats, files, or current ND project state unless that context is explicitly supplied through this gateway. Full ND connected-state access is a separate layer.''' 
WRITE_SYSTEM=BASE_SYSTEM+'''\nFor literary work: preserve the author's voice and intent, avoid generic AI phrasing, excessive explanation and moralizing. Prefer precise revision, strong prose, concrete imagery and stylistic restraint. If asked to critique, identify only material weaknesses and propose the smallest justified changes.'''
RESEARCH_SYSTEM=BASE_SYSTEM+'''\nFor research: separate evidence from inference, preserve source URLs or source labels present in supplied research material, note uncertainty, and synthesize rather than merely summarize. Prefer primary or authoritative evidence when available.'''
DEEP_SYSTEM=BASE_SYSTEM+'''\nFor difficult analytical work: reason carefully, test assumptions, consider competing explanations, and give a compact final answer with the strongest conclusions and important uncertainty.'''


def cleanerr(x):
    s=str(x)
    for secret in (TOKEN,GROQ_API_KEY,MISTRAL_API_KEY,PATH_KEY):
        if secret:s=s.replace(secret,'[redacted]')
    return s[:1600]

def http_json(url,payload,key,timeout=120,headers_extra=None):
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

def groq_chat(messages,model=None,reasoning='medium',max_tokens=1800):
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

def mistral_text(content):
    if isinstance(content,str):return content.strip()
    if isinstance(content,list):
        out=[]
        for c in content:
            if not isinstance(c,dict):continue
            if c.get('type')=='text' and c.get('text'):out.append(c['text'])
            elif c.get('type') in (None,'output_text') and c.get('content'):out.append(str(c['content']))
        return '\n'.join(out).strip()
    return ''

def mistral_chat(messages,reasoning='high',max_tokens=3000):
    if not MISTRAL_API_KEY:raise RuntimeError('MISTRAL_API_KEY missing')
    payload={'model':MISTRAL_MODEL,'messages':messages,'reasoning_effort':reasoning,'max_tokens':max_tokens}
    j=http_json('https://api.mistral.ai/v1/chat/completions',payload,MISTRAL_API_KEY)
    ch=j.get('choices') or []
    if not ch:raise RuntimeError('Mistral returned no choices')
    out=mistral_text((ch[0].get('message') or {}).get('content'))
    if not out:raise RuntimeError('Mistral returned empty text')
    return out

def heuristic_route(text):
    t=text.lower()
    if any(x in t for x in ('исслед','источник','проверь в интернете','актуальн','последние','новост','сравни данные','найди информацию','research','source','latest','web search')):return 'research'
    if any(x in t for x in ('рассказ','глава','книга','текст','редакт','перепиши','стиль','литератур','сцена','диалог','проза','write','rewrite','chapter')):return 'write'
    if len(text)>1400 or any(x in t for x in ('проанализируй глубоко','сложный анализ','разбери подробно','критически','докажи','опроверг','deep analysis')):return 'deep'
    return 'fast'

def classify_route(text):
    try:
        prompt='''Classify the user's request for routing. Return exactly one word: fast, write, research, or deep.\nfast = ordinary conversation/simple Q&A.\nwrite = book, prose, editing, literary criticism or rewriting.\nresearch = needs current facts, sources, web investigation, comparison of evidence.\ndeep = difficult non-current reasoning/analysis/planning.\nRequest:\n'''+text[:3000]
        out=groq_chat([{'role':'user','content':prompt}],GROQ_MODEL,'low',32).lower()
        for k in ('research','write','deep','fast'):
            if re.search(r'\b'+k+r'\b',out):return k
    except Exception as e:print('ROUTER_CLASSIFY_FALLBACK',cleanerr(e),flush=True)
    return heuristic_route(text)

def routed_response(uid,text):
    hist=history_by_uid.get(uid,[])[-8:]
    forced=mode_by_uid.get(uid,'auto')
    route=classify_route(text) if forced=='auto' else forced
    state['last_route']=route
    print('AI_ROUTE',json.dumps({'uid':uid,'route':route,'mistral':bool(MISTRAL_API_KEY)}),flush=True)
    def save(out):
        history_by_uid[uid]=(hist+[{'role':'user','content':text[:8000]},{'role':'assistant','content':out[:10000]}])[-8:]
        state['ai_calls']+=1
        return out
    try:
        if route=='research':
            evidence=groq_chat([{'role':'system','content':'Research the request using web/tools when useful. Return factual findings, source names/URLs when available, disagreements and uncertainty.'},{'role':'user','content':text[:8000]}],GROQ_RESEARCH_MODEL,'medium',3200)
            if MISTRAL_API_KEY:
                synth='User request:\n'+text[:7000]+'\n\nResearch material from Groq Compound:\n'+evidence[:18000]+'\n\nSynthesize a rigorous answer. Preserve useful source references. Do not invent sources.'
                return save(mistral_chat([{'role':'system','content':RESEARCH_SYSTEM},{'role':'user','content':synth}],'high',3800))
            return save(evidence)
        if route=='write':
            msgs=[{'role':'system','content':WRITE_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
            if MISTRAL_API_KEY:return save(mistral_chat(msgs,'medium',4200))
            return save(groq_chat(msgs,GROQ_MODEL,'medium',3000))
        if route=='deep':
            msgs=[{'role':'system','content':DEEP_SYSTEM}]+hist+[{'role':'user','content':text[:10000]}]
            if MISTRAL_API_KEY:return save(mistral_chat(msgs,'high',4200))
            return save(groq_chat(msgs,GROQ_MODEL,'high',3200))
        msgs=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:8000]}]
        return save(groq_chat(msgs,GROQ_MODEL,'medium',2200))
    except Exception as e:
        print('PRIMARY_ROUTE_ERROR',cleanerr(e),flush=True)
        state['last_error']=cleanerr(e)
        fallback=[{'role':'system','content':BASE_SYSTEM}]+hist+[{'role':'user','content':text[:8000]}]
        return save(groq_chat(fallback,GROQ_MODEL,'medium',2400))

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
    return r.get('items') or [] if isinstance(r,dict) else (r if isinstance(r,list) else [])

def register():
    gid=resolve_gid();state['group_id']=gid
    sid=None
    for s in servers(gid):
        if (s.get('url') or '').rstrip('/')==CALLBACK_URL.rstrip('/'):
            sid=int(s['id']);break
    if sid is None:
        r=vk('groups.addCallbackServer',{'group_id':gid,'url':CALLBACK_URL,'title':'ND Adaptive Gateway'})
        sid=int(r.get('server_id') if isinstance(r,dict) else r)
    state['callback_server_id']=sid
    time.sleep(1);vk('groups.setCallbackSettings',{'group_id':gid,'server_id':sid,'api_version':V,'message_new':1})
    state['callback_configured']=True
    print('VK_READY',json.dumps({'group_id':gid,'server_id':sid,'groq':bool(GROQ_API_KEY),'mistral':bool(MISTRAL_API_KEY),'allowed_count':len(ALLOWED)}),flush=True)

def startup():
    if not TOKEN:state['phase']='waiting_for_token';return
    for wait in (1,3,8,15,30):
        time.sleep(wait)
        try:
            register();state['phase']='ready';state['last_error']=None
            try:
                groq_chat([{'role':'user','content':'Reply exactly OK.'}],GROQ_MODEL,'low',256);state['groq_probe']='ok';print('GROQ_PROBE_OK',flush=True)
            except Exception as e:state['groq_probe']='error';print('GROQ_PROBE_ERROR',cleanerr(e),flush=True)
            if MISTRAL_API_KEY:
                try:
                    mistral_chat([{'role':'user','content':'Reply exactly OK.'}],'none',64);state['mistral_probe']='ok';print('MISTRAL_PROBE_OK',flush=True)
                except Exception as e:state['mistral_probe']='error';state['last_error']=cleanerr(e);print('MISTRAL_PROBE_ERROR',cleanerr(e),flush=True)
            else:state['mistral_probe']='not_configured'
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
    for part in parts[:8]:
        r=vk('messages.send',{'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':part})
        results.append(r)
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
        if p=='/':self.out(200,{'service':'ND Adaptive VK Gateway','health':'/health','groq':bool(GROQ_API_KEY),'mistral':bool(MISTRAL_API_KEY)});return
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
                r=vk('groups.getCallbackConfirmationCode',{'group_id':int(gid or state['group_id'])});self.out(200,r.get('code') if isinstance(r,dict) else r,'text/plain; charset=utf-8')
            except Exception:self.out(500,'error','text/plain; charset=utf-8')
            return
        self.out(200,'ok','text/plain; charset=utf-8')
        if typ!='message_new' or not remember_event(eid):return
        obj=b.get('object') or {};m=obj.get('message') or obj
        if not isinstance(m,dict):return
        peer=m.get('peer_id');uid=m.get('from_id');text=(m.get('text') or '').strip()
        if not peer or not uid:return
        print('VK_MESSAGE',json.dumps({'from_id':uid,'peer_id':peer,'kind':'command' if text.startswith('/') else 'text'}),flush=True)
        def reply():
            try:
                if text=='/whoami':send(peer,'VK user id: %s'%uid);return
                if text=='/nd-test':send(peer,'ND VK Gateway: связь работает.');return
                if text=='/status':
                    send(peer,'ND Adaptive Gateway: VK=OK; Groq=%s (%s); Mistral=%s (%s); mode=%s; last_route=%s'%(
                        'OK' if GROQ_API_KEY else 'OFF',state.get('groq_probe'),'OK' if MISTRAL_API_KEY else 'OFF',state.get('mistral_probe'),mode_by_uid.get(uid,'auto'),state.get('last_route')));return
                if text.startswith('/mode'):
                    p=text.split(None,1)
                    if len(p)==1:send(peer,'Режим: %s. Доступно: auto, fast, write, research, deep.'%mode_by_uid.get(uid,'auto'));return
                    mode=p[1].strip().lower()
                    if mode not in ('auto','fast','write','research','deep'):send(peer,'Неизвестный режим. Доступно: auto, fast, write, research, deep.');return
                    mode_by_uid[uid]=mode;send(peer,'Режим установлен: '+mode);return
                if text=='/reset':history_by_uid.pop(uid,None);mode_by_uid.pop(uid,None);send(peer,'Контекст и режим сброшены.');return
                if ALLOWED and int(uid) not in ALLOWED:send(peer,'Доступ к AI-контуру ND для этого аккаунта пока не разрешён. Ваш VK ID: %s'%uid);return
                now=time.time();last=last_call.get(uid,0)
                if now-last<2:time.sleep(2-(now-last))
                last_call[uid]=time.time();send(peer,routed_response(uid,text or 'Продолжи.'))
            except Exception as e:
                state['last_error']=cleanerr(e);print('VK_MESSAGE_ERROR',cleanerr(e),flush=True)
                try:send(peer,'Ошибка AI-контура. Событие зарегистрировано.')
                except Exception:pass
        threading.Thread(target=reply,daemon=True).start()

print('ND_VK_GATEWAY_V8_ADAPTIVE_START',json.dumps({'port':PORT,'groq':bool(GROQ_API_KEY),'mistral':bool(MISTRAL_API_KEY),'groq_model':GROQ_MODEL,'mistral_model':MISTRAL_MODEL,'allowed_count':len(ALLOWED)}),flush=True)
threading.Thread(target=startup,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
