import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9ebbfe3c8dbeb9a57f23e63c34527d5e3afd46fc/tmp/nd_vk_gateway_v13_nd_readonly.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

# Patch the V13 source directly rather than stacking wrappers.
code=code.replace("r'[A-Za-zА-Яа-яЁё0-9_-]{3,}'", "r'[A-Za-zА-Яа-яЁё0-9_-]{2,}'",1)
code=code.replace("ND_VK_GATEWAY_V13_ND_READONLY_START", "ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START",1)
code=code.replace("ND_V13_WRAPPER_LOADED", "ND_V17_INNER_LOADED",1)

old_listing="""    try:
        u='https://cloud-api.yandex.net/v1/disk/resources/files?limit=1000&fields=items.name,items.path,items.size,items.mime_type'
        j=ro_get_json(u,headers,35)
    except Exception as e:
        print('ND_RO_YANDEX_LIST_ERROR',cleanerr(e),flush=True);return []
    terms=nd_query_terms(q)
    cand=[]
    for item in (j.get('items') or []):
"""
new_listing="""    items=[]
    for folder in ('/сон том 2','/сон том 2/Черновики','/сон том 2/Проработка глав'):
        try:
            u='https://cloud-api.yandex.net/v1/disk/resources?path='+quote(folder,safe='')+'&limit=1000&fields=_embedded.items.name,_embedded.items.path,_embedded.items.size,_embedded.items.mime_type'
            j=ro_get_json(u,headers,35)
            for ii in (((j.get('_embedded') or {}).get('items') or [])):
                if not ii.get('path') and ii.get('name'):
                    ii=dict(ii);ii['path']='disk:'+folder.rstrip('/')+'/'+ii.get('name','')
                items.append(ii)
        except Exception as e:
            print('ND_RO_YANDEX_FOLDER_ERROR',json.dumps({'folder':folder,'error':cleanerr(e)},ensure_ascii=False),flush=True)
    exts={};with_path=0
    for ii in items:
        if ii.get('path'):with_path+=1
        nn=(ii.get('name') or '').lower();ee=(nn.rsplit('.',1)[-1] if '.' in nn else '[none]');exts[ee]=exts.get(ee,0)+1
    print('ND_RO_YANDEX_SCAN',json.dumps({'items':len(items),'with_path':with_path,'extensions':exts},ensure_ascii=False),flush=True)
    if not items:return []
    terms=nd_query_terms(q)
    cand=[];seen_paths=set()
    for item in items:
        p0=item.get('path') or ''
        if p0 in seen_paths:continue
        seen_paths.add(p0)
"""
if old_listing not in code:raise RuntimeError('V13 Yandex listing block not found')
code=code.replace(old_listing,new_listing,1)

old_filter="        if '/сон том 2/' not in pl:continue\n"
if old_filter not in code:raise RuntimeError('V13 path filter not found')
code=code.replace(old_filter,'',1)

old_append="if text:out.append(('Yandex Disk: '+p,text[:7000]))"
new_append="if text:\n                print('ND_RO_YANDEX_READ_OK',json.dumps({'ext':p.rsplit('.',1)[-1].lower() if '.' in p else 'none','chars':len(text)},ensure_ascii=False),flush=True)\n                out.append(('Yandex Disk: '+p,text[:7000]))"
if old_append not in code:raise RuntimeError('V13 Yandex append point not found')
code=code.replace(old_append,new_append,1)

print('ND_V17_BOOTSTRAP',flush=True)
exec(compile(code,'nd_vk_gateway_v17_bootstrap.py','exec'))
