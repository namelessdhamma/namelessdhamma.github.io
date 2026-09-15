import json, os, subprocess, sys, time, threading, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_INNER_GATEWAY_PORT','3001'))
RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BROWSERLESS_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
ROUTER_TOKEN=os.environ.get('ND_VK_MCP_ROUTE_TOKEN','').strip()
GROQ_API_KEY=os.environ.get('GROQ_API_KEY','').strip()
GROQ_MODEL=os.environ.get('GROQ_MODEL','openai/gpt-oss-120b').strip()
OPENROUTER_API_KEY=(os.environ.get('OpenRouter','') or os.environ.get('OPENROUTER_API_KEY','')).strip()
OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()
MEMOS_API_KEY=os.environ.get('MEMOS_API_KEY','').strip()
MEMOS_BASE_URL=os.environ.get('MEMOS_BASE_URL','https://memos.memtensor.cn/api/openmem/v1').strip().rstrip('/')
MEMOS_USER_ID=os.environ.get('MEMOS_USER_ID','nd-true-memory-qualification').strip() or 'nd-true-memory-qualification'
MEMOS_ALLOW_WRITES=os.environ.get('MEMOS_ALLOW_WRITES','false').strip().lower() in ('1','true','yes','on')
MEMOS_MCP_PATH_TOKEN=os.environ.get('MEMOS_MCP_PATH_TOKEN','').strip()
ND_MEMOS_QUALIFY_TRIGGER=os.environ.get('ND_MEMOS_QUALIFY_TRIGGER','').strip()
KERNEL_API_KEY=os.environ.get('KERNEL_API_KEY','').strip()
ND_KERNEL_BOOTSTRAP_TRIGGER=os.environ.get('ND_KERNEL_BOOTSTRAP_TRIGGER','').strip()
ND_KERNEL_MEMOS_ACTION=os.environ.get('ND_KERNEL_MEMOS_ACTION','').strip()
ND_KERNEL_MEMOS_SESSION_ID=os.environ.get('ND_KERNEL_MEMOS_SESSION_ID','').strip()
ND_KERNEL_MEMOS_EMAIL=os.environ.get('ND_KERNEL_MEMOS_EMAIL','').strip()
ND_KERNEL_MEMOS_CODE=os.environ.get('ND_KERNEL_MEMOS_CODE','').strip()
ND_NOTEBOOKLM_BOOTSTRAP_KEY=os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_KEY','').strip()
ND_NOTEBOOKLM_BOOTSTRAP_SHARED_TOKEN=os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_SHARED_TOKEN','').strip()
ND_NOTEBOOKLM_BOOTSTRAP_EXCHANGE_URL=os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_EXCHANGE_URL','').strip()
NL_BOOTSTRAP={}
if BROWSERLESS_TOKEN.lower().startswith('bearer '): BROWSERLESS_TOKEN=BROWSERLESS_TOKEN[7:].strip()
INNER_URL='http://127.0.0.1:%d' % INNER_PORT
GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'

inner_path='/tmp/nd_inner_gateway.py'
src=urllib.request.urlopen(GATEWAY_URL,timeout=30).read()
open(inner_path,'wb').write(src)
env=dict(os.environ); env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)
probe_last={}

