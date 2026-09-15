import urllib.request, os

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/61bc11a0025e0c4b32dc555d9248ff87261dd7f8/tmp/nd_gateway_browserless_frontproxy_v10_memos_kernel_bootstrap.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

src=src.replace(
"OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()\n",
"OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()\nOPENAI_API_KEY=os.environ.get('OPENAI_API_KEY','').strip()\nOPENAI_MODEL=os.environ.get('OPENAI_MODEL','gpt-5.6').strip() or 'gpt-5.6'\n",
1)

anchor="GEMINI_GITHUB_RELAY_URL='https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-gemini-mcp/github'\n"
addition=r'''
def openai_agents_api_call(method,path,payload=None,timeout=180):
    if not OPENAI_API_KEY:
        return 503,{'ok':False,'provider':'openai_agents_api','error':'openai_api_key_missing'}
    url='https://api.openai.com/v1'+path
    data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    headers={'Authorization':'Bearer '+OPENAI_API_KEY,'Accept':'application/json','User-Agent':'ND-Agents-API-Qualification/0.1'}
    if data is not None: headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            try: obj=json.loads(raw or '{}')
            except Exception: obj={'raw':raw[:8000]}
            return r.status,{'ok':True,'provider':'openai_agents_api','upstream':obj}
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace')
        try: obj=json.loads(raw or '{}')
        except Exception: obj={'raw':raw[:8000]}
        return e.code,{'ok':False,'provider':'openai_agents_api','upstream_status':e.code,'upstream':obj}
    except Exception as e:
        return 502,{'ok':False,'provider':'openai_agents_api','error':clean_error(e)}

def openai_agents_probe():
    code,obj=openai_agents_api_call('GET','/agents/sessions?limit=1&order=desc')
    if isinstance(obj,dict):
        obj['qualification']='ND_AGENTS_API_V0_1'
        obj['model_configured']=OPENAI_MODEL
    return code,obj

def openai_agents_session_create(body):
    body=body if isinstance(body,dict) else {}
    prompt=str(body.get('input') or 'Return exactly: ND_AGENTS_API_PASS')[:12000]
    instructions=str(body.get('instructions') or 'You are a bounded Nameless Dhamma Agents API qualification agent. Follow the user input exactly. Do not call external tools.')[:12000]
    model=str(body.get('model') or OPENAI_MODEL)[:128]
    payload={'environment':{'type':'none'},'agent':{'name':'ND Agents API Qualification','instructions':instructions,'model':model,'multi_agent':{'enabled':False}},'input':prompt,'metadata':{'nd_scope':'qualification','nd_revision':'ND_AGENTS_API_V0_1'}}
    code,obj=openai_agents_api_call('POST','/agents/sessions',payload,timeout=240)
    if isinstance(obj,dict): obj['qualification']='ND_AGENTS_API_V0_1'
    return code,obj
'''
assert src.count(anchor)==1
src=src.replace(anchor,anchor+addition,1)

old="""    def do_GET(self):
        if self.notebooklm_bootstrap_get(): return
"""
new="""    def openai_agents_get(self):
        p=self.path.split('?',1)[0]
        if p not in ('/nd/openai/agents/status','/nd/openai/agents/probe'): return False
        if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        if p.endswith('/status'):
            self.send_json(200,{'ok':True,'provider':'openai_agents_api','configured':bool(OPENAI_API_KEY),'model':OPENAI_MODEL,'mode':'bounded_qualification','revision':'ND_AGENTS_API_V0_1'}); return True
        code,obj=openai_agents_probe(); self.send_json(code,obj); return True

    def openai_agents_post(self):
        p=self.path.split('?',1)[0]
        if p!='/nd/openai/agents/session': return False
        if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return True
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n>262144: raise RuntimeError('request_too_large')
            body=json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
            if not isinstance(body,dict): raise RuntimeError('body_must_be_object')
        except Exception as e:
            self.send_json(400,{'ok':False,'error':clean_error(e)}); return True
        code,obj=openai_agents_session_create(body); self.send_json(code,obj); return True

    def do_GET(self):
        if self.notebooklm_bootstrap_get(): return
        if self.openai_agents_get(): return
"""
assert src.count(old)==1
src=src.replace(old,new,1)
old2="""        if self.memos_post(): return
        if self.gemini_github_relay(): return
"""
new2="""        if self.memos_post(): return
        if self.openai_agents_post(): return
        if self.gemini_github_relay(): return
"""
assert src.count(old2)==1
src=src.replace(old2,new2,1)

# Preserve the currently adopted Generation 8.1 Drive startup behavior.
needle='threading.Thread(target=drive_qualify_once,daemon=True).start()'
assert src.count(needle)==1
src=src.replace(needle,'# Drive startup qualification invocation disabled after Generation 8.1 adoption',1)

exec(compile(src,'nd_gateway_openai_agents_qualification_v01.py','exec'))
