import json, os, random, subprocess, sys, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_INNER_GATEWAY_PORT','3001'))
INNER_URL='http://127.0.0.1:%d' % INNER_PORT
GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'

# Existing Browserless relay: preserve exactly as an independent failover capability.
RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BROWSERLESS_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
if BROWSERLESS_TOKEN.lower().startswith('bearer '):
    BROWSERLESS_TOKEN=BROWSERLESS_TOKEN[7:].strip()

# Direct VK MCP.
VK_TOKEN=os.environ.get('VK_GROUP_TOKEN','').strip()
VK_API_VERSION=os.environ.get('VK_API_VERSION','5.199').strip()
VK_ALLOWED={int(x.strip()) for x in os.environ.get('VK_ALLOWED_USER_IDS','').replace(';',',').split(',') if x.strip().isdigit()}
VK_MCP_TOKEN=os.environ.get('ND_VK_MCP_ROUTE_TOKEN','').strip()
VK_MCP_PATH=('/vk/mcp/'+VK_MCP_TOKEN) if VK_MCP_TOKEN else ''

# Direct Yandex Disk MCP.
YANDEX_TOKEN=os.environ.get('YANDEX_DISK_TOKEN','').strip()
YANDEX_MCP_TOKEN=os.environ.get('ND_YANDEX_MCP_ROUTE_TOKEN','').strip()
YANDEX_MCP_PATH=('/yandex/mcp/'+YANDEX_MCP_TOKEN) if YANDEX_MCP_TOKEN else ''
YANDEX_API='https://cloud-api.yandex.net/v1/disk'

# Keep previous VK runtime alive on an internal port; all non-MCP/non-relay traffic is proxied to it.
inner_path='/tmp/nd_inner_gateway.py'
src=urllib.request.urlopen(GATEWAY_URL,timeout=30).read()
open(inner_path,'wb').write(src)
env=dict(os.environ)
env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)

def clean_error(x):
    s=str(x)
    for secret in (BROWSERLESS_TOKEN,VK_TOKEN,VK_MCP_TOKEN,YANDEX_TOKEN,YANDEX_MCP_TOKEN):
        if secret:
            s=s.replace(secret,'[REDACTED]')
            s=s.replace(urllib.parse.quote(secret,safe=''),'[REDACTED]')
    return s[:1600]

# ---------------- Browserless relay (preserved) ----------------

def parse_sse(raw):
    text=raw.decode('utf-8','replace')
    vals=[]
    for line in text.splitlines():
        if line.startswith('data: '):
            try: vals.append(json.loads(line[6:]))
            except Exception: pass
    if not vals:
        raise RuntimeError('Browserless MCP returned no parsable SSE data')
    return vals[-1]

