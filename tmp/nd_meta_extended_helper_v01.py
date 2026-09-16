import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ca940470eee420524ed9a2c79f4bc15d92e2a0f9/tmp/nd_meta_fb_ig_ads_combined_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_fb_ig_ads_combined_helper_v01.py','exec'),ns)

EXTRA=r"""
_META_EXT_MUTATIONS={}

def _ext_guard(args):
    mid=str(args.get('mutation_id') or '').strip()
    if not mid: return None,{'ok':False,'error':'mutation_id_required'}
    if not bool(args.get('confirm')): return None,{'ok':False,'error':'confirm_required'}
    return mid,None

def _ext_once(mid,key,fn):
    sig=str(key)
    old=_META_EXT_MUTATIONS.get(mid)
    if old:
        if old.get('signature')!=sig: return {'ok':False,'error':'mutation_id_payload_mismatch','mutation_id':mid}
        return {'ok':old.get('ok',False),'mutation_id':mid,'retry_blocked':True,'prior':old}
    out=fn()
    rec={'ok':bool(out.get('ok')),'signature':sig,'outcome':out.get('outcome'),'status':out.get('status'),'result':out}
    _META_EXT_MUTATIONS[mid]=rec
    return {'ok':rec['ok'],'mutation_id':mid,'result':out,'outcome':out.get('outcome'),'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

def _meta_permissions_tool():
    return _meta._graph('me/permissions','GET',{})

def _meta_insights_tool(args):
    oid=str(args.get('object_id') or '').strip()
    if not oid: return {'ok':False,'error':'object_id_required'}
    p={}
    for k in ('metric','period','since','until','breakdowns','date_preset','time_increment','level'):
        if args.get(k) not in (None,''): p[k]=str(args.get(k))
    return _meta._graph(oid+'/insights','GET',p)

def _ig_comments_tool(args):
    op=str(args.get('operation') or '').strip().lower()
    tok,state=_meta._page_token()
    if not tok: return {'ok':False,'error':'page_access_token_unavailable','detail':state}
    oid=str(args.get('object_id') or '').strip()
    cid=str(args.get('comment_id') or '').strip()
    if op=='list':
        return _meta._graph(oid+'/comments','GET',{'fields':'id,text,username,timestamp,hidden','limit':str(args.get('limit') or 50)},token=tok)
    if op=='get':
        if not cid: return {'ok':False,'error':'comment_id_required'}
        return _meta._read(cid,'id,text,username,timestamp,hidden',token=tok)
    mid,err=_ext_guard(args)
    if err: return err
    if op=='reply':
        if not cid: return {'ok':False,'error':'comment_id_required'}
        return _ext_once(mid,'ig-reply:'+cid+':'+str(args.get('message') or ''),lambda:_meta._graph(cid+'/replies','POST',{'message':str(args.get('message') or '')},token=tok))
    if op=='hide':
        if not cid: return {'ok':False,'error':'comment_id_required'}
        hidden='true' if bool(args.get('hidden',True)) else 'false'
        return _ext_once(mid,'ig-hide:'+cid+':'+hidden,lambda:_meta._graph(cid,'POST',{'hide':hidden},token=tok))
    if op=='delete':
        if not cid: return {'ok':False,'error':'comment_id_required'}
        return _ext_once(mid,'ig-delete:'+cid,lambda:_meta._graph(cid,'DELETE',{},token=tok))
    return {'ok':False,'error':'unsupported_operation'}

def _ads_object_tool(args):
    typ=str(args.get('object_type') or '').strip().lower()
    op=str(args.get('operation') or '').strip().lower()
    oid=str(args.get('object_id') or '').strip()
    if typ not in ('campaign','adset','ad'): return {'ok':False,'error':'unsupported_object_type'}
    plural={'campaign':'campaigns','adset':'adsets','ad':'ads'}[typ]
    default_fields={'campaign':'id,name,status,effective_status,objective','adset':'id,name,status,effective_status,campaign_id,daily_budget,lifetime_budget,billing_event,optimization_goal','ad':'id,name,status,effective_status,adset_id,creative'}[typ]
    if op=='list':
        return _meta._graph(_meta.AD_ACCOUNT_ID+'/'+plural,'GET',{'fields':str(args.get('fields') or default_fields),'limit':str(args.get('limit') or 50)})
    if op=='get':
        if not oid: return {'ok':False,'error':'object_id_required'}
        return _meta._read(oid,str(args.get('fields') or default_fields))
    mid,err=_ext_guard(args)
    if err: return err
    params=args.get('params') or {}
    if not isinstance(params,dict): return {'ok':False,'error':'params_must_be_object'}
    if op=='create':
        if 'status' not in params: params=dict(params, status='PAUSED')
        return _ext_once(mid,typ+'-create:'+json.dumps(params,sort_keys=True,ensure_ascii=False),lambda:_meta._graph(_meta.AD_ACCOUNT_ID+'/'+plural,'POST',params))
    if op=='update':
        if not oid: return {'ok':False,'error':'object_id_required'}
        return _ext_once(mid,typ+'-update:'+oid+':'+json.dumps(params,sort_keys=True,ensure_ascii=False),lambda:_meta._graph(oid,'POST',params))
    if op=='delete':
        if not oid: return {'ok':False,'error':'object_id_required'}
        return _ext_once(mid,typ+'-delete:'+oid,lambda:_meta._graph(oid,'DELETE',{}))
    return {'ok':False,'error':'unsupported_operation'}

def _messenger_tool(args):
    op=str(args.get('operation') or '').strip().lower()
    if op!='send': return {'ok':False,'error':'unsupported_operation'}
    rid=str(args.get('recipient_id') or '').strip()
    if not rid: return {'ok':False,'error':'recipient_id_required'}
    mid,err=_ext_guard(args)
    if err: return err
    tok,state=_meta._page_token()
    if not tok: return {'ok':False,'error':'page_access_token_unavailable','detail':state}
    params={'recipient':json.dumps({'id':rid}),'message':json.dumps({'text':str(args.get('message') or '')}),'messaging_type':str(args.get('messaging_type') or 'RESPONSE')}
    return _ext_once(mid,'messenger-send:'+rid+':'+str(args.get('message') or ''),lambda:_meta._graph(_meta.PAGE_ID+'/messages','POST',params,token=tok))

_prev_tools=meta_mcp_tools
_prev_call=meta_mcp_call

def meta_mcp_tools():
    tools=list(_prev_tools())
    tools += [
      {'name':'meta_permissions','description':'Read permissions granted to the current Meta system-user token.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'meta_insights','description':'Read Meta insights for any supported object.','inputSchema':{'type':'object','properties':{'object_id':{'type':'string'},'metric':{'type':'string'},'period':{'type':'string'},'since':{'type':'string'},'until':{'type':'string'},'breakdowns':{'type':'string'},'date_preset':{'type':'string'},'time_increment':{'type':'string'},'level':{'type':'string'}},'required':['object_id'],'additionalProperties':False}},
      {'name':'meta_instagram_comments','description':'Instagram comment read/reply/hide/delete. Mutations require confirm=true and stable mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','reply','hide','delete']},'object_id':{'type':'string'},'comment_id':{'type':'string'},'message':{'type':'string'},'hidden':{'type':'boolean'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_ads_object','description':'Marketing API campaign/adset/ad list/get/create/update/delete. Create defaults to PAUSED when status is omitted. Mutations require confirm=true and stable mutation_id.','inputSchema':{'type':'object','properties':{'object_type':{'type':'string','enum':['campaign','adset','ad']},'operation':{'type':'string','enum':['list','get','create','update','delete']},'object_id':{'type':'string'},'fields':{'type':'string'},'params':{'type':'object'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['object_type','operation'],'additionalProperties':False}},
      {'name':'meta_messenger','description':'Send Messenger messages from the configured Facebook Page. Requires recipient_id plus confirm=true and stable mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['send']},'recipient_id':{'type':'string'},'message':{'type':'string'},'messaging_type':{'type':'string'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}}
    ]
    return tools

def meta_mcp_call(name,args):
    if name=='meta_permissions': return _meta_permissions_tool()
    if name=='meta_insights': return _meta_insights_tool(args or {})
    if name=='meta_instagram_comments': return _ig_comments_tool(args or {})
    if name=='meta_ads_object': return _ads_object_tool(args or {})
    if name=='meta_messenger': return _messenger_tool(args or {})
    return _prev_call(name,args)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+EXTRA
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1: raise RuntimeError('ext runtime exec marker not found exactly once')
    lines=[
      "runtime_anchor='class H(BaseHTTPRequestHandler):\\n'",
      "if s.count(runtime_anchor)!=1: raise RuntimeError('ext helper class anchor mismatch')",
      "runtime_globals="+repr(RUNTIME_GLOBALS),
      "s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)",
      "post_anchor=\"    def do_POST(self):\\n        p=self.path.split('?',1)[0]\\n\"",
      "if s.count(post_anchor)!=1: raise RuntimeError('ext helper do_POST anchor mismatch')",
      "mcp_method="+repr(MCP_METHOD),
      "s=s.replace(post_anchor,mcp_method,1)",
      "server_anchor=\"ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()\"",
      "if s.count(server_anchor)!=1: raise RuntimeError('ext helper server anchor mismatch')",
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\nthreading.Thread(target=meta_fb_qualify_once,daemon=True).start()\\nthreading.Thread(target=meta_igads_qualify_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_EXTENDED_HELPER_READY '+json.dumps({'tools':14,'permissions':True,'insights':True,'instagram_comments':True,'ads_object':True,'messenger':True},ensure_ascii=False),flush=True)",
      runtime_exec
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
