import base64, json, os, subprocess, sys, urllib.parse, urllib.request, http.client, secrets, time, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3100'))
INNER_PORT=int(os.environ.get('ND_GITHUB_INNER_HTTP_PORT','3000'))
GITHUB_PAT=os.environ.get('ND_GITHUB_PAT','').strip()
PATH_TOKEN=os.environ.get('ND_GITHUB_MCP_PATH_TOKEN','').strip()
OWNER=os.environ.get('ND_GITHUB_OWNER','namelessdhamma').strip() or 'namelessdhamma'
INLINE_MAX=int(os.environ.get('ND_GITHUB_INLINE_MAX','600000') or '600000')
VK_TOKEN=os.environ.get('VK_GROUP_TOKEN','').strip()
VK_SCREEN=os.environ.get('VK_GROUP_SCREEN_NAME','namelessdhamma').strip().lstrip('@') or 'namelessdhamma'
VK_VERSION=os.environ.get('VK_API_VERSION','5.199').strip() or '5.199'
VK_VIDEO_PATH_TOKEN=(os.environ.get('ND_VK_VIDEO_MCP_PATH_TOKEN','') or os.environ.get('ND_VK_MCP_ROUTE_TOKEN','')).strip()
VK_VIDEO_MUTATIONS=set()
VK_ID_CLIENT_ID='54776731'
VK_ID_REDIRECT='https://nd-qstash-control-v2-production.up.railway.app/vk/oauth/callback'
VK_OAUTH_PENDING={}
VK_OAUTH_FILE='/data/vk-video-oauth.json'

LAUNCHER=os.environ.get('ND_VK_V19_PINNED_FRONT_LAUNCHER','')
if not LAUNCHER:
    raise RuntimeError('ND_VK_V19_PINNED_FRONT_LAUNCHER is not configured')
inner_path='/tmp/nd_current_gateway.py'
with open(inner_path,'w',encoding='utf-8') as f:
    f.write(LAUNCHER)
env=dict(os.environ)
env['PORT']=str(INNER_PORT)
child=subprocess.Popen([sys.executable,'-u',inner_path],env=env)
INNER='http://127.0.0.1:%d' % INNER_PORT

def clean(x):
    z=str(x)
    for secret in (GITHUB_PAT,PATH_TOKEN,VK_TOKEN,VK_VIDEO_PATH_TOKEN):
        if secret: z=z.replace(secret,'[REDACTED]')
    return z[:2000]

def repo_base(repo):
    repo=str(repo or '').strip()
    if not repo or '/' in repo or repo in ('.','..'): raise RuntimeError('invalid_repo')
    return '/repos/'+urllib.parse.quote(OWNER,safe='')+'/'+urllib.parse.quote(repo,safe='')

def q(v): return urllib.parse.quote(str(v),safe='')