def post_browserless_mcp(payload,session_id=None):
    if not BROWSERLESS_TOKEN:
        raise RuntimeError('browserless_not_configured')
    headers={
        'Authorization':'Bearer '+BROWSERLESS_TOKEN,
        'Accept':'application/json, text/event-stream',
        'Content-Type':'application/json',
        'User-Agent':'ND-True-Doctor-Railway-Relay/2.0'
    }
    if session_id:
        headers['Mcp-Session-Id']=session_id
        headers['MCP-Protocol-Version']='2025-06-18'
    req=urllib.request.Request(
        'https://mcp.browserless.io/mcp',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            return r.status,dict(r.headers.items()),r.read()
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('Browserless MCP HTTP %s: %s'%(e.code,clean_error(body)))

ALLOWED_BL_TOOLS={
    'browserless_export','browserless_skill','browserless_agent','browserless_search',
    'browserless_performance','browserless_account','browserless_usage',
    'browserless_sessions','browserless_logs','browserless_smartscraper',
    'browserless_function','browserless_map','browserless_crawl','browserless_profiles'
}

def browserless_tool_call(name,args=None):
    if name not in ALLOWED_BL_TOOLS:
        raise RuntimeError('tool is not allowlisted')
    init={
        'jsonrpc':'2.0','id':1,'method':'initialize',
        'params':{
            'protocolVersion':'2025-06-18',
            'capabilities':{},
            'clientInfo':{'name':'ND True Doctor Railway Relay','version':'2.0'}
        }
    }
    status,headers,raw=post_browserless_mcp(init)
    if status!=200: raise RuntimeError('initialize failed')
    init_msg=parse_sse(raw)
    sid=headers.get('Mcp-Session-Id') or headers.get('mcp-session-id')
    if not sid: raise RuntimeError('Browserless MCP did not return a session id')
    post_browserless_mcp({'jsonrpc':'2.0','method':'notifications/initialized','params':{}},sid)
    status,_,raw=post_browserless_mcp({
        'jsonrpc':'2.0','id':2,'method':'tools/call',
        'params':{'name':name,'arguments':args or {}}
    },sid)
    if status!=200: raise RuntimeError('tools/call failed')
    return {
        'ok':True,
        'provider':'Browserless',
        'serverInfo':((init_msg.get('result') or {}).get('serverInfo') or {}),
        'tool':name,
        'response':parse_sse(raw)
    }

def browserless_profiles():
    try:
        out=browserless_tool_call('browserless_profiles',{
            'limit':20,'offset':0,
            '_prompt':'ND Doctor Railway relay verification: list Browserless profiles only; no mutation.'
        })
        return 200,out
    except Exception as e:
        print('BROWSERLESS_RAILWAY_RELAY_ERROR',clean_error(e),flush=True)
        return 502,{'ok':False,'provider':'Browserless','error':clean_error(e)}

# ---------------- MCP common ----------------

def mcp_result(i,r): return {'jsonrpc':'2.0','id':i,'result':r}
def mcp_error(i,c,m): return {'jsonrpc':'2.0','id':i,'error':{'code':c,'message':m}}

RO={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True}
WR={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':False,'openWorldHint':True}
DEL={'readOnlyHint':False,'destructiveHint':True,'idempotentHint':False,'openWorldHint':True}

def common_initialize(name,version,instructions,req):
    rid=req.get('id')
    params=req.get('params') or {}
    ver=params.get('protocolVersion') or '2025-06-18'
    return 200,mcp_result(rid,{
        'protocolVersion':ver,
        'capabilities':{'tools':{'listChanged':False}},
        'serverInfo':{'name':name,'version':version},
        'instructions':instructions
    })

# ---------------- VK MCP ----------------

def vk(method,params=None,timeout=25):
    if not VK_TOKEN: raise RuntimeError('VK_GROUP_TOKEN missing')
    p=dict(params or {})
    p['access_token']=VK_TOKEN
    p['v']=VK_API_VERSION
    data=urllib.parse.urlencode({k:str(v) for k,v in p.items() if v is not None}).encode()
    req=urllib.request.Request(
        'https://api.vk.com/method/'+method,
        data=data,method='POST',
        headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'nd-vk-mcp/1.2'}
    )
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=json.loads(r.read().decode())
    if 'error' in body:
        e=body['error']
        raise RuntimeError('VK %s error %s: %s'%(method,e.get('error_code'),e.get('error_msg')))
    return body.get('response')

def vk_require_peer(value):
    try: peer=int(value)
    except Exception: raise RuntimeError('peer_id must be an integer')
    if not VK_ALLOWED: raise RuntimeError('VK_ALLOWED_USER_IDS is empty; access is fail-closed')
    if peer not in VK_ALLOWED: raise RuntimeError('peer_id is outside VK_ALLOWED_USER_IDS')
    return peer

def vk_tools():
    return [
      {'name':'vk_status','description':'Verify direct VK API reachability and community identity without returning message contents.',
       'inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':RO},
      {'name':'vk_get_users','description':'Read basic VK profile data for allow-listed users.',
       'inputSchema':{'type':'object','properties':{'user_ids':{'type':'array','items':{'type':'integer'}}},'additionalProperties':False},'annotations':RO},
      {'name':'vk_get_conversations','description':'Read recent direct VK conversations, filtered to allow-listed users.',
       'inputSchema':{'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':100,'default':20},'offset':{'type':'integer','minimum':0,'default':0},'unread_only':{'type':'boolean','default':False}},'additionalProperties':False},'annotations':RO},
      {'name':'vk_get_history','description':'Read message history for one allow-listed VK peer.',
       'inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'count':{'type':'integer','minimum':1,'maximum':100,'default':30},'offset':{'type':'integer','minimum':0,'default':0}},'required':['peer_id'],'additionalProperties':False},'annotations':RO},
      {'name':'vk_send_message','description':'Send a plain-text VK message to one allow-listed peer.',
       'inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'},'message':{'type':'string','minLength':1,'maxLength':3500},'reply_to':{'type':'integer'}},'required':['peer_id','message'],'additionalProperties':False},'annotations':WR},
      {'name':'vk_mark_as_read','description':'Mark messages from one allow-listed VK peer as read.',
       'inputSchema':{'type':'object','properties':{'peer_id':{'type':'integer'}},'required':['peer_id'],'additionalProperties':False},'annotations':WR},
    ]

