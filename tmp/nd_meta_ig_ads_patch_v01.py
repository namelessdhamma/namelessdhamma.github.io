import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/76ac61a8d25aeb4dc789e50e2343fbc100a36152/tmp/nd_meta_fb_crud_patch_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_fb_crud_patch_v01.py','exec'),ns)

EXTRA = r"""
_META_IG_MUTATIONS={}
_META_AD_MUTATIONS={}

def _guard_mutation(args):
    mid=str(args.get('mutation_id') or '').strip()
    if not mid: return None,{'ok':False,'error':'mutation_id_required'}
    if not bool(args.get('confirm')): return None,{'ok':False,'error':'confirm_required'}
    return mid,None

def _ig_token():
    tok,state=_meta._page_token()
    if not tok: raise RuntimeError(str(state))
    return tok

def _ig_media_tool(args):
    op=str(args.get('operation') or '').strip().lower()
    tok=_ig_token()
    if op=='list':
        return _meta._graph(_meta.IG_ID+'/media','GET',{'fields':'id,caption,media_type,media_url,permalink,timestamp','limit':str(args.get('limit') or 50)},token=tok)
    if op=='get':
        mid=str(args.get('media_id') or '').strip()
        if not mid: return {'ok':False,'error':'media_id_required'}
        return _meta._read(mid,'id,caption,media_type,media_url,permalink,timestamp,status_code,status',token=tok)
    mid,err=_guard_mutation(args)
    if err: return err
    prior=_META_IG_MUTATIONS.get(mid)
    if prior: return {'ok':prior.get('ok',False),'mutation_id':mid,'retry_blocked':True,'prior':prior}
    if op=='create_container':
        p={}
        if args.get('image_url'): p['image_url']=str(args.get('image_url'))
        if args.get('video_url'): p['video_url']=str(args.get('video_url'))
        if args.get('caption') is not None: p['caption']=str(args.get('caption') or '')
        if args.get('media_type'): p['media_type']=str(args.get('media_type'))
        if not p.get('image_url') and not p.get('video_url'):
            return {'ok':False,'error':'image_url_or_video_url_required'}
        out=_meta._graph(_meta.IG_ID+'/media','POST',p,token=tok,timeout=90)
        cid=str(((out.get('data') or {}).get('id')) or '')
        if out.get('outcome')=='OUTCOME_UNKNOWN':
            rec={'ok':False,'mutation_id':mid,'outcome':'OUTCOME_UNKNOWN','retry_blocked':True,'container_id':cid}
            _META_IG_MUTATIONS[mid]=rec; return rec
        rb=_meta._read(cid,'id,status_code,status',token=tok) if cid else None
        rec={'ok':bool(out.get('ok') and cid and rb and rb.get('ok')),'mutation_id':mid,'outcome':out.get('outcome'),'container_id':cid,'readback':rb,'public_post_created':False}
        _META_IG_MUTATIONS[mid]=rec; return rec
    if op=='publish':
        cid=str(args.get('creation_id') or '').strip()
        if not cid: return {'ok':False,'error':'creation_id_required'}
        out=_meta._graph(_meta.IG_ID+'/media_publish','POST',{'creation_id':cid},token=tok,timeout=90)
        pubid=str(((out.get('data') or {}).get('id')) or '')
        if out.get('outcome')=='OUTCOME_UNKNOWN':
            rec={'ok':False,'mutation_id':mid,'outcome':'OUTCOME_UNKNOWN','retry_blocked':True,'creation_id':cid}
            _META_IG_MUTATIONS[mid]=rec; return rec
        rb=_meta._read(pubid,'id,caption,media_type,permalink,timestamp',token=tok) if pubid else None
        rec={'ok':bool(out.get('ok') and pubid and rb and rb.get('ok')),'mutation_id':mid,'outcome':out.get('outcome'),'media_id':pubid,'readback':rb,'public_post_created':bool(pubid)}
        _META_IG_MUTATIONS[mid]=rec; return rec
    return {'ok':False,'error':'unsupported_operation'}

def _ads_campaign_tool(args):
    op=str(args.get('operation') or '').strip().lower()
    if op=='list':
        return _meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','GET',{'fields':'id,name,status,effective_status,objective','limit':str(args.get('limit') or 50)})
    if op=='get':
        cid=str(args.get('campaign_id') or '').strip()
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        return _meta._read(cid,'id,name,status,effective_status,objective,special_ad_categories')
    mid,err=_guard_mutation(args)
    if err: return err
    prior=_META_AD_MUTATIONS.get(mid)
    if prior: return {'ok':prior.get('ok',False),'mutation_id':mid,'retry_blocked':True,'prior':prior}
    if op=='create':
        name=str(args.get('name') or '').strip()
        if not name: return {'ok':False,'error':'name_required'}
        p={
          'name':name,
          'objective':str(args.get('objective') or 'OUTCOME_TRAFFIC'),
          'status':str(args.get('status') or 'PAUSED').upper(),
          'special_ad_categories':json.dumps(args.get('special_ad_categories') or []),
          'is_adset_budget_sharing_enabled':'true' if bool(args.get('is_adset_budget_sharing_enabled')) else 'false'
        }
        out=_meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','POST',p)
        cid=str(((out.get('data') or {}).get('id')) or '')
        if out.get('outcome')=='OUTCOME_UNKNOWN':
            rec={'ok':False,'mutation_id':mid,'outcome':'OUTCOME_UNKNOWN','retry_blocked':True,'campaign_id':cid}
            _META_AD_MUTATIONS[mid]=rec; return rec
        rb=_meta._read(cid,'id,name,status,effective_status,objective') if cid else None
        rec={'ok':bool(out.get('ok') and cid and rb and rb.get('ok')),'mutation_id':mid,'outcome':out.get('outcome'),'campaign_id':cid,'readback':rb}
        _META_AD_MUTATIONS[mid]=rec; return rec
    if op=='update':
        cid=str(args.get('campaign_id') or '').strip()
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        p={}
        for k in ('name','status'):
            if args.get(k) is not None: p[k]=str(args.get(k))
        if not p: return {'ok':False,'error':'no_update_fields'}
        out=_meta._graph(cid,'POST',p)
        rb=_meta._read(cid,'id,name,status,effective_status,objective')
        rec={'ok':bool(out.get('ok') and rb.get('ok')),'mutation_id':mid,'outcome':out.get('outcome'),'campaign_id':cid,'readback':rb}
        _META_AD_MUTATIONS[mid]=rec; return rec
    if op=='delete':
        cid=str(args.get('campaign_id') or '').strip()
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        out=_meta._graph(cid,'DELETE',{})
        rb=_meta._read(cid,'id,name,status,effective_status')
        deleted=bool((not rb.get('ok')) or str(((rb.get('data') or {}).get('status') or '')).upper()=='DELETED' or str(((rb.get('data') or {}).get('effective_status') or '')).upper()=='DELETED')
        rec={'ok':deleted,'mutation_id':mid,'outcome':'CONFIRMED_APPLIED' if deleted else out.get('outcome'),'campaign_id':cid,'delete':out,'readback':rb,'deleted_confirmed':deleted}
        _META_AD_MUTATIONS[mid]=rec; return rec
    return {'ok':False,'error':'unsupported_operation'}

_prev_tools=meta_mcp_tools
_prev_call=meta_mcp_call

def meta_mcp_tools():
    tools=list(_prev_tools())
    tools += [
      {'name':'meta_instagram_media','description':'Instagram professional media access: list/get/create_container/publish. Mutations require confirm=true and stable mutation_id. Container creation does not publish publicly until publish is called.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create_container','publish']},'media_id':{'type':'string'},'creation_id':{'type':'string'},'image_url':{'type':'string'},'video_url':{'type':'string'},'caption':{'type':'string'},'media_type':{'type':'string'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_ads_campaign','description':'Meta Marketing API campaign CRUD under the configured business ad account. Create supports PAUSED or ACTIVE. Mutations require confirm=true and stable mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','create','update','delete']},'campaign_id':{'type':'string'},'name':{'type':'string'},'objective':{'type':'string'},'status':{'type':'string'},'special_ad_categories':{'type':'array','items':{'type':'string'}},'is_adset_budget_sharing_enabled':{'type':'boolean'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}}
    ]
    return tools

def meta_mcp_call(name,args):
    if name=='meta_instagram_media': return _ig_media_tool(args or {})
    if name=='meta_ads_campaign': return _ads_campaign_tool(args or {})
    return _prev_call(name,args)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+EXTRA
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1: raise RuntimeError('runtime exec marker not found exactly once')
    lines=[
      "runtime_anchor='class H(BaseHTTPRequestHandler):\\n'",
      "if s.count(runtime_anchor)!=1: raise RuntimeError('igads helper class anchor mismatch')",
      "runtime_globals="+repr(RUNTIME_GLOBALS),
      "s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)",
      "post_anchor=\"    def do_POST(self):\\n        p=self.path.split('?',1)[0]\\n\"",
      "if s.count(post_anchor)!=1: raise RuntimeError('igads helper do_POST anchor mismatch')",
      "mcp_method="+repr(MCP_METHOD),
      "s=s.replace(post_anchor,mcp_method,1)",
      "server_anchor=\"ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()\"",
      "if s.count(server_anchor)!=1: raise RuntimeError('igads helper server anchor mismatch')",
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_IG_ADS_PATCH_READY '+json.dumps({'tools':['meta_instagram_media','meta_ads_campaign']},ensure_ascii=False),flush=True)",
      runtime_exec
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