# V7: restore the previously qualified Drive bridge as an internal child.
# Credentials remain in Railway environment; this front only proxies /drive/*.
DRIVE_PORT=int(os.environ.get('ND_DRIVE_BRIDGE_PORT','3002'))
DRIVE_URL='http://127.0.0.1:%d' % DRIVE_PORT
DRIVE_FRONT_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1bb27fa0c61e24d373cb170c2edea61e5d3f3cbd/tmp/nd_safe_tool_broker_v14_enable_docs_front.js'
drive_child=None
try:
    subprocess.run(['apk','add','--no-cache','nodejs'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    urllib.request.urlretrieve(DRIVE_FRONT_URL,'/tmp/nd-drive-front.mjs')
    drive_env=dict(os.environ); drive_env['PORT']=str(DRIVE_PORT)
    drive_child=subprocess.Popen(['node','/tmp/nd-drive-front.mjs'],env=drive_env)
    print('ND_DRIVE_CHILD_LAUNCHED '+json.dumps({'port':DRIVE_PORT}),flush=True)
except Exception as e:
    print('ND_DRIVE_CHILD_START_ERROR '+json.dumps({'error':str(e)[:500]}),flush=True)

def drive_internal_call(tool,args):
    token=os.environ.get('ND_DRIVE_BRIDGE_TOKEN','').strip()
    if not token: raise RuntimeError('drive_bridge_token_missing')
    raw=json.dumps({'tool':tool,'args':args},ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(
        DRIVE_URL+'/drive/invoke',data=raw,method='POST',
        headers={'Content-Type':'application/json','X-ND-Bridge-Key':token,'User-Agent':'ND-Drive-v7-Qualification/1.0'})
    with urllib.request.urlopen(req,timeout=90) as r:
        obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    if not obj.get('ok'): raise RuntimeError('drive_bridge_invalid_response')
    return obj.get('result') or {}

def drive_qualify_once():
    time.sleep(4)
    writable=[x.strip() for x in os.environ.get('ND_DRIVE_MCP_WRITABLE_FILE_IDS','').split(',') if x.strip()]
    if not writable:
        print('ND_DRIVE_WRITE_QUALIFICATION '+json.dumps({'ok':False,'reason':'no_writable_target'}),flush=True);return
    doc=writable[0]
    marker='\n[ND_DRIVE_EXTERNAL_WRITE_PROBE_'+str(int(time.time()))+']\n'
    appended=False
    stale_rejected=False
    try:
        before=drive_internal_call('docs_read',{'document_id':doc})
        before_rev=before.get('revision_id')
        ap=drive_internal_call('docs_append',{'document_id':doc,'text':marker,'expected_revision_id':before_rev})
        appended=True
        after=drive_internal_call('docs_read',{'document_id':doc})
        readback=marker in (after.get('text') or '')
        try:
            drive_internal_call('docs_append',{'document_id':doc,'text':'\n[ND_STALE_SHOULD_NOT_WRITE]\n','expected_revision_id':before_rev})
        except HTTPError as e:
            stale_rejected=(e.code==409)
        except Exception as e:
            stale_rejected=('409' in str(e) or 'REVISION_MISMATCH' in str(e))
        clean=drive_internal_call('docs_replace_exact',{'document_id':doc,'old_text':marker,'new_text':'','expected_revision_id':after.get('revision_id')})
        appended=False
        final=drive_internal_call('docs_read',{'document_id':doc})
        clean_final=(marker not in (final.get('text') or '') and '[ND_STALE_SHOULD_NOT_WRITE]' not in (final.get('text') or ''))
        ok=bool(readback and stale_rejected and clean_final and ap.get('after_revision_id')!=before_rev)
        print('ND_DRIVE_WRITE_QUALIFICATION '+json.dumps({'ok':ok,'document_id':doc,'readback':readback,'stale_rejected':stale_rejected,'cleanup':clean_final,'before_revision':before_rev,'after_revision':ap.get('after_revision_id'),'final_revision':final.get('revision_id')},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_DRIVE_WRITE_QUALIFICATION '+json.dumps({'ok':False,'document_id':doc,'error':str(e)[:700]}),flush=True)
        if appended:
            try:
                cur=drive_internal_call('docs_read',{'document_id':doc})
                if marker in (cur.get('text') or ''):
                    drive_internal_call('docs_replace_exact',{'document_id':doc,'old_text':marker,'new_text':'','expected_revision_id':cur.get('revision_id')})
                    print('ND_DRIVE_WRITE_QUALIFICATION_CLEANUP '+json.dumps({'ok':True,'document_id':doc}),flush=True)
            except Exception as ce:
                print('ND_DRIVE_WRITE_QUALIFICATION_CLEANUP '+json.dumps({'ok':False,'document_id':doc,'error':str(ce)[:500]}),flush=True)

threading.Thread(target=drive_qualify_once,daemon=True).start()


def _bl_api_url(path):
    sep='&' if '?' in path else '?'
    return 'https://production-sfo.browserless.io'+path+sep+'token='+urllib.parse.quote(BROWSERLESS_TOKEN,safe='')

def _json_request(url,method='GET',payload=None,headers=None,timeout=90):
    data=None
    h=dict(headers or {})
    if payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        h.setdefault('Content-Type','application/json')
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            return r.status,(json.loads(raw) if raw else {})
    except HTTPError as e:
        try:
            raw=e.read().decode('utf-8','replace')
        except Exception:
            raw=''
        detail=raw[:1200]
        if BROWSERLESS_TOKEN:
            detail=detail.replace(BROWSERLESS_TOKEN,'[REDACTED]').replace(urllib.parse.quote(BROWSERLESS_TOKEN,safe=''),'[REDACTED]')
        raise RuntimeError('HTTP %s: %s' % (e.code, detail or e.reason))

def _bql(session_url,query):
    url=session_url
    if 'token=' not in url:
        url += ('&' if '?' in url else '?')+'token='+urllib.parse.quote(BROWSERLESS_TOKEN,safe='')
    return _json_request(url,'POST',{'query':query,'variables':{}},timeout=90)[1]

def _bootstrap_exchange(target,oauth_token):
    if not ND_NOTEBOOKLM_BOOTSTRAP_EXCHANGE_URL or not ND_NOTEBOOKLM_BOOTSTRAP_SHARED_TOKEN:
        raise RuntimeError('bootstrap_exchange_unconfigured')
    headers={'Authorization':'Bearer '+ND_NOTEBOOKLM_BOOTSTRAP_SHARED_TOKEN,'Content-Type':'application/json'}
    _,obj=_json_request(
        ND_NOTEBOOKLM_BOOTSTRAP_EXCHANGE_URL,'POST',
        {'target':target,'oauth_token':oauth_token},headers=headers,timeout=150)
    if not obj.get('ok'):
        raise RuntimeError('bootstrap_exchange_failed:'+str(obj.get('error') or 'unknown'))
    return obj

def _bootstrap_poll(target,browserql,stop_url):
    state=NL_BOOTSTRAP.setdefault(target,{})
    deadline=time.time()+285
    state.update({'phase':'waiting_google','started_at':int(time.time())})
    try:
        while time.time()<deadline:
            try:
                q='mutation ReadOAuthCookie { cookies { cookies { name value domain } } }'
                obj=_bql(browserql,q)
                cookies=((((obj.get('data') or {}).get('cookies') or {}).get('cookies')) or [])
                token=''
                for ck in cookies:
                    if ck.get('name')=='oauth_token' and ck.get('value'):
                        token=str(ck.get('value')); break
                if token:
                    state['phase']='exchanging'
                    result=_bootstrap_exchange(target,token)
                    safe={'ok':True,'target':target,'phase':'done','notebook_count':result.get('notebook_count'),'credential_persisted':result.get('credential_persisted'),'path':result.get('path')}
                    if result.get('sealed_master_token_b64'):
                        safe['sealed_master_token_b64']=result.get('sealed_master_token_b64')
                    NL_BOOTSTRAP[target]=safe
                    return
            except HTTPError as e:
                if e.code not in (408,409,429):
                    state['last_poll_error']='http_'+str(e.code)
            except Exception as e:
                state['last_poll_error']=clean_error(e)
            time.sleep(3)
        state['phase']='timeout'
        state['ok']=False
    except Exception as e:
        NL_BOOTSTRAP[target]={'ok':False,'target':target,'phase':'failed','error':clean_error(e)}
    finally:
        try:
            _json_request(stop_url+('&' if '?' in stop_url else '?')+'token='+urllib.parse.quote(BROWSERLESS_TOKEN,safe=''),'DELETE',timeout=20)
        except Exception:
            pass

def _bootstrap_stage_error(stage,e):
    if isinstance(e,HTTPError):
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        return RuntimeError(stage+':http_'+str(e.code)+':'+(body[:1000] or str(e.reason)))
    return RuntimeError(stage+':'+str(e))

def _kernel_json(path, method='GET', payload=None, timeout=90):
    if not KERNEL_API_KEY:
        raise RuntimeError('kernel_not_configured')
    data=None
    headers={'Authorization':'Bearer '+KERNEL_API_KEY,'User-Agent':'ND-NotebookLM-Kernel-Bootstrap/1.0'}
    if payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        headers['Content-Type']='application/json'
    req=urllib.request.Request('https://api.onkernel.com'+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            return r.status,(json.loads(raw) if raw else {})
    except HTTPError as e:
        try:
            raw=e.read().decode('utf-8','replace')
        except Exception:
            raw=''
        raise RuntimeError('kernel_http_%s:%s' % (e.code,clean_error(raw or str(e))))

def _kernel_playwright(session_id, code, timeout_sec=30):
    path='/browsers/'+urllib.parse.quote(session_id,safe='')+'/playwright/execute'
    _,obj=_kernel_json(path,'POST',{'code':code,'timeout_sec':timeout_sec},timeout=max(45,timeout_sec+15))
    if not isinstance(obj,dict) or not obj.get('success'):
        raise RuntimeError('kernel_playwright_failed:'+clean_error((obj or {}).get('error') or obj))
    return obj.get('result')

def _kernel_bootstrap_poll(target, session_id):
    state=NL_BOOTSTRAP.setdefault(target,{})
    deadline=time.time()+900
    state.update({'phase':'waiting_google','started_at':int(time.time()),'transport':'kernel'})
    try:
        while time.time()<deadline:
            try:
                result=_kernel_playwright(session_id, """
const cookies = await context.cookies('https://accounts.google.com');
const found = cookies.find(c => c.name === 'oauth_token' && c.value);
let title = '';
try { title = await page.title(); } catch {}
return { oauth_token: found ? found.value : '', url: page.url(), title };
""", 30)
                token=str((result or {}).get('oauth_token') or '')
                state['page_url']=str((result or {}).get('url') or '')[:500]
                state['page_title']=str((result or {}).get('title') or '')[:200]
                if token:
                    state['phase']='exchanging'
                    exchange=_bootstrap_exchange(target,token)
                    NL_BOOTSTRAP[target]={
                        'ok':True,'target':target,'phase':'done','transport':'kernel',
                        'notebook_count':exchange.get('notebook_count'),
                        'credential_persisted':exchange.get('credential_persisted'),
                        'path':exchange.get('path')
                    }
                    return
            except Exception as e:
                state['last_poll_error']=clean_error(e)
            time.sleep(3)
        state['phase']='timeout'
        state['ok']=False
    except Exception as e:
        NL_BOOTSTRAP[target]={'ok':False,'target':target,'phase':'failed','transport':'kernel','error':clean_error(e)}
    finally:
        try:
            _kernel_json('/browsers/'+urllib.parse.quote(session_id,safe=''),'DELETE',None,timeout=20)
        except Exception:
            pass

def notebooklm_bootstrap_start(target):
    if target not in ('railway','render'):
        raise RuntimeError('invalid_target')
    if not KERNEL_API_KEY:
        raise RuntimeError('kernel_not_configured')
    name='nd-notebooklm-'+target+'-'+str(int(time.time()))
    payload={
        'stealth':True,
        'headless':False,
        'timeout_seconds':1200,
        'start_url':'https://accounts.google.com/EmbeddedSetup',
        'name':name
    }
    try:
        _,session=_kernel_json('/browsers','POST',payload,timeout=60)
    except Exception as e:
        raise _bootstrap_stage_error('kernel_session_create',e)
    session_id=str(session.get('session_id') or '')
    live=str(session.get('browser_live_view_url') or '')
    if not session_id or not live:
        raise RuntimeError('kernel_session_create:missing_session_or_live_url')
    preflight={}
    try:
        preflight=_kernel_playwright(session_id, """
await page.waitForTimeout(1200);
let title=''; let text='';
try { title=await page.title(); } catch {}
try { text=(await page.locator('body').innerText()).slice(0,240); } catch {}
return {url:page.url(),title,text};
""",30) or {}
        print('ND_NOTEBOOKLM_KERNEL_PREFLIGHT '+json.dumps({
            'url':str(preflight.get('url') or '')[:500],
            'title':str(preflight.get('title') or '')[:200],
            'text':str(preflight.get('text') or '')[:240]
        },ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_NOTEBOOKLM_KERNEL_PREFLIGHT '+json.dumps({'error':clean_error(e)},ensure_ascii=False),flush=True)
    NL_BOOTSTRAP[target]={
        'ok':None,'target':target,'phase':'waiting_google','transport':'kernel',
        'session_id':session_id,'live_url':live,'started_at':int(time.time()),
        'page_url':str(preflight.get('url') or '')[:500],
        'page_title':str(preflight.get('title') or '')[:200]
    }
    threading.Thread(target=_kernel_bootstrap_poll,args=(target,session_id),daemon=True).start()
    return live

def notebooklm_bootstrap_status(target):
    st=dict(NL_BOOTSTRAP.get(target) or {'ok':None,'target':target,'phase':'not_started'})
    st.pop('live_url',None)
    return st

def clean_error(x):
    s=str(x)
    for token in (BROWSERLESS_TOKEN,ROUTER_TOKEN,GROQ_API_KEY,OPENROUTER_API_KEY,MEMOS_API_KEY,KERNEL_API_KEY):
        if token:
            s=s.replace(token,'[REDACTED]')
            s=s.replace(urllib.parse.quote(token,safe=''),'[REDACTED]')
    return s[:1200]

def parse_sse(raw):
    text=raw.decode('utf-8','replace'); vals=[]
    for line in text.splitlines():
        if line.startswith('data: '):
            try: vals.append(json.loads(line[6:]))
            except Exception: pass
    if not vals: raise RuntimeError('Browserless MCP returned no parsable SSE data')
    return vals[-1]

def post_mcp(payload,session_id=None):
    if not BROWSERLESS_TOKEN: raise RuntimeError('browserless_not_configured')
    headers={'Authorization':'Bearer '+BROWSERLESS_TOKEN,'Accept':'application/json, text/event-stream','Content-Type':'application/json','User-Agent':'ND-True-Doctor-Railway-Relay/2.0'}
    if session_id:
        headers['Mcp-Session-Id']=session_id; headers['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request('https://mcp.browserless.io/mcp',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=90) as r: return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('Browserless MCP HTTP %s: %s'%(e.code,clean_error(body)))

ALLOWED_BL_TOOLS={'browserless_export','browserless_skill','browserless_agent','browserless_search','browserless_performance','browserless_account','browserless_usage','browserless_sessions','browserless_logs','browserless_smartscraper','browserless_function','browserless_map','browserless_crawl','browserless_profiles'}

def browserless_tool_call(name,args=None):
    if name not in ALLOWED_BL_TOOLS: raise RuntimeError('tool is not allowlisted')
    init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'ND True Doctor Railway Relay','version':'2.0'}}}
    status,headers,raw=post_mcp(init)
    if status!=200: raise RuntimeError('initialize failed')
    init_msg=parse_sse(raw); sid=headers.get('Mcp-Session-Id') or headers.get('mcp-session-id')
    if not sid: raise RuntimeError('Browserless MCP did not return a session id')
    post_mcp({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},sid)
    status,_,raw=post_mcp({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args or {}}},sid)
    if status!=200: raise RuntimeError('tools/call failed')
    return {'ok':True,'provider':'Browserless','serverInfo':((init_msg.get('result') or {}).get('serverInfo') or {}),'tool':name,'response':parse_sse(raw)}

def browserless_profiles():
    try:
        out=browserless_tool_call('browserless_profiles',{'limit':20,'offset':0,'_prompt':'ND Doctor Railway relay verification: list Browserless profiles only; no mutation.'}); return 200,out
    except Exception as e:
        print('BROWSERLESS_RAILWAY_RELAY_ERROR',clean_error(e),flush=True); return 502,{'ok':False,'provider':'Browserless','error':clean_error(e)}

def auth_ok(headers):
    if not ROUTER_TOKEN: return False
    return (headers.get('Authorization') or '').strip() == 'Bearer '+ROUTER_TOKEN

def inner_health():
    try:
        with urllib.request.urlopen(INNER_URL+'/health',timeout=8) as r:
            raw=r.read();
            try: body=json.loads(raw.decode('utf-8','replace'))
            except Exception: body={'raw':raw.decode('utf-8','replace')[:600]}
            return r.status,body
    except Exception as e: return 502,{'ok':False,'error':clean_error(e)}

def provider_probe(provider):
    now=time.time(); last=probe_last.get(provider,0)
    if now-last<15: return 429,{'ok':False,'error':'rate_limited','retry_after_sec':max(1,int(15-(now-last)))}
    probe_last[provider]=now
    if provider=='groq':
        key=GROQ_API_KEY; model=GROQ_MODEL; url='https://api.groq.com/openai/v1/chat/completions'; headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    elif provider=='openrouter':
        key=OPENROUTER_API_KEY; model=OPENROUTER_MODEL; url='https://openrouter.ai/api/v1/chat/completions'; headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://namelessdhamma.org','X-Title':'ND Router Qualification'}
    else: return 400,{'ok':False,'error':'provider_must_be_groq_or_openrouter'}
    if not key: return 503,{'ok':False,'provider':provider,'error':'provider_not_configured'}
    payload={'model':model,'messages':[{'role':'user','content':'Reply exactly ND_ROUTER_PROBE_OK.'}],'max_tokens':32,'temperature':0}
    t0=time.time(); req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as r: data=json.loads(r.read().decode('utf-8','replace'))
        reply=str((((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '')).strip()
        return 200,{'ok':reply=='ND_ROUTER_PROBE_OK','provider':provider,'configured_model':model,'response_model':data.get('model'),'reply':reply[:120],'latency_ms':int((time.time()-t0)*1000),'channel':'railway'}
    except HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')[:800]
        except Exception: detail=''
        return e.code,{'ok':False,'provider':provider,'error':clean_error(detail),'channel':'railway'}
    except Exception as e: return 502,{'ok':False,'provider':provider,'error':clean_error(e),'channel':'railway'}


def memos_http(path,payload):
    if not MEMOS_API_KEY:
        return 503,{'ok':False,'provider':'memos','error':'memos_not_configured'}
    raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(
        MEMOS_BASE_URL+path,data=raw,method='POST',
        headers={
            'Authorization':'Token '+MEMOS_API_KEY,
            'Content-Type':'application/json',
            'User-Agent':'ND-True-Memory-MemOS-Qualification/1.0'
        })
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            body=r.read().decode('utf-8','replace')
            try: obj=json.loads(body) if body else {}
            except Exception: obj={'raw':body[:1200]}
            return r.status,obj
    except HTTPError as e:
        try:
            body=e.read().decode('utf-8','replace')
            try: obj=json.loads(body) if body else {}
            except Exception: obj={'raw':body[:1200]}
        except Exception:
            obj={'error':'upstream_http_'+str(e.code)}
        return e.code,obj
    except Exception as e:
        return 502,{'ok':False,'provider':'memos','error':clean_error(e)}

def memos_upstream_ok(code,obj):
    if code < 200 or code >= 300:
        return False
    if isinstance(obj,dict) and 'code' in obj:
        return obj.get('code') in (0,'0',None)
    return True


MEMOS_CORE_PATHS={
    'add_message':'/add/message',
    'search_memory':'/search/memory',
    'get_memory':'/get/memory',
    'update_memory':'/update/memory',
    'delete_memory':'/delete/memory',
}

def memos_prepare_payload(operation,args):
    if not isinstance(args,dict):
        raise RuntimeError('arguments_must_be_object')
    p=dict(args)
    p.pop('user_id',None)
    if operation=='add_message':
        msgs=p.get('messages')
        conv=str(p.get('conversation_id') or '').strip()
        if not conv or len(conv)>256:
            raise RuntimeError('invalid_conversation_id')
        if not isinstance(msgs,list) or not msgs or len(msgs)>200:
            raise RuntimeError('invalid_messages')
        total=0; clean=[]
        for m in msgs:
            if not isinstance(m,dict):
                raise RuntimeError('invalid_message_item')
            role=str(m.get('role') or '').strip()
            content=str(m.get('content') or '')
            if role not in ('user','assistant','system','tool') or not content or len(content)>100000:
                raise RuntimeError('invalid_message')
            total+=len(content)
            if total>500000:
                raise RuntimeError('messages_too_large')
            item={'role':role,'content':content}
            for k in ('name','tool_call_id'):
                if k in m: item[k]=m[k]
            clean.append(item)
        p['messages']=clean
        p['conversation_id']=conv
        p['user_id']=MEMOS_USER_ID
    elif operation=='search_memory':
        q=str(p.get('query') or '').strip()
        if not q or len(q)>50000:
            raise RuntimeError('invalid_query')
        p['query']=q
        p['user_id']=MEMOS_USER_ID
    elif operation=='get_memory':
        p['user_id']=MEMOS_USER_ID
    elif operation=='update_memory':
        mid=str(p.get('memory_id') or '').strip()
        if not mid:
            raise RuntimeError('memory_id_required')
        p['memory_id']=mid
    elif operation=='delete_memory':
        mids=p.get('memory_ids')
        all_for_user=bool(p.pop('all_for_user',False))
        if mids:
            if not isinstance(mids,list) or not mids or len(mids)>500:
                raise RuntimeError('invalid_memory_ids')
            p={'memory_ids':[str(x) for x in mids if str(x).strip()]}
            if not p['memory_ids']:
                raise RuntimeError('invalid_memory_ids')
        elif all_for_user:
            p={'user_id':MEMOS_USER_ID}
        else:
            raise RuntimeError('memory_ids_or_all_for_user_required')
    else:
        raise RuntimeError('unknown_memos_operation')
    return p

def memos_core_call(operation,args):
    if operation not in MEMOS_CORE_PATHS:
        return 400,{'ok':False,'provider':'memos','error':'unknown_operation'}
    if operation in ('add_message','update_memory','delete_memory') and not MEMOS_ALLOW_WRITES:
        return 403,{'ok':False,'provider':'memos','error':'memos_writes_disabled'}
    try:
        payload=memos_prepare_payload(operation,args)
    except Exception as e:
        return 400,{'ok':False,'provider':'memos','error':clean_error(e)}
    code,obj=memos_http(MEMOS_CORE_PATHS[operation],payload)
    return code,{
        'ok':memos_upstream_ok(code,obj),
        'provider':'memos',
        'operation':operation,
        'authority':False,
        'upstream_status':code,
        'upstream':obj,
    }

def memos_mcp_tools():
    common_note='ND True Memory derived memory layer. MemOS is not canonical authority; current StateHead/Registry/artifacts override recalled memory.'
    return [
      {
        'name':'memos_add_message',
        'description':'Write conversation turns into ND MemOS and let MemOS extract/update long-term memories. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'conversation_id':{'type':'string'},
          'messages':{'type':'array','items':{'type':'object','properties':{
            'role':{'type':'string','enum':['user','assistant','system','tool']},
            'content':{'type':'string'}
          },'required':['role','content'],'additionalProperties':True}},
          'agent_id':{'type':'string'}
        },'required':['conversation_id','messages'],'additionalProperties':True}
      },
      {
        'name':'memos_search_memory',
        'description':'Semantic/hybrid search over ND MemOS memories with optional native MemOS retrieval filters. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'query':{'type':'string'},
          'conversation_id':{'type':'string'},
          'agent_id':{'type':'string'},
          'memory_limit_number':{'type':'integer','minimum':1,'maximum':200},
          'include_memory_view':{'type':'array','items':{'type':'string'}},
          'filter':{'type':'object','additionalProperties':True},
          'relativity':{'type':'number'}
        },'required':['query'],'additionalProperties':True}
      },
      {
        'name':'memos_get_memory',
        'description':'List/paginate ND MemOS memories using native MemOS get-memory parameters. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'agent_id':{'type':'string'},
          'page':{'type':'integer','minimum':1},
          'page_size':{'type':'integer','minimum':1,'maximum':200},
          'include_memory_view':{'type':'array','items':{'type':'string'}},
          'filter':{'type':'object','additionalProperties':True}
        },'additionalProperties':True}
      },
      {
        'name':'memos_update_memory',
        'description':'Update an existing ND MemOS memory by memory_id, including title/content/status fields supported by MemOS. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'memory_id':{'type':'string'},
          'title':{'type':'string'},
          'content':{'type':'string'},
          'status':{'type':'string'},
          'tags':{'type':'array','items':{'type':'string'}}
        },'required':['memory_id'],'additionalProperties':True}
      },
      {
        'name':'memos_delete_memory',
        'description':'Delete specific ND MemOS memories, or explicitly clear the fixed ND user namespace with all_for_user=true. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'memory_ids':{'type':'array','items':{'type':'string'}},
          'all_for_user':{'type':'boolean','default':False}
        },'additionalProperties':False}
      },
      {
        'name':'memos_core_call',
        'description':'Full core MemOS memory operation passthrough for ND. Supports add_message, search_memory, get_memory, update_memory, delete_memory; user scope is pinned server-side. '+common_note,
        'inputSchema':{'type':'object','properties':{
          'operation':{'type':'string','enum':['add_message','search_memory','get_memory','update_memory','delete_memory']},
          'payload':{'type':'object','additionalProperties':True}
        },'required':['operation','payload'],'additionalProperties':False}
      }
    ]