def gh(path,method='GET',body=None,accept='application/vnd.github+json',raw=False,timeout=60):
    if not GITHUB_PAT: raise RuntimeError('github_not_configured')
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    headers={
      'Authorization':'Bearer '+GITHUB_PAT,
      'Accept':accept,
      'X-GitHub-Api-Version':'2022-11-28',
      'User-Agent':'ND-GitHub-MCP/1.0'
    }
    if data is not None: headers['Content-Type']='application/json'
    req=urllib.request.Request('https://api.github.com'+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            b=r.read()
            if raw: return b
            return json.loads(b.decode('utf-8','replace')) if b else {}
    except HTTPError as e:
        b=e.read().decode('utf-8','replace')
        raise RuntimeError('github_http_%s:%s'%(e.code,clean(b or e.reason)))


def vk_api_call(method,params=None,timeout=60):
    if not VK_TOKEN:
        raise RuntimeError('vk_not_configured')
    form=dict(params or {})
    form['access_token']=VK_TOKEN
    form['v']=VK_VERSION
    req=urllib.request.Request(
        'https://api.vk.com/method/'+str(method).strip(),
        data=urllib.parse.urlencode({k:str(v) for k,v in form.items() if v is not None}).encode('utf-8'),
        headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-MCP/1.0'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    except Exception as e:
        raise RuntimeError('vk_transport:'+clean(e))
    if obj.get('error'):
        err=obj.get('error') or {}
        raise RuntimeError('vk_api_%s:%s'%(err.get('error_code'),clean(err.get('error_msg'))))
    return obj.get('response')


def vk_oauth_load():
    try:
        with open(VK_OAUTH_FILE,'r',encoding='utf-8') as f:
            obj=json.load(f)
        return obj if isinstance(obj,dict) else None
    except FileNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError('vk_oauth_load:'+clean(e))

def vk_oauth_store(tok,device_id):
    if not isinstance(tok,dict):
        raise RuntimeError('vk_oauth_invalid_bundle')
    access=str(tok.get('access_token') or '')
    refresh=str(tok.get('refresh_token') or '')
    if not access or not refresh or not device_id:
        raise RuntimeError('vk_oauth_incomplete_bundle')
    now=int(time.time())
    bundle={
      'client_id':VK_ID_CLIENT_ID,
      'device_id':str(device_id),
      'access_token':access,
      'refresh_token':refresh,
      'token_type':tok.get('token_type'),
      'scope':tok.get('scope'),
      'user_id':tok.get('user_id'),
      'obtained_at':now,
      'expires_at':now+max(60,int(tok.get('expires_in') or 3600)),
    }
    os.makedirs(os.path.dirname(VK_OAUTH_FILE),exist_ok=True)
    tmp=VK_OAUTH_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(bundle,f,ensure_ascii=False,separators=(',',':'))
        f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o600)
    os.replace(tmp,VK_OAUTH_FILE)
    try: os.chmod(VK_OAUTH_FILE,0o600)
    except Exception: pass
    return bundle

def vk_oauth_refresh(bundle):
    refresh=str((bundle or {}).get('refresh_token') or '')
    device=str((bundle or {}).get('device_id') or '')
    if not refresh or not device:
        raise RuntimeError('vk_oauth_refresh_missing_state')
    state=secrets.token_urlsafe(32)
    form={
      'grant_type':'refresh_token',
      'refresh_token':refresh,
      'client_id':VK_ID_CLIENT_ID,
      'device_id':device,
      'state':state,
    }
    req=urllib.request.Request(
      'https://id.vk.ru/oauth2/auth',
      data=urllib.parse.urlencode(form).encode('utf-8'),
      headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-MCP/1.0'},
      method='POST',
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            tok=json.loads(r.read().decode('utf-8','replace') or '{}')
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace')
        raise RuntimeError('vk_oauth_refresh_http_%s:%s'%(e.code,clean(raw or e.reason)))
    if tok.get('error'):
        raise RuntimeError('vk_oauth_refresh:'+clean(tok.get('error_description') or tok.get('error')))
    if str(tok.get('state') or state)!=state:
        raise RuntimeError('vk_oauth_refresh_state_mismatch')
    return vk_oauth_store(tok,device)

def vk_video_user_token(force_refresh=False):
    bundle=vk_oauth_load()
    if not bundle:
        raise RuntimeError('vk_user_oauth_required')
    now=int(time.time())
    if not force_refresh and bundle.get('access_token') and int(bundle.get('expires_at') or 0)>now+120:
        return str(bundle['access_token']),bundle
    bundle=vk_oauth_refresh(bundle)
    return str(bundle['access_token']),bundle

def vk_api_call_with_token(method,params,token,timeout=60):
    form=dict(params or {})
    form['access_token']=token
    form['v']=VK_VERSION
    req=urllib.request.Request(
        'https://api.vk.com/method/'+str(method).strip(),
        data=urllib.parse.urlencode({k:str(v) for k,v in form.items() if v is not None}).encode('utf-8'),
        headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-MCP/1.0'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    except Exception as e:
        raise RuntimeError('vk_transport:'+clean(e))
    return obj

def vk_video_user_api(method,params=None,timeout=60):
    token,_=vk_video_user_token(False)
    obj=vk_api_call_with_token(method,params or {},token,timeout)
    err=obj.get('error') if isinstance(obj,dict) else None
    if isinstance(err,dict) and int(err.get('error_code') or 0)==5:
        token,_=vk_video_user_token(True)
        obj=vk_api_call_with_token(method,params or {},token,timeout)
        err=obj.get('error') if isinstance(obj,dict) else None
    if err:
        raise RuntimeError('vk_api_%s:%s'%(err.get('error_code'),clean(err.get('error_msg'))))
    return obj.get('response')

def vk_oauth_status():
    b=vk_oauth_load()
    if not b:
        return {'stored':False}
    return {
      'stored':True,
      'client_id':b.get('client_id'),
      'user_id':b.get('user_id'),
      'scope':b.get('scope'),
      'expires_at':b.get('expires_at'),
      'refresh_token_present':bool(b.get('refresh_token')),
    }

def vk_video_group():
    obj=vk_api_call('groups.getById',{'group_id':VK_SCREEN,'fields':'name,screen_name,members_count'})
    rows=obj.get('groups') if isinstance(obj,dict) else obj
    if not isinstance(rows,list) or not rows:
        raise RuntimeError('vk_group_not_resolved')
    g=rows[0]
    return {'id':int(g.get('id')),'name':g.get('name'),'screen_name':g.get('screen_name'),'members_count':g.get('members_count')}

def vk_video_guard(mutation_id,confirm):
    mid=str(mutation_id or '').strip()
    if confirm is not True:
        raise RuntimeError('confirm_true_required')
    if not mid:
        raise RuntimeError('mutation_id_required')
    if mid in VK_VIDEO_MUTATIONS:
        raise RuntimeError('duplicate_mutation_id')
    VK_VIDEO_MUTATIONS.add(mid)
    return mid

def vk_video_upload_stream(upload_url,file_url,timeout=1800):
    src_req=urllib.request.Request(str(file_url),headers={'User-Agent':'ND-VK-VIDEO-MCP/1.0'},method='GET')
    src=urllib.request.urlopen(src_req,timeout=60)
    try:
        size_header=src.headers.get('Content-Length')
        if not size_header:
            raise RuntimeError('source_content_length_required')
        size=int(size_header)
        if size<=0:
            raise RuntimeError('source_empty')
        ctype=(src.headers.get('Content-Type') or 'video/mp4').split(';')[0].strip() or 'video/mp4'
        boundary='----NDVK'+secrets.token_hex(12)
        prefix=('--'+boundary+'\r\nContent-Disposition: form-data; name="video_file"; filename="video.mp4"\r\nContent-Type: '+ctype+'\r\n\r\n').encode('utf-8')
        suffix=('\r\n--'+boundary+'--\r\n').encode('utf-8')
        total=len(prefix)+size+len(suffix)
        u=urllib.parse.urlparse(str(upload_url))
        if u.scheme!='https' or not u.hostname:
            raise RuntimeError('vk_upload_url_invalid')
        path=(u.path or '/')+(('?'+u.query) if u.query else '')
        conn=http.client.HTTPSConnection(u.hostname,u.port or 443,timeout=timeout)
        try:
            conn.putrequest('POST',path)
            conn.putheader('Content-Type','multipart/form-data; boundary='+boundary)
            conn.putheader('Content-Length',str(total))
            conn.putheader('User-Agent','ND-VK-VIDEO-MCP/1.0')
            conn.endheaders()
            conn.send(prefix)
            remaining=size
            while remaining>0:
                chunk=src.read(min(1024*1024,remaining))
                if not chunk:
                    raise RuntimeError('source_truncated')
                conn.send(chunk)
                remaining-=len(chunk)
            conn.send(suffix)
            resp=conn.getresponse()
            raw=resp.read().decode('utf-8','replace')
            if resp.status<200 or resp.status>=300:
                raise RuntimeError('vk_upload_http_%s:%s'%(resp.status,clean(raw)))
            try:
                return json.loads(raw) if raw else {}
            except Exception:
                return {'raw':raw[:2000]}
        finally:
            conn.close()
    finally:
        try: src.close()
        except Exception: pass

def vk_video_tools():
    return [
      {'name':'vk_video_status','description':'Verify direct VK Video API reachability and list recent videos for the configured ND community.','inputSchema':{'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':100}},'additionalProperties':False}},
      {'name':'vk_video_auth_probe','description':'Probe whether the configured direct VK token can call video.save for the ND community. Creates only an upload slot and attempts immediate cleanup; no video bytes are uploaded. Requires confirm=true and unique mutation_id.','inputSchema':{'type':'object','properties':{'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['confirm','mutation_id'],'additionalProperties':False}},
      {'name':'vk_video_upload_from_url','description':'Upload one video directly to the configured ND VK community from an HTTPS source URL, bypassing Make and browsers. Requires confirm=true and unique mutation_id.','inputSchema':{'type':'object','properties':{'title':{'type':'string','minLength':1,'maxLength':250},'description':{'type':'string','maxLength':2048},'file_url':{'type':'string','minLength':8},'wallpost':{'type':'boolean'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['title','file_url','confirm','mutation_id'],'additionalProperties':False}},
      {'name':'vk_video_get','description':'Read one VK video by owner_id and video_id.','inputSchema':{'type':'object','properties':{'owner_id':{'type':'integer'},'video_id':{'type':'integer'}},'required':['owner_id','video_id'],'additionalProperties':False}},
      {'name':'vk_video_delete','description':'Delete one VK video owned by the configured community. Requires confirm=true and unique mutation_id.','inputSchema':{'type':'object','properties':{'owner_id':{'type':'integer'},'video_id':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['owner_id','video_id','confirm','mutation_id'],'additionalProperties':False}},
    ]

def vk_video_call(name,a):
    a=a or {}
    if not isinstance(a,dict):
        raise RuntimeError('arguments_must_be_object')
    g=vk_video_group()
    owner=-int(g['id'])
    if name=='vk_video_status':
        count=max(1,min(100,int(a.get('count') or 20)))
        videos=vk_api_call('video.get',{'owner_id':owner,'count':count,'offset':0}) or {}
        return {'ok':True,'provider':'vk','route':'direct_api','api_version':VK_VERSION,'group':g,'oauth':vk_oauth_status(),'videos':videos,'outcome':'READ_PASS'}
    if name=='vk_video_auth_probe':
        mid=vk_video_guard(a.get('mutation_id'),a.get('confirm'))
        saved=vk_video_user_api('video.save',{'group_id':int(g['id']),'name':'ND direct VK Video auth probe','description':'Temporary authorization probe; no bytes uploaded.','wallpost':0})
        cleanup={'attempted':False}
        vid=int((saved or {}).get('video_id') or 0); own=int((saved or {}).get('owner_id') or owner)
        if vid>0:
            cleanup['attempted']=True
            try:
                cleanup['response']=vk_video_user_api('video.delete',{'video_id':vid,'owner_id':own,'target_id':owner})
                cleanup['ok']=True
            except Exception as e:
                cleanup['ok']=False; cleanup['error']=clean(e)
        return {'ok':True,'mutation_id':mid,'video_save':{'owner_id':own,'video_id':vid,'upload_url_present':bool((saved or {}).get('upload_url'))},'cleanup':cleanup,'outcome':'AUTH_WRITE_PASS'}
    if name=='vk_video_upload_from_url':
        mid=vk_video_guard(a.get('mutation_id'),a.get('confirm'))
        title=str(a.get('title') or '').strip()
        desc=str(a.get('description') or '')
        file_url=str(a.get('file_url') or '').strip()
        if not title or len(title)>250:
            raise RuntimeError('invalid_title')
        if len(desc)>2048:
            raise RuntimeError('description_too_long')
        if not file_url.startswith('https://'):
            raise RuntimeError('file_url_must_be_https')
        saved=vk_video_user_api('video.save',{'group_id':int(g['id']),'name':title,'description':desc,'wallpost':1 if a.get('wallpost') is True else 0})
        up=(saved or {}).get('upload_url')
        if not up:
            raise RuntimeError('vk_upload_url_missing')
        uploaded=vk_video_upload_stream(up,file_url)
        vid=int((saved or {}).get('video_id') or uploaded.get('video_id') or uploaded.get('video_hash') or 0)
        own=int((saved or {}).get('owner_id') or owner)
        rb=None
        if vid>0:
            for _ in range(8):
                try:
                    got=vk_api_call('video.get',{'videos':'%s_%s'%(own,vid),'extended':0}) or {}
                    items=got.get('items') if isinstance(got,dict) else None
                    if items:
                        rb=items[0]; break
                except Exception:
                    pass
                time.sleep(3)
        return {'ok':True,'mutation_id':mid,'owner_id':own,'video_id':vid,'upload_response':uploaded,'readback':rb,'processing':rb is None,'outcome':'CONFIRMED_APPLIED' if rb else 'UPLOAD_ACCEPTED_PROCESSING'}
    if name=='vk_video_get':
        own=int(a.get('owner_id')); vid=int(a.get('video_id'))
        got=vk_api_call('video.get',{'videos':'%s_%s'%(own,vid),'extended':0}) or {}
        return {'ok':True,'owner_id':own,'video_id':vid,'result':got,'outcome':'READ_PASS'}
    if name=='vk_video_delete':
        mid=vk_video_guard(a.get('mutation_id'),a.get('confirm'))
        own=int(a.get('owner_id')); vid=int(a.get('video_id'))
        if own!=owner:
            raise RuntimeError('owner_not_configured_community')
        res=vk_video_user_api('video.delete',{'video_id':vid,'owner_id':own,'target_id':owner})
        rb=vk_api_call('video.get',{'videos':'%s_%s'%(own,vid),'extended':0}) or {}
        return {'ok':True,'mutation_id':mid,'owner_id':own,'video_id':vid,'response':res,'readback':rb,'outcome':'CONFIRMED_APPLIED'}
    raise RuntimeError('unknown_vk_video_tool')

def tools():
    return [
      {'name':'github_list_repositories','description':'List repositories owned by the configured ND GitHub account. Results are inline JSON; no ChatGPT file download is used.','inputSchema':{'type':'object','properties':{'page':{'type':'integer','minimum':1},'per_page':{'type':'integer','minimum':1,'maximum':100}},'additionalProperties':False}},
      {'name':'github_get_repo','description':'Get repository metadata for an ND-owned repository.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'}},'required':['repo'],'additionalProperties':False}},
      {'name':'github_list_path','description':'List one repository directory and return names, paths, types, sizes and SHAs inline.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'},'path':{'type':'string'},'ref':{'type':'string'}},'required':['repo'],'additionalProperties':False}},
      {'name':'github_get_file','description':'Read a UTF-8 GitHub file inline in MCP output. This tool never emits an attachment or download artifact. Optional line bounds limit returned text.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'},'path':{'type':'string'},'ref':{'type':'string'},'start_line':{'type':'integer','minimum':1},'end_line':{'type':'integer','minimum':1}},'required':['repo','path'],'additionalProperties':False}},
      {'name':'github_search_code','description':'Search code across repositories owned by the configured ND GitHub account.','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'page':{'type':'integer','minimum':1},'per_page':{'type':'integer','minimum':1,'maximum':100}},'required':['query'],'additionalProperties':False}},
      {'name':'github_create_or_update_file','description':'Create or replace one UTF-8 text file. expected_sha is mandatory when the file already exists, preventing blind overwrite.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'},'path':{'type':'string'},'content':{'type':'string'},'message':{'type':'string'},'branch':{'type':'string'},'expected_sha':{'type':'string'}},'required':['repo','path','content','message'],'additionalProperties':False}},
      {'name':'github_delete_file','description':'Delete a file only when its expected current blob SHA is supplied.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'},'path':{'type':'string'},'message':{'type':'string'},'branch':{'type':'string'},'expected_sha':{'type':'string'}},'required':['repo','path','message','expected_sha'],'additionalProperties':False}},
      {'name':'github_create_branch','description':'Create a branch from an existing base branch/ref.','inputSchema':{'type':'object','properties':{'repo':{'type':'string'},'branch':{'type':'string'},'base':{'type':'string'}},'required':['repo','branch'],'additionalProperties':False}},
    ]

