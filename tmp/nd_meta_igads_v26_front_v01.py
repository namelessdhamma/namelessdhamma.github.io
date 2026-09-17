import urllib.request

CANONICAL_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/12b41bdcc52b58781d3dd046842fbdf741ff89fb/tmp/nd_meta_fb_crud_front_v01.py'
HELPER_SUFFIX='/tmp/nd_meta_fb_crud_helper_v01.py'
_orig_urlopen=urllib.request.urlopen

V26_EXT = r"""
def _campaign_probe_v26(rev):
    name='ND_META_Q_'+_meta._tag(rev)+'_PAUSED'
    existing,_=_meta._find_campaign(name)
    cid=existing or ''
    created=False
    if not cid:
        create=_meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','POST',{'name':name,'objective':'OUTCOME_TRAFFIC','status':'PAUSED','special_ad_categories':json.dumps([]),'is_adset_budget_sharing_enabled':'false'})
        if create.get('outcome')=='OUTCOME_UNKNOWN':
            cid,_=_meta._find_campaign(name)
            if not cid:
                return {'ok':False,'stage':'create','outcome':'OUTCOME_UNKNOWN','create':create,'reconciled':False,'spend_possible':False}
        elif not create.get('ok'):
            return {'ok':False,'stage':'create','create':create,'spend_possible':False}
        else:
            cid=str(((create.get('data') or {}).get('id')) or '')
            created=bool(cid)
    if not cid:
        return {'ok':False,'stage':'create','error':'missing_campaign_id','spend_possible':False}
    read=_meta._read(cid,'id,name,status,effective_status,objective,special_ad_categories')
    paused=bool(read.get('ok') and str(((read.get('data') or {}).get('status') or '')).upper()=='PAUSED')
    delete=_meta._graph(cid,'DELETE',{})
    after=_meta._read(cid,'id,name,status,effective_status')
    deleted=bool((not after.get('ok')) or str(((after.get('data') or {}).get('status') or '')).upper()=='DELETED' or str(((after.get('data') or {}).get('effective_status') or '')).upper()=='DELETED')
    ok=bool(read.get('ok') and paused and deleted)
    return {'ok':ok,'name':name,'created':created,'campaign_id':cid,'readback':read,'paused_confirmed':paused,'delete':delete,'delete_readback':after,'deleted_confirmed':deleted,'adsets_created':0,'ads_created':0,'spend_possible':False}

_meta.campaign_probe=_campaign_probe_v26
"""

class _BytesResponse:
    def __init__(self, data):
        self._data=data
    def read(self):
        return self._data
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False

def _urlopen_v26(req, *args, **kwargs):
    url=getattr(req,'full_url',None) or str(req)
    if not url.endswith(HELPER_SUFFIX):
        return _orig_urlopen(req,*args,**kwargs)
    with _orig_urlopen(req,*args,**kwargs) as r:
        src=r.read().decode('utf-8')
    src += "\nRUNTIME_GLOBALS = RUNTIME_GLOBALS + '\\n' + " + repr(V26_EXT) + "\n"
    print('ND_META_IGADS_V26_HELPER_INTERCEPT',flush=True)
    return _BytesResponse(src.encode('utf-8'))

urllib.request.urlopen=_urlopen_v26
src=_orig_urlopen(CANONICAL_FRONT,timeout=30).read().decode('utf-8')
print('ND_META_IGADS_V26_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_fb_crud_front_v01.py','exec'))
