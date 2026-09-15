import urllib.request

U='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/61bc11a0025e0c4b32dc555d9248ff87261dd7f8/tmp/nd_gateway_browserless_frontproxy_v10_memos_kernel_bootstrap.py'
s=urllib.request.urlopen(U,timeout=30).read().decode()

a="OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free').strip()\n"
b=a+"LINEAR_API_KEY=os.environ.get('ND_LINEAR_API_KEY','').strip()\nLINEAR_MCP_URL='https://mcp.linear.app/mcp'\n"
assert s.count(a)==1
s=s.replace(a,b,1)

anchor='def memos_http(path,payload):\n'
code=r'''
def linear_post(payload,sid=None):
    if not LINEAR_API_KEY: raise RuntimeError('linear_not_configured')
    h={'Authorization':'Bearer '+LINEAR_API_KEY,'Content-Type':'application/json','Accept':'application/json, text/event-stream','User-Agent':'ND-Railway-Linear/1.0'}
    if sid:
        h['Mcp-Session-Id']=sid; h['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request(LINEAR_MCP_URL,data=json.dumps(payload).encode(),method='POST',headers=h)
    try:
        with urllib.request.urlopen(req,timeout=120) as r:
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
    try:
        c,sid,hello=linear_post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'ND Railway Linear','version':'1.0'}}})
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
    except Exception as e:
        z=str(e)
        if LINEAR_API_KEY: z=z.replace(LINEAR_API_KEY,'[REDACTED]')
        return 502,{'ok':False,'provider':'linear','transport':'railway_to_official_linear_mcp','error':z[:1200]}

'''
assert s.count(anchor)==1
s=s.replace(anchor,code+anchor,1)

a2="        if p.startswith('/drive/'):\n            self.drive_forward(); return\n"
b2=a2+"""        if p=='/nd/linear/invoke':\n            if not auth_ok(self.headers): self.send_json(403,{'ok':False,'error':'forbidden'}); return\n            try:\n                n=int(self.headers.get('Content-Length','0') or 0); q=json.loads(self.rfile.read(n).decode() or '{}')\n                c,o=linear_call(str(q.get('operation') or ''),str(q.get('tool') or ''),q.get('arguments') or {})\n                self.send_json(c,o); return\n            except Exception as e:\n                self.send_json(400,{'ok':False,'provider':'linear','error':str(e)[:800]}); return\n"""
assert s.count(a2)==1
s=s.replace(a2,b2,1)
exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))

