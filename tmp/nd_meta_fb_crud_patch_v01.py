import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6f405bb76a4b5db745e6c3d5f5e7607813ee7444/tmp/nd_meta_pass2_runtime_patch_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_pass2_runtime_patch_helper_v01.py','exec'),ns)

EXTRA = r"""
_META_FB_MUTATIONS={}

def _fb_guard(args):
    mid=str(args.get('mutation_id') or '').strip()
    if not mid:
        return None,{'ok':False,'error':'mutation_id_required'}
    if not bool(args.get('confirm')):
        return None,{'ok':False,'error':'confirm_required'}
    return mid,None

def _fb_page_token():
    tok,state=_meta._page_token()
    if not tok:
        raise RuntimeError(str(state))
    return tok

def _fb_post_tool(args):
    op=str(args.get('operation') or '').strip().lower()
    token=_fb_page_token()
    if op=='get':
        pid=str(args.get('post_id') or '').strip()
        if not pid: return {'ok':False,'error':'post_id_required'}
        return _meta._read(pid,'id,message,created_time,is_published,permalink_url',token=token)
    mid,err=_fb_guard(args)
    if err: return err
    prior=_META_FB_MUTATIONS.get(mid)
    if prior:
        return {'ok':prior.get('ok',False),'mutation_id':mid,'retry_blocked':True,'prior':prior}
    if op=='create':
        marker='NDMCP_'+mid[:40]
        msg=str(args.get('message') or '')
        published='true' if bool(args.get('published')) else 'false'
        out=_meta._graph(_meta.PAGE_ID+'/feed','POST',{'message':marker+' '+msg,'published':published},token=token)
        pid=str(((out.get('data') or {}).get('id')) or '')
        if out.get('outcome')=='OUTCOME_UNKNOWN':
            found,_=_meta._find_unpublished(marker,token)
            if found:
                pid=found
                out={'ok':True,'status':200,'data':{'id':pid},'outcome':'CONFIRMED_APPLIED','reconciled':True}
            else:
                rec={'ok':False,'outcome':'OUTCOME_UNKNOWN','post_id':'','retry_blocked':True}
                _META_FB_MUTATIONS[mid]=rec
                return rec
        rb=_meta._read(pid,'id,message,created_time,is_published',token=token) if pid else None
        rec={'ok':bool(out.get('ok') and rb and rb.get('ok')),'outcome':out.get('outcome'),'post_id':pid,'readback':rb}
        _META_FB_MUTATIONS[mid]=rec
        return rec
    if op=='update':
        pid=str(args.get('post_id') or '').strip()
        if not pid: return {'ok':False,'error':'post_id_required'}
        out=_meta._graph(pid,'POST',{'message':str(args.get('message') or '')},token=token)
        rb=_meta._read(pid,'id,message,created_time,is_published',token=token)
        rec={'ok':bool(out.get('ok') and rb.get('ok')),'outcome':out.get('outcome'),'post_id':pid,'readback':rb}
        _META_FB_MUTATIONS[mid]=rec
        return rec
    if op=='delete':
        pid=str(args.get('post_id') or '').strip()
        if not pid: return {'ok':False,'error':'post_id_required'}
        out=_meta._graph(pid,'DELETE',{},token=token)
        absent,after=_meta._confirm_absent(pid,token=token)
        rec={'ok':bool(absent),'outcome':'CONFIRMED_APPLIED' if absent else out.get('outcome'),'post_id':pid,'delete':out,'delete_readback_absent':absent,'after':after}
        _META_FB_MUTATIONS[mid]=rec
        return rec
    return {'ok':False,'error':'unsupported_operation'}

_meta_base_tools=meta_mcp_tools
_meta_base_call=meta_mcp_call

def meta_mcp_tools():
    tools=list(_meta_base_tools())
    tools.append({
      'name':'meta_facebook_post',
      'description':'Facebook Page post CRUD. Mutations require confirm=true and stable mutation_id. Create defaults to unpublished unless published=true.',
      'inputSchema':{
        'type':'object',
        'properties':{
          'operation':{'type':'string','enum':['get','create','update','delete']},
          'post_id':{'type':'string'},
          'message':{'type':'string'},
          'published':{'type':'boolean'},
          'confirm':{'type':'boolean'},
          'mutation_id':{'type':'string'}
        },
        'required':['operation'],
        'additionalProperties':False
      }
    })
    return tools

def meta_mcp_call(name,args):
    if name=='meta_facebook_post':
        return _fb_post_tool(args or {})
    return _meta_base_call(name,args)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+EXTRA
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1:
        raise RuntimeError('runtime exec marker not found exactly once')
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
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_FB_CRUD_PATCH_READY '+json.dumps({'tool':'meta_facebook_post'},ensure_ascii=False),flush=True)",
      runtime_exec
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
