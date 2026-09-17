import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'
HELPER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'

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
    return {'ok':bool(read.get('ok') and paused and deleted),'name':name,'created':created,'campaign_id':cid,'readback':read,'paused_confirmed':paused,'delete':delete,'delete_readback':after,'deleted_confirmed':deleted,'adsets_created':0,'ads_created':0,'spend_possible':False}

_meta.campaign_probe=_campaign_probe_v26
"""

outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
final_outer_exec="exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))"
if outer.count(final_outer_exec)!=1:
    raise RuntimeError('igads inner final exec marker mismatch')
stage="\n".join([
    "helper_ns={}",
    "helper_src=urllib.request.urlopen("+repr(HELPER)+",timeout=30).read().decode('utf-8')",
    "exec(compile(helper_src,'nd_meta_fb_crud_helper_v01.py','exec'),helper_ns)",
    "helper_ns['RUNTIME_GLOBALS']=helper_ns['RUNTIME_GLOBALS']+'\\n'+"+repr(V26_EXT),
    "src=helper_ns['patch_linear_wrapper_source'](src)",
    "print('ND_META_IGADS_INNER_READY',flush=True)",
    final_outer_exec,
])
outer=outer.replace(final_outer_exec,stage,1)
print('ND_META_IGADS_OUTER_READY',flush=True)
exec(compile(outer,'nd_meta_igads_inner_wrapper_v01_outer.py','exec'))
