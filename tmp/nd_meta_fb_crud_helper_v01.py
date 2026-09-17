import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6f405bb76a4b5db745e6c3d5f5e7607813ee7444/tmp/nd_meta_pass2_runtime_patch_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_pass2_runtime_patch_helper_v01.py','exec'),ns)

FB_EXT = r"""
META_FB_MUTATIONS={}
META_FB_QUALIFY_TRIGGER=os.environ.get('ND_META_FB_WRITE_QUALIFY_REV','').strip()

def _fb_token():
    tok,state=_meta._page_token()
    return tok,state

def _fb_guarded_mutation(path,method,params,args,readback_fields=''):
    mid=str(args.get('mutation_id') or '').strip()
    if not bool(args.get('confirm')): return {'ok':False,'error':'confirm_required'}
    if not mid: return {'ok':False,'error':'mutation_id_required'}
    sig=json.dumps({'path':path,'method':method,'params':params},sort_keys=True,separators=(',',':'),ensure_ascii=False)
    old=META_FB_MUTATIONS.get(mid)
    if old:
        if old.get('signature')!=sig: return {'ok':False,'error':'mutation_id_payload_mismatch','mutation_id':mid}
        return {'ok':old.get('outcome')=='CONFIRMED_APPLIED','mutation_id':mid,'retry_blocked':True,'prior':old}
    token,state=_fb_token()
    if not token: return {'ok':False,'error':'page_access_token_unavailable','detail':state}
    out=_meta._graph(path,method,params,token=token)
    META_FB_MUTATIONS[mid]={'signature':sig,'outcome':out.get('outcome'),'status':out.get('status'),'ts':int(time.time())}
    rb=None
    if readback_fields and out.get('ok'):
        rb=_meta._read(path,readback_fields,token=token)
    return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'readback':rb,'outcome':out.get('outcome'),'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

def _fb_post_tool(args):
    op=str(args.get('operation') or '').lower()
    token,state=_fb_token()
    if not token: return {'ok':False,'error':'page_access_token_unavailable','detail':state}
    if op=='list':
        return _meta._graph(_meta.PAGE_ID+'/promotable_posts','GET',{'fields':'id,message,is_published,created_time','limit':str(args.get('limit') or 25)},token=token)
    pid=str(args.get('post_id') or '').strip()
    if op=='get':
        return _meta._read(pid,'id,message,created_time,is_published',token=token)
    if op=='create':
        p={'message':str(args.get('message') or ''),'published':'true' if bool(args.get('published')) else 'false'}
        return _fb_guarded_mutation(_meta.PAGE_ID+'/feed','POST',p,args)
    if op=='update':
        return _fb_guarded_mutation(pid,'POST',{'message':str(args.get('message') or '')},args,'id,message,created_time')
    if op=='delete':
        return _fb_guarded_mutation(pid,'DELETE',{},args)
    return {'ok':False,'error':'unsupported_operation'}

def _fb_comment_tool(args):
    op=str(args.get('operation') or '').lower()
    token,state=_fb_token()
    if not token: return {'ok':False,'error':'page_access_token_unavailable','detail':state}
    oid=str(args.get('object_id') or '').strip()
    cid=str(args.get('comment_id') or '').strip()
    if op=='list':
        return _meta._graph(oid+'/comments','GET',{'fields':'id,message,created_time','limit':str(args.get('limit') or 25)},token=token)
    if op=='get':
        return _meta._read(cid,'id,message,created_time',token=token)
    if op=='create':
        return _fb_guarded_mutation(oid+'/comments','POST',{'message':str(args.get('message') or '')},args)
    if op=='update':
        return _fb_guarded_mutation(cid,'POST',{'message':str(args.get('message') or '')},args,'id,message,created_time')
    if op=='delete':
        return _fb_guarded_mutation(cid,'DELETE',{},args)
    return {'ok':False,'error':'unsupported_operation'}

def _fb_full_qualification(rev):
    marker='ND_META_FB_FULL_'+_meta._tag(rev)
    token,state=_fb_token()
    if not token: return {'ok':False,'stage':'page_token','detail':state}
    cr=_meta._graph(_meta.PAGE_ID+'/feed','POST',{'message':marker+' create','published':'false'},token=token)
    if not cr.get('ok'): return {'ok':False,'stage':'post_create','detail':cr}
    pid=str(((cr.get('data') or {}).get('id')) or '')
    r1=_meta._read(pid,'id,message,created_time',token=token)
    ed=_meta._graph(pid,'POST',{'message':marker+' edited'},token=token)
    r2=_meta._read(pid,'id,message,created_time',token=token)
    cid=''
    cc=_meta._graph(pid+'/comments','POST',{'message':marker+' comment'},token=token)
    if cc.get('ok'): cid=str(((cc.get('data') or {}).get('id')) or '')
    cr1=_meta._read(cid,'id,message,created_time',token=token) if cid else {'ok':False,'error':'missing_comment_id'}
    ce=_meta._graph(cid,'POST',{'message':marker+' comment edited'},token=token) if cid else {'ok':False}
    cr2=_meta._read(cid,'id,message,created_time',token=token) if cid else {'ok':False}
    cd=_meta._graph(cid,'DELETE',{},token=token) if cid else {'ok':False}
    cabs,_=_meta._confirm_absent(cid,token=token) if cid else (False,{})
    pd=_meta._graph(pid,'DELETE',{},token=token)
    pabs,_=_meta._confirm_absent(pid,token=token)
    ok=bool(r1.get('ok') and ed.get('ok') and r2.get('ok') and cc.get('ok') and cr1.get('ok') and ce.get('ok') and cr2.get('ok') and cabs and pd.get('ok') and pabs)
    return {'ok':ok,'post_id':pid,'post_create':cr,'post_read_create':r1,'post_edit':ed,'post_read_edit':r2,'comment_id':cid,'comment_create':cc,'comment_read_create':cr1,'comment_edit':ce,'comment_read_edit':cr2,'comment_delete':cd,'comment_deleted_confirmed':cabs,'post_delete':pd,'post_deleted_confirmed':pabs,'public_post_created':False}

def meta_mcp_tools():
    return [
      {'name':'meta_status','description':'Read live Meta Business, Facebook Page, Instagram and Ads account status.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_business','description':'Read the configured Meta Business identity.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_page','description':'Read the configured Facebook Page identity.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_instagram','description':'Read the configured Instagram professional account.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_ads','description':'Read the configured Meta ad account identity/status.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_facebook_posts','description':'Facebook Page post CRUD. create defaults to unpublished unless published=true. Mutations require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'post_id':{'type':'string'},'message':{'type':'string'},'published':{'type':'boolean'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_facebook_comments','description':'Facebook Page comment CRUD. Mutations require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'object_id':{'type':'string'},'comment_id':{'type':'string'},'message':{'type':'string'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
    ]

def meta_mcp_call(name,args):
    if name=='meta_status': return _meta.read_probes()
    key={'meta_business':'business','meta_page':'page','meta_instagram':'instagram','meta_ads':'ads'}.get(name)
    if key:
        reads=_meta.read_probes(); probe=((reads.get('probes') or {}).get(key) or {})
        return {'ok':bool(probe.get('ok')),'provider':'meta','route':'direct_mcp','graph_version':getattr(_meta,'GRAPH_VERSION','unknown'),'probe':probe}
    if name=='meta_facebook_posts': return _fb_post_tool(args)
    if name=='meta_facebook_comments': return _fb_comment_tool(args)
    raise RuntimeError('unknown_meta_mcp_tool')

def meta_fb_qualify_once():
    if not META_FB_QUALIFY_TRIGGER: return
    time.sleep(9)
    try:
        out=_fb_full_qualification(META_FB_QUALIFY_TRIGGER)
        print('ND_META_FB_FULL_QUALIFY '+json.dumps(out,ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_META_FB_FULL_QUALIFY '+json.dumps({'ok':False,'error':str(e)[:700]},ensure_ascii=False),flush=True)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+FB_EXT
ns['MCP_METHOD']=ns['MCP_METHOD'].replace("Nameless Dhamma Meta read MCP.","Nameless Dhamma Meta MCP with guarded Facebook Page and comment CRUD.")
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1: raise RuntimeError('runtime exec marker not found exactly once')
    lines=[
      "runtime_anchor='class H(BaseHTTPRequestHandler):\\n'",
      "if s.count(runtime_anchor)!=1: raise RuntimeError('fb helper class anchor mismatch')",
      "runtime_globals="+repr(RUNTIME_GLOBALS),
      "s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)",
      "post_anchor=\"    def do_POST(self):\\n        p=self.path.split('?',1)[0]\\n\"",
      "if s.count(post_anchor)!=1: raise RuntimeError('fb helper do_POST anchor mismatch')",
      "mcp_method="+repr(MCP_METHOD),
      "s=s.replace(post_anchor,mcp_method,1)",
      "server_anchor=\"ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()\"",
      "if s.count(server_anchor)!=1: raise RuntimeError('fb helper server anchor mismatch')",
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\nthreading.Thread(target=meta_fb_qualify_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_FB_CRUD_HELPER_READY '+json.dumps({'direct_mcp':True,'tools':7,'facebook_crud':True,'browser':False},ensure_ascii=False),flush=True)",
      runtime_exec,
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
# checkpoint-pin: meta-fb-crud-v1
