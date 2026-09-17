import io
import urllib.request

CURRENT_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/5a1d067997e7ea2127e76535550e51fb08b9e57b/tmp/nd_meta_fb_list_v26_front_v01.py'
BASE_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/cbd3279fa9fa0eec25609a438883d9660077d681/tmp/nd_github_mcp_front_v1.py'
_real_urlopen=urllib.request.urlopen

class _MemResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

def _patch_base(src):
    src=src.replace(
        "import base64, json, os, subprocess, sys, urllib.parse, urllib.request\n",
        "import base64, json, os, subprocess, sys, urllib.parse, urllib.request, secrets, time\n",
        1,
    )
    marker="def tools():\n"
    if src.count(marker)!=1:
        raise RuntimeError('vk unified tools anchor mismatch')
    vk_code=r'''
VK_TOKEN=os.environ.get('VK_GROUP_TOKEN','').strip()
VK_SCREEN=os.environ.get('VK_GROUP_SCREEN_NAME','namelessdhamma').strip().lstrip('@') or 'namelessdhamma'
VK_VERSION=os.environ.get('VK_API_VERSION','5.199').strip() or '5.199'
VK_MCP_TOKEN=os.environ.get('ND_VK_MCP_ROUTE_TOKEN','').strip()
VK_ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}
VK_MUTATIONS=set()

def vk_clean(x):
    z=str(x)
    for secret in (VK_TOKEN,VK_MCP_TOKEN):
        if secret: z=z.replace(secret,'[REDACTED]')
    return z[:2000]

def vk_api_call(method,params=None,timeout=45):
    if not VK_TOKEN: raise RuntimeError('vk_not_configured')
    form=dict(params or {})
    form['access_token']=VK_TOKEN
    form['v']=VK_VERSION
    req=urllib.request.Request(
        'https://api.vk.com/method/'+str(method).strip(),
        data=urllib.parse.urlencode({k:str(v) for k,v in form.items() if v is not None}).encode('utf-8'),
        method='POST',
        headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-MCP/2.0'},
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    except Exception as e:
        raise RuntimeError('vk_transport:'+vk_clean(e))
    if obj.get('error'):
        err=obj.get('error') or {}
        raise RuntimeError('vk_api_%s:%s'%(err.get('error_code'),vk_clean(err.get('error_msg'))))
    return obj.get('response')

def vk_group():
    obj=vk_api_call('groups.getById',{'group_id':VK_SCREEN,'fields':'name,screen_name,members_count'})
    rows=obj.get('groups') if isinstance(obj,dict) else obj
    if not isinstance(rows,list) or not rows: raise RuntimeError('vk_group_not_resolved')
    g=rows[0]
    return {'id':int(g.get('id')),'name':g.get('name'),'screen_name':g.get('screen_name'),'members_count':g.get('members_count')}

def vk_peer_allowed(peer_id):
    p=int(peer_id)
    if VK_ALLOWED and p not in VK_ALLOWED: raise RuntimeError('peer_not_allowlisted')
    return p

def vk_mutation_guard(mutation_id,confirm):
    mid=str(mutation_id or '').strip()
    if confirm is not True: raise RuntimeError('confirm_true_required')
    if not mid: raise RuntimeError('mutation_id_required')
    if mid in VK_MUTATIONS: raise RuntimeError('duplicate_mutation_id')
    VK_MUTATIONS.add(mid)
    return mid

def vk_tools():
    return [
      {'name':'vk_status','description':'Verify direct VK API reachability and community identity without returning message contents.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'vk_get_users','description':'Read basic VK profile data for allow-listed users.','inputSchema':{'type':'object','properties':{'user_ids':{'type':'array','items':{'type':'integer'}}},'additionalProperties':False}},
      {'name':'vk_get_conversations','description':'Read recent direct VK conversations, filtered to allow-listed users.','inputSchema':{'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0},'unread_only':{'type':'boolean'}},'additionalProperties':False}},
      {'name':'vk_get_history','description':'Read message history for one allow-listed VK peer.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'count':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0}},'required':['peer_id'],'additionalProperties':False}},
      {'name':'vk_send_message','description':'Send a plain-text VK message to one allow-listed peer.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'message':{'type':'string','minLength':1,'maxLength':3500},'reply_to':{'type':'integer'}},'required':['peer_id','message'],'additionalProperties':False}},
      {'name':'vk_mark_as_read','description':'Mark messages from one allow-listed VK peer as read.','inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'}},'required':['peer_id'],'additionalProperties':False}},
      {'name':'vk_wall_posts','description':'List, create, edit, or delete posts on the configured ND VK community wall. Mutations require confirm=true and a unique mutation_id.','inputSchema':{'type':'object','properties':{'action':{'type':'string','enum':['list','create','edit','delete']},'count':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0},'post_id':{'type':'integer'},'message':{'type':'string'},'attachments':{'type':'string'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['action'],'additionalProperties':False}},
      {'name':'vk_api','description':'Call an arbitrary VK API method. Read-style methods are direct; all other methods require confirm=true and a unique mutation_id.','inputSchema':{'type':'object','properties':{'method':{'type':'string'},'params':{'type':'object'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['method'],'additionalProperties':False}},
    ]

def vk_call(name,a):
    a=a or {}
    if not isinstance(a,dict): raise RuntimeError('arguments_must_be_object')
    if name=='vk_status':
        g=vk_group()
        return {'ok':True,'route':'railway','provider':'vk','api_version':VK_VERSION,'group':g,'allowed_users':len(VK_ALLOWED),'outcome':'CONFIRMED_APPLIED'}
    if name=='vk_get_users':
        ids=a.get('user_ids')
        if ids is None: ids=sorted(VK_ALLOWED)
        ids=[vk_peer_allowed(x) for x in ids]
        if not ids: return {'ok':True,'users':[]}
        rows=vk_api_call('users.get',{'user_ids':','.join(str(x) for x in ids),'fields':'screen_name,first_name,last_name'})
        return {'ok':True,'users':rows or []}
    if name=='vk_get_conversations':
        count=max(1,min(100,int(a.get('count') or 20))); offset=max(0,int(a.get('offset') or 0))
        p={'count':count,'offset':offset,'extended':0}
        if a.get('unread_only') is True: p['filter']='unread'
        obj=vk_api_call('messages.getConversations',p) or {}
        out=[]
        for row in (obj.get('items') or []):
            conv=row.get('conversation') or {}; peer=(conv.get('peer') or {}); pid=peer.get('id')
            if peer.get('type')!='user' or pid is None: continue
            if VK_ALLOWED and int(pid) not in VK_ALLOWED: continue
            out.append(row)
        return {'ok':True,'count':len(out),'items':out}
    if name=='vk_get_history':
        peer=vk_peer_allowed(a.get('peer_id')); count=max(1,min(100,int(a.get('count') or 30))); offset=max(0,int(a.get('offset') or 0))
        return {'ok':True,'peer_id':peer,'history':vk_api_call('messages.getHistory',{'peer_id':peer,'count':count,'offset':offset})}
    if name=='vk_send_message':
        peer=vk_peer_allowed(a.get('peer_id')); msg=str(a.get('message') or '')
        if not msg or len(msg)>3500: raise RuntimeError('invalid_message')
        p={'peer_id':peer,'message':msg,'random_id':secrets.randbelow(2000000000)+1}
        if a.get('reply_to') is not None: p['reply_to']=int(a.get('reply_to'))
        rid=vk_api_call('messages.send',p)
        return {'ok':True,'peer_id':peer,'message_id':rid,'outcome':'CONFIRMED_APPLIED'}
    if name=='vk_mark_as_read':
        peer=vk_peer_allowed(a.get('peer_id')); res=vk_api_call('messages.markAsRead',{'peer_id':peer})
        return {'ok':True,'peer_id':peer,'response':res,'outcome':'CONFIRMED_APPLIED'}
    if name=='vk_wall_posts':
        action=str(a.get('action') or '').strip().lower(); g=vk_group(); owner=-int(g['id'])
        if action=='list':
            count=max(1,min(100,int(a.get('count') or 20))); offset=max(0,int(a.get('offset') or 0))
            return {'ok':True,'group':g,'wall':vk_api_call('wall.get',{'owner_id':owner,'count':count,'offset':offset})}
        mid=vk_mutation_guard(a.get('mutation_id'),a.get('confirm'))
        if action=='create':
            p={'owner_id':owner,'from_group':1,'message':str(a.get('message') or '')}
            if a.get('attachments'): p['attachments']=str(a.get('attachments'))
            res=vk_api_call('wall.post',p); post_id=int((res or {}).get('post_id'))
            rb=vk_api_call('wall.getById',{'posts':'%s_%s'%(owner,post_id)})
            return {'ok':True,'action':action,'mutation_id':mid,'post_id':post_id,'readback':rb,'outcome':'CONFIRMED_APPLIED'}
        post_id=int(a.get('post_id') or 0)
        if post_id<=0: raise RuntimeError('post_id_required')
        if action=='edit':
            p={'owner_id':owner,'post_id':post_id,'message':str(a.get('message') or '')}
            if a.get('attachments') is not None: p['attachments']=str(a.get('attachments') or '')
            res=vk_api_call('wall.edit',p); rb=vk_api_call('wall.getById',{'posts':'%s_%s'%(owner,post_id)})
            return {'ok':True,'action':action,'mutation_id':mid,'post_id':post_id,'response':res,'readback':rb,'outcome':'CONFIRMED_APPLIED'}
        if action=='delete':
            res=vk_api_call('wall.delete',{'owner_id':owner,'post_id':post_id})
            rb=vk_api_call('wall.getById',{'posts':'%s_%s'%(owner,post_id)})
            return {'ok':True,'action':action,'mutation_id':mid,'post_id':post_id,'response':res,'readback':rb,'outcome':'CONFIRMED_APPLIED'}
        raise RuntimeError('unsupported_wall_action')
    if name=='vk_api':
        method=str(a.get('method') or '').strip(); params=a.get('params') or {}
        if not method or not isinstance(params,dict): raise RuntimeError('method_and_params_required')
        low=method.lower()
        readish=('.get' in low or '.search' in low or low.startswith('utils.') or low.startswith('users.get') or low.startswith('groups.get') or low.startswith('wall.get') or low.startswith('messages.get'))
        mid=None
        if not readish: mid=vk_mutation_guard(a.get('mutation_id'),a.get('confirm'))
        res=vk_api_call(method,params)
        return {'ok':True,'method':method,'mutation':not readish,'mutation_id':mid,'response':res,'outcome':'CONFIRMED_APPLIED'}
    raise RuntimeError('unknown_vk_tool')

'''
    src=src.replace(marker,vk_code+marker,1)
    class_marker="class H(BaseHTTPRequestHandler):\n"
    if src.count(class_marker)!=1:
        raise RuntimeError('vk unified class anchor mismatch')
    methods=r'''class H(BaseHTTPRequestHandler):
    def is_vk_mcp(self):
        expected=('/vk/mcp/'+VK_MCP_TOKEN) if VK_MCP_TOKEN else ''
        return bool(expected and self.path.split('?',1)[0]==expected)
    def vk_mcp(self):
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':vk_clean(e)},'id':None}); return
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized': self.send_response(204); self.end_headers(); return
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'nd-vk-direct-mcp','version':'2.0.0'},'instructions':'Direct bounded VK access for Nameless Dhamma. Community wall mutations require explicit confirmation and unique mutation IDs.'}}); return
        if method=='ping': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return
        if method=='tools/list': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':vk_tools()}}); return
        if method=='tools/call':
            p=msg.get('params') or {}
            try:
                obj=vk_call(str(p.get('name') or ''),p.get('arguments') or {}); err=False
            except Exception as e:
                obj={'ok':False,'error':vk_clean(e)}; err=True
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],'structuredContent':obj,'isError':err}}); return
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})
'''
    src=src.replace(class_marker,methods,1)
    old_post="    def do_POST(self):\n        if self.is_mcp(): self.mcp(); return\n        self.forward()\n"
    new_post="    def do_POST(self):\n        if self.is_vk_mcp(): self.vk_mcp(); return\n        if self.is_mcp(): self.mcp(); return\n        self.forward()\n"
    if src.count(old_post)!=1:
        raise RuntimeError('vk unified POST anchor mismatch')
    src=src.replace(old_post,new_post,1)
    old_get="    def do_GET(self):\n        if self.path.split('?',1)[0]=='/nd/github/health':\n"
    new_get="    def do_GET(self):\n        if self.path.split('?',1)[0]=='/vk/health':\n            try: self.send_json(200,vk_call('vk_status',{}))\n            except Exception as e: self.send_json(503,{'ok':False,'provider':'vk','error':vk_clean(e)})\n            return\n        if self.path.split('?',1)[0]=='/nd/github/health':\n"
    if src.count(old_get)!=1:
        raise RuntimeError('vk unified GET anchor mismatch')
    src=src.replace(old_get,new_get,1)
    return src

def _patched_urlopen(url,*args,**kwargs):
    target=url.full_url if hasattr(url,'full_url') else str(url)
    r=_real_urlopen(url,*args,**kwargs)
    if target!=BASE_FRONT:
        return r
    data=r.read().decode('utf-8')
    try: r.close()
    except Exception: pass
    return _MemResponse(_patch_base(data).encode('utf-8'))

urllib.request.urlopen=_patched_urlopen
front=_real_urlopen(CURRENT_FRONT,timeout=30).read().decode('utf-8')
print('ND_VK_META_UNIFIED_FRONT_READY',flush=True)
exec(compile(front,'nd_vk_meta_unified_front_v01.py','exec'))
