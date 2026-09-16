import base64, json, os, subprocess, sys, urllib.parse, urllib.request
from urllib.error import HTTPError

TARGET_REPO=os.environ.get('ND_META_GITHUB_TARGET_REPO','namelessdhamma/nameless-dhamma-vault').strip()
GITHUB_PAT=os.environ.get('ND_GITHUB_PAT','').strip()
SECRET_MAP={
  'ND_META_USER_ACCESS_TOKEN': os.environ.get('ND_META_USER_ACCESS_TOKEN','').strip(),
  'ND_META_GRAPH_VERSION': os.environ.get('ND_META_GRAPH_VERSION','v26.0').strip() or 'v26.0',
  'ND_META_BUSINESS_ID': os.environ.get('ND_META_BUSINESS_ID','').strip(),
  'ND_FACEBOOK_PAGE_ID': os.environ.get('ND_FACEBOOK_PAGE_ID','').strip(),
  'ND_INSTAGRAM_USER_ID': os.environ.get('ND_INSTAGRAM_USER_ID','').strip(),
  'ND_META_AD_ACCOUNT_ID': os.environ.get('ND_META_AD_ACCOUNT_ID','').strip(),
  'ND_META_MCP_PATH_TOKEN': os.environ.get('ND_META_MCP_PATH_TOKEN','').strip(),
}

def gh(path,method='GET',body=None):
    if not GITHUB_PAT: raise RuntimeError('github_pat_missing')
    data=None if body is None else json.dumps(body).encode('utf-8')
    headers={
      'Authorization':'Bearer '+GITHUB_PAT,
      'Accept':'application/vnd.github+json',
      'X-GitHub-Api-Version':'2022-11-28',
      'User-Agent':'ND-Meta-GitHub-Secret-Bootstrap/1.0'
    }
    if data is not None: headers['Content-Type']='application/json'
    req=urllib.request.Request('https://api.github.com'+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read().decode('utf-8','replace')
            return r.status,(json.loads(raw) if raw else {})
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace')
        raise RuntimeError('github_http_%s:%s'%(e.code,raw[:1200]))

def ensure_nacl():
    try:
        import nacl.public, nacl.encoding
        return
    except Exception:
        subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir','PyNaCl==1.5.0'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def encrypt(public_key_b64,value):
    import nacl.public, nacl.encoding
    public_key=nacl.public.PublicKey(public_key_b64.encode('utf-8'),nacl.encoding.Base64Encoder())
    box=nacl.public.SealedBox(public_key)
    enc=box.encrypt(value.encode('utf-8'))
    return base64.b64encode(enc).decode('ascii')

def main():
    if not TARGET_REPO or '/' not in TARGET_REPO: raise RuntimeError('invalid_target_repo')
    missing=[k for k,v in SECRET_MAP.items() if not v]
    if missing: raise RuntimeError('missing_source_values:'+','.join(missing))
    ensure_nacl()
    status,key=gh('/repos/'+TARGET_REPO+'/actions/secrets/public-key')
    if status!=200 or not key.get('key') or not key.get('key_id'): raise RuntimeError('github_public_key_unavailable')
    done=[]
    for name,value in SECRET_MAP.items():
        encrypted=encrypt(key['key'],value)
        code,_=gh('/repos/'+TARGET_REPO+'/actions/secrets/'+urllib.parse.quote(name,safe=''),'PUT',{'encrypted_value':encrypted,'key_id':key['key_id']})
        if code not in (201,204): raise RuntimeError('secret_write_failed:'+name+':'+str(code))
        done.append(name)
    print('ND_META_GITHUB_SECRET_BOOTSTRAP '+json.dumps({'ok':True,'repo':TARGET_REPO,'secret_names':done},ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
