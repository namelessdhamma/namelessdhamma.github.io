import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
needle="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
assert outer.count(needle)==1

inject=r'''
# ---- ND YouTube Full MCP v0.1 ----
youtube_env_anchor="MEMOS_MCP_PATH_TOKEN=os.environ.get('MEMOS_MCP_PATH_TOKEN','').strip()\n"
assert s.count(youtube_env_anchor)==1
s=s.replace(youtube_env_anchor,youtube_env_anchor+"""
YOUTUBE_MCP_PATH_TOKEN=os.environ.get('ND_YOUTUBE_MCP_PATH_TOKEN','').strip()
YOUTUBE_CLIENT_ID=os.environ.get('ND_YOUTUBE_CLIENT_ID','').strip()
YOUTUBE_CLIENT_SECRET=os.environ.get('ND_YOUTUBE_CLIENT_SECRET','').strip()
YOUTUBE_REFRESH_TOKEN=os.environ.get('ND_YOUTUBE_REFRESH_TOKEN','').strip()
YOUTUBE_WRITES_ENABLED=os.environ.get('ND_SOCIAL_WRITES_ENABLED','true').strip().lower() in ('1','true','yes','on')
""",1)

yt_helpers=r"""
import http.client
import mimetypes

_YT_TOKEN_URL='https://oauth2.googleapis.com/token'
_YT_API='https://www.googleapis.com/youtube/v3/'
_YT_UPLOAD='https://www.googleapis.com/upload/youtube/v3/'
_YT_ANALYTICS='https://youtubeanalytics.googleapis.com/v2/'

def yt_required():
    if not YOUTUBE_CLIENT_ID: raise RuntimeError('youtube_client_id_missing')
    if not YOUTUBE_CLIENT_SECRET: raise RuntimeError('youtube_client_secret_missing')
    if not YOUTUBE_REFRESH_TOKEN: raise RuntimeError('youtube_refresh_token_missing')

def yt_access_token():
    yt_required()
    data=urllib.parse.urlencode({
      'client_id':YOUTUBE_CLIENT_ID,
      'client_secret':YOUTUBE_CLIENT_SECRET,
      'refresh_token':YOUTUBE_REFRESH_TOKEN,
      'grant_type':'refresh_token'
    }).encode('utf-8')
    req=urllib.request.Request(_YT_TOKEN_URL,data=data,method='POST',headers={
      'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json',
      'User-Agent':'ND-YouTube-MCP/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    except HTTPError as e:
        detail=e.read().decode('utf-8','replace')
        raise RuntimeError('youtube_token_http_%s:%s'%(e.code,detail[:700]))
    tok=str(obj.get('access_token') or '')
    if not tok: raise RuntimeError('youtube_access_token_missing')
    return tok

def yt_http(method,url,payload=None,timeout=120):
    token=yt_access_token()
    data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    headers={'Authorization':'Bearer '+token,'Accept':'application/json','User-Agent':'ND-YouTube-MCP/1.0'}
    if data is not None: headers['Content-Type']='application/json; charset=UTF-8'
    req=urllib.request.Request(url,data=data,method=method.upper(),headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            return json.loads(raw or '{}') if raw else {'ok':True}
    except HTTPError as e:
        detail=e.read().decode('utf-8','replace')
        raise RuntimeError('youtube_http_%s:%s'%(e.code,detail[:1600]))

def yt_api(method,resource,query=None,payload=None):
    clean=str(resource or '').strip().lstrip('/')
    if not clean or '..' in clean or '://' in clean: raise RuntimeError('invalid_youtube_resource')
    url=_YT_API+urllib.parse.quote(clean,safe='/')
    if query:
        url+='?'+urllib.parse.urlencode({str(k):str(v) for k,v in query.items() if v is not None},doseq=True)
    return yt_http(method,url,payload)

def yt_channel():
    obj=yt_api('GET','channels',{'part':'id,snippet,statistics,contentDetails,brandingSettings,status','mine':'true','maxResults':'10'})
    items=obj.get('items') or []
    if not items: raise RuntimeError('youtube_authorized_channel_not_found')
    return items[0]

def yt_video(video_id):
    obj=yt_api('GET','videos',{'part':'id,snippet,status,statistics,contentDetails','id':str(video_id)})
    items=obj.get('items') or []
    if not items: raise RuntimeError('youtube_video_not_found')
    return items[0]

def yt_json_object(value,label):
    if isinstance(value,dict): return value
    if value in (None,''): return {}
    try: obj=json.loads(str(value))
    except Exception: raise RuntimeError(label+'_invalid_json')
    if not isinstance(obj,dict): raise RuntimeError(label+'_must_be_object')
    return obj

def yt_json_array(value,label):
    if isinstance(value,list): return value
    if value in (None,''): return []
    try: obj=json.loads(str(value))
    except Exception: raise RuntimeError(label+'_invalid_json')
    if not isinstance(obj,list): raise RuntimeError(label+'_must_be_array')
    return obj

def yt_upload_url(media_url,metadata):
    if not str(media_url).startswith(('https://','http://')): raise RuntimeError('media_url_must_be_http')
    req=urllib.request.Request(media_url,headers={'User-Agent':'ND-YouTube-MCP/1.0'})
    source=urllib.request.urlopen(req,timeout=60)
    try:
        length_raw=(source.headers.get('Content-Length') or '').strip()
        if not length_raw.isdigit(): raise RuntimeError('media_content_length_required')
        length=int(length_raw)
        ctype=(source.headers.get('Content-Type') or '').split(';',1)[0].strip() or mimetypes.guess_type(urllib.parse.urlparse(media_url).path)[0] or 'application/octet-stream'
        token=yt_access_token()
        init_data=json.dumps(metadata,ensure_ascii=False).encode('utf-8')
        init_req=urllib.request.Request(_YT_UPLOAD+'videos?uploadType=resumable&part=snippet,status',data=init_data,method='POST',headers={
          'Authorization':'Bearer '+token,'Content-Type':'application/json; charset=UTF-8',
          'X-Upload-Content-Type':ctype,'X-Upload-Content-Length':str(length),
          'Content-Length':str(len(init_data)),'Accept':'application/json'})
        with urllib.request.urlopen(init_req,timeout=60) as r:
            session=str(r.headers.get('Location') or '')
        if not session: raise RuntimeError('youtube_upload_session_missing')
        parsed=urllib.parse.urlsplit(session)
        cls=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
        conn=cls(parsed.hostname,parsed.port,timeout=600)
        path=parsed.path+(('?'+parsed.query) if parsed.query else '')
        conn.putrequest('PUT',path); conn.putheader('Content-Type',ctype); conn.putheader('Content-Length',str(length)); conn.putheader('Authorization','Bearer '+token); conn.endheaders()
        sent=0
        while True:
            chunk=source.read(1024*1024)
            if not chunk: break
            conn.send(chunk); sent+=len(chunk)
        if sent!=length:
            conn.close(); raise RuntimeError('youtube_upload_length_mismatch')
        res=conn.getresponse(); raw=res.read().decode('utf-8','replace'); status=res.status; conn.close()
        if status not in (200,201): raise RuntimeError('youtube_upload_http_%s:%s'%(status,raw[:1000]))
        return json.loads(raw or '{}')
    finally:
        try: source.close()
        except Exception: pass

def yt_thumbnail(video_id,image_url):
    if not str(image_url).startswith(('https://','http://')): raise RuntimeError('image_url_must_be_http')
    req=urllib.request.Request(image_url,headers={'User-Agent':'ND-YouTube-MCP/1.0'})
    with urllib.request.urlopen(req,timeout=60) as src:
        data=src.read(20*1024*1024+1)
        ctype=(src.headers.get('Content-Type') or '').split(';',1)[0].strip() or 'application/octet-stream'
    if len(data)>20*1024*1024: raise RuntimeError('thumbnail_too_large')
    token=yt_access_token()
    url=_YT_UPLOAD+'thumbnails/set?'+urllib.parse.urlencode({'videoId':str(video_id)})
    req=urllib.request.Request(url,data=data,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':ctype,'Content-Length':str(len(data)),'Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as r: return json.loads(r.read().decode('utf-8','replace') or '{}')
    except HTTPError as e:
        raise RuntimeError('youtube_thumbnail_http_%s:%s'%(e.code,e.read().decode('utf-8','replace')[:1000]))

def youtube_mcp_tools():
    return [
      {'name':'youtube_account','description':'Read the authorized YouTube channel identity, handle, statistics and uploads playlist.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
      {'name':'youtube_list_videos','description':'List videos from the authorized channel uploads playlist.','inputSchema':{'type':'object','properties':{'max_results':{'type':'integer','minimum':1,'maximum':50},'page_token':{'type':'string'}},'additionalProperties':False}},
      {'name':'youtube_get_video','description':'Read metadata, status and statistics for one video.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'}},'required':['video_id'],'additionalProperties':False}},
      {'name':'youtube_update_video','description':'Update title, description, tags, category, privacy, schedule or made-for-kids status.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'},'title':{'type':'string'},'description':{'type':'string'},'tags':{'type':'array','items':{'type':'string'}},'category_id':{'type':'string'},'privacy_status':{'type':'string','enum':['private','public','unlisted']},'publish_at':{'type':'string'},'made_for_kids':{'type':'boolean'}},'required':['video_id'],'additionalProperties':False}},
      {'name':'youtube_delete_video','description':'Permanently delete a video. Requires confirm=true.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'},'confirm':{'type':'boolean'}},'required':['video_id','confirm'],'additionalProperties':False}},
      {'name':'youtube_upload_video_from_url','description':'Upload a video from an HTTP(S) URL using resumable upload.','inputSchema':{'type':'object','properties':{'media_url':{'type':'string'},'title':{'type':'string'},'description':{'type':'string'},'privacy_status':{'type':'string','enum':['private','public','unlisted']},'tags':{'type':'array','items':{'type':'string'}},'category_id':{'type':'string'},'publish_at':{'type':'string'},'made_for_kids':{'type':'boolean'}},'required':['media_url','title'],'additionalProperties':False}},
      {'name':'youtube_set_thumbnail','description':'Set a custom thumbnail from an HTTP(S) image URL.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'},'image_url':{'type':'string'}},'required':['video_id','image_url'],'additionalProperties':False}},
      {'name':'youtube_list_comments','description':'List comment threads for a video.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'},'max_results':{'type':'integer','minimum':1,'maximum':100},'page_token':{'type':'string'}},'required':['video_id'],'additionalProperties':False}},
      {'name':'youtube_create_comment','description':'Create a top-level comment on a video.','inputSchema':{'type':'object','properties':{'video_id':{'type':'string'},'text':{'type':'string'}},'required':['video_id','text'],'additionalProperties':False}},
      {'name':'youtube_reply_comment','description':'Reply to an existing comment.','inputSchema':{'type':'object','properties':{'parent_comment_id':{'type':'string'},'text':{'type':'string'}},'required':['parent_comment_id','text'],'additionalProperties':False}},
      {'name':'youtube_delete_comment','description':'Delete a comment. Requires confirm=true.','inputSchema':{'type':'object','properties':{'comment_id':{'type':'string'},'confirm':{'type':'boolean'}},'required':['comment_id','confirm'],'additionalProperties':False}},
      {'name':'youtube_list_playlists','description':'List playlists owned by the authorized channel.','inputSchema':{'type':'object','properties':{'max_results':{'type':'integer','minimum':1,'maximum':50},'page_token':{'type':'string'}},'additionalProperties':False}},
      {'name':'youtube_create_playlist','description':'Create a playlist.','inputSchema':{'type':'object','properties':{'title':{'type':'string'},'description':{'type':'string'},'privacy_status':{'type':'string','enum':['private','public','unlisted']}},'required':['title'],'additionalProperties':False}},
      {'name':'youtube_delete_playlist','description':'Delete a playlist. Requires confirm=true.','inputSchema':{'type':'object','properties':{'playlist_id':{'type':'string'},'confirm':{'type':'boolean'}},'required':['playlist_id','confirm'],'additionalProperties':False}},
      {'name':'youtube_add_to_playlist','description':'Add a video to a playlist.','inputSchema':{'type':'object','properties':{'playlist_id':{'type':'string'},'video_id':{'type':'string'},'position':{'type':'integer'}},'required':['playlist_id','video_id'],'additionalProperties':False}},
      {'name':'youtube_remove_from_playlist','description':'Remove a playlist item. Requires confirm=true.','inputSchema':{'type':'object','properties':{'playlist_item_id':{'type':'string'},'confirm':{'type':'boolean'}},'required':['playlist_item_id','confirm'],'additionalProperties':False}},
      {'name':'youtube_analytics','description':'Query YouTube Analytics for the authorized channel.','inputSchema':{'type':'object','properties':{'start_date':{'type':'string'},'end_date':{'type':'string'},'metrics':{'type':'string'},'dimensions':{'type':'string'},'filters':{'type':'string'},'sort':{'type':'string'}},'required':['start_date','end_date'],'additionalProperties':False}},
      {'name':'youtube_api','description':'Full low-level YouTube Data API v3 access for GET/POST/PUT/PATCH/DELETE. DELETE requires confirm_destructive=true.','inputSchema':{'type':'object','properties':{'method':{'type':'string','enum':['GET','POST','PUT','PATCH','DELETE']},'resource':{'type':'string'},'query':{'type':'object'},'body':{'type':'object'},'confirm_destructive':{'type':'boolean'}},'required':['method','resource'],'additionalProperties':False}}
    ]

def youtube_tool_call(name,args):
    args=args if isinstance(args,dict) else {}
    if name=='youtube_account':
        item=yt_channel(); sn=item.get('snippet') or {}; st=item.get('statistics') or {}; cd=item.get('contentDetails') or {}
        return {'ok':True,'channel':{'id':item.get('id'),'title':sn.get('title'),'customUrl':sn.get('customUrl'),'description':sn.get('description'),'subscriberCount':st.get('subscriberCount'),'videoCount':st.get('videoCount'),'viewCount':st.get('viewCount'),'uploadsPlaylist':((cd.get('relatedPlaylists') or {}).get('uploads'))}}
    if name=='youtube_list_videos':
        ch=yt_channel(); uploads=((ch.get('contentDetails') or {}).get('relatedPlaylists') or {}).get('uploads')
        q={'part':'id,snippet,contentDetails,status','playlistId':uploads,'maxResults':max(1,min(int(args.get('max_results') or 25),50))}
        if args.get('page_token'): q['pageToken']=str(args['page_token'])
        return {'ok':True,'result':yt_api('GET','playlistItems',q)}
    if name=='youtube_get_video':
        return {'ok':True,'result':yt_video(str(args.get('video_id') or ''))}
    if name=='youtube_update_video':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        vid=str(args.get('video_id') or ''); cur=yt_video(vid); sn=dict(cur.get('snippet') or {}); st=dict(cur.get('status') or {})
        for k,target in [('title','title'),('description','description'),('category_id','categoryId')]:
            if args.get(k) not in (None,''): sn[target]=str(args[k])
        if 'tags' in args: sn['tags']=[str(x) for x in (args.get('tags') or [])]
        if args.get('privacy_status'): st['privacyStatus']=str(args['privacy_status'])
        if args.get('publish_at'): st['publishAt']=str(args['publish_at']); st['privacyStatus']='private'
        if 'made_for_kids' in args: st['selfDeclaredMadeForKids']=bool(args['made_for_kids'])
        return {'ok':True,'result':yt_api('PUT','videos',{'part':'snippet,status'},{'id':vid,'snippet':sn,'status':st})}
    if name=='youtube_delete_video':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        if args.get('confirm') is not True: raise RuntimeError('confirm_required')
        return {'ok':True,'result':yt_api('DELETE','videos',{'id':str(args.get('video_id') or '')})}
    if name=='youtube_upload_video_from_url':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        privacy=str(args.get('privacy_status') or 'private')
        meta={'snippet':{'title':str(args.get('title') or ''),'description':str(args.get('description') or ''),'categoryId':str(args.get('category_id') or '22')},'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':bool(args.get('made_for_kids',False))}}
        if args.get('tags'): meta['snippet']['tags']=[str(x) for x in args['tags']]
        if args.get('publish_at'): meta['status']['privacyStatus']='private'; meta['status']['publishAt']=str(args['publish_at'])
        return {'ok':True,'result':yt_upload_url(str(args.get('media_url') or ''),meta)}
    if name=='youtube_set_thumbnail':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        return {'ok':True,'result':yt_thumbnail(str(args.get('video_id') or ''),str(args.get('image_url') or ''))}
    if name=='youtube_list_comments':
        q={'part':'id,snippet,replies','videoId':str(args.get('video_id') or ''),'maxResults':max(1,min(int(args.get('max_results') or 50),100)),'textFormat':'plainText'}
        if args.get('page_token'): q['pageToken']=str(args['page_token'])
        return {'ok':True,'result':yt_api('GET','commentThreads',q)}
    if name=='youtube_create_comment':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        p={'snippet':{'videoId':str(args.get('video_id') or ''),'topLevelComment':{'snippet':{'textOriginal':str(args.get('text') or '')}}}}
        return {'ok':True,'result':yt_api('POST','commentThreads',{'part':'snippet'},p)}
    if name=='youtube_reply_comment':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        p={'snippet':{'parentId':str(args.get('parent_comment_id') or ''),'textOriginal':str(args.get('text') or '')}}
        return {'ok':True,'result':yt_api('POST','comments',{'part':'snippet'},p)}
    if name=='youtube_delete_comment':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        if args.get('confirm') is not True: raise RuntimeError('confirm_required')
        return {'ok':True,'result':yt_api('DELETE','comments',{'id':str(args.get('comment_id') or '')})}
    if name=='youtube_list_playlists':
        q={'part':'id,snippet,status,contentDetails','mine':'true','maxResults':max(1,min(int(args.get('max_results') or 50),50))}
        if args.get('page_token'): q['pageToken']=str(args['page_token'])
        return {'ok':True,'result':yt_api('GET','playlists',q)}
    if name=='youtube_create_playlist':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        p={'snippet':{'title':str(args.get('title') or ''),'description':str(args.get('description') or '')},'status':{'privacyStatus':str(args.get('privacy_status') or 'private')}}
        return {'ok':True,'result':yt_api('POST','playlists',{'part':'snippet,status'},p)}
    if name=='youtube_delete_playlist':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        if args.get('confirm') is not True: raise RuntimeError('confirm_required')
        return {'ok':True,'result':yt_api('DELETE','playlists',{'id':str(args.get('playlist_id') or '')})}
    if name=='youtube_add_to_playlist':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        sn={'playlistId':str(args.get('playlist_id') or ''),'resourceId':{'kind':'youtube#video','videoId':str(args.get('video_id') or '')}}
        if int(args.get('position',-1))>=0: sn['position']=int(args['position'])
        return {'ok':True,'result':yt_api('POST','playlistItems',{'part':'snippet'},{'snippet':sn})}
    if name=='youtube_remove_from_playlist':
        if not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        if args.get('confirm') is not True: raise RuntimeError('confirm_required')
        return {'ok':True,'result':yt_api('DELETE','playlistItems',{'id':str(args.get('playlist_item_id') or '')})}
    if name=='youtube_analytics':
        q={'ids':'channel==MINE','startDate':str(args.get('start_date') or ''),'endDate':str(args.get('end_date') or ''),'metrics':str(args.get('metrics') or 'views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost')}
        for k in ('dimensions','filters','sort'):
            if args.get(k): q[k]=str(args[k])
        return {'ok':True,'result':yt_http('GET',_YT_ANALYTICS+'reports?'+urllib.parse.urlencode(q))}
    if name=='youtube_api':
        verb=str(args.get('method') or '').upper()
        if verb not in ('GET','POST','PUT','PATCH','DELETE'): raise RuntimeError('unsupported_http_method')
        if verb!='GET' and not YOUTUBE_WRITES_ENABLED: raise RuntimeError('youtube_writes_disabled')
        if verb=='DELETE' and args.get('confirm_destructive') is not True: raise RuntimeError('confirm_required')
        return {'ok':True,'result':yt_api(verb,str(args.get('resource') or ''),args.get('query') or {},None if verb in ('GET','DELETE') else (args.get('body') or {}))}
    raise RuntimeError('unknown_youtube_tool')
"""
assert s.count("class H(BaseHTTPRequestHandler):")==1
s=s.replace("class H(BaseHTTPRequestHandler):",yt_helpers+"\nclass H(BaseHTTPRequestHandler):",1)

yt_method=r"""
    def youtube_mcp(self):
        p=self.path.split('?',1)[0]
        expected=('/nd/youtube/mcp/'+YOUTUBE_MCP_PATH_TOKEN) if YOUTUBE_MCP_PATH_TOKEN else ''
        if not expected or p!=expected: return False
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':clean_error(e)},'id':None}); return True
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized':
            self.send_response(204); self.end_headers(); return True
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{
              'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
              'serverInfo':{'name':'nd-youtube-full-mcp','version':'1.0.0'},
              'instructions':'Nameless Dhamma YouTube MCP with full read/write access to the authorized channel. Destructive delete tools require explicit confirm=true.'
            }}); return True
        if method=='ping':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return True
        if method=='tools/list':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':youtube_mcp_tools()}}); return True
        if method=='tools/call':
            params=msg.get('params') or {}; name=str(params.get('name') or ''); args=params.get('arguments') or {}
            try:
                obj=youtube_tool_call(name,args)
                result={'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],'structuredContent':obj,'isError':False}
            except Exception as e:
                obj={'ok':False,'error':clean_error(e)}
                result={'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],'structuredContent':obj,'isError':True}
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':result}); return True
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}}); return True
"""
anchor_method="    def memos_mcp(self):\n"
assert s.count(anchor_method)==1
s=s.replace(anchor_method,yt_method+"\n"+anchor_method,1)

post_anchor="        if self.memos_mcp(): return\n"
assert s.count(post_anchor)==1
s=s.replace(post_anchor,"        if self.youtube_mcp(): return\n"+post_anchor,1)

print('ND_YOUTUBE_FULL_MCP_PATCH_READY '+json.dumps({
  'configured':bool(YOUTUBE_MCP_PATH_TOKEN and YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN),
  'writes_enabled':bool(YOUTUBE_WRITES_ENABLED),
  'tool_count':len(youtube_mcp_tools())
}),flush=True)
# ---- end ND YouTube Full MCP ----
exec(compile(s,'nd_gateway_youtube_full_mcp_v01_runtime.py','exec'))
'''
outer=outer.replace(needle,inject,1)
exec(compile(outer,'nd_gateway_youtube_full_mcp_v01_outer.py','exec'))
