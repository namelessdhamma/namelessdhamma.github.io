import hashlib, json, os, socket, time, urllib.parse, urllib.request
from urllib.error import HTTPError, URLError

GRAPH_VERSION=(os.environ.get('ND_META_GRAPH_VERSION','v26.0').strip() or 'v26.0')
META_TOKEN=os.environ.get('ND_META_USER_ACCESS_TOKEN','').strip()
BUSINESS_ID=os.environ.get('ND_META_BUSINESS_ID','').strip()
PAGE_ID=os.environ.get('ND_FACEBOOK_PAGE_ID','').strip()
IG_ID=os.environ.get('ND_INSTAGRAM_USER_ID','').strip()
AD_ACCOUNT_ID=os.environ.get('ND_META_AD_ACCOUNT_ID','').strip()
if AD_ACCOUNT_ID and not AD_ACCOUNT_ID.startswith('act_'):
    AD_ACCOUNT_ID='act_'+AD_ACCOUNT_ID
_EXTRA_SECRETS=[]

def _redact(value):
    s=str(value)
    for secret in [META_TOKEN]+list(_EXTRA_SECRETS):
        if secret:
            s=s.replace(secret,'[REDACTED]')
            s=s.replace(urllib.parse.quote(secret,safe=''),'[REDACTED]')
    return s[:4000]

def _safe_obj(obj):
    if isinstance(obj,dict):
        out={}
        for k,v in obj.items():
            if str(k).lower() in ('access_token','token','appsecret_proof'):
                out[k]='[REDACTED]'
            else:
                out[k]=_safe_obj(v)
        return out
    if isinstance(obj,list): return [_safe_obj(x) for x in obj]
    if isinstance(obj,str): return _redact(obj)
    return obj

def _graph(path, method='GET', params=None, token=None, timeout=60):
    tok=(token or META_TOKEN).strip()
    if not tok:
        return {'ok':False,'status':0,'error':'AWAITING_AUTH:ND_META_USER_ACCESS_TOKEN','outcome':'CONFIRMED_NOT_APPLIED'}
    p=dict(params or {})
    url='https://graph.facebook.com/'+GRAPH_VERSION+'/'+str(path).lstrip('/')
    data=None
    headers={'Authorization':'Bearer '+tok,'Accept':'application/json','User-Agent':'ND-True-SMM-Meta-Qualification/1.0'}
    if method.upper()=='GET':
        if p: url += '?' + urllib.parse.urlencode(p)
    else:
        data=urllib.parse.urlencode(p).encode('utf-8')
        headers['Content-Type']='application/x-www-form-urlencoded'
    req=urllib.request.Request(url,data=data,headers=headers,method=method.upper())
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            try: obj=json.loads(raw) if raw else {}
            except Exception: obj={'raw':raw[:2000]}
            if isinstance(obj,dict) and obj.get('error'):
                return {'ok':False,'status':r.status,'error':_safe_obj(obj.get('error')),'outcome':'CONFIRMED_NOT_APPLIED'}
            return {'ok':True,'status':r.status,'data':_safe_obj(obj),'outcome':'CONFIRMED_APPLIED'}
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace')
        try: obj=json.loads(raw) if raw else {}
        except Exception: obj={'raw':raw[:2000]}
        return {'ok':False,'status':e.code,'error':_safe_obj(obj.get('error') if isinstance(obj,dict) and obj.get('error') else obj),'outcome':'CONFIRMED_NOT_APPLIED'}
    except (URLError, TimeoutError, socket.timeout) as e:
        return {'ok':False,'status':0,'error':'transport:'+_redact(e),'outcome':'OUTCOME_UNKNOWN'}
    except Exception as e:
        return {'ok':False,'status':0,'error':'client:'+_redact(e),'outcome':'OUTCOME_UNKNOWN'}

def configured():
    return {'token':bool(META_TOKEN),'business_id':bool(BUSINESS_ID),'page_id':bool(PAGE_ID),
            'instagram_id':bool(IG_ID),'ad_account_id':bool(AD_ACCOUNT_ID),'graph_version':GRAPH_VERSION}

def _read(path, fields, token=None):
    return _graph(path,'GET',{'fields':fields},token=token)

