import os,json,threading,time,hashlib,random
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request,urlopen

PORT=int(os.environ.get('PORT','3000'))
TOKEN=os.environ.get('VK_GROUP_TOKEN','')
OPENAI_API_KEY=os.environ.get('OPENAI_API_KEY','')
OPENAI_MODEL=os.environ.get('OPENAI_MODEL','gpt-5.6-luna')
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

state={'ok':True,'phase':'starting','token_present':bool(TOKEN),'openai_present':bool(OPENAI_API_KEY),'model':OPENAI_MODEL,'group_id':None,'callback_server_id':None,'callback_configured':False,'last_error':None,'last_event_type':None,'last_event_at':None,'gpt_calls':0}
prev_by_uid={}
seen=set(); seen_order=[]
last_call={}
lock=threading.Lock()

SYSTEM_INSTRUCTIONS='''You are the VK interface of Nameless Dhamma (ND), an independent Buddhist research and creative project. Respond in the language of the user; default to Russian. Be concise, precise, and useful. Do not claim to have access to the user's ChatGPT account, ChatGPT memory, private chats, files, or project state unless that context was explicitly provided through this gateway. When asked about ND-specific current state that is not in the conversation, say that the VK gateway currently provides the GPT dialogue layer but not yet the full ND connected-state layer. Avoid pretending that this API session is the same as the user's ChatGPT project chat.''' 

def cleanerr(e):
    s=str(e)
    for secret in (TOKEN,OPENAI_API_KEY,PATH_KEY):
        if secret:s=s.replace(secret,'[redacted]')
    return s[:700]

def vk(method,p=None,timeout=20):
    if not TOKEN: raise RuntimeError('VK_GROUP_TOKEN missing')
    q=dict(p or {});q['access_token']=TOKEN;q['v']=V
    req=Request('https://api.vk.com/method/'+method,data=urlencode({k:str(v) for k,v in q.items() if v is not None}).encode(),method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urlopen(req,timeout=timeout) as r:j=json.loads(r.read().decode())
    if 'error' in j:
        e=j['error'];raise RuntimeError('VK %s error %s: %s'%(method,e.get('error_code'),e.get('error_msg')))
    return j.get('response')

def openai_response(uid,text):
    if not OPENAI_API_KEY: raise RuntimeError('OPENAI_API_KEY missing')
    payload={'model':OPENAI_MODEL,'instructions':SYSTEM_INSTRUCTIONS,'input':text,'store':True,'max_output_tokens':1200}
    prev=prev_by_uid.get(uid)
    if prev: payload['previous_response_id']=prev
    req=Request('https://api.openai.com/v1/responses',data=json.dumps(payload,ensure_ascii=False).encode(),method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+OPENAI_API_KEY})
    with urlopen(req,timeout=90) as r:j=json.loads(r.read().decode())
    rid=j.get('id')
    if rid: prev_by_uid[uid]=rid
    out=[]
    for item in j.get('output') or []:
        if item.get('type')=='message':
            for c in item.get('content') or []:
                if c.get('type')=='output_text' and c.get('text'): out.append(c['text'])
    text='\n'.join(out).strip()
    if not text: text='GPT ответил без текстового содержимого.'
    state['gpt_calls']+=1
    return text[:3900]

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
        r=vk('groups.addCallbackServer',{'group_id':gid,'url':CALLBACK_URL,'title':'ND Gateway3'})
        sid=int(r.get('server_id') if isinstance(r,dict) else r)
    state['callback_server_id']=sid
    time.sleep(1)
    vk('groups.setCallbackSettings',{'group_id':gid,'server_id':sid,'api_version':V,'message_new':1})
    state['callback_configured']=True;state['phase']='ready';state['last_error']=None
    print('VK_READY',json.dumps({'group_id':gid,'server_id':sid,'callback_configured':True,'openai_present':bool(OPENAI_API_KEY),'allowed_count':len(ALLOWED)}),flush=True)

def startup():
    if not TOKEN:state['phase']='waiting_for_token';return
    for wait in (1,3,8,15,30):
        time.sleep(wait)
        try:register();return
        except Exception as e:
            state['last_error']=cleanerr(e);state['phase']='retrying';print('VK_RETRY',state['last_error'],flush=True)
    state['phase']='error'

def send(peer,text):
    r=vk('messages.send',{'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':text[:3900]})
    print('VK_SENT',json.dumps({'peer_id':peer,'result':r}),flush=True)
    return r

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
        raw=(json.dumps(body,ensure_ascii=False) if isinstance(body,(dict,list)) else str(body)).encode()
        self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        p=self.path.split('?',1)[0]
        if p=='/health':self.out(200,state);return
        if p=='/':self.out(200,{'service':'ND VK Gateway','qualification':True,'health':'/health','gpt_ready':bool(OPENAI_API_KEY)});return
        self.out(404,{'error':'not_found'})
    def do_POST(self):
        if self.path.split('?',1)[0]!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
            n=int(self.headers.get('Content-Length','0'));b=json.loads(self.rfile.read(n).decode() or '{}')
        except Exception:self.out(400,'bad request','text/plain; charset=utf-8');return
        typ=b.get('type');gid=b.get('group_id');eid=b.get('event_id');state['last_event_type']=typ;state['last_event_at']=int(time.time())
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
        print('VK_MESSAGE',json.dumps({'from_id':uid,'peer_id':peer,'kind':'command' if text.startswith('/') else 'text'},ensure_ascii=False),flush=True)
        if not peer or not uid:return
        def reply():
            try:
                if text=='/whoami':send(peer,'VK user id: %s'%uid);return
                if text=='/nd-test':send(peer,'ND VK Gateway: связь с Nameless Dhamma работает.');return
                if text=='/status':send(peer,'ND VK Gateway: VK=OK; GPT=%s; model=%s'%('OK' if OPENAI_API_KEY else 'NOT CONFIGURED',OPENAI_MODEL));return
                if ALLOWED and int(uid) not in ALLOWED:
                    send(peer,'Доступ к GPT-контуру ND для этого аккаунта пока не разрешён. Ваш VK ID: %s'%uid);return
                if not OPENAI_API_KEY:
                    send(peer,'VK-контур работает. GPT-контур подготовлен, но OpenAI API key ещё не подключён.');return
                now=time.time();last=last_call.get(uid,0)
                if now-last<2: time.sleep(2-(now-last))
                last_call[uid]=time.time()
                send(peer,openai_response(uid,text or 'Продолжи.'))
            except Exception as e:
                state['last_error']=cleanerr(e);print('VK_MESSAGE_ERROR',state['last_error'],flush=True)
                try:send(peer,'Ошибка GPT-контура. Событие зарегистрировано; повторите сообщение позднее.')
                except Exception:pass
        threading.Thread(target=reply,daemon=True).start()

print('ND_VK_GATEWAY_V3_START',json.dumps({'port':PORT,'token_present':bool(TOKEN),'openai_present':bool(OPENAI_API_KEY),'allowed_count':len(ALLOWED)}),flush=True)
threading.Thread(target=startup,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