def vk_call(name,args):
    args=args or {}
    if name=='vk_status':
        return {'ok':True,'transport':'DIRECT_VK_API','api_version':VK_API_VERSION,'allowed_peer_count':len(VK_ALLOWED),'group':vk('groups.getById')}
    if name=='vk_get_users':
        ids=args.get('user_ids')
        ids=sorted(VK_ALLOWED) if ids is None else [vk_require_peer(x) for x in ids]
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
            if pid in VK_ALLOWED: filtered.append(item)
        return {'ok':True,'response':{'count':len(filtered),'items':filtered}}
    if name=='vk_get_history':
        peer=vk_require_peer(args.get('peer_id'))
        return {'ok':True,'response':vk('messages.getHistory',{'peer_id':peer,'count':max(1,min(int(args.get('count',30)),100)),'offset':max(0,int(args.get('offset',0))),'rev':0})}
    if name=='vk_send_message':
        peer=vk_require_peer(args.get('peer_id'));message=str(args.get('message') or '').strip()
        if not message: raise RuntimeError('message must not be empty')
        if len(message)>3500: raise RuntimeError('message exceeds 3500-character MCP limit')
        p={'peer_id':peer,'random_id':random.randint(1,2000000000),'message':message}
        if args.get('reply_to') is not None:p['reply_to']=int(args['reply_to'])
        return {'ok':True,'response':vk('messages.send',p)}
    if name=='vk_mark_as_read':
        peer=vk_require_peer(args.get('peer_id'))
        return {'ok':True,'response':vk('messages.markAsRead',{'peer_id':peer})}
    raise RuntimeError('unknown VK tool: '+str(name))