def memos_mcp_tool_call(name,args):
    mapping={
      'memos_add_message':'add_message',
      'memos_search_memory':'search_memory',
      'memos_get_memory':'get_memory',
      'memos_update_memory':'update_memory',
      'memos_delete_memory':'delete_memory',
    }
    if name=='memos_core_call':
        if not isinstance(args,dict):
            return 400,{'ok':False,'error':'arguments_must_be_object'}
        op=str(args.get('operation') or '')
        payload=args.get('payload') or {}
        return memos_core_call(op,payload)
    op=mapping.get(name)
    if not op:
        return 404,{'ok':False,'error':'unknown_tool'}
    return memos_core_call(op,args or {})

def memos_qualification_once():
    if not ND_MEMOS_QUALIFY_TRIGGER or not MEMOS_API_KEY or not MEMOS_ALLOW_WRITES:
        return
    time.sleep(3)
    marker='ND_MEMOS_QUAL_'+ND_MEMOS_QUALIFY_TRIGGER
    conv='nd-memos-qualification-'+ND_MEMOS_QUALIFY_TRIGGER[-24:]
    result={'trigger':ND_MEMOS_QUALIFY_TRIGGER,'marker':marker,'steps':{}}
    try:
        code,add=memos_core_call('add_message',{'conversation_id':conv,'messages':[
          {'role':'user','content':'Qualification marker: '+marker+'. Store this as a temporary test memory.'},
          {'role':'assistant','content':'Acknowledged temporary qualification marker '+marker+'.'}
        ]})
        result['steps']['add']={'code':code,'ok':bool(add.get('ok'))}
        found=[]
        search_obj=None
        for _ in range(12):
            time.sleep(3)
            sc,search_obj=memos_core_call('search_memory',{'query':marker,'conversation_id':conv,'memory_limit_number':20})
            up=(search_obj or {}).get('upstream') or {}
            data=up.get('data') or {}
            found=data.get('memory_detail_list') or data.get('memory_list') or []
            if found: break
        result['steps']['search']={'ok':bool(found),'count':len(found)}
        mid=''
        for item in found:
            if isinstance(item,dict) and item.get('id'):
                mid=str(item.get('id')); break
        if mid:
            uc,upd=memos_core_call('update_memory',{'memory_id':mid,'content':marker+' UPDATED'})
            result['steps']['update']={'code':uc,'ok':bool(upd.get('ok')),'memory_id':mid}
            gc,geto=memos_core_call('get_memory',{'page':1,'page_size':100})
            result['steps']['get']={'code':gc,'ok':bool(geto.get('ok'))}
            dc,dele=memos_core_call('delete_memory',{'memory_ids':[mid]})
            result['steps']['delete']={'code':dc,'ok':bool(dele.get('ok'))}
        else:
            result['steps']['update']={'ok':False,'reason':'no_memory_id'}
            result['steps']['get']={'ok':False,'reason':'no_memory_id'}
            result['steps']['delete']={'ok':False,'reason':'no_memory_id'}
        result['ok']=all(bool((result['steps'].get(k) or {}).get('ok')) for k in ('add','search','update','get','delete'))
    except Exception as e:
        result['ok']=False
        result['error']=clean_error(e)
    print('ND_MEMOS_FULL_QUALIFICATION '+json.dumps(result,ensure_ascii=False),flush=True)

