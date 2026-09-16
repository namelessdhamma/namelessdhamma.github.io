import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

final_outer_exec="exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))"
if outer.count(final_outer_exec)!=1:
    raise RuntimeError('pass2 v2 outer final exec marker not found exactly once')

stage=r'''
runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
if src.count(runtime_exec)!=1:
    raise RuntimeError('pass2 v2 runtime exec marker not found exactly once')

inject=r"""
# ---- ND Meta pass-2 v2 Direct MCP + GitHub bootstrap patch ----
runtime_anchor="class H(BaseHTTPRequestHandler):\n"
if s.count(runtime_anchor)!=1:
    raise RuntimeError('pass2 v2 class anchor not found exactly once')

runtime_globals=r'''
META_MCP_PATH_TOKEN=os.environ.get('ND_META_MCP_PATH_TOKEN','').strip()
META_GITHUB_BOOTSTRAP_TRIGGER=os.environ.get('ND_META_GITHUB_BOOTSTRAP_REV','').strip()
META_GITHUB_BOOTSTRAP_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/7afdc1b8880aba2b411b71de2d661c057fc9d107/tmp/nd_meta_github_secret_bootstrap_v01.py'

def meta_mcp_tools():
    return [
      {'name':'meta_status','description':'Read live Meta Business, Facebook Page, Instagram and Ads account status through the ND Meta credential.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_business','description':'Read the configured ND Meta Business identity.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_page','description':'Read the configured Nameless Dhamma Facebook Page identity.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_instagram','description':'Read the configured Nameless Dhamma Instagram professional account identity.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_ads','description':'Read the configured ND Meta business ad account identity and status.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
    ]

def meta_mcp_call(name,args):
    reads=_meta.read_probes()
    if name=='meta_status':
        return reads
    key={'meta_business':'business','meta_page':'page','meta_instagram':'instagram','meta_ads':'ads'}.get(name)
    if not key:
        raise RuntimeError('unknown_meta_mcp_tool')
    probe=((reads.get('probes') or {}).get(key) or {})
    return {'ok':bool(probe.get('ok')),'provider':'meta','route':'direct_mcp','graph_version':getattr(_meta,'GRAPH_VERSION','unknown'),'probe':probe}

def meta_github_bootstrap_once():
    if not META_GITHUB_BOOTSTRAP_TRIGGER:
        return
    time.sleep(5)
    try:
        path='/tmp/nd_meta_github_secret_bootstrap_v01.py'
        urllib.request.urlretrieve(META_GITHUB_BOOTSTRAP_URL,path)
        env=dict(os.environ)
        env['ND_META_GITHUB_TARGET_REPO']='namelessdhamma/nameless-dhamma-vault'
        p=subprocess.run([sys.executable,'-u',path],env=env,capture_output=True,text=True,timeout=180)
        line=''
        for x in (p.stdout or '').splitlines():
            if x.startswith('ND_META_GITHUB_SECRET_BOOTSTRAP '):
                line=x
        if p.returncode==0 and line:
            print(line,flush=True)
        else:
            print('ND_META_GITHUB_SECRET_BOOTSTRAP '+json.dumps({'ok':False,'returncode':p.returncode,'error':'bootstrap_failed_without_secret_output'},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_META_GITHUB_SECRET_BOOTSTRAP '+json.dumps({'ok':False,'error':str(e)[:500]},ensure_ascii=False),flush=True)

def _meta_mcp_post_local(payload):
    url='http://127.0.0.1:%d/nd/meta/mcp/%s'%(PORT,urllib.parse.quote(META_MCP_PATH_TOKEN,safe=''))
    req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json','Accept':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.status,json.loads(r.read().decode('utf-8','replace') or '{}')

def meta_mcp_selftest_once():
    if not META_MCP_PATH_TOKEN:
        print('ND_META_MCP_SELFTEST '+json.dumps({'ok':False,'reason':'path_token_missing'}),flush=True)
        return
    time.sleep(8)
    try:
        c1,h=_meta_mcp_post_local({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'ND Meta Selftest','version':'1.0'}}})
        c2,t=_meta_mcp_post_local({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        c3,sr=_meta_mcp_post_local({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'meta_status','arguments':{}}})
        tools=(((t.get('result') or {}).get('tools')) or [])
        structured=((sr.get('result') or {}).get('structuredContent') or {})
        ok=bool(c1==200 and c2==200 and c3==200 and len(tools)>=5 and structured.get('ok'))
        print('ND_META_MCP_SELFTEST '+json.dumps({'ok':ok,'initialize_status':c1,'tools_status':c2,'call_status':c3,'tools_count':len(tools),'meta_reads_ok':bool(structured.get('ok'))},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_META_MCP_SELFTEST '+json.dumps({'ok':False,'error':str(e)[:500]},ensure_ascii=False),flush=True)
'''
s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)

post_anchor="    def do_POST(self):\n        p=self.path.split('?',1)[0]\n"
if s.count(post_anchor)!=1:
    raise RuntimeError('pass2 v2 do_POST anchor not found exactly once')

mcp_method=r'''    def meta_mcp(self):
        p=self.path.split('?',1)[0]
        expected=('/nd/meta/mcp/'+META_MCP_PATH_TOKEN) if META_MCP_PATH_TOKEN else ''
        if not expected or p!=expected:
            return False
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576:
                raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict):
                raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':str(e)[:300]},'id':None}); return True
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized':
            self.send_response(204); self.end_headers(); return True
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'nd-meta-direct-mcp','version':'1.0.0'},'instructions':'Nameless Dhamma Meta read MCP. Meta credentials remain server-side; output is redacted JSON.'}}); return True
        if method=='ping':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return True
        if method=='tools/list':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':meta_mcp_tools()}}); return True
        if method=='tools/call':
            q=msg.get('params') or {}
            try:
                out=meta_mcp_call(str(q.get('name') or ''),q.get('arguments') or {}); err=not bool(out.get('ok'))
            except Exception as e:
                out={'ok':False,'error':str(e)[:500]}; err=True
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(out,ensure_ascii=False)}],'structuredContent':out,'isError':err}}); return True
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}}); return True

    def do_POST(self):
        p=self.path.split('?',1)[0]
        if self.meta_mcp(): return
'''
s=s.replace(post_anchor,mcp_method,1)

server_anchor="ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
if s.count(server_anchor)!=1:
    raise RuntimeError('pass2 v2 server anchor not found exactly once')
s=s.replace(server_anchor,"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\n"+server_anchor,1)

print('ND_META_PASS2_PATCH_V2_READY '+json.dumps({'direct_mcp':True,'github_bootstrap':bool(os.environ.get('ND_META_GITHUB_BOOTSTRAP_REV','').strip()),'browser':False},ensure_ascii=False),flush=True)
exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))
"""
src=src.replace(runtime_exec,inject,1)
print('ND_META_PASS2_STAGE_V2_READY',flush=True)
exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))
'''
outer=outer.replace(final_outer_exec,stage,1)
print('ND_META_PASS2_OUTER_V2_READY',flush=True)
exec(compile(outer,'nd_meta_pass2_inner_wrapper_v02_outer.py','exec'))
