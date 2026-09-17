import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/bd211fd66784d31a4a5c3d07044465dcd3756d87/tmp/nd_meta_vk_multiplex_front_v02.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

anchor="VK_ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}\n"
inject=anchor+"QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\nGEMINI_INTROSPECT_URL='https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-gemini-mcp/introspect'\n"
if src.count(anchor)!=1:
    raise RuntimeError('gemini drive mcp env anchor mismatch')
src=src.replace(anchor,inject,1)

method_anchor="    def forward(self):\n"
methods=r'''    def gemini_token_active(self):
        auth=self.headers.get('Authorization','')
        if not auth.startswith('Bearer '): return False
        try:
            req=urllib.request.Request(GEMINI_INTROSPECT_URL,headers={'Authorization':auth,'Accept':'application/json','User-Agent':'ND-Gemini-Drive-MCP/1.0'},method='GET')
            with urllib.request.urlopen(req,timeout=20) as r:
                obj=json.loads(r.read().decode('utf-8','replace') or '{}')
            return bool(obj.get('active'))
        except Exception:
            return False

    def gemini_drive_tool(self,tool,args):
        if tool not in ('nd_authority','google_drive_search'):
            raise RuntimeError('tool_denied')
        if not QSTASH_TOKEN:
            raise RuntimeError('internal_broker_auth_unconfigured')
        query=str((args or {}).get('query') or '').strip()[:9000]
        if not query: raise RuntimeError('query_required')
        raw=json.dumps({'tool':tool,'query':query},ensure_ascii=False).encode('utf-8')
        req=urllib.request.Request(
            META+'/invoke',data=raw,method='POST',
            headers={
                'Authorization':'Bearer '+QSTASH_TOKEN,
                'Content-Type':'application/json',
                'Accept':'application/json',
                'User-Agent':'ND-Gemini-Drive-MCP/1.0'
            })
        with urllib.request.urlopen(req,timeout=120) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
        if not isinstance(obj,dict) or 'result' not in obj:
            raise RuntimeError('invalid_internal_broker_response')
        return {'ok':True,'provider':'google_drive','transport':'gemini_mcp_to_existing_railway_drive_broker','tool':tool,'result':obj.get('result'),'mutations':False}

    def gemini_drive_mcp(self):
        if not self.gemini_token_active():
            self.send_json(401,{'jsonrpc':'2.0','error':{'code':-32001,'message':'Unauthorized'},'id':None}); return
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':clean(e)},'id':None}); return
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized': self.send_response(204); self.end_headers(); return
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':str(((msg.get('params') or {}).get('protocolVersion')) or '2025-06-18'),'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'nd-gemini-drive-mcp','version':'1.0.0'},'instructions':'Private read-only MCP over the existing ND Google Drive authority/search broker. No writes or mutations.'}}); return
        if method=='ping': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return
        if method=='tools/list':
            tools=[
              {'name':'nd_authority','description':'Retrieve current authoritative/canonical ND context from Google Drive StateHead, Registry, durable memory and relevant canonical components.','inputSchema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':9000}},'required':['query'],'additionalProperties':False}},
              {'name':'google_drive_search','description':'Search live Google Drive project files and read relevant text content. Read-only.','inputSchema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':9000}},'required':['query'],'additionalProperties':False}}
            ]
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':tools}}); return
        if method=='tools/call':
            p=msg.get('params') or {}; name=str(p.get('name') or ''); args=p.get('arguments') or {}
            try:
                out=self.gemini_drive_tool(name,args); err=False
            except Exception as e:
                out={'ok':False,'error':clean(e)}; err=True
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(out,ensure_ascii=False)}],'structuredContent':out,'isError':err}}); return
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})

'''
if src.count(method_anchor)!=1:
    raise RuntimeError('gemini drive mcp method anchor mismatch')
src=src.replace(method_anchor,methods+method_anchor,1)

old_post="    def do_POST(self):\n        if self.is_vk_mcp(): self.vk_mcp(); return\n        self.forward()\n"
new_post="    def do_POST(self):\n        if self.path.split('?',1)[0]=='/gemini/drive/mcp': self.gemini_drive_mcp(); return\n        if self.is_vk_mcp(): self.vk_mcp(); return\n        self.forward()\n"
if src.count(old_post)!=1:
    raise RuntimeError('gemini drive mcp POST anchor mismatch')
src=src.replace(old_post,new_post,1)

health_anchor="        if path=='/vk/health':\n"
health_inject="        if path=='/gemini/drive/health':\n            self.send_json(200,{'ok':True,'service':'nd-gemini-drive-mcp','mode':'PRIVATE_READ_ONLY','tools':['nd_authority','google_drive_search'],'auth':'nd-gemini-mcp bearer introspection','mcp':'/gemini/drive/mcp'}); return\n"+health_anchor
if src.count(health_anchor)!=1:
    raise RuntimeError('gemini drive mcp health anchor mismatch')
src=src.replace(health_anchor,health_inject,1)

print('ND_GEMINI_DRIVE_MCP_V04_READY '+json.dumps({'endpoint':'/gemini/drive/mcp','health':'/gemini/drive/health','read_only':True,'auth':'gemini_bearer_introspection'}),flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v04_gemini_drive_mcp_runtime.py','exec'))