threading.Thread(target=memos_qualification_once,daemon=True).start()

def memos_mcp_selftest_once():
    if not MEMOS_MCP_PATH_TOKEN:
        return
    time.sleep(7)
    base='http://127.0.0.1:%d/nd/memory/memos/mcp/%s' % (PORT,urllib.parse.quote(MEMOS_MCP_PATH_TOKEN,safe=''))
    def call(obj):
        req=urllib.request.Request(base,data=json.dumps(obj).encode('utf-8'),method='POST',headers={'Content-Type':'application/json','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode('utf-8','replace') or '{}')
    out={'ok':False}
    try:
        s1,r1=call({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'nd-memos-selftest','version':'1.0'}}})
        s2,r2=call({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        tools=((r2.get('result') or {}).get('tools') or [])
        names=[str(x.get('name') or '') for x in tools if isinstance(x,dict)]
        required={'memos_add_message','memos_search_memory','memos_get_memory','memos_update_memory','memos_delete_memory','memos_core_call'}
        out={'ok':s1==200 and s2==200 and required.issubset(set(names)),'initialize_status':s1,'tools_status':s2,'tools':names}
    except Exception as e:
        out={'ok':False,'error':clean_error(e)}
    print('ND_MEMOS_MCP_SELFTEST '+json.dumps(out,ensure_ascii=False),flush=True)

threading.Thread(target=memos_mcp_selftest_once,daemon=True).start()


def kernel_bootstrap_once():
    if not KERNEL_API_KEY or not ND_KERNEL_BOOTSTRAP_TRIGGER:
        return
    headers={
        'Authorization':'Bearer '+KERNEL_API_KEY,
        'Content-Type':'application/json',
        'User-Agent':'ND-Kernel-MemOS-Bootstrap/1.1'
    }
    try:
        req=urllib.request.Request('https://api.onkernel.com/browsers',headers=headers,method='GET')
        with urllib.request.urlopen(req,timeout=30) as r:
            existing=json.loads(r.read().decode('utf-8','replace') or '[]')
        if isinstance(existing,dict):
            existing=existing.get('data') or existing.get('browsers') or []
        for b in (existing or []):
            if not isinstance(b,dict) or b.get('deleted_at'): continue
            live=str(b.get('browser_live_view_url') or '')
            start_url=str(b.get('start_url') or '')
            name=str(b.get('name') or '')
            if live and ('memos-dashboard.openmem.net' in start_url or name.startswith('nd-memos-registration')):
                print('ND_KERNEL_MEMOS_BOOTSTRAP '+json.dumps({
                    'ok':True,'reused':True,'session_id':b.get('session_id'),
                    'browser_live_view_url':live,'timeout_seconds':b.get('timeout_seconds'),
                    'start_url':start_url
                },ensure_ascii=False),flush=True)
                return
    except Exception as e:
        print('ND_KERNEL_MEMOS_LIST '+json.dumps({'ok':False,'error':clean_error(e)},ensure_ascii=False),flush=True)
    payload={
        'stealth':True,
        'headless':False,
        'timeout_seconds':7200,
        'start_url':'https://memos-dashboard.openmem.net/',
        'name':'nd-memos-registration-'+ND_KERNEL_BOOTSTRAP_TRIGGER[-12:]
    }
    req=urllib.request.Request(
        'https://api.onkernel.com/browsers',
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
        print('ND_KERNEL_MEMOS_BOOTSTRAP '+json.dumps({
            'ok':True,'reused':False,
            'session_id':obj.get('session_id'),
            'browser_live_view_url':obj.get('browser_live_view_url'),
            'timeout_seconds':obj.get('timeout_seconds'),
            'start_url':obj.get('start_url')
        },ensure_ascii=False),flush=True)
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')[:1200]
        except Exception: body=''
        print('ND_KERNEL_MEMOS_BOOTSTRAP '+json.dumps({'ok':False,'status':e.code,'error':clean_error(body or str(e))},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_KERNEL_MEMOS_BOOTSTRAP '+json.dumps({'ok':False,'error':clean_error(e)},ensure_ascii=False),flush=True)

threading.Thread(target=kernel_bootstrap_once,daemon=True).start()


def kernel_playwright_execute(code,timeout_sec=60):
    if not KERNEL_API_KEY or not ND_KERNEL_MEMOS_SESSION_ID:
        raise RuntimeError('kernel_action_unconfigured')
    url='https://api.onkernel.com/browsers/'+urllib.parse.quote(ND_KERNEL_MEMOS_SESSION_ID,safe='')+'/playwright/execute'
    payload={'code':code,'timeout_sec':timeout_sec}
    req=urllib.request.Request(
        url,data=json.dumps(payload).encode('utf-8'),method='POST',
        headers={
            'Authorization':'Bearer '+KERNEL_API_KEY,
            'Content-Type':'application/json',
            'User-Agent':'ND-Kernel-MemOS-Registration/1.0'
        })
    try:
        with urllib.request.urlopen(req,timeout=timeout_sec+15) as r:
            return json.loads(r.read().decode('utf-8','replace') or '{}')
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')[:2000]
        except Exception: body=''
        raise RuntimeError('kernel_playwright_http_%s:%s'%(e.code,body or e.reason))

def kernel_memos_action_once():
    action=ND_KERNEL_MEMOS_ACTION
    if not action: return
    time.sleep(2)
    try:
        if action=='inspect':
            code="""
await page.goto('https://memos-dashboard.openmem.net/', {waitUntil:'domcontentloaded'});
await page.waitForTimeout(2500);
return {
  url: page.url(),
  title: await page.title(),
  body: (await page.locator('body').innerText()).slice(0,6000),
  inputs: await page.locator('input').evaluateAll(es => es.map(e => ({type:e.type, placeholder:e.placeholder, value:e.value, name:e.name}))),
  buttons: await page.locator('button').evaluateAll(es => es.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0,50))
};
"""
        elif action=='request_code':
            if not ND_KERNEL_MEMOS_EMAIL: raise RuntimeError('memos_email_missing')
            email=json.dumps(ND_KERNEL_MEMOS_EMAIL)
            code=f"""
await page.goto('https://memos-dashboard.openmem.net/', {{waitUntil:'domcontentloaded'}});
await page.waitForTimeout(1500);
const email={email};
const emailInput=page.locator('input').first();
await emailInput.fill(email);
const btn=page.getByRole('button', {{name:/Get verification code/i}});
await btn.click();
await page.waitForTimeout(1500);
return {{url:page.url(), body:(await page.locator('body').innerText()).slice(0,3500)}};
"""
        elif action=='submit_code':
            if not ND_KERNEL_MEMOS_CODE: raise RuntimeError('memos_code_missing')
            vcode=json.dumps(ND_KERNEL_MEMOS_CODE)
            code=f"""
const code={vcode};
const inputs=page.locator('input');
const n=await inputs.count();
if(n<2) throw new Error('verification input not found');
await inputs.nth(1).fill(code);
await page.getByRole('button', {{name:/Confirm/i}}).click();
await page.waitForTimeout(3500);
return {{url:page.url(), body:(await page.locator('body').innerText()).slice(0,5000)}};
"""
        elif action=='inspect_dashboard':
            code="""
await page.waitForTimeout(1200);
return {
  url: page.url(),
  title: await page.title(),
  body: (await page.locator('body').innerText()).slice(0,8000),
  links: await page.locator('a').evaluateAll(es => es.map(e => ({text:(e.innerText||e.textContent||'').trim(), href:e.href})).filter(x=>x.text||x.href).slice(0,100)),
  buttons: await page.locator('button').evaluateAll(es => es.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0,100))
};
"""
        elif action=='inspect_apikeys':
            code="""
await page.goto('https://memos-dashboard.openmem.net/apikeys/', {waitUntil:'domcontentloaded'});
await page.waitForTimeout(2000);
return {
  url: page.url(),
  title: await page.title(),
  body: (await page.locator('body').innerText()).slice(0,8000),
  inputs: await page.locator('input').evaluateAll(es => es.map(e => ({type:e.type,placeholder:e.placeholder,name:e.name,value:e.value}))),
  buttons: await page.locator('button').evaluateAll(es => es.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0,100)),
  links: await page.locator('a').evaluateAll(es => es.map(e => ({text:(e.innerText||e.textContent||'').trim(),href:e.href})).filter(x=>x.text||x.href).slice(0,100))
};
"""
        elif action=='open_login':
            code="""
await page.goto('https://memos.openmem.net/?from=%2Fapikeys%2F', {waitUntil:'domcontentloaded'});
await page.waitForTimeout(1200);
let target=page.getByRole('button', {name:/Cloud API Quick Start/i});
if(await target.count()) {
  await target.first().click();
} else {
  target=page.getByRole('button', {name:/Start now/i});
  if(await target.count()) await target.first().click();
}
await page.waitForTimeout(2200);
const pages=context.pages();
const details=[];
for (const p of pages) {
  let body='';
  try { body=(await p.locator('body').innerText()).slice(0,3500); } catch(e){}
  details.push({url:p.url(), title:await p.title(), body});
}
return {activeUrl:page.url(), pages:details};
"""
        elif action=='raw_dashboard':
            code="""
const r=await context.request.get('https://memos-dashboard.openmem.net/', {maxRedirects:0});
const text=await r.text();
return {status:r.status(), headers:r.headers(), body:text.slice(0,12000)};
"""
        elif action=='discover_dashboard_scripts':
            code="""
await page.goto('https://memos-dashboard.openmem.net/', {waitUntil:'domcontentloaded'});
await page.waitForTimeout(1200);
const scripts=await page.locator('script[src]').evaluateAll(es=>es.map(e=>e.src));
const out=[];
for(const src of scripts.slice(0,40)){
  try{
    const txt=await page.evaluate(async u=>await (await fetch(u)).text(),src);
    const needles=['Welcome to MemOS','verification code','Get verification code','Please enter your email address','apikey','api key'];
    const hits=[];
    for(const n of needles){
      const i=txt.toLowerCase().indexOf(n.toLowerCase());
      if(i>=0) hits.push({needle:n,snippet:txt.slice(Math.max(0,i-700),i+1600)});
    }
    if(hits.length) out.push({src,hits});
  }catch(e){}
}
return {url:page.url(),scripts:scripts.slice(0,40),matches:out};
"""
        else:
            raise RuntimeError('unknown_kernel_memos_action')
        obj=kernel_playwright_execute(code,60)
        # Never log verification code even if echoed by upstream.
        safe=json.dumps(obj,ensure_ascii=False)
        if ND_KERNEL_MEMOS_CODE: safe=safe.replace(ND_KERNEL_MEMOS_CODE,'[REDACTED]')
        print('ND_KERNEL_MEMOS_ACTION '+safe[:12000],flush=True)
    except Exception as e:
        print('ND_KERNEL_MEMOS_ACTION '+json.dumps({'success':False,'action':action,'error':clean_error(e)},ensure_ascii=False),flush=True)

threading.Thread(target=kernel_memos_action_once,daemon=True).start()

GEMINI_GITHUB_RELAY_URL='https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-gemini-mcp/github'

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8'); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def relay_browserless(self):
        expected=('/browserless/profiles/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            code,obj=browserless_profiles(); self.send_json(code,obj); return True
        return False
    def router_get(self):
        p=self.path.split('?',1)[0]
        if p not in ('/nd/router/status','/nd/router/health'): return False
        if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        code,health=inner_health()
        if p.endswith('/status'):
            self.send_json(200,{'ok':code==200,'channel':'railway','proxy':'v6-router-control','inner_health_status':code,'inner_health':health,'providers':{'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'drive_port':DRIVE_PORT,'drive_child':bool(drive_child)}})
        else: self.send_json(code,{'ok':code==200,'channel':'railway','inner_health':health})
        return True
    def memos_get(self):
        p=self.path.split('?',1)[0]
        if p!='/nd/memory/memos/status': return False
        if not auth_ok(self.headers):
            self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        self.send_json(200,{
            'ok':True,
            'provider':'memos',
            'mode':'cloud_bounded_qualification',
            'configured':bool(MEMOS_API_KEY),
            'writes_enabled':bool(MEMOS_ALLOW_WRITES),
            'fixed_user_id':MEMOS_USER_ID,
            'authority':False,
            'routes':['probe','search','get','add','update','delete','mcp']
        })
        return True

    def memos_mcp(self):
        p=self.path.split('?',1)[0]
        expected=('/nd/memory/memos/mcp/'+MEMOS_MCP_PATH_TOKEN) if MEMOS_MCP_PATH_TOKEN else ''
        if not expected or p!=expected: return False
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':clean_error(e)},'id':None}); return True
        mid=msg.get('id')
        method=str(msg.get('method') or '')
        if method=='notifications/initialized':
            self.send_response(204); self.end_headers(); return True
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{
                'protocolVersion':'2025-06-18',
                'capabilities':{'tools':{}},
                'serverInfo':{'name':'nd-memos-remote-mcp','version':'1.0.0'},
                'instructions':'ND True Memory MemOS bridge with full core read/write lifecycle. MemOS is derived memory, not canonical authority.'
            }}); return True
        if method=='ping':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return True
        if method=='tools/list':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':memos_mcp_tools()}}); return True
        if method=='tools/call':
            params=msg.get('params') or {}
            name=str(params.get('name') or '')
            args=params.get('arguments') or {}
            code,obj=memos_mcp_tool_call(name,args)
            payload={'jsonrpc':'2.0','id':mid,'result':{
              'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],
              'structuredContent':obj,
              'isError':not bool(obj.get('ok'))
            }}
            self.send_json(200,payload); return True
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}}); return True

    def memos_post(self):
        p=self.path.split('?',1)[0]
        allowed={
          '/nd/memory/memos/probe':'probe',
          '/nd/memory/memos/search':'search_memory',
          '/nd/memory/memos/get':'get_memory',
          '/nd/memory/memos/add':'add_message',
          '/nd/memory/memos/update':'update_memory',
          '/nd/memory/memos/delete':'delete_memory',
        }
        op=allowed.get(p)
        if not op: return False
        if not auth_ok(self.headers):
            self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        if not MEMOS_API_KEY:
            self.send_json(503,{'ok':False,'provider':'memos','error':'memos_not_configured'}); return True
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n > 1048576: raise RuntimeError('request_too_large')
            body=json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
            if not isinstance(body,dict): raise RuntimeError('body_must_be_object')
        except Exception as e:
            self.send_json(400,{'ok':False,'error':clean_error(e)}); return True
        if op=='probe':
            code,obj=memos_core_call('search_memory',{'query':'ND_MEMOS_CONNECTIVITY_PROBE','conversation_id':'nd-memos-connectivity-probe'})
        else:
            code,obj=memos_core_call(op,body)
        self.send_json(200 if bool(obj.get('ok')) else code,obj); return True


    def drive_forward(self):
        n=int(self.headers.get('Content-Length','0') or 0); body=self.rfile.read(n) if n else None
        url=DRIVE_URL+self.path; headers={}
        for k,v in self.headers.items():
            if k.lower() in ('host','connection','content-length','transfer-encoding'): continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read(); self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() in ('connection','transfer-encoding','content-length'): continue
                    self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read(); self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'): continue
                self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except Exception as e:
            self.send_json(503,{'ok':False,'error':'drive_bridge_unavailable','detail':clean_error(e)})

    def forward(self):
        n=int(self.headers.get('Content-Length','0') or 0); body=self.rfile.read(n) if n else None; url=INNER_URL+self.path; headers={}
        for k,v in self.headers.items():
            if k.lower() in ('host','connection','content-length','transfer-encoding'): continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read(); self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() in ('connection','transfer-encoding','content-length'): continue
                    self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read(); self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'): continue
                self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except Exception as e: self.send_json(502,{'error':'inner_gateway_unavailable','detail':clean_error(e)})
    def notebooklm_bootstrap_get(self):
        p=self.path.split('?',1)[0]
        prefix='/notebooklm/bootstrap/'
        if not p.startswith(prefix): return False
        parts=p[len(prefix):].split('/')
        if len(parts)<2: self.send_json(404,{'ok':False,'error':'not_found'}); return True
        if not ND_NOTEBOOKLM_BOOTSTRAP_KEY or parts[-1]!=ND_NOTEBOOKLM_BOOTSTRAP_KEY:
            self.send_json(404,{'ok':False,'error':'not_found'}); return True
        if parts[0]=='status' and len(parts)==3:
            target=parts[1]
            self.send_json(200,notebooklm_bootstrap_status(target)); return True
        target=parts[0]
        if target not in ('railway','render'):
            self.send_json(404,{'ok':False,'error':'not_found'}); return True
        try:
            live=notebooklm_bootstrap_start(target)
            self.send_response(302); self.send_header('Location',live); self.send_header('Cache-Control','no-store'); self.end_headers()
        except Exception as e:
            err=clean_error(e)
            print('ND_NOTEBOOKLM_BOOTSTRAP_START_ERROR '+json.dumps({'target':target,'error':err},ensure_ascii=False),flush=True)
            self.send_json(502,{'ok':False,'target':target,'error':err,'rev':'notebooklm-bootstrap-diag-3'})
        return True

    def do_GET(self):
        if self.notebooklm_bootstrap_get(): return
        if self.path.split('?',1)[0].startswith('/drive/'):
            self.drive_forward(); return
        if self.relay_browserless() or self.memos_get() or self.router_get(): return
        self.forward()
    def bootstrap_browserless(self):
        global BROWSERLESS_TOKEN
        expected=('/browserless/bootstrap/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if not expected or self.path.split('?',1)[0]!=expected: return False
        if BROWSERLESS_TOKEN: self.send_json(409,{'ok':False,'error':'browserless_already_configured'}); return True
        auth=(self.headers.get('Authorization') or '').strip()
        if not auth.startswith('Bearer '): self.send_json(401,{'ok':False,'error':'missing_bearer'}); return True
        token=auth[7:].strip()
        if len(token)<20: self.send_json(400,{'ok':False,'error':'invalid_token_shape'}); return True
        BROWSERLESS_TOKEN=token; self.send_json(200,{'ok':True,'configured':True,'persistence':'process_memory'}); return True
    def gemini_github_relay(self):
        p=self.path.split('?',1)[0]
        if p!='/gemini/github': return False
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>524288:
                self.send_json(413,{'ok':False,'error':'request_too_large'}); return True
            body=self.rfile.read(n) if n else b'{}'
            auth=(self.headers.get('Authorization') or '').strip()
            if not auth.startswith('Bearer '):
                self.send_json(401,{'ok':False,'error':'missing_oidc_bearer'}); return True
            req=urllib.request.Request(
                GEMINI_GITHUB_RELAY_URL,
                data=body,
                method='POST',
                headers={
                    'Authorization':auth,
                    'Content-Type':'application/json',
                    'Accept':'application/json',
                    'User-Agent':'ND-Gemini-Railway-Relay/1.0'
                }
            )
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read()
                    try: obj=json.loads(raw.decode('utf-8','replace') or '{}')
                    except Exception: obj={'ok':False,'error':'invalid_upstream_json'}
                    if isinstance(obj,dict):
                        obj.setdefault('relay','railway_to_supabase')
                    self.send_json(r.status,obj); return True
            except HTTPError as e:
                raw=e.read().decode('utf-8','replace')
                try: obj=json.loads(raw or '{}')
                except Exception: obj={'ok':False,'error':'upstream_http_'+str(e.code)}
                if isinstance(obj,dict): obj.setdefault('relay','railway_to_supabase')
                self.send_json(e.code,obj); return True
        except Exception as e:
            self.send_json(502,{'ok':False,'error':'gemini_relay_unavailable','detail':clean_error(e),'relay':'railway_to_supabase'}); return True

    def do_POST(self):
        p=self.path.split('?',1)[0]
        if p.startswith('/drive/'):
            self.drive_forward(); return
        if self.memos_mcp(): return
        if self.memos_post(): return
        if self.gemini_github_relay(): return
        if self.bootstrap_browserless(): return
        if p=='/nd/router/request':
            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return
            try:
                n=int(self.headers.get('Content-Length','0') or 0); b=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            except Exception: self.send_json(400,{'ok':False,'error':'bad_request'}); return
            code,obj=provider_probe(str(b.get('provider') or '').strip().lower()); self.send_json(code,obj); return
        expected=('/browserless/call/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and p==expected:
            try:
                n=int(self.headers.get('Content-Length','0') or 0); body=json.loads(self.rfile.read(n).decode('utf-8') or '{}'); name=str(body.get('tool') or ''); args=body.get('arguments') or {}
                if not isinstance(args,dict): raise RuntimeError('arguments must be an object')
                self.send_json(200,browserless_tool_call(name,args)); return
            except Exception as e: self.send_json(400,{'ok':False,'error':clean_error(e)}); return
        self.forward()

# NotebookLM bootstrap transport is exercised on demand only. Startup self-probe removed to avoid Browserless same-session contention.

print('ND_BROWSERLESS_FRONT_PROXY_V9_MEMOS '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'router_control':bool(ROUTER_TOKEN),'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'memos':bool(MEMOS_API_KEY),'memos_writes':bool(MEMOS_ALLOW_WRITES),'memos_mcp':bool(MEMOS_MCP_PATH_TOKEN)}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
