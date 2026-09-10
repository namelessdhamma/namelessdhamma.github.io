import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9ebbfe3c8dbeb9a57f23e63c34527d5e3afd46fc/tmp/nd_vk_gateway_v13_nd_readonly.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

code=code.replace("r'[A-Za-zА-Яа-яЁё0-9_-]{3,}'", "r'[A-Za-zА-Яа-яЁё0-9_-]{2,}'",1)
code=code.replace("ND_VK_GATEWAY_V13_ND_READONLY_START", "ND_VK_GATEWAY_V14_ND_READONLY_START",1)
code=code.replace("ND_V13_WRAPPER_LOADED", "ND_V14_WRAPPER_LOADED",1)

old="""    try:
        u='https://cloud-api.yandex.net/v1/disk/resources/files?limit=1000&fields=items.name,items.path,items.size,items.mime_type'
        j=ro_get_json(u,headers,35)
    except Exception as e:
        print('ND_RO_YANDEX_LIST_ERROR',cleanerr(e),flush=True);return []
    terms=nd_query_terms(q)
    cand=[]
    for item in (j.get('items') or []):
"""
new="""    items=[]
    for folder in ('/сон том 2','/сон том 2/Черновики','/сон том 2/Проработка глав'):
        try:
            u='https://cloud-api.yandex.net/v1/disk/resources?path='+quote(folder,safe='')+'&limit=1000&fields=_embedded.items.name,_embedded.items.path,_embedded.items.size,_embedded.items.mime_type'
            j=ro_get_json(u,headers,35)
            items.extend(((j.get('_embedded') or {}).get('items') or []))
        except Exception as e:
            print('ND_RO_YANDEX_FOLDER_ERROR',json.dumps({'folder':folder,'error':cleanerr(e)},ensure_ascii=False),flush=True)
    if not items:return []
    terms=nd_query_terms(q)
    cand=[];seen_paths=set()
    for item in items:
        p0=item.get('path') or ''
        if p0 in seen_paths:continue
        seen_paths.add(p0)
"""
if old not in code:
    raise RuntimeError('V13 Yandex listing block not found')
code=code.replace(old,new,1)

print('ND_V14_BOOTSTRAP',flush=True)
exec(compile(code,'nd_vk_gateway_v14_bootstrap.py','exec'))
