import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
wrapper=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

needle="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if needle not in wrapper:
    raise RuntimeError('V14 exec marker missing')

patch=r'''
# ---- ND VK DIRECT MCP v1: additive, bounded, no Make changes ----
old_env="""CALLBACK_URL=PUBLIC_BASE+CALLBACK_PATH if PUBLIC_BASE else ''
ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}
"""
new_env="""CALLBACK_URL=PUBLIC_BASE+CALLBACK_PATH if PUBLIC_BASE else ''
MCP_ROUTE_TOKEN=os.environ.get('ND_VK_MCP_ROUTE_TOKEN','').strip()
MCP_PATH='/vk/mcp/'+MCP_ROUTE_TOKEN if MCP_ROUTE_TOKEN else ''
ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}
"""
if old_env not in src:
    raise RuntimeError('V14 env anchor missing')
src=src.replace(old_env,new_env,1)

mcp_code=r"""
def mcp_require_peer(peer_id):
    try: peer_id=int(peer_id)
    except Exception: raise RuntimeError('peer_id must be an integer')
    if not ALLOWED: raise RuntimeError('VK_ALLOWED_USER_IDS is empty; MCP peer access is fail-closed')
    if peer_id not in ALLOWED: raise RuntimeError('peer_id is outside VK_ALLOWED_USER_IDS')
    return peer_id

def mcp_tools():
    return [
        {'name':'vk_status','description':'Verify direct VK API reachability and community identity without returning message contents.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
        {'name':'vk_get_users','description':'Read basic VK profile data for allow-listed users.','inputSchema':{'type':'object','properties':{'user_ids':{'type':'array','items':{'type':'integer'}}},'additionalProperties':False}},
        {'name':'vk_get_conversations','description':'Read recent VK direct conversations, filtered to allow-listed user IDs.','inputSchema':{'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':100,'default':20},'offset':{'type':'integer','minimum':0,'default':0},'unread_only':{'type':'boolean','default':False}},'additionalProperties':False}},
        {'name':'vk_get_history','description':'Read message history for one allow-listed VK peer.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'count':{'type':'integer','minimum':1,'maximum':100,'default':30},'offset':{'type':'integer','minimum':0,'default':0}},'required':['peer_id'],'additionalProperties':False}},
        {'name':'vk_send_message','description':'Send a plain-text VK message to one allow-listed peer.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'message':{'type':'string','minLength':1,'maxLength':3500},'reply_to':{'type':'integer'}},'required':['peer_id','message'],'additionalProperties':False}},
        {'name':'vk_mark_as_read','description':'Mark messages from one allow-listed VK peer as read.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'}},'required':['peer_id'],'additionalProperties':False}},
    ]

def mcp_call(name,args):
    args=args or {}
    if name=='vk_status':
        gid=resolve_gid()
        return {'ok':True,'transport':'DIRECT_VK_API','api_version':V,'group_id':gid,'allowed_peer_count':len(ALLOWED)}
    if name=='vk_get_users':
        ids=args.get('user_ids')
        ids=sorted(ALLOWED) if ids is None else [mcp_require_peer(x) for x in ids]
        if not ids:return {'ok':True,'response':[]}
        return {'ok':True,'response':vk('users.get',{'user_ids':','.join(str(x) for x in ids),'fields':'first_name,last_name,screen_name'})}
    if name=='vk_get_conversations':
        count=max(1,min(int(args.get('count',20)),100));offset=max(0,int(args.get('offset',0)))
        filt='unread' if bool(args.get('unread_only',False)) else 'all'
        resp=vk('messages.getConversations',{'count':count,'offset':offset,'filter':filt,'extended':0}) or {}
        items=(resp.get('items') or []) if isinstance(resp,dict) else []
        filtered=[]
        for item in items:
            try: pid=int((((item.get('conversation') or {}).get('peer') or {}).get('id')))
            except Exception: continue
            if pid in ALLOWED: filtered.append(item)
        return {'ok':True,'response':{'count':len(filtered),'items':filtered}}
    if name=='vk_get_history':
        peer=mcp_require_peer(args.get('peer_id'))
        count=max(1,min(int(args.get('count',30)),100));offset=max(0,int(args.get('offset',0)))
        return {'ok':True,'response':vk('messages.getHistory',{'peer_id':peer,'count':count,'offset':offset,'rev':0})}
    if name=='vk_send_message':
        peer=mcp_require_peer(args.get('peer_id'));message=str(args.get('message') or '').strip()
        if not message:raise RuntimeError('message must not be empty')
        if len(message)>3500:raise RuntimeError('message exceeds 3500-character MCP limit')
        p={'peer_id':peer,'random_id':random.randint(1,2000000000),'message':message}
        if args.get('reply_to') is not None:p['reply_to']=int(args.get('reply_to'))
        return {'ok':True,'response':vk('messages.send',p)}
    if name=='vk_mark_as_read':
        peer=mcp_require_peer(args.get('peer_id'))
        return {'ok':True,'response':vk('messages.markAsRead',{'peer_id':peer})}
    raise RuntimeError('unknown MCP tool: '+str(name))

def mcp_result(req_id,result):
    return {'jsonrpc':'2.0','id':req_id,'result':result}

def mcp_error(req_id,code,message):
    return {'jsonrpc':'2.0','id':req_id,'error':{'code':code,'message':message}}

def mcp_dispatch(req):
    if not isinstance(req,dict): return (400,mcp_error(None,-32600,'Invalid Request'))
    method=req.get('method');rid=req.get('id');params=req.get('params') or {}
    if method=='initialize':
        requested=params.get('protocolVersion') or '2025-06-18'
        return (200,mcp_result(rid,{
            'protocolVersion':requested,
            'capabilities':{'tools':{'listChanged':False}},
            'serverInfo':{'name':'ND VK','version':'1.0.0'},
            'instructions':'Direct bounded VK access. Peer reads/writes are restricted to VK_ALLOWED_USER_IDS. Make remains an independent fallback.'
        }))
    if method in ('notifications/initialized','notifications/cancelled'):
        return (202,None)
    if method=='ping': return (200,mcp_result(rid,{}))
    if method=='tools/list': return (200,mcp_result(rid,{'tools':mcp_tools()}))
    if method=='tools/call':
        name=params.get('name');args=params.get('arguments') or {}
        try:
            result=mcp_call(name,args)
            text=json.dumps(result,ensure_ascii=False)
            return (200,mcp_result(rid,{'content':[{'type':'text','text':text}],'structuredContent':result,'isError':False}))
        except Exception as e:
            msg=cleanerr(e)
            return (200,mcp_result(rid,{'content':[{'type':'text','text':msg}],'isError':True}))
    return (200,mcp_error(rid,-32601,'Method not found'))

"""
anchor="class H(BaseHTTPRequestHandler):\n"
if anchor not in src:
    raise RuntimeError('V14 handler anchor missing')
src=src.replace(anchor,mcp_code+"\n"+anchor,1)

old_post="""    def do_POST(self):
        if self.path.split('?',1)[0]!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
"""
new_post="""    def handle_mcp(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            req=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            status,body=mcp_dispatch(req)
            if body is None:
                self.send_response(status);self.send_header('Content-Length','0');self.end_headers();return
            self.out(status,body)
        except Exception as e:
            self.out(400,mcp_error(None,-32700,cleanerr(e)))

    def do_POST(self):
        p=self.path.split('?',1)[0]
        if MCP_ROUTE_TOKEN and p==MCP_PATH:self.handle_mcp();return
        if p!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
        try:
"""
if old_post not in src:
    raise RuntimeError('V14 POST anchor missing')
src=src.replace(old_post,new_post,1)

old_root="""        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL});return
"""
new_root="""        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL,'direct_mcp_configured':bool(MCP_ROUTE_TOKEN)});return
"""
if old_root in src: src=src.replace(old_root,new_root,1)

old_server_start="ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
new_server_start="print('ND_VK_DIRECT_MCP_READY',json.dumps({'configured':bool(MCP_ROUTE_TOKEN),'tool_count':len(mcp_tools())}),flush=True)\\nThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
if old_server_start not in src:
    raise RuntimeError('V15 server-start anchor missing')
src=src.replace(old_server_start,new_server_start,1)

# ---- end direct MCP patch ----
'''

wrapper=wrapper.replace(needle,patch+"\n"+needle,1)
exec(compile(wrapper,'nd_vk_gateway_v15_direct_mcp.py','exec'))
