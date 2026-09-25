import base64, json, os, subprocess, sys, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
INNER_PORT=int(os.environ.get('ND_GITHUB_MCP_INNER_PORT','3100'))
GITHUB_PAT=os.environ.get('ND_GITHUB_PAT','').strip()
PATH_TOKEN=os.environ.get('ND_GITHUB_MCP_PATH_TOKEN','').strip()
OWNER=os.environ.get('ND_GITHUB_OWNER','namelessdhamma').strip() or 'namelessdhamma'
INLINE_MAX=int(os.environ.get('ND_GITHUB_INLINE_MAX','600000') or '600000')

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
    for secret in (GITHUB_PAT,PATH_TOKEN):
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

    if name=='github_search_code':
        query=str(a.get('query') or '').strip()
        if not query: raise RuntimeError('query_required')
        page=max(1,int(a.get('page') or 1)); per=max(1,min(100,int(a.get('per_page') or 20)))
        obj=gh('/search/code?q='+q(query+' user:'+OWNER)+'&page=%d&per_page=%d'%(page,per),accept='application/vnd.github.text-match+json')
        return {'ok':True,'query':query,'owner':OWNER,'total_count':obj.get('total_count'),'items':[{'name':x.get('name'),'path':x.get('path'),'sha':x.get('sha'),'html_url':x.get('html_url'),'repository':((x.get('repository') or {}).get('full_name')),'text_matches':x.get('text_matches') or []} for x in (obj.get('items') or [])]}

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
        if self.is_mcp(): self.mcp(); return
        self.forward()
    def do_GET(self):
        if self.path.split('?',1)[0]=='/nd/github/health':
            self.send_json(200,{'ok':True,'service':'nd-github-direct-mcp','version':'1.1.0','configured':bool(GITHUB_PAT and PATH_TOKEN),'owner':OWNER,'inline_only':True,'attachments':False}); return
        self.forward()
    def do_DELETE(self): self.forward()
    def do_PUT(self): self.forward()
    def do_PATCH(self): self.forward()

try:
    _probe=call('github_get_repo',{'repo':'namelessdhamma.github.io'})
    print('ND_GITHUB_MCP_SELFTEST '+json.dumps({'ok':bool(_probe.get('ok')),'repo':((_probe.get('repository') or {}).get('full_name')),'inline_only':True,'attachments':False}),flush=True)
except Exception as _e:
    print('ND_GITHUB_MCP_SELFTEST '+json.dumps({'ok':False,'error':clean(_e)}),flush=True)

print('ND_GITHUB_MCP_FRONT_V2_CURRENT_WRAPPER '+json.dumps({'port':PORT,'inner_port':INNER_PORT,'configured':bool(GITHUB_PAT and PATH_TOKEN),'owner':OWNER,'inline_only':True,'attachments':False}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
