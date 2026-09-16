import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6f405bb76a4b5db745e6c3d5f5e7607813ee7444/tmp/nd_meta_pass2_runtime_patch_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_pass2_runtime_patch_helper_v01.py','exec'),ns)

EXTRA = r"""
META_MUTATION_CACHE={}

def _mutation_guard(key,signature):
    prior=META_MUTATION_CACHE.get(key)
    if prior and prior.get('signature')!=signature:
        return {'ok':False,'error':'mutation_id_payload_mismatch'}
    if prior and prior.get('outcome') in ('CONFIRMED_APPLIED','OUTCOME_UNKNOWN'):
        return {'ok':prior.get('outcome')=='CONFIRMED_APPLIED','retry_blocked':True,'prior':prior}
    return None

def _store_mutation(key,signature,out):
    META_MUTATION_CACHE[key]={'signature':signature,'outcome':out.get('outcome'),'status':out.get('status'),'ts':int(time.time())}

def _require_write(args):
    mid=str(args.get('mutation_id') or '').strip()
    if not mid: return None, {'ok':False,'error':'mutation_id_required'}
    if not bool(args.get('confirm')): return None, {'ok':False,'error':'confirm_required'}
    return mid,None

def _sig(name,args):
    return hashlib.sha256(json.dumps({'name':name,'args':args},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()

def meta_mcp_tools():
    empty={'type':'object','properties':{},'additionalProperties':False}
    return [
      {'name':'meta_status','description':'Read live Meta Business, Facebook Page, Instagram and Ads account status.','inputSchema':empty},
      {'name':'meta_business','description':'Read the configured Meta Business identity.','inputSchema':empty},
      {'name':'meta_page','description':'Read the configured Facebook Page identity.','inputSchema':empty},
      {'name':'meta_instagram','description':'Read the configured Instagram professional account.','inputSchema':empty},
      {'name':'meta_ads','description':'Read the configured Meta ad account identity/status.','inputSchema':empty},
      {'name':'meta_facebook_posts','description':'Facebook Page post CRUD. Writes require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'post_id':{'type':'string'},'message':{'type':'string'},'published':{'type':'boolean'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_instagram_media','description':'Instagram media read/create-container/publish. Public publish requires confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create_container','publish']},'media_id':{'type':'string'},'creation_id':{'type':'string'},'image_url':{'type':'string'},'video_url':{'type':'string'},'caption':{'type':'string'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_comments','description':'Facebook/Instagram comment CRUD. Writes require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'object_id':{'type':'string'},'comment_id':{'type':'string'},'message':{'type':'string'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_insights','description':'Read insights for a supported Meta object.','inputSchema':{'type':'object','properties':{'object_id':{'type':'string'},'metric':{'type':'string'},'period':{'type':'string'},'since':{'type':'string'},'until':{'type':'string'}},'required':['object_id'],'additionalProperties':False}},
      {'name':'meta_ads_campaigns','description':'Marketing API campaign list/get/create/update/delete. Campaign creation defaults PAUSED and writes require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'campaign_id':{'type':'string'},'name':{'type':'string'},'objective':{'type':'string'},'status':{'type':'string'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_safe_qualification','description':'Run bounded reversible write qualification: unpublished Facebook post, non-published Instagram container, PAUSED ad campaign; no public post and no spend.','inputSchema':{'type':'object','properties':{'qualification_rev':{'type':'string'},'confirm':{'type':'boolean'}},'required':['qualification_rev','confirm'],'additionalProperties':False}},
    ]

def meta_mcp_call(name,args):
    if name=='meta_status': return _meta.read_probes()
    key={'meta_business':'business','meta_page':'page','meta_instagram':'instagram','meta_ads':'ads'}.get(name)
    if key:
        reads=_meta.read_probes(); p=((reads.get('probes') or {}).get(key) or {})
        return {'ok':bool(p.get('ok')),'provider':'meta','route':'direct_mcp','probe':p}

    if name=='meta_facebook_posts':
        op=str(args.get('operation') or '')
        if op=='list': return _meta._graph(_meta.PAGE_ID+'/feed','GET',{'fields':'id,message,created_time,is_published','limit':'100'})
        if op=='get': return _meta._read(str(args.get('post_id') or ''),'id,message,created_time,permalink_url,is_published')
        mid,err=_require_write(args)
        if err: return err
        sig=_sig(name,args); prior=_mutation_guard(mid,sig)
        if prior: return prior
        if op=='create':
            out=_meta._graph(_meta.PAGE_ID+'/feed','POST',{'message':str(args.get('message') or ''),'published':'true' if bool(args.get('published')) else 'false'})
        elif op=='update':
            out=_meta._graph(str(args.get('post_id') or ''),'POST',{'message':str(args.get('message') or '')})
        elif op=='delete':
            out=_meta._graph(str(args.get('post_id') or ''),'DELETE',{})
        else: return {'ok':False,'error':'unsupported_operation'}
        _store_mutation(mid,sig,out)
        return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

    if name=='meta_instagram_media':
        op=str(args.get('operation') or '')
        if op=='list': return _meta._graph(_meta.IG_ID+'/media','GET',{'fields':'id,caption,media_type,permalink,timestamp','limit':'100'})
        if op=='get': return _meta._read(str(args.get('media_id') or ''),'id,caption,media_type,permalink,timestamp,status_code')
        mid,err=_require_write(args)
        if err: return err
        sig=_sig(name,args); prior=_mutation_guard(mid,sig)
        if prior: return prior
        if op=='create_container':
            p={}
            if args.get('image_url'): p['image_url']=args.get('image_url')
            if args.get('video_url'): p['video_url']=args.get('video_url')
            if args.get('caption') is not None: p['caption']=args.get('caption')
            out=_meta._graph(_meta.IG_ID+'/media','POST',p)
        elif op=='publish':
            out=_meta._graph(_meta.IG_ID+'/media_publish','POST',{'creation_id':str(args.get('creation_id') or '')})
        else: return {'ok':False,'error':'unsupported_operation'}
        _store_mutation(mid,sig,out)
        return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

    if name=='meta_comments':
        op=str(args.get('operation') or '')
        oid=str(args.get('object_id') or ''); cid=str(args.get('comment_id') or '')
        if op=='list': return _meta._graph(oid+'/comments','GET',{'fields':'id,message,from,created_time','limit':'100'})
        if op=='get': return _meta._read(cid,'id,message,from,created_time')
        mid,err=_require_write(args)
        if err: return err
        sig=_sig(name,args); prior=_mutation_guard(mid,sig)
        if prior: return prior
        if op=='create': out=_meta._graph(oid+'/comments','POST',{'message':str(args.get('message') or '')})
        elif op=='update': out=_meta._graph(cid,'POST',{'message':str(args.get('message') or '')})
        elif op=='delete': out=_meta._graph(cid,'DELETE',{})
        else: return {'ok':False,'error':'unsupported_operation'}
        _store_mutation(mid,sig,out)
        return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

    if name=='meta_insights':
        p={'metric':str(args.get('metric') or '')}
        for k in ('period','since','until'):
            if args.get(k): p[k]=args.get(k)
        return _meta._graph(str(args.get('object_id') or '')+'/insights','GET',p)

    if name=='meta_ads_campaigns':
        op=str(args.get('operation') or '')
        cid=str(args.get('campaign_id') or '')
        if op=='list': return _meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','GET',{'fields':'id,name,status,effective_status,objective','limit':'100'})
        if op=='get': return _meta._read(cid,'id,name,status,effective_status,objective,special_ad_categories')
        mid,err=_require_write(args)
        if err: return err
        sig=_sig(name,args); prior=_mutation_guard(mid,sig)
        if prior: return prior
        if op=='create':
            out=_meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','POST',{'name':str(args.get('name') or 'ND Meta campaign'),'objective':str(args.get('objective') or 'OUTCOME_TRAFFIC'),'status':str(args.get('status') or 'PAUSED'),'special_ad_categories':json.dumps([])})
        elif op=='update':
            p={}
            if args.get('name') is not None: p['name']=args.get('name')
            if args.get('status') is not None: p['status']=args.get('status')
            out=_meta._graph(cid,'POST',p)
        elif op=='delete': out=_meta._graph(cid,'DELETE',{})
        else: return {'ok':False,'error':'unsupported_operation'}
        _store_mutation(mid,sig,out)
        return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

    if name=='meta_safe_qualification':
        if not bool(args.get('confirm')): return {'ok':False,'error':'confirm_required'}
        return _meta.qualify_all(str(args.get('qualification_rev') or ''))

    raise RuntimeError('unknown_meta_mcp_tool')
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+EXTRA
ns['MCP_METHOD']=ns['MCP_METHOD'].replace("Nameless Dhamma Meta read MCP.","Nameless Dhamma guarded Meta SMM read/write MCP.")
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1: raise RuntimeError('runtime exec marker not found exactly once')
    lines=[
      "runtime_anchor='class H(BaseHTTPRequestHandler):\\n'",
      "if s.count(runtime_anchor)!=1: raise RuntimeError('full helper class anchor mismatch')",
      "runtime_globals="+repr(RUNTIME_GLOBALS),
      "s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)",
      "post_anchor=\"    def do_POST(self):\\n        p=self.path.split('?',1)[0]\\n\"",
      "if s.count(post_anchor)!=1: raise RuntimeError('full helper do_POST anchor mismatch')",
      "mcp_method="+repr(MCP_METHOD),
      "s=s.replace(post_anchor,mcp_method,1)",
      "server_anchor=\"ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()\"",
      "if s.count(server_anchor)!=1: raise RuntimeError('full helper server anchor mismatch')",
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_TYPED_RW_MCP_READY '+json.dumps({'tools':11,'browser':False},ensure_ascii=False),flush=True)",
      runtime_exec,
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
