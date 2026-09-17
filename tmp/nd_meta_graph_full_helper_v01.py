import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_fb_crud_helper_v01.py','exec'),ns)

GRAPH_EXT = r"""
_meta_mcp_tools_base=meta_mcp_tools
_meta_mcp_call_base=meta_mcp_call
META_GRAPH_MUTATIONS={}

def _meta_graph_token(path, mode):
    m=str(mode or 'auto').lower()
    if m=='system':
        return None, {'ok':True,'mode':'system'}
    if m=='page':
        tok,state=_meta._page_token()
        return tok,state
    if m!='auto':
        return '', {'ok':False,'error':'token_mode_must_be_auto_system_or_page'}
    p=str(path or '').lstrip('/')
    if (_meta.PAGE_ID and p.startswith(_meta.PAGE_ID)) or (_meta.IG_ID and p.startswith(_meta.IG_ID)):
        tok,state=_meta._page_token()
        return tok,state
    return None, {'ok':True,'mode':'system'}

def _meta_graph_tool(args):
    method=str(args.get('method') or 'GET').upper()
    path=str(args.get('path') or '').strip().lstrip('/')
    params=args.get('params') or {}
    if not path:
        return {'ok':False,'error':'path_required'}
    if method not in ('GET','POST','DELETE'):
        return {'ok':False,'error':'method_must_be_GET_POST_or_DELETE'}
    if not isinstance(params,dict):
        return {'ok':False,'error':'params_must_be_object'}
    token,state=_meta_graph_token(path,args.get('token_mode'))
    if state and not state.get('ok'):
        return {'ok':False,'error':'token_resolution_failed','detail':state}
    timeout=int(args.get('timeout') or 60)
    timeout=max(1,min(timeout,120))
    if method=='GET':
        return _meta._graph(path,'GET',params,token=token,timeout=timeout)

    mid=str(args.get('mutation_id') or '').strip()
    if not bool(args.get('confirm')):
        return {'ok':False,'error':'confirm_required'}
    if not mid:
        return {'ok':False,'error':'mutation_id_required'}
    sig=json.dumps({'path':path,'method':method,'params':params,'token_mode':str(args.get('token_mode') or 'auto')},
                   sort_keys=True,separators=(',',':'),ensure_ascii=False)
    old=META_GRAPH_MUTATIONS.get(mid)
    if old:
        if old.get('signature')!=sig:
            return {'ok':False,'error':'mutation_id_payload_mismatch','mutation_id':mid}
        return {'ok':old.get('outcome')=='CONFIRMED_APPLIED',
                'mutation_id':mid,'retry_blocked':True,'prior':old}

    out=_meta._graph(path,method,params,token=token,timeout=timeout)
    rec={'signature':sig,'outcome':out.get('outcome'),'status':out.get('status'),'ts':int(time.time())}
    META_GRAPH_MUTATIONS[mid]=rec
    return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,
            'outcome':out.get('outcome'),'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

def meta_mcp_tools():
    tools=_meta_mcp_tools_base()
    tools.append({
      'name':'meta_graph',
      'description':'Direct Meta Graph API access using the existing server-side ND token. Can read, create, edit, publish, manage comments/media/messages/ads and perform any other Graph operation allowed by the token. GET is direct; POST/DELETE require confirm=true and a unique mutation_id. token_mode may be auto, system, or page.',
      'inputSchema':{
        'type':'object',
        'properties':{
          'method':{'type':'string','enum':['GET','POST','DELETE']},
          'path':{'type':'string'},
          'params':{'type':'object','additionalProperties':True},
          'token_mode':{'type':'string','enum':['auto','system','page']},
          'timeout':{'type':'integer','minimum':1,'maximum':120},
          'confirm':{'type':'boolean'},
          'mutation_id':{'type':'string'}
        },
        'required':['method','path'],
        'additionalProperties':False
      }
    })
    return tools

def meta_mcp_call(name,args):
    if name=='meta_graph':
        return _meta_graph_tool(args)
    return _meta_mcp_call_base(name,args)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+GRAPH_EXT
ns['MCP_METHOD']=ns['MCP_METHOD'].replace(
    'Nameless Dhamma Meta MCP with guarded Facebook Page and comment CRUD.',
    'Nameless Dhamma Meta MCP with direct Graph API access using the existing server-side token.'
)
_base_patch=ns['patch_linear_wrapper_source']

def patch_linear_wrapper_source(src):
    out=_base_patch(src)
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if out.count(runtime_exec)!=1:
        raise RuntimeError('meta graph full runtime exec marker mismatch')
    marker="print('ND_META_GRAPH_FULL_READY '+json.dumps({'direct_mcp':True,'tools':8,'generic_graph':True,'mutations_guarded':True},ensure_ascii=False),flush=True)\n"
    return out.replace(runtime_exec,marker+runtime_exec,1)

RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']
# checkpoint-pin: meta-graph-full-v1
