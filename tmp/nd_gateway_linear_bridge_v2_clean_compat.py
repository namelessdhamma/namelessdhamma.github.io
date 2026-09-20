import urllib.request, json

print('ND_LINEAR_BRIDGE_WRAPPER_BOOT {"version":"v2-clean-compat"}',flush=True)
U='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/86a36679ede94ac3d24053e81fa543ec61a2ede9/tmp/nd_gateway_browserless_frontproxy_v11_no_memory_plugin.py'
s=urllib.request.urlopen(U,timeout=30).read().decode()

a="OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()\n"
b=a+"LINEAR_API_KEY=os.environ.get('ND_LINEAR_API_KEY','').strip()\nLINEAR_MCP_URL='https://mcp.linear.app/mcp'\nLINEAR_QUALIFICATION_STATE={'configured':bool(LINEAR_API_KEY),'ok':False,'stage':'not_run'}\n"
assert s.count(a)==1
s=s.replace(a,b,1)

anchor='def browserless_profiles():\n'
code=r'''
def linear_post(payload,sid=None,timeout=45):
    if not LINEAR_API_KEY: raise RuntimeError('linear_not_configured')
    h={'Authorization':'Bearer '+LINEAR_API_KEY,'Content-Type':'application/json','Accept':'application/json, text/event-stream','User-Agent':'ND-Railway-Linear/1.2'}
    if sid:
        h['Mcp-Session-Id']=sid
        h['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request(LINEAR_MCP_URL,data=json.dumps(payload).encode(),method='POST',headers=h)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            vals=[]
            for line in raw.splitlines():
                if line.startswith('data: '):
                    try: vals.append(json.loads(line[6:]))
                    except Exception: pass
            try: obj=vals[-1] if vals else (json.loads(raw) if raw else {})
            except Exception: obj={'raw':raw[:4000]}
            return r.status,r.headers.get('Mcp-Session-Id'),obj
    except HTTPError as e:
        body=e.read().decode('utf-8','replace')
        if LINEAR_API_KEY: body=body.replace(LINEAR_API_KEY,'[REDACTED]')
        raise RuntimeError('Linear MCP HTTP %s: %s' % (e.code,body[:1000]))

def linear_call(op,tool='',args=None):
    c,sid,hello=linear_post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'ND Railway Linear','version':'1.2'}}})
    if c!=200: raise RuntimeError('linear_initialize_failed')
    linear_post({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},sid)
    if op=='tools_list':
        p={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}
    elif op=='tool_call':
        if not tool or not isinstance(args or {},dict): return 400,{'ok':False,'error':'tool_call_requires_tool'}
        p={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':tool,'arguments':args or {}}}
    else:
        return 400,{'ok':False,'error':'bad_linear_operation'}
    c,_,resp=linear_post(p,sid)
    return 200,{'ok':c==200,'provider':'linear','transport':'railway_to_official_linear_mcp','serverInfo':((hello.get('result') or {}).get('serverInfo') or {}),'operation':op,'response':resp}

def linear_qualify_sync():
    global LINEAR_QUALIFICATION_STATE
    st={'configured':bool(LINEAR_API_KEY),'ok':False,'stage':'start'}
    try:
        st['stage']='tools_list'
        c1,o1=linear_call('tools_list')
        tools=((((o1.get('response') or {}).get('result') or {}).get('tools')) or [])
        st['tools_count']=len(tools)
        st['stage']='get_workspace'
        c2,o2=linear_call('tool_call','get_workspace',{})
        content=((((o2.get('response') or {}).get('result') or {}).get('content')) or [])
        st['workspace_read']=bool(content)
        st['serverInfo']=o2.get('serverInfo') or o1.get('serverInfo') or {}
        st['ok']=bool(c1==200 and c2==200 and o1.get('ok') and o2.get('ok') and tools and content)
        st['stage']='complete' if st['ok'] else 'semantic_check_failed'
    except Exception as e:
        z=str(e)
        if LINEAR_API_KEY: z=z.replace(LINEAR_API_KEY,'[REDACTED]')
        st['error']=z[:800]
        st['stage']='error'
    LINEAR_QUALIFICATION_STATE=st
    print('ND_LINEAR_RAILWAY_QUALIFICATION '+json.dumps(st,ensure_ascii=False),flush=True)

linear_qualify_sync()

'''
assert s.count(anchor)==1
s=s.replace(anchor,code+anchor,1)

get_anchor="    def do_GET(self):\n        if self.notebooklm_bootstrap_get(): return\n"
get_inject="    def do_GET(self):\n        if self.path.split('?',1)[0]=='/nd/linear/status':\n            self.send_json(200,LINEAR_QUALIFICATION_STATE); return\n        if self.notebooklm_bootstrap_get(): return\n"
assert s.count(get_anchor)==1
s=s.replace(get_anchor,get_inject,1)

post_anchor="        if p.startswith('/drive/'):\n            self.drive_forward(); return\n"
post_inject=post_anchor+"""        if p=='/nd/linear/invoke':\n            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return\n            try:\n                n=int(self.headers.get('Content-Length','0') or 0); q=json.loads(self.rfile.read(n).decode() or '{}')\n                c,o=linear_call(str(q.get('operation') or ''),str(q.get('tool') or ''),q.get('arguments') or {})\n                self.send_json(c,o); return\n            except Exception as e:\n                z=str(e)\n                if LINEAR_API_KEY: z=z.replace(LINEAR_API_KEY,'[REDACTED]')\n                self.send_json(502,{'ok':False,'provider':'linear','error':z[:800]}); return\n"""
assert s.count(post_anchor)==1
s=s.replace(post_anchor,post_inject,1)

needle="threading.Thread(target=drive_qualify_once,daemon=True).start()"
if s.count(needle)==1:
    s=s.replace(needle,"# Drive startup qualification invocation disabled after current protocol adoption",1)

print('ND_LINEAR_BRIDGE_PATCH_READY '+json.dumps({'endpoint':('/nd/linear/invoke' in s),'status_endpoint':('/nd/linear/status' in s),'credential_env':('ND_LINEAR_API_KEY' in s)}),flush=True)
exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))