def vk_dispatch(req):
    if not isinstance(req,dict):return 400,mcp_error(None,-32600,'Invalid Request')
    rid=req.get('id');method=req.get('method');params=req.get('params') or {}
    if method=='initialize':
        return common_initialize('ND VK','1.2.0','Direct bounded VK access. Make remains an independent fallback.',req)
    if method in ('notifications/initialized','notifications/cancelled'):return 202,None
    if method=='ping':return 200,mcp_result(rid,{})
    if method=='tools/list':return 200,mcp_result(rid,{'tools':vk_tools()})
    if method=='tools/call':
        try:
            data=vk_call(params.get('name'),params.get('arguments') or {})
            return 200,mcp_result(rid,{'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data,'isError':False})
        except Exception as e:
            return 200,mcp_result(rid,{'content':[{'type':'text','text':clean_error(e)}],'isError':True})
    return 404,mcp_error(rid,-32601,'Method not found')

# ---------------- Yandex Disk direct API + MCP ----------------

def yandex_request(method,endpoint,query=None,body=None,timeout=45):
    if not YANDEX_TOKEN: raise RuntimeError('YANDEX_DISK_TOKEN missing')
    url=YANDEX_API+endpoint
    if query:
        url+='?'+urllib.parse.urlencode({k:v for k,v in query.items() if v is not None},doseq=True)
    headers={'Authorization':'OAuth '+YANDEX_TOKEN,'Accept':'application/json','User-Agent':'nd-yandex-mcp/1.0'}
    data=None
    if body is not None:
        data=json.dumps(body,ensure_ascii=False).encode('utf-8')
        headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=data,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read()
            ct=(r.headers.get('Content-Type') or '').lower()
            if not raw:return {'status':r.status}
            if 'json' in ct:
                out=json.loads(raw.decode('utf-8','replace'))
                if isinstance(out,dict):out.setdefault('_http_status',r.status)
                return out
            return {'status':r.status,'text':raw.decode('utf-8','replace')[:8000]}
    except HTTPError as e:
        try:
            raw=e.read().decode('utf-8','replace')
            obj=json.loads(raw) if raw else {}
        except Exception:
            obj={'description':raw[:1500] if 'raw' in locals() else ''}
        msg=obj.get('message') or obj.get('description') or ('HTTP %s'%e.code)
        raise RuntimeError('Yandex Disk HTTP %s: %s'%(e.code,msg))

def yandex_download_href(path):
    out=yandex_request('GET','/resources/download',{'path':path})
    href=out.get('href') if isinstance(out,dict) else None
    if not href:raise RuntimeError('Yandex Disk did not return a download href')
    return href

def yandex_upload_bytes(path,data,overwrite=True,content_type='application/octet-stream'):
    out=yandex_request('GET','/resources/upload',{'path':path,'overwrite':'true' if overwrite else 'false'})
    href=out.get('href') if isinstance(out,dict) else None
    if not href:raise RuntimeError('Yandex Disk did not return an upload href')
    req=urllib.request.Request(href,data=data,method='PUT',headers={'Content-Type':content_type,'User-Agent':'nd-yandex-mcp/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            r.read()
            return {'status':r.status,'path':path,'bytes':len(data)}
    except HTTPError as e:
        try:msg=e.read().decode('utf-8','replace')[:1200]
        except Exception:msg=''
        raise RuntimeError('Yandex upload HTTP %s: %s'%(e.code,msg))

def yandex_tools():
    return [
      {'name':'yandex_status','description':'Verify direct Yandex Disk API access and return storage/account quota metadata.',
       'inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':RO},
      {'name':'yandex_list','description':'List files and folders in a Yandex Disk directory.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string','default':'disk:/'},'limit':{'type':'integer','minimum':1,'maximum':100,'default':50},'offset':{'type':'integer','minimum':0,'default':0},'sort':{'type':'string','default':'name'}},'additionalProperties':False},'annotations':RO},
      {'name':'yandex_stat','description':'Read metadata for one Yandex Disk resource.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'annotations':RO},
      {'name':'yandex_read_text','description':'Download and read a UTF-8/text-like Yandex Disk file with a bounded character limit.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'},'max_chars':{'type':'integer','minimum':1,'maximum':200000,'default':50000}},'required':['path'],'additionalProperties':False},'annotations':RO},
      {'name':'yandex_get_download_url','description':'Return a temporary direct download URL for a Yandex Disk file.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'annotations':RO},
      {'name':'yandex_write_text','description':'Create or replace a UTF-8 text file on Yandex Disk.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'},'text':{'type':'string','maxLength':1000000},'overwrite':{'type':'boolean','default':True}},'required':['path','text'],'additionalProperties':False},'annotations':WR},
      {'name':'yandex_mkdir','description':'Create a folder on Yandex Disk.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'annotations':WR},
      {'name':'yandex_copy','description':'Copy a Yandex Disk file or folder.',
       'inputSchema':{'type':'object','properties':{'from_path':{'type':'string'},'to_path':{'type':'string'},'overwrite':{'type':'boolean','default':False}},'required':['from_path','to_path'],'additionalProperties':False},'annotations':WR},
      {'name':'yandex_move','description':'Move or rename a Yandex Disk file or folder.',
       'inputSchema':{'type':'object','properties':{'from_path':{'type':'string'},'to_path':{'type':'string'},'overwrite':{'type':'boolean','default':False}},'required':['from_path','to_path'],'additionalProperties':False},'annotations':WR},
      {'name':'yandex_delete','description':'Delete a Yandex Disk file or folder; by default it is moved to Trash.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'},'permanently':{'type':'boolean','default':False}},'required':['path'],'additionalProperties':False},'annotations':DEL},
      {'name':'yandex_publish','description':'Publish a Yandex Disk resource and return its metadata/public link when available.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'annotations':WR},
      {'name':'yandex_unpublish','description':'Remove public access from a published Yandex Disk resource.',
       'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'annotations':WR},
    ]

def yandex_call(name,args):
    args=args or {}
    if name=='yandex_status':
        data=yandex_request('GET','/')
        return {'ok':True,'transport':'DIRECT_YANDEX_DISK_API','total_space':data.get('total_space'),'used_space':data.get('used_space'),'trash_size':data.get('trash_size'),'system_folders':data.get('system_folders')}
    if name=='yandex_list':
        path=str(args.get('path') or 'disk:/')
        data=yandex_request('GET','/resources',{'path':path,'limit':max(1,min(int(args.get('limit',50)),100)),'offset':max(0,int(args.get('offset',0))),'sort':str(args.get('sort') or 'name')})
        emb=(data.get('_embedded') or {}) if isinstance(data,dict) else {}
        items=[]
        for it in emb.get('items') or []:
            items.append({k:it.get(k) for k in ('name','path','type','size','created','modified','mime_type','md5','sha256','public_url') if k in it})
        return {'ok':True,'path':path,'total':emb.get('total'),'limit':emb.get('limit'),'offset':emb.get('offset'),'items':items}
    if name=='yandex_stat':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        data=yandex_request('GET','/resources',{'path':path,'limit':1})
        keep=('name','path','type','size','created','modified','mime_type','md5','sha256','public_url','public_key','media_type','file')
        return {'ok':True,'resource':{k:data.get(k) for k in keep if isinstance(data,dict) and k in data}}
    if name=='yandex_read_text':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        max_chars=max(1,min(int(args.get('max_chars',50000)),200000))
        href=yandex_download_href(path)
        req=urllib.request.Request(href,headers={'User-Agent':'nd-yandex-mcp/1.0'})
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read(min(max_chars*4+4,800004))
            truncated=(len(raw)>=min(max_chars*4+4,800004))
        text=raw.decode('utf-8','replace')
        if len(text)>max_chars:
            text=text[:max_chars];truncated=True
        return {'ok':True,'path':path,'text':text,'truncated':truncated}
    if name=='yandex_get_download_url':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        return {'ok':True,'path':path,'href':yandex_download_href(path),'temporary':True}
    if name=='yandex_write_text':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        text=str(args.get('text') if args.get('text') is not None else '')
        return {'ok':True,'response':yandex_upload_bytes(path,text.encode('utf-8'),bool(args.get('overwrite',True)),'text/plain; charset=utf-8')}
    if name=='yandex_mkdir':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        return {'ok':True,'response':yandex_request('PUT','/resources',{'path':path})}
    if name=='yandex_copy':
        a=str(args.get('from_path') or '');b=str(args.get('to_path') or '')
        if not a or not b:raise RuntimeError('from_path and to_path are required')
        return {'ok':True,'response':yandex_request('POST','/resources/copy',{'from':a,'path':b,'overwrite':'true' if args.get('overwrite',False) else 'false'})}
    if name=='yandex_move':
        a=str(args.get('from_path') or '');b=str(args.get('to_path') or '')
        if not a or not b:raise RuntimeError('from_path and to_path are required')
        return {'ok':True,'response':yandex_request('POST','/resources/move',{'from':a,'path':b,'overwrite':'true' if args.get('overwrite',False) else 'false'})}
    if name=='yandex_delete':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        return {'ok':True,'response':yandex_request('DELETE','/resources',{'path':path,'permanently':'true' if args.get('permanently',False) else 'false'})}
    if name=='yandex_publish':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        op=yandex_request('PUT','/resources/publish',{'path':path})
        meta=yandex_request('GET','/resources',{'path':path,'limit':1})
        return {'ok':True,'operation':op,'public_url':meta.get('public_url'),'public_key':meta.get('public_key')}
    if name=='yandex_unpublish':
        path=str(args.get('path') or '')
        if not path:raise RuntimeError('path is required')
        return {'ok':True,'response':yandex_request('DELETE','/resources/publish',{'path':path})}
    raise RuntimeError('unknown Yandex tool: '+str(name))

def yandex_dispatch(req):
    if not isinstance(req,dict):return 400,mcp_error(None,-32600,'Invalid Request')
    rid=req.get('id');method=req.get('method');params=req.get('params') or {}
    if method=='initialize':
        return common_initialize('ND Yandex Disk','1.0.0','Direct Yandex Disk API access. Existing automation routes remain independent fallbacks.',req)
    if method in ('notifications/initialized','notifications/cancelled'):return 202,None
    if method=='ping':return 200,mcp_result(rid,{})
    if method=='tools/list':return 200,mcp_result(rid,{'tools':yandex_tools()})
    if method=='tools/call':
        try:
            data=yandex_call(params.get('name'),params.get('arguments') or {})
            return 200,mcp_result(rid,{'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data,'isError':False})
        except Exception as e:
            return 200,mcp_result(rid,{'content':[{'type':'text','text':clean_error(e)}],'isError':True})
    return 404,mcp_error(rid,-32601,'Method not found')

# ---------------- Public front gateway ----------------

class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass

    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        if raw:self.wfile.write(raw)

    def origin_ok(self):
        origin=(self.headers.get('Origin') or '').strip()
        return (not origin) or origin in ('https://chatgpt.com','https://chat.openai.com')

    def is_vk_mcp(self):
        return bool(VK_MCP_PATH) and self.path.split('?',1)[0]==VK_MCP_PATH

    def is_yandex_mcp(self):
        return bool(YANDEX_MCP_PATH) and self.path.split('?',1)[0]==YANDEX_MCP_PATH

    def handle_mcp(self,dispatcher):
        if not self.origin_ok():
            self.send_json(403,mcp_error(None,-32000,'Forbidden origin'));return
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            req=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            status,body=dispatcher(req)
            if body is None:
                self.send_response(status);self.send_header('Content-Length','0');self.end_headers()
            else:self.send_json(status,body)
        except Exception as e:
            self.send_json(400,mcp_error(None,-32700,clean_error(e)))

    def relay_browserless(self):
        expected=('/browserless/profiles/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            code,obj=browserless_profiles()
            self.send_json(code,obj)
            return True
        return False

    def bootstrap_browserless(self):
        global BROWSERLESS_TOKEN
        expected=('/browserless/bootstrap/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if not expected or self.path.split('?',1)[0]!=expected:
            return False
        if BROWSERLESS_TOKEN:
            self.send_json(409,{'ok':False,'error':'browserless_already_configured'})
            return True
        auth=(self.headers.get('Authorization') or '').strip()
        if not auth.startswith('Bearer '):
            self.send_json(401,{'ok':False,'error':'missing_bearer'})
            return True
        token=auth[7:].strip()
        if len(token)<20:
            self.send_json(400,{'ok':False,'error':'invalid_token_shape'})
            return True
        BROWSERLESS_TOKEN=token
        self.send_json(200,{'ok':True,'configured':True,'persistence':'process_memory'})
        return True

    def forward(self):
        n=int(self.headers.get('Content-Length','0') or 0)
        body=self.rfile.read(n) if n else None
        url=INNER_URL+self.path
        headers={}
        for k,v in self.headers.items():
            if k.lower() in ('host','connection','content-length','transfer-encoding'):continue
            headers[k]=v
        req=urllib.request.Request(url,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read();status=r.status;rh=r.headers
        except HTTPError as e:
            raw=e.read();status=e.code;rh=e.headers
        except Exception as e:
            self.send_json(502,{'error':'inner_gateway_unavailable','detail':clean_error(e)});return
        self.send_response(status)
        for k,v in rh.items():
            if k.lower() in ('connection','transfer-encoding','content-length'):continue
            self.send_header(k,v)
        self.send_header('Content-Length',str(len(raw)));self.end_headers()
        if raw:self.wfile.write(raw)

    def do_GET(self):
        if self.is_vk_mcp() or self.is_yandex_mcp():
            self.send_response(405);self.send_header('Allow','POST');self.send_header('Content-Length','0');self.end_headers();return
        if self.relay_browserless():return
        self.forward()

    def do_DELETE(self):
        if self.is_vk_mcp() or self.is_yandex_mcp():
            self.send_response(405);self.send_header('Allow','POST');self.send_header('Content-Length','0');self.end_headers();return
        self.forward()

    def do_POST(self):
        if self.is_vk_mcp():self.handle_mcp(vk_dispatch);return
        if self.is_yandex_mcp():self.handle_mcp(yandex_dispatch);return
        if self.bootstrap_browserless():return
        expected=('/browserless/call/'+RELAY_TOKEN) if RELAY_TOKEN else ''
        if expected and self.path.split('?',1)[0]==expected:
            try:
                n=int(self.headers.get('Content-Length','0') or 0)
                body=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                name=str(body.get('tool') or '')
                args=body.get('arguments') or {}
                if not isinstance(args,dict):raise RuntimeError('arguments must be an object')
                self.send_json(200,browserless_tool_call(name,args));return
            except Exception as e:
                self.send_json(400,{'ok':False,'error':clean_error(e)});return
        self.forward()

print('ND_MULTI_FRONT_V1_START '+json.dumps({
    'port':PORT,'inner_port':INNER_PORT,
    'browserless_relay':bool(RELAY_TOKEN),'browserless_configured':bool(BROWSERLESS_TOKEN),
    'vk_mcp':bool(VK_MCP_PATH),'vk_tools':len(vk_tools()),
    'yandex_mcp':bool(YANDEX_MCP_PATH),'yandex_tools':len(yandex_tools()),
    'yandex_token_present':bool(YANDEX_TOKEN)
}),flush=True)

# Bounded wait for inner legacy health; failure does not prevent MCP routes from coming up.
for _ in range(50):
    try:
        urllib.request.urlopen(INNER_URL+'/health',timeout=1).read()
        print('ND_INNER_GATEWAY_READY',flush=True);break
    except Exception:time.sleep(0.2)

ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
