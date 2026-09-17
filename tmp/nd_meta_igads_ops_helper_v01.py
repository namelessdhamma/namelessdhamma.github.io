import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'
ns={}
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
exec(compile(src,'nd_meta_fb_crud_helper_v01.py','exec'),ns)

IGADS_OPS_EXT = r"""
_meta_mcp_tools_base=meta_mcp_tools
_meta_mcp_call_base=meta_mcp_call
META_IGADS_MUTATIONS={}

def _igads_guard(args,path,method,params,token=None):
    mid=str(args.get('mutation_id') or '').strip()
    if not bool(args.get('confirm')): return {'ok':False,'error':'confirm_required'}
    if not mid: return {'ok':False,'error':'mutation_id_required'}
    sig=json.dumps({'path':path,'method':method,'params':params},sort_keys=True,separators=(',',':'),ensure_ascii=False)
    old=META_IGADS_MUTATIONS.get(mid)
    if old:
        if old.get('signature')!=sig: return {'ok':False,'error':'mutation_id_payload_mismatch','mutation_id':mid}
        return {'ok':old.get('outcome')=='CONFIRMED_APPLIED','mutation_id':mid,'retry_blocked':True,'prior':old}
    out=_meta._graph(path,method,params,token=token)
    rec={'signature':sig,'outcome':out.get('outcome'),'status':out.get('status'),'ts':int(time.time())}
    META_IGADS_MUTATIONS[mid]=rec
    return {'ok':bool(out.get('ok')),'mutation_id':mid,'result':out,'outcome':out.get('outcome'),'retry_blocked':out.get('outcome')=='OUTCOME_UNKNOWN'}

def _ig_media_tool(args):
    op=str(args.get('operation') or '').lower()
    if op=='list':
        return _meta._graph(_meta.IG_ID+'/media','GET',{'fields':'id,caption,media_type,media_url,permalink,timestamp','limit':str(args.get('limit') or 25)})
    oid=str(args.get('media_id') or args.get('container_id') or '').strip()
    if op=='get':
        if not oid: return {'ok':False,'error':'media_id_required'}
        return _meta._read(oid,'id,caption,media_type,media_url,permalink,timestamp')
    if op=='container_status':
        if not oid: return {'ok':False,'error':'container_id_required'}
        return _meta._read(oid,'id,status_code,status')
    if op=='create_container':
        image_url=str(args.get('image_url') or '').strip()
        if not image_url: return {'ok':False,'error':'image_url_required'}
        params={'image_url':image_url,'caption':str(args.get('caption') or '')}
        out=_igads_guard(args,_meta.IG_ID+'/media','POST',params)
        cid=str((((out.get('result') or {}).get('data') or {}).get('id')) or '')
        rb=_meta._read(cid,'id,status_code,status') if cid else None
        out['container_id']=cid
        out['readback']=rb
        out['media_publish_called']=False
        out['public_post_created']=False
        return out
    if op=='publish':
        return {'ok':False,'error':'public_publish_not_qualified','fail_closed':True}
    return {'ok':False,'error':'unsupported_operation'}

def _ads_campaign_tool(args):
    op=str(args.get('operation') or '').lower()
    cid=str(args.get('campaign_id') or '').strip()
    fields='id,name,status,effective_status,objective,special_ad_categories'
    if op=='list':
        return _meta._graph(_meta.AD_ACCOUNT_ID+'/campaigns','GET',{'fields':fields,'limit':str(args.get('limit') or 25)})
    if op=='get':
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        return _meta._read(cid,fields)
    if op=='insights':
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        return _meta._graph(cid+'/insights','GET',{'fields':'impressions,reach,clicks,spend,cpm,cpc,ctr','date_preset':str(args.get('date_preset') or 'last_30d')})
    if op=='create_paused':
        name=str(args.get('name') or '').strip()
        if not name: return {'ok':False,'error':'name_required'}
        params={'name':name,'objective':str(args.get('objective') or 'OUTCOME_TRAFFIC'),'status':'PAUSED','special_ad_categories':json.dumps([]),'is_adset_budget_sharing_enabled':'false'}
        out=_igads_guard(args,_meta.AD_ACCOUNT_ID+'/campaigns','POST',params)
        new_id=str((((out.get('result') or {}).get('data') or {}).get('id')) or '')
        out['campaign_id']=new_id
        out['readback']=_meta._read(new_id,fields) if new_id else None
        out['adsets_created']=0
        out['ads_created']=0
        out['spend_possible']=False
        return out
    if op=='update_paused':
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        params={'status':'PAUSED'}
        if str(args.get('name') or '').strip(): params['name']=str(args.get('name')).strip()
        out=_igads_guard(args,cid,'POST',params)
        out['readback']=_meta._read(cid,fields) if out.get('ok') else None
        out['spend_possible']=False
        return out
    if op=='delete':
        if not cid: return {'ok':False,'error':'campaign_id_required'}
        out=_igads_guard(args,cid,'DELETE',{})
        rb=_meta._read(cid,'id,name,status,effective_status')
        out['readback']=rb
        out['deleted_confirmed']=bool((not rb.get('ok')) or str(((rb.get('data') or {}).get('status') or '')).upper()=='DELETED' or str(((rb.get('data') or {}).get('effective_status') or '')).upper()=='DELETED')
        out['spend_possible']=False
        return out
    if op=='activate':
        return {'ok':False,'error':'campaign_activation_not_qualified','fail_closed':True}
    return {'ok':False,'error':'unsupported_operation'}

def meta_mcp_tools():
    tools=_meta_mcp_tools_base()
    tools.extend([
      {'name':'meta_instagram_media','description':'Instagram media reads and guarded non-public image-container creation. Public publish is fail-closed until separately qualified. Mutations require confirm=true and mutation_id.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','container_status','create_container','publish']},'media_id':{'type':'string'},'container_id':{'type':'string'},'image_url':{'type':'string'},'caption':{'type':'string'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
      {'name':'meta_ads_campaigns','description':'Meta Ads campaign reads/insights and guarded PAUSED-only create/update/delete. Activation is fail-closed. Mutations require confirm=true and mutation_id; this tool does not create ad sets or ads.','inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['list','get','insights','create_paused','update_paused','delete','activate']},'campaign_id':{'type':'string'},'name':{'type':'string'},'objective':{'type':'string'},'date_preset':{'type':'string'},'limit':{'type':'integer'},'confirm':{'type':'boolean'},'mutation_id':{'type':'string'}},'required':['operation'],'additionalProperties':False}},
    ])
    return tools

def meta_mcp_call(name,args):
    if name=='meta_instagram_media': return _ig_media_tool(args)
    if name=='meta_ads_campaigns': return _ads_campaign_tool(args)
    return _meta_mcp_call_base(name,args)

def meta_igads_ops_selftest_once():
    time.sleep(11)
    try:
        ig=meta_mcp_call('meta_instagram_media',{'operation':'list','limit':1})
        ads=meta_mcp_call('meta_ads_campaigns',{'operation':'list','limit':1})
        print('ND_META_IGADS_OPS_SELFTEST '+json.dumps({'ok':bool(ig.get('ok') and ads.get('ok')),'tools_count':len(meta_mcp_tools()),'instagram_list_ok':bool(ig.get('ok')),'ads_list_ok':bool(ads.get('ok')),'public_publish_enabled':False,'ads_activation_enabled':False},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_META_IGADS_OPS_SELFTEST '+json.dumps({'ok':False,'error':str(e)[:700]},ensure_ascii=False),flush=True)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"
"+IGADS_OPS_EXT
ns['MCP_METHOD']=ns['MCP_METHOD'].replace('Nameless Dhamma Meta MCP with guarded Facebook Page and comment CRUD.','Nameless Dhamma Meta MCP with guarded Facebook, Instagram media and PAUSED-only Ads operations.')
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']
_base_patch=ns['patch_linear_wrapper_source']

def patch_linear_wrapper_source(src):
    out=_base_patch(src)
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if out.count(runtime_exec)!=1: raise RuntimeError('igads ops runtime exec marker mismatch')
    inject="threading.Thread(target=meta_igads_ops_selftest_once,daemon=True).start()
print('ND_META_IGADS_OPS_HELPER_READY '+json.dumps({'direct_mcp':True,'tools':9,'facebook_crud':True,'instagram_ops':True,'ads_ops':True,'public_publish':False,'ads_activation':False},ensure_ascii=False),flush=True)
"+runtime_exec
    return out.replace(runtime_exec,inject,1)
# checkpoint-pin: meta-igads-ops-v1