def read_probes():
    probes={}
    probes['business']=_read(BUSINESS_ID,'id,name') if BUSINESS_ID else {'ok':False,'error':'missing_business_id','outcome':'CONFIRMED_NOT_APPLIED'}
    probes['page']=_read(PAGE_ID,'id,name,username') if PAGE_ID else {'ok':False,'error':'missing_page_id','outcome':'CONFIRMED_NOT_APPLIED'}
    probes['instagram']=_read(IG_ID,'id,username,media_count') if IG_ID else {'ok':False,'error':'missing_instagram_id','outcome':'CONFIRMED_NOT_APPLIED'}
    probes['ads']=_read(AD_ACCOUNT_ID,'id,name,account_id,account_status,currency,timezone_name') if AD_ACCOUNT_ID else {'ok':False,'error':'missing_ad_account_id','outcome':'CONFIRMED_NOT_APPLIED'}
    ok=all(bool(v.get('ok')) for v in probes.values())
    return {'ok':ok,'route':'railway','provider':'meta','graph_version':GRAPH_VERSION,'probes':probes}

def _page_token():
    if not PAGE_ID: return '', {'ok':False,'error':'missing_page_id'}
    url='https://graph.facebook.com/'+GRAPH_VERSION+'/'+PAGE_ID+'?'+urllib.parse.urlencode({'fields':'id,name,access_token'})
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+META_TOKEN,'Accept':'application/json','User-Agent':'ND-True-SMM-Meta-Qualification/1.0'},method='GET')
    try:
        with urllib.request.urlopen(req,timeout=60) as resp:
            obj=json.loads(resp.read().decode('utf-8','replace') or '{}')
        tok=str(obj.get('access_token') or '')
    except Exception as e:
        return '', {'ok':False,'error':'page_token_fetch:'+_redact(e)}
    if tok:
        _EXTRA_SECRETS.append(tok)
        return tok, {'ok':True,'page_id':PAGE_ID}
    return '', {'ok':False,'error':'page_access_token_unavailable'}

def _tag(rev):
    return hashlib.sha256(str(rev).encode('utf-8')).hexdigest()[:12]

def _find_unpublished(marker, token):
    if not PAGE_ID: return None, {'ok':False,'error':'missing_page_id'}
    r=_graph(PAGE_ID+'/promotable_posts','GET',{'fields':'id,message,is_published','limit':'100'},token=token)
    if not r.get('ok'): return None,r
    for item in ((r.get('data') or {}).get('data') or []):
        if marker in str(item.get('message') or ''):
            return str(item.get('id') or ''),r
    return None,r

def _confirm_absent(path, token=None):
    r=_read(path,'id',token=token)
    return (not r.get('ok')),r

def facebook_unpublished_probe(rev):
    marker='ND_META_Q_'+_tag(rev)
    token,tok_state=_page_token()
    if not token: return {'ok':False,'stage':'page_token','detail':tok_state}
    existing,_=_find_unpublished(marker,token)
    post_id=existing or ''
    created=False
    if not post_id:
        create=_graph(PAGE_ID+'/feed','POST',{'message':marker+' unpublished qualification','published':'false'},token=token)
        if create.get('outcome')=='OUTCOME_UNKNOWN':
            post_id,_=_find_unpublished(marker,token)
            if not post_id:
                return {'ok':False,'stage':'create','outcome':'OUTCOME_UNKNOWN','create':create,'reconciled':False}
        elif not create.get('ok'):
            return {'ok':False,'stage':'create','create':create}
        else:
            post_id=str(((create.get('data') or {}).get('id')) or '')
            created=bool(post_id)
    if not post_id: return {'ok':False,'stage':'create','error':'missing_post_id'}
    read=_read(post_id,'id,message,created_time',token=token)
    delete=_graph(post_id,'DELETE',{},token=token)
    absent,after=_confirm_absent(post_id,token=token)
    if delete.get('outcome')=='OUTCOME_UNKNOWN' and not absent:
        delete2=_graph(post_id,'DELETE',{},token=token)
        absent,after=_confirm_absent(post_id,token=token)
        delete={'first':delete,'retry_after_confirmed_not_applied':delete2}
    ok=bool(read.get('ok') and absent)
    return {'ok':ok,'marker':marker,'created':created,'post_id':post_id,'readback':read,'delete':delete,'delete_readback_absent':absent,'after':after}

def _ig_image_url():
    explicit=os.environ.get('ND_META_QUAL_IMAGE_URL','').strip()
    if explicit: return explicit
    host=os.environ.get('RAILWAY_PUBLIC_DOMAIN','').strip()
    return ('https://'+host+'/nd/meta/qualification-image.jpg') if host else ''

