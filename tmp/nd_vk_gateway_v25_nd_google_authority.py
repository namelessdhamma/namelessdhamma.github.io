import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/e1fdbc500903ce58f8913e24d361d8d5cd1d3e65/tmp/nd_vk_gateway_v23_nd_readonly_ranked.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V23_OUTER',flush=True)"
if marker not in outer: raise RuntimeError('V23 outer marker not found')

# Patch the V17/V13 source-generation chain before it executes.
patch = r'''
# Extend the V13 read-only context with authoritative Google Drive StateHead -> Registry resolution.
needle="print('ND_V23_BOOTSTRAP',flush=True)"
if needle not in outer: raise RuntimeError('V23 bootstrap marker not found')
google_patch=r"""
# Google Drive read-only authority layer.
code=code.replace("import os,json,threading,time,hashlib,random,re,base64,zipfile,io,html",
                  "import os,json,threading,time,hashlib,random,re,base64,zipfile,io,html,struct",1)

insert_before="def heuristic_route(text):\\n"
if insert_before not in code: raise RuntimeError('Google insert marker not found')
google_code=r"""
ND_GOOGLE_CLIENT_EMAIL=os.environ.get('ND_GOOGLE_CLIENT_EMAIL','')
ND_GOOGLE_PRIVATE_KEY_B64=os.environ.get('ND_GOOGLE_PRIVATE_KEY_B64','')
ND_GOOGLE_STATEHEAD_ID=os.environ.get('ND_GOOGLE_STATEHEAD_ID','1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ')
_google_token_cache={'token':'','exp':0}
_google_authority_cache={'at':0,'state':None,'registry':None}

def _b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')

def _der_one(data,off=0):
    if off>=len(data): raise ValueError('DER eof')
    tag=data[off];off+=1
    if off>=len(data): raise ValueError('DER len eof')
    n=data[off];off+=1
    if n & 0x80:
        k=n&0x7f
        if k<1 or k>4 or off+k>len(data): raise ValueError('DER bad len')
        n=int.from_bytes(data[off:off+k],'big');off+=k
    end=off+n
    if end>len(data): raise ValueError('DER truncated')
    return tag,data[off:end],end

def _der_children(seq):
    out=[];off=0
    while off<len(seq):
        tag,val,off=_der_one(seq,off);out.append((tag,val))
    return out

def _google_rsa_nd():
    if not ND_GOOGLE_PRIVATE_KEY_B64: raise RuntimeError('ND_GOOGLE_PRIVATE_KEY_B64 missing')
    try: pem=base64.b64decode(ND_GOOGLE_PRIVATE_KEY_B64).decode('utf-8','replace')
    except Exception as e: raise RuntimeError('Google key base64 decode failed')
    body=''.join(x.strip() for x in pem.splitlines() if not x.startswith('---'))
    der=base64.b64decode(body)
    tag,top,_=_der_one(der,0)
    if tag!=0x30: raise RuntimeError('Google key DER is not sequence')
    ch=_der_children(top)
    if 'BEGIN PRIVATE KEY' in pem and 'BEGIN RSA PRIVATE KEY' not in pem:
        octets=[v for t,v in ch if t==0x04]
        if not octets: raise RuntimeError('Google PKCS8 private key missing')
        t2,rsa_seq,_=_der_one(octets[0],0)
        if t2!=0x30: raise RuntimeError('Google RSA key invalid')
        rc=_der_children(rsa_seq)
    else:
        rc=ch
    ints=[int.from_bytes(v,'big',signed=False) for t,v in rc if t==0x02]
    if len(ints)<4: raise RuntimeError('Google RSA key parameters missing')
    return ints[1],ints[3]

def _google_rs256(data):
    n,d=_google_rsa_nd()
    digest=hashlib.sha256(data).digest()
    di=bytes.fromhex('3031300d060960864801650304020105000420')+digest
    k=(n.bit_length()+7)//8
    ps=b'\\xff'*(k-len(di)-3)
    em=b'\\x00\\x01'+ps+b'\\x00'+di
    sig=pow(int.from_bytes(em,'big'),d,n).to_bytes(k,'big')
    return sig

def google_access_token():
    now=int(time.time())
    if _google_token_cache['token'] and now<_google_token_cache['exp']-120:
        return _google_token_cache['token']
    if not ND_GOOGLE_CLIENT_EMAIL: raise RuntimeError('ND_GOOGLE_CLIENT_EMAIL missing')
    head=_b64u(json.dumps({'alg':'RS256','typ':'JWT'},separators=(',',':')).encode())
    claims={'iss':ND_GOOGLE_CLIENT_EMAIL,'scope':'https://www.googleapis.com/auth/drive.readonly','aud':'https://oauth2.googleapis.com/token','iat':now,'exp':now+3600}
    body=_b64u(json.dumps(claims,separators=(',',':')).encode())
    signing=(head+'.'+body).encode()
    jwt=head+'.'+body+'.'+_b64u(_google_rs256(signing))
    form=urlencode({'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer','assertion':jwt}).encode()
    req=Request('https://oauth2.googleapis.com/token',data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'nd-vk-google-readonly/1.0'})
    with urlopen(req,timeout=30) as r:j=json.loads(r.read().decode())
    tok=j.get('access_token')
    if not tok: raise RuntimeError('Google OAuth returned no access token')
    _google_token_cache.update({'token':tok,'exp':now+int(j.get('expires_in') or 3600)})
    return tok

def google_get_bytes(url,timeout=35,max_bytes=1200000):
    tok=google_access_token()
    req=Request(url,method='GET',headers={'Authorization':'Bearer '+tok,'User-Agent':'nd-vk-google-readonly/1.0'})
    try:
        with urlopen(req,timeout=timeout) as r:return r.read(max_bytes+1)[:max_bytes]
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('Google HTTP %s: %s'%(e.code,body[:600]))

def google_get_json(url,timeout=35):
    return json.loads(google_get_bytes(url,timeout,1500000).decode('utf-8','replace'))

def google_file_meta(fid):
    fields=quote('id,name,mimeType,modifiedTime,parents,webViewLink',safe=',')
    return google_get_json('https://www.googleapis.com/drive/v3/files/'+quote(fid,safe='')+'?supportsAllDrives=true&fields='+fields)

def google_file_text(fid,meta=None,max_chars=9000):
    meta=meta or google_file_meta(fid)
    mt=meta.get('mimeType') or ''
    qid=quote(fid,safe='')
    if mt=='application/vnd.google-apps.document':
        u='https://www.googleapis.com/drive/v3/files/'+qid+'/export?mimeType='+quote('text/plain',safe='')
        raw=google_get_bytes(u,45,1500000)
        return raw.decode('utf-8','replace')[:max_chars]
    if mt=='application/vnd.google-apps.spreadsheet':
        u='https://www.googleapis.com/drive/v3/files/'+qid+'/export?mimeType='+quote('text/csv',safe='')
        raw=google_get_bytes(u,45,1200000)
        return raw.decode('utf-8','replace')[:max_chars]
    if mt in ('application/json','text/plain','text/markdown','text/csv','application/octet-stream') or mt.startswith('text/'):
        raw=google_get_bytes('https://www.googleapis.com/drive/v3/files/'+qid+'?alt=media&supportsAllDrives=true',45,1500000)
        return raw.decode('utf-8','replace')[:max_chars]
    if mt=='application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        raw=google_get_bytes('https://www.googleapis.com/drive/v3/files/'+qid+'?alt=media&supportsAllDrives=true',45,6000000)
        return docx_text(raw)[:max_chars]
    return ''

def google_json_file(fid):
    txt=google_file_text(fid,max_chars=1000000)
    return json.loads(txt.lstrip('\\ufeff'))

def google_state_registry():
    now=time.time()
    if _google_authority_cache['state'] is not None and now-_google_authority_cache['at']<180:
        return _google_authority_cache['state'],_google_authority_cache['registry']
    state=google_json_file(ND_GOOGLE_STATEHEAD_ID)
    cr=(state.get('capability_registry') or {})
    rid=cr.get('canonical_artifact_id')
    if not rid: raise RuntimeError('StateHead has no capability registry artifact')
    registry=google_json_file(rid)
    if str(registry.get('version'))!=str(cr.get('registry_version')):
        raise RuntimeError('Google Registry version mismatch with StateHead')
    _google_authority_cache.update({'at':now,'state':state,'registry':registry})
    return state,registry

def google_component_score(c,terms,q):
    blob=' '.join(str(c.get(k) or '') for k in ('component_key','semantic_id','version','exact_status','canonical_artifact_name','owner')).lower()
    s=0
    for t in terms:
        if t in blob:s+=5
    low=q.lower()
    key=(c.get('component_key') or '').lower()
    if any(x in low for x in ('исслед','research')) and any(x in key for x in ('true_research','pcpa','paccaya','dhamma','governing')):s+=8
    if any(x in low for x in ('книг','рассказ','текст','литератур','write','book')) and 'book' in key:s+=12
    if any(x in low for x in ('визуал','изображ','visual')) and 'visual' in key:s+=12
    if any(x in low for x in ('архитект','architecture','система','system','state','памят','memory')) and any(x in key for x in ('system','working_architecture','storage','schema','interop')):s+=10
    if any(x in low for x in ('скил','skill','capabil','способност')) and 'skill' in blob:s+=8
    return s

def google_bundle_summary(state):
    latest=((state.get('durable_record_store') or {}).get('latest_bundle') or {})
    bid=latest.get('artifact_id')
    if not bid:return ''
    try:b=google_json_file(bid)
    except Exception as e:return 'Latest durable bundle unavailable: '+cleanerr(e)
    cp=None;tx=None
    for rr in b.get('records') or []:
        rec=rr.get('record') or {}
        if rec.get('record_type')=='Checkpoint':cp=rec
        if rec.get('record_type')=='TransactionRecord':tx=rec
    out={'bundle_id':b.get('bundle_id'),'checkpoint_id':b.get('checkpoint_id'),'created_at':b.get('created_at')}
    if cp:
        out['active_frontier_ids']=cp.get('active_frontier_ids')
        out['primary_frontier_question_id']=cp.get('primary_frontier_question_id')
        out['model_id']=cp.get('model_id');out['model_version']=cp.get('model_version')
        out['latest_transaction_id']=cp.get('latest_transaction_id')
    if tx:
        out['operation_mode']=tx.get('operation_mode');out['changed_ids']=tx.get('changed_ids');out['published_at']=tx.get('published_at')
    return json.dumps(out,ensure_ascii=False,indent=2)

def google_search_discovery(q):
    low=q.lower()
    if not any(x in low for x in ('plugin','плагин','tool','инструмент','agent','агент','automation','автомат','connector','подключ')):
        return []
    terms=nd_query_terms(q)
    focus=terms[0] if terms else 'ND'
    esc=focus.replace("'","\\'")
    query="trashed=false and fullText contains '"+esc+"'"
    params=urlencode({'q':query,'pageSize':12,'orderBy':'modifiedTime desc','fields':'files(id,name,mimeType,modifiedTime,webViewLink)','supportsAllDrives':'true','includeItemsFromAllDrives':'true'})
    try:j=google_get_json('https://www.googleapis.com/drive/v3/files?'+params)
    except Exception as e:
        print('ND_RO_GOOGLE_DISCOVERY_ERROR',cleanerr(e),flush=True);return []
    out=[]
    for f in (j.get('files') or [])[:3]:
        try:
            txt=google_file_text(f.get('id'),f,3500)
            if txt.strip():out.append(('Google Drive NON-AUTHORITATIVE discovery: '+(f.get('name') or f.get('id')),txt))
        except Exception:pass
    return out

def google_nd_context(q):
    if not ND_READONLY_ENABLED or not ND_GOOGLE_CLIENT_EMAIL or not ND_GOOGLE_PRIVATE_KEY_B64:return []
    state,registry=google_state_registry()
    terms=nd_query_terms(q)
    cr=state.get('capability_registry') or {}
    sh_summary={
      'record_type':state.get('record_type'),'status':state.get('status'),'head_id':state.get('head_id'),
      'published_at':state.get('published_at'),'registry_id':cr.get('registry_id'),'registry_version':cr.get('registry_version'),
      'registry_artifact_id':cr.get('canonical_artifact_id'),'durable_store':(state.get('durable_record_store') or {}).get('store_id')
    }
    comps=registry.get('components') or []
    cap_lines=[]
    for c in comps:
        cap_lines.append('%s | %s v%s | %s | read=%s | write=%s'%(
            c.get('component_key'),c.get('semantic_id'),c.get('version'),c.get('exact_status'),
            ','.join(c.get('read_permissions') or [])[:180],','.join(c.get('write_permissions') or [])[:180]))
    pieces=[('Google Drive AUTHORITATIVE StateHead',json.dumps(sh_summary,ensure_ascii=False,indent=2)),
            ('Google Drive AUTHORITATIVE capability registry '+str(registry.get('version')),'\\n'.join(cap_lines)[:8000])]
    mem=google_bundle_summary(state)
    if mem:pieces.append(('Google Drive AUTHORITATIVE durable memory summary',mem[:5000]))
    ranked=sorted(((google_component_score(c,terms,q),c) for c in comps),key=lambda x:x[0],reverse=True)
    taken=0
    for score,c in ranked:
        if score<=0 or taken>=2:break
        fid=c.get('canonical_artifact_id')
        if not fid:continue
        try:
            meta=google_file_meta(fid);txt=google_file_text(fid,meta,5200)
            if txt.strip():
                label='Google Drive CANONICAL component: %s | %s v%s | %s'%(c.get('component_key'),c.get('semantic_id'),c.get('version'),c.get('exact_status'))
                pieces.append((label,txt));taken+=1
        except Exception as e:
            print('ND_RO_GOOGLE_COMPONENT_ERROR',json.dumps({'component':c.get('component_key'),'error':cleanerr(e)},ensure_ascii=False),flush=True)
    pieces.extend(google_search_discovery(q))
    print('ND_RO_GOOGLE_CONTEXT',json.dumps({'registry_version':registry.get('version'),'components':len(comps),'selected_components':taken,'pieces':len(pieces)},ensure_ascii=False),flush=True)
    return pieces

def nd_google_probe():
    time.sleep(5)
    try:
        st,rg=google_state_registry()
        print('ND_GOOGLE_READONLY_PROBE',json.dumps({'ok':True,'statehead_status':st.get('status'),'registry_version':rg.get('version'),'components':len(rg.get('components') or []),'mutations':False},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_GOOGLE_READONLY_PROBE',json.dumps({'ok':False,'error':cleanerr(e),'mutations':False},ensure_ascii=False),flush=True)

"""
code=code.replace(insert_before,google_code+insert_before,1)

old_pieces="""    pieces=[]
    try:pieces.extend(github_nd_context(q))
    except Exception as e:print('ND_RO_GITHUB_ERROR',cleanerr(e),flush=True)
    try:pieces.extend(yandex_nd_context(q))
    except Exception as e:print('ND_RO_YANDEX_ERROR',cleanerr(e),flush=True)
"""
new_pieces="""    pieces=[]
    try:pieces.extend(google_nd_context(q))
    except Exception as e:print('ND_RO_GOOGLE_ERROR',cleanerr(e),flush=True)
    try:pieces.extend(github_nd_context(q))
    except Exception as e:print('ND_RO_GITHUB_ERROR',cleanerr(e),flush=True)
    try:pieces.extend(yandex_nd_context(q))
    except Exception as e:print('ND_RO_YANDEX_ERROR',cleanerr(e),flush=True)
"""
if old_pieces not in code: raise RuntimeError('ND context pieces block not found')
code=code.replace(old_pieces,new_pieces,1)

code=code.replace("any(x in low for x in ('nd','nameless','архитект','statehead','registry','агент','книга','глава','рассказ','черновик','чистовик','сон том'))",
                  "any(x in low for x in ('nd','nameless','архитект','statehead','registry','агент','книга','глава','рассказ','черновик','чистовик','сон том','скил','skill','плагин','plugin','инструмент','tool','памят','memory','автомат','automation','connector','подключ'))",1)

code=code.replace("if used+len(chunk)>18000:chunk=chunk[:max(0,18000-used)]","if used+len(chunk)>22000:chunk=chunk[:max(0,22000-used)]",1)
code=code.replace("if used>=18000:break","if used>=22000:break",1)

probe_marker="threading.Thread(target=nd_ro_probe,daemon=True).start()\\n"
if probe_marker in code:
    code=code.replace(probe_marker,probe_marker+"threading.Thread(target=nd_google_probe,daemon=True).start()\\n",1)

code=code.replace("ND_VK_GATEWAY_V13_ND_READONLY_START","ND_VK_GATEWAY_V25_ND_GOOGLE_AUTHORITY_START",1)
"""
outer=outer.replace(needle,google_patch+"\nprint('ND_V25_BOOTSTRAP',flush=True)",1)
'''
outer=outer.replace(marker,patch+"\nprint('ND_V25_OUTER',flush=True)",1)
exec(compile(outer,'nd_vk_gateway_v25_outer.py','exec'))
