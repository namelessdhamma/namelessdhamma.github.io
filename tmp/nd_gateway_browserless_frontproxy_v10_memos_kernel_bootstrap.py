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

def notebooklm_bootstrap_start(target):
    if target not in ('railway','render'):
        raise RuntimeError('invalid_target')
    if not BROWSERLESS_TOKEN:
        raise RuntimeError('browserless_not_configured')
    payload={'ttl':300000,'stealth':True}
    try:
        _,session=_json_request(_bl_api_url('/session'),'POST',payload,timeout=60)
    except Exception as e:
        raise _bootstrap_stage_error('session_create',e)
    browserql=str(session.get('browserQL') or '')
    stop=str(session.get('stop') or '')
    if not browserql or not stop:
        raise RuntimeError('session_create:browserless_session_missing_urls')
    query='mutation StartNotebookLMBootstrap { goto(url: "https://accounts.google.com/EmbeddedSetup/identifier?flowName=EmbeddedSetupAndroid", waitUntil: domContentLoaded) { status } liveURL(timeout: 120000, interactable: true, quality: 60) { liveURL } }'
    try:
        obj=_bql(browserql,query)
    except Exception as e:
        raise _bootstrap_stage_error('bql_google_liveurl',e)
    if obj.get('errors'):
        raise RuntimeError('bql_google_liveurl:graphql:'+json.dumps(obj.get('errors'),ensure_ascii=False)[:1000])
    live=((((obj.get('data') or {}).get('liveURL') or {}).get('liveURL')) or '')
    if not live:
        raise RuntimeError('bql_google_liveurl:browserless_liveurl_missing')
    NL_BOOTSTRAP[target]={'ok':None,'target':target,'phase':'waiting_google','live_url':live,'started_at':int(time.time())}
    threading.Thread(target=_bootstrap_poll,args=(target,browserql,stop),daemon=True).start()
    return live

def notebooklm_bootstrap_status(target):
    st=dict(NL_BOOTSTRAP.get(target) or {'ok':None,'target':target,'phase':'not_started'})
    st.pop('live_url',None)
    return st

def clean_error(x):
    s=str(x)
    for token in (BROWSERLESS_TOKEN,ROUTER_TOKEN,GROQ_API_KEY,OPENROUTER_API_KEY,MEMOS_API_KEY):
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
            'routes':['probe','search','add']
        })
        return True

    def memos_post(self):
        p=self.path.split('?',1)[0]
        allowed=('/nd/memory/memos/probe','/nd/memory/memos/search','/nd/memory/memos/add')
        if p not in allowed: return False
        if not auth_ok(self.headers):
            self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        if not MEMOS_API_KEY:
            self.send_json(503,{'ok':False,'provider':'memos','error':'memos_not_configured'}); return True
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n > 262144: raise RuntimeError('request_too_large')
            body=json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
            if not isinstance(body,dict): raise RuntimeError('body_must_be_object')
        except Exception as e:
            self.send_json(400,{'ok':False,'error':clean_error(e)}); return True

        if p.endswith('/probe'):
            code,obj=memos_http('/search/memory',{
                'query':'ND_MEMOS_CONNECTIVITY_PROBE',
                'user_id':MEMOS_USER_ID,
                'conversation_id':'nd-memos-connectivity-probe'
            })
            self.send_json(200 if memos_upstream_ok(code,obj) else code,{
                'ok':memos_upstream_ok(code,obj),
                'provider':'memos',
                'operation':'probe',
                'upstream_status':code,
                'upstream':obj
            }); return True

        if p.endswith('/search'):
            query=str(body.get('query') or '').strip()
            if not query or len(query)>20000:
                self.send_json(400,{'ok':False,'error':'invalid_query'}); return True
            payload={'query':query,'user_id':MEMOS_USER_ID}
            conv=str(body.get('conversation_id') or '').strip()
            if conv:
                if len(conv)>256:
                    self.send_json(400,{'ok':False,'error':'conversation_id_too_long'}); return True
                payload['conversation_id']=conv
            code,obj=memos_http('/search/memory',payload)
            self.send_json(200 if memos_upstream_ok(code,obj) else code,{
                'ok':memos_upstream_ok(code,obj),
                'provider':'memos',
                'operation':'search',
                'upstream_status':code,
                'upstream':obj
            }); return True

        if not MEMOS_ALLOW_WRITES:
            self.send_json(403,{'ok':False,'provider':'memos','error':'memos_writes_disabled'}); return True
        conv=str(body.get('conversation_id') or '').strip()
        messages=body.get('messages')
        if not conv or len(conv)>256:
            self.send_json(400,{'ok':False,'error':'invalid_conversation_id'}); return True
        if not isinstance(messages,list) or not messages or len(messages)>100:
            self.send_json(400,{'ok':False,'error':'invalid_messages'}); return True
        clean=[]
        total=0
        for m in messages:
            if not isinstance(m,dict):
                self.send_json(400,{'ok':False,'error':'invalid_message_item'}); return True
            role=str(m.get('role') or '').strip()
            content=str(m.get('content') or '')
            if role not in ('user','assistant') or not content or len(content)>50000:
                self.send_json(400,{'ok':False,'error':'invalid_message'}); return True
            total += len(content)
            if total>200000:
                self.send_json(400,{'ok':False,'error':'messages_too_large'}); return True
            clean.append({'role':role,'content':content})
        code,obj=memos_http('/add/message',{
            'user_id':MEMOS_USER_ID,
            'conversation_id':conv,
            'messages':clean
        })
        self.send_json(200 if memos_upstream_ok(code,obj) else code,{
            'ok':memos_upstream_ok(code,obj),
            'provider':'memos',
            'operation':'add',
            'upstream_status':code,
            'upstream':obj
        }); return True

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
    def do_POST(self):
        p=self.path.split('?',1)[0]
        if p.startswith('/drive/'):
            self.drive_forward(); return
        if self.memos_post(): return
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

print('ND_BROWSERLESS_FRONT_PROXY_V9_MEMOS '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'router_control':bool(ROUTER_TOKEN),'groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'memos':bool(MEMOS_API_KEY),'memos_writes':bool(MEMOS_ALLOW_WRITES)}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
