import urllib.request, json

print('ND_LINEAR_BRIDGE_WRAPPER_BOOT {"version":"v4-full-drive-qualified"}',flush=True)
U='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/86a36679ede94ac3d24053e81fa543ec61a2ede9/tmp/nd_gateway_browserless_frontproxy_v11_no_memory_plugin.py'
s=urllib.request.urlopen(U,timeout=30).read().decode()

OLD_DRIVE="DRIVE_FRONT_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1bb27fa0c61e24d373cb170c2edea61e5d3f3cbd/tmp/nd_safe_tool_broker_v14_enable_docs_front.js'"
NEW_DRIVE="DRIVE_FRONT_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/bee0a32d8f0b5cbeb5484e6423fe04b04a413c49/tmp/nd_drive_full_user_qstash_v1.mjs'"
if s.count(OLD_DRIVE)!=1:
    raise RuntimeError('drive_front_marker_missing')
s=s.replace(OLD_DRIVE,NEW_DRIVE,1)

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
    fullq = r'''
def drive_full_qualify_once():
    time.sleep(6)
    root='0AOdPxVrJUuLLUk9PVA'
    created=[]
    rec={'ok':False,'stage':'start'}
    def call(tool,args):
        return drive_internal_call(tool,args)
    try:
        stamp=str(int(time.time()))
        folder=call('drive_create_folder',{'name':'ND QSTASH FULL RW QUAL '+stamp,'parent_id':root})
        fid=folder.get('id'); created.append(fid)
        sub=call('drive_create_folder',{'name':'MOVE TARGET','parent_id':fid})
        sid=sub.get('id'); created.append(sid)
        rec['folder_create']=bool(fid and sid)

        raw=call('drive_create_raw_file',{'name':'probe.json','mime_type':'application/json','parent_id':fid,'content_text':'{"v":1}'})
        rid=raw.get('id'); created.append(rid)
        rf=call('fetch',{'id':rid})
        rec['raw_create_read']='{"v":1}' in str((((rf or {}).get('content') or {}).get('content') or ''))
        rm=call('drive_get_metadata',{'file_id':rid})
        rv=str((rm or {}).get('version') or (rm or {}).get('drive_version') or '')
        rep=call('drive_replace_content',{'file_id':rid,'content_text':'{"v":2,"ok":true}','mime_type':'application/json','expected_drive_version':rv})
        rec['raw_replace']=bool((rep or {}).get('after_drive_version'))
        rm2=call('drive_get_metadata',{'file_id':rid})
        rv2=str((rm2 or {}).get('version') or (rm2 or {}).get('drive_version') or '')
        mv=call('drive_update_metadata',{'file_id':rid,'name':'probe-renamed.json','add_parent_id':sid,'remove_parent_id':fid,'expected_drive_version':rv2})
        mf=(mv or {}).get('file') or {}
        rec['rename_move']=(mf.get('name')=='probe-renamed.json' and sid in (mf.get('parents') or []))

        doc=call('drive_create_native_file',{'name':'probe-doc','kind':'document','parent_id':fid})
        did=doc.get('id'); created.append(did)
        d0=call('docs_read',{'document_id':did})
        d1=call('docs_batch_update',{'document_id':did,'expected_revision_id':d0.get('revision_id'),'requests':[{'insertText':{'endOfSegmentLocation':{},'text':'FULL DOC WRITE'}}]})
        d2=call('docs_read',{'document_id':did})
        rec['docs_batch']=('FULL DOC WRITE' in str(d2.get('text') or '') and bool(d1.get('after_revision_id')))

        sh=call('drive_create_native_file',{'name':'probe-sheet','kind':'spreadsheet','parent_id':fid})
        shid=sh.get('id'); created.append(shid)
        call('sheets_update_values',{'spreadsheet_id':shid,'range':'A1:B2','values':[['a','b'],['1','2']]})
        sr=call('sheets_get_values',{'spreadsheet_id':shid,'range':'A1:B2'})
        rec['sheets_values']=((sr or {}).get('values')==[['a','b'],['1','2']])
        call('sheets_batch_update',{'spreadsheet_id':shid,'requests':[{'addSheet':{'properties':{'title':'Extra'}}}]})
        sg=call('sheets_get',{'spreadsheet_id':shid})
        rec['sheets_batch']=('Extra' in [((x.get('properties') or {}).get('title')) for x in ((sg or {}).get('sheets') or [])])

        pr=call('drive_create_native_file',{'name':'probe-slides','kind':'presentation','parent_id':fid})
        pid=pr.get('id'); created.append(pid)
        pg0=call('slides_get',{'presentation_id':pid})
        n0=len((pg0 or {}).get('slides') or [])
        call('slides_batch_update',{'presentation_id':pid,'requests':[{'createSlide':{}}]})
        pg1=call('slides_get',{'presentation_id':pid})
        rec['slides_batch']=(len((pg1 or {}).get('slides') or [])==n0+1)

        children=call('drive_list_children',{'folder_id':fid,'top_n':50})
        rec['list_children']=any(x.get('id')==did for x in ((children or {}).get('results') or []))

        dm=call('drive_get_metadata',{'file_id':did})
        dv=str((dm or {}).get('version') or (dm or {}).get('drive_version') or '')
        tr=call('drive_update_metadata',{'file_id':did,'trashed':True,'expected_drive_version':dv})
        rec['trash']=bool(((tr or {}).get('file') or {}).get('trashed'))
        dm2=call('drive_get_metadata',{'file_id':did})
        dv2=str((dm2 or {}).get('version') or (dm2 or {}).get('drive_version') or '')
        ur=call('drive_update_metadata',{'file_id':did,'trashed':False,'expected_drive_version':dv2})
        rec['untrash']=not bool(((ur or {}).get('file') or {}).get('trashed'))

        stale=False
        try:
            call('drive_replace_content',{'file_id':rid,'content_text':'SHOULD_NOT_WRITE','mime_type':'application/json','expected_drive_version':rv})
        except Exception as e:
            stale=('DRIVE_VERSION_MISMATCH' in str(e) or '409' in str(e))
        rec['stale_drive_version']=stale
        required=['folder_create','raw_create_read','raw_replace','rename_move','docs_batch','sheets_values','sheets_batch','slides_batch','list_children','trash','untrash','stale_drive_version']
        rec['functional_pass']=all(bool(rec.get(k)) for k in required)
    except Exception as e:
        rec['error']=clean_error(e)
    finally:
        cleanup=[]
        for file_id in reversed(created):
            if not file_id: continue
            try:
                call('drive_delete_file',{'file_id':file_id})
                cleanup.append({'id':file_id,'deleted':True})
            except Exception as e:
                cleanup.append({'id':file_id,'deleted':False,'error':clean_error(e)})
        rec['cleanup_pass']=bool(cleanup) and all(x.get('deleted') for x in cleanup)
        rec['ok']=bool(rec.get('functional_pass') and rec.get('cleanup_pass'))
        rec['created_count']=len(created)
        print('ND_DRIVE_FULL_RW_QUALIFICATION '+json.dumps(rec,ensure_ascii=False),flush=True)

threading.Thread(target=drive_full_qualify_once,daemon=True).start()
'''
    s=s.replace(needle,fullq,1)

print('ND_LINEAR_BRIDGE_PATCH_READY '+json.dumps({'endpoint':('/nd/linear/invoke' in s),'status_endpoint':('/nd/linear/status' in s),'credential_env':('ND_LINEAR_API_KEY' in s),'full_drive_child':True}),flush=True)
exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))