def instagram_container_probe(rev):
    token,tok_state=_page_token()
    if not token: return {'ok':False,'applicable':False,'stage':'page_token','detail':tok_state}
    image_url=_ig_image_url()
    if not image_url: return {'ok':False,'applicable':False,'stage':'image_url','error':'qualification_image_url_unavailable'}
    caption='ND_META_Q_'+_tag(rev)+' non-published qualification container'
    create=_graph(IG_ID+'/media','POST',{'image_url':image_url,'caption':caption},token=token,timeout=90)
    if create.get('outcome')=='OUTCOME_UNKNOWN':
        return {'ok':False,'applicable':True,'stage':'create','outcome':'OUTCOME_UNKNOWN','create':create,'retry':False}
    if not create.get('ok'): return {'ok':False,'applicable':True,'stage':'create','create':create}
    cid=str(((create.get('data') or {}).get('id')) or '')
    if not cid: return {'ok':False,'applicable':True,'stage':'create','error':'missing_container_id'}
    time.sleep(2)
    read=_read(cid,'id,status_code,status',token=token)
    return {'ok':bool(read.get('ok')),'applicable':True,'container_id':cid,'readback':read,'media_publish_called':False,'public_post_created':False,'cleanup':'provider_ephemeral_container_expires'}

def _find_campaign(name):
    r=_graph(AD_ACCOUNT_ID+'/campaigns','GET',{'fields':'id,name,status,effective_status','limit':'100'})
    if not r.get('ok'): return None,r
    for item in ((r.get('data') or {}).get('data') or []):
        if str(item.get('name') or '')==name:
            return str(item.get('id') or ''),r
    return None,r

def campaign_probe(rev):
    name='ND_META_Q_'+_tag(rev)+'_PAUSED'
    existing,_=_find_campaign(name)
    cid=existing or ''
    created=False
    if not cid:
        create=_graph(AD_ACCOUNT_ID+'/campaigns','POST',{'name':name,'objective':'OUTCOME_TRAFFIC','status':'PAUSED','special_ad_categories':json.dumps([]),'is_adset_budget_sharing_enabled':'false'})
        if create.get('outcome')=='OUTCOME_UNKNOWN':
            cid,_=_find_campaign(name)
            if not cid:
                return {'ok':False,'stage':'create','outcome':'OUTCOME_UNKNOWN','create':create,'reconciled':False,'spend_possible':False}
        elif not create.get('ok'):
            return {'ok':False,'stage':'create','create':create,'spend_possible':False}
        else:
            cid=str(((create.get('data') or {}).get('id')) or '')
            created=bool(cid)
    if not cid: return {'ok':False,'stage':'create','error':'missing_campaign_id','spend_possible':False}
    read=_read(cid,'id,name,status,effective_status,objective,special_ad_categories')
    paused=bool(read.get('ok') and str(((read.get('data') or {}).get('status') or '')).upper()=='PAUSED')
    delete=_graph(cid,'DELETE',{})
    after=_read(cid,'id,name,status,effective_status')
    deleted=bool((not after.get('ok')) or str(((after.get('data') or {}).get('status') or '')).upper()=='DELETED' or str(((after.get('data') or {}).get('effective_status') or '')).upper()=='DELETED')
    if delete.get('outcome')=='OUTCOME_UNKNOWN' and not deleted:
        delete2=_graph(cid,'DELETE',{})
        after=_read(cid,'id,name,status,effective_status')
        deleted=bool((not after.get('ok')) or str(((after.get('data') or {}).get('status') or '')).upper()=='DELETED' or str(((after.get('data') or {}).get('effective_status') or '')).upper()=='DELETED')
        delete={'first':delete,'retry_after_confirmed_not_applied':delete2}
    ok=bool(read.get('ok') and paused and deleted)
    return {'ok':ok,'name':name,'created':created,'campaign_id':cid,'readback':read,'paused_confirmed':paused,'delete':delete,'delete_readback':after,'deleted_confirmed':deleted,'adsets_created':0,'ads_created':0,'spend_possible':False}

def qualify_all(rev):
    started=int(time.time())
    reads=read_probes()
    result={'provider':'meta','route':'railway','graph_version':GRAPH_VERSION,'qualification_rev':_tag(rev),'started_at':started,'configured':configured(),'reads':reads}
    if not reads.get('ok'):
        result.update({'status':'FAIL','ok':False,'writes_skipped':True,'reason':'read_precondition_failed'})
        return result
    fb=facebook_unpublished_probe(rev)
    ig=instagram_container_probe(rev)
    ads=campaign_probe(rev)
    result['facebook_unpublished']=fb
    result['instagram_container']=ig
    result['ads_paused_campaign']=ads
    core=bool(reads.get('ok') and fb.get('ok') and ads.get('ok'))
    status='PASS' if core and ig.get('ok') else ('PARTIAL' if core else 'FAIL')
    result.update({'status':status,'ok':status=='PASS','core_meta_pass':core,'finished_at':int(time.time())})
    return _safe_obj(result)