def call(name,a):
    a=a or {}
    if not isinstance(a,dict): raise RuntimeError('arguments_must_be_object')
    if name=='github_list_repositories':
        page=max(1,int(a.get('page') or 1)); per=max(1,min(100,int(a.get('per_page') or 30)))
        obj=gh('/user/repos?affiliation=owner,collaborator,organization_member&sort=updated&direction=desc&page=%d&per_page=%d'%(page,per))
        rows=[]
        for r in obj:
            if str(((r.get('owner') or {}).get('login') or '')).lower()!=OWNER.lower(): continue
            rows.append({'name':r.get('name'),'full_name':r.get('full_name'),'private':r.get('private'),'default_branch':r.get('default_branch'),'updated_at':r.get('updated_at'),'html_url':r.get('html_url')})
        return {'ok':True,'owner':OWNER,'repositories':rows}

    if name=='github_search_code':
        query=str(a.get('query') or '').strip()
        if not query: raise RuntimeError('query_required')
        page=max(1,int(a.get('page') or 1)); per=max(1,min(100,int(a.get('per_page') or 20)))
        obj=gh('/search/code?q='+q(query+' user:'+OWNER)+'&page=%d&per_page=%d'%(page,per),accept='application/vnd.github.text-match+json')
        return {'ok':True,'query':query,'owner':OWNER,'total_count':obj.get('total_count'),'items':[{'name':x.get('name'),'path':x.get('path'),'sha':x.get('sha'),'html_url':x.get('html_url'),'repository':((x.get('repository') or {}).get('full_name')),'text_matches':x.get('text_matches') or []} for x in (obj.get('items') or [])]}

    repo=str(a.get('repo') or '').strip(); base=repo_base(repo)
    if name=='github_get_repo':
        r=gh(base)
        return {'ok':True,'repository':{'name':r.get('name'),'full_name':r.get('full_name'),'private':r.get('private'),'default_branch':r.get('default_branch'),'description':r.get('description'),'updated_at':r.get('updated_at'),'html_url':r.get('html_url')}}

    if name=='github_list_path':
        path=str(a.get('path') or '').strip().lstrip('/')
        suffix='/contents/'+urllib.parse.quote(path,safe='/') if path else '/contents'
        ref=str(a.get('ref') or '').strip()
        if ref: suffix+='?ref='+q(ref)
        obj=gh(base+suffix)
        if not isinstance(obj,list): raise RuntimeError('path_is_not_directory')
        return {'ok':True,'repo':repo,'path':path,'entries':[{'name':x.get('name'),'path':x.get('path'),'type':x.get('type'),'size':x.get('size'),'sha':x.get('sha')} for x in obj]}

    if name=='github_get_file':
        path=str(a.get('path') or '').strip().lstrip('/')
        if not path: raise RuntimeError('path_required')
        suffix='/contents/'+urllib.parse.quote(path,safe='/')
        ref=str(a.get('ref') or '').strip(); qs=('?ref='+q(ref)) if ref else ''
        meta=gh(base+suffix+qs)
        if not isinstance(meta,dict) or meta.get('type')!='file': raise RuntimeError('path_is_not_file')
        size=int(meta.get('size') or 0)
        if size>INLINE_MAX: raise RuntimeError('file_too_large_for_inline_mcp:%d>%d'%(size,INLINE_MAX))
        raw=gh(base+suffix+qs,accept='application/vnd.github.raw+json',raw=True)
        text=raw.decode('utf-8','replace'); lines=text.splitlines()
        start=max(1,int(a.get('start_line') or 1)); end=int(a.get('end_line') or len(lines))
        end=max(start,min(end,len(lines))) if lines else 0
        return {'ok':True,'repo':repo,'path':path,'sha':meta.get('sha'),'size':size,'encoding':'utf-8','start_line':start,'end_line':end,'total_lines':len(lines),'content':'\n'.join(lines[start-1:end]) if lines else ''}

    if name=='github_create_or_update_file':
        path=str(a.get('path') or '').strip().lstrip('/'); content=a.get('content'); message=str(a.get('message') or '').strip(); branch=str(a.get('branch') or '').strip(); expected=str(a.get('expected_sha') or '').strip()
        if not path or not isinstance(content,str) or not message: raise RuntimeError('path_content_message_required')
        exists=None
        try: exists=gh(base+'/contents/'+urllib.parse.quote(path,safe='/')+(('?ref='+q(branch)) if branch else ''))
        except Exception as e:
            if 'github_http_404' not in str(e): raise
        if isinstance(exists,dict) and exists.get('sha'):
            if not expected: raise RuntimeError('expected_sha_required_for_update')
            if expected!=str(exists.get('sha')): raise RuntimeError('sha_mismatch')
        elif expected: raise RuntimeError('expected_sha_supplied_but_file_missing')
        body={'message':message,'content':base64.b64encode(content.encode('utf-8')).decode('ascii')}
        if branch: body['branch']=branch
        if expected: body['sha']=expected
        out=gh(base+'/contents/'+urllib.parse.quote(path,safe='/'),'PUT',body)
        return {'ok':True,'repo':repo,'path':path,'commit_sha':((out.get('commit') or {}).get('sha')),'content_sha':((out.get('content') or {}).get('sha')),'html_url':((out.get('content') or {}).get('html_url'))}

    if name=='github_delete_file':
        path=str(a.get('path') or '').strip().lstrip('/'); message=str(a.get('message') or '').strip(); branch=str(a.get('branch') or '').strip(); expected=str(a.get('expected_sha') or '').strip()
        if not path or not message or not expected: raise RuntimeError('path_message_expected_sha_required')
        body={'message':message,'sha':expected}
        if branch: body['branch']=branch
        out=gh(base+'/contents/'+urllib.parse.quote(path,safe='/'),'DELETE',body)
        return {'ok':True,'repo':repo,'path':path,'commit_sha':((out.get('commit') or {}).get('sha'))}

    if name=='github_create_branch':
        branch=str(a.get('branch') or '').strip(); base_ref=str(a.get('base') or 'main').strip()
        if not branch or branch.startswith('refs/'): raise RuntimeError('invalid_branch')
        refobj=gh(base+'/git/ref/heads/'+urllib.parse.quote(base_ref,safe='/')); sha=str((((refobj.get('object') or {}).get('sha')) or ''))
        if not sha: raise RuntimeError('base_ref_sha_missing')
        out=gh(base+'/git/refs','POST',{'ref':'refs/heads/'+branch,'sha':sha})
        return {'ok':True,'repo':repo,'branch':branch,'base':base_ref,'sha':(((out.get('object') or {}).get('sha')) or sha)}

    raise RuntimeError('unknown_github_tool')

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def is_mcp(self):
        expected=('/nd/github/mcp/'+PATH_TOKEN) if PATH_TOKEN else ''
        return bool(expected and self.path.split('?',1)[0]==expected)
    def is_vk_video_mcp(self):
        expected=('/nd/vk-video/mcp/'+VK_VIDEO_PATH_TOKEN) if VK_VIDEO_PATH_TOKEN else ''
        return bool(expected and self.path.split('?',1)[0]==expected)
    def vk_video_mcp(self):
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':clean(e)},'id':None}); return
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized': self.send_response(204); self.end_headers(); return
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'nd-vk-video-direct-mcp','version':'1.0.0'},'instructions':'Direct VK Video publishing for Nameless Dhamma. No Make or browser dependency. Mutations require confirm=true and unique mutation_id.'}}); return
        if method=='ping': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return
        if method=='tools/list': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':vk_video_tools()}}); return
        if method=='tools/call':
            p=msg.get('params') or {}
            try:
                obj=vk_video_call(str(p.get('name') or ''),p.get('arguments') or {}); err=False
            except Exception as e:
                obj={'ok':False,'error':clean(e)}; err=True
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],'structuredContent':obj,'isError':err}}); return
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})
    def mcp(self):
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n<0 or n>1048576: raise RuntimeError('request_too_large')
            msg=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if not isinstance(msg,dict): raise RuntimeError('invalid_jsonrpc')
        except Exception as e:
            self.send_json(400,{'jsonrpc':'2.0','error':{'code':-32700,'message':clean(e)},'id':None}); return
        mid=msg.get('id'); method=str(msg.get('method') or '')
        if method=='notifications/initialized': self.send_response(204); self.end_headers(); return
        if method=='initialize':
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'nd-github-direct-mcp','version':'1.0.0'},'instructions':'Direct Nameless Dhamma GitHub MCP. All file contents are returned inline as text/JSON; this server never emits ChatGPT attachment/download artifacts.'}}); return
        if method=='ping': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{}}); return
        if method=='tools/list': self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':tools()}}); return
        if method=='tools/call':
            p=msg.get('params') or {}
            try:
                obj=call(str(p.get('name') or ''),p.get('arguments') or {}); err=False
            except Exception as e:
                obj={'ok':False,'error':clean(e)}; err=True
            self.send_json(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(obj,ensure_ascii=False)}],'structuredContent':obj,'isError':err}}); return
        self.send_json(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})
    def forward(self):
        n=int(self.headers.get('Content-Length','0') or 0); body=self.rfile.read(n) if n else None
        headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','content-length','transfer-encoding')}
        req=urllib.request.Request(INNER+self.path,data=body,headers=headers,method=self.command)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read(); self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() not in ('connection','transfer-encoding','content-length'): self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except HTTPError as e:
            raw=e.read(); self.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() not in ('connection','transfer-encoding','content-length'): self.send_header(k,v)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except Exception as e: self.send_json(502,{'ok':False,'error':'existing_gateway_unavailable','detail':clean(e)})
    def do_POST(self):
        if self.is_vk_video_mcp(): self.vk_video_mcp(); return
        if self.is_mcp(): self.mcp(); return
        self.forward()
    def vk_oauth_start(self):
        state=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
        VK_OAUTH_PENDING[state]={'verifier':verifier,'created':time.time()}
        q=urllib.parse.urlencode({
          'response_type':'code',
          'client_id':VK_ID_CLIENT_ID,
          'redirect_uri':VK_ID_REDIRECT,
          'state':state,
          'code_challenge':challenge,
          'code_challenge_method':'S256',
          'scope':'video',
          'prompt':'consent',
        })
        self.send_response(302)
        self.send_header('Location','https://id.vk.ru/authorize?'+q)
        self.send_header('Cache-Control','no-store')
        self.end_headers()
    def vk_oauth_callback(self):
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if qs.get('error'):
            self.send_json(400,{'ok':False,'stage':'authorize','error':qs.get('error',[None])[0],'error_description':qs.get('error_description',[None])[0]}); return
        state=str(qs.get('state',[''])[0]); code=str(qs.get('code',[''])[0]); device=str(qs.get('device_id',[''])[0])
        rec=VK_OAUTH_PENDING.pop(state,None)
        if not rec or (time.time()-float(rec.get('created') or 0))>600:
            self.send_json(400,{'ok':False,'stage':'callback','error':'state_missing_or_expired'}); return
        if not code or not device:
            self.send_json(400,{'ok':False,'stage':'callback','error':'code_or_device_missing'}); return
        form={
          'grant_type':'authorization_code',
          'code':code,
          'code_verifier':rec['verifier'],
          'client_id':VK_ID_CLIENT_ID,
          'device_id':device,
          'redirect_uri':VK_ID_REDIRECT,
          'state':state,
        }
        req=urllib.request.Request('https://id.vk.ru/oauth2/auth',data=urllib.parse.urlencode(form).encode('utf-8'),headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-OAUTH-PROBE/1.0'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=30) as rr:
                tok=json.loads(rr.read().decode('utf-8','replace') or '{}')
        except HTTPError as e:
            raw=e.read().decode('utf-8','replace')
            self.send_json(400,{'ok':False,'stage':'token_exchange','error':clean(raw or e.reason)}); return
        access=str(tok.get('access_token') or '')
        if not access:
            self.send_json(400,{'ok':False,'stage':'token_exchange','error':'access_token_missing'}); return
        try:
            params={'group_id':228330620,'name':'ND direct VK Video OAuth probe','description':'Temporary authorization probe; no video bytes are uploaded.','wallpost':0,'access_token':access,'v':VK_VERSION}
            req2=urllib.request.Request('https://api.vk.com/method/video.save',data=urllib.parse.urlencode(params).encode('utf-8'),headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-OAUTH-PROBE/1.0'},method='POST')
            with urllib.request.urlopen(req2,timeout=30) as rr:
                obj=json.loads(rr.read().decode('utf-8','replace') or '{}')
            if obj.get('error'):
                err=obj.get('error') or {}
                self.send_json(403,{'ok':False,'stage':'video_save','error_code':err.get('error_code'),'error':err.get('error_msg'),'scope':tok.get('scope'),'token_persisted':False}); return
            saved=obj.get('response') or {}
            vid=int(saved.get('video_id') or 0); own=int(saved.get('owner_id') or -228330620)
            cleanup=None
            if vid:
                p={'video_id':vid,'owner_id':own,'target_id':-228330620,'access_token':access,'v':VK_VERSION}
                qreq=urllib.request.Request('https://api.vk.com/method/video.delete',data=urllib.parse.urlencode(p).encode('utf-8'),headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ND-VK-VIDEO-OAUTH-PROBE/1.0'},method='POST')
                try:
                    with urllib.request.urlopen(qreq,timeout=30) as qr:
                        cleanup=json.loads(qr.read().decode('utf-8','replace') or '{}')
                except Exception as ce:
                    cleanup={'error':clean(ce)}
            persisted=vk_oauth_store(tok,device)
            self.send_json(200,{'ok':True,'stage':'complete','app_id':VK_ID_CLIENT_ID,'scope':tok.get('scope'),'video_save':{'owner_id':own,'video_id':vid,'upload_url_present':bool(saved.get('upload_url'))},'cleanup':cleanup,'refresh_token_present':bool(tok.get('refresh_token')),'token_persisted':True,'oauth':{'user_id':persisted.get('user_id'),'expires_at':persisted.get('expires_at')}})
        finally:
            access=''; tok={}
    def do_GET(self):
        _p=self.path.split('?',1)[0]
        if _p=='/vk/oauth/start':
            self.vk_oauth_start(); return
        if _p=='/vk/oauth/callback':
            self.vk_oauth_callback(); return
        if _p=='/nd/vk-video/health':
            try:
                g=vk_video_group()
                self.send_json(200,{'ok':True,'service':'nd-vk-video-direct-mcp','version':'1.1.0','configured':bool(VK_TOKEN and VK_VIDEO_PATH_TOKEN),'group':g,'oauth':vk_oauth_status(),'browser_required':False,'make_required':False})
            except Exception as e:
                self.send_json(503,{'ok':False,'service':'nd-vk-video-direct-mcp','error':clean(e)})
            return
        if self.path.split('?',1)[0]=='/nd/github/health':
            self.send_json(200,{'ok':True,'service':'nd-github-direct-mcp','version':'1.1.0','configured':bool(GITHUB_PAT and PATH_TOKEN),'owner':OWNER,'inline_only':True,'attachments':False}); return
        self.forward()
    def do_DELETE(self): self.forward()
    def do_PUT(self): self.forward()
    def do_PATCH(self): self.forward()

print('ND_GITHUB_MCP_FRONT_V6_SEARCH_FIXED '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'configured':bool(GITHUB_PAT and PATH_TOKEN),'owner':OWNER,'inline_only':True,'attachments':False,'vk_video_configured':bool(VK_TOKEN and VK_VIDEO_PATH_TOKEN)}),flush=True)
if str(os.environ.get('ND_VK_VIDEO_SELFTEST_ONCE','')).strip().lower() in ('1','true','yes','on'):
    try:
        _token,_bundle=vk_video_user_token(True)
        _params={'group_id':228330620,'name':'ND direct VK Video refresh self-test','description':'Temporary refresh-token qualification; no video bytes uploaded.','wallpost':0}
        _obj=vk_api_call_with_token('video.save',_params,_token,30)
        if _obj.get('error'):
            _err=_obj.get('error') or {}
            raise RuntimeError('video_save_%s:%s'%(_err.get('error_code'),clean(_err.get('error_msg'))))
        _saved=_obj.get('response') or {}
        _vid=int(_saved.get('video_id') or 0); _own=int(_saved.get('owner_id') or -228330620)
        _cleanup=None
        if _vid:
            _del=vk_api_call_with_token('video.delete',{'video_id':_vid,'owner_id':_own,'target_id':-228330620},_token,30)
            _cleanup=_del
        print('ND_VK_VIDEO_REFRESH_SELFTEST '+json.dumps({'ok':True,'owner_id':_own,'video_id':_vid,'upload_url_present':bool(_saved.get('upload_url')),'cleanup':_cleanup,'oauth':vk_oauth_status()},ensure_ascii=False),flush=True)
    except Exception as _e:
        print('ND_VK_VIDEO_REFRESH_SELFTEST '+json.dumps({'ok':False,'error':clean(_e),'oauth':vk_oauth_status()},ensure_ascii=False),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
