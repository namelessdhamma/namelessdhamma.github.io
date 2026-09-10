import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/bb32a0851e4e6174c7f4eec7af74c2d82be4093d/tmp/nd_vk_gateway_v14_nd_readonly_yandex.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="""    if not items:return []
    terms=nd_query_terms(q)
"""
new="""    exts={}
    for _i in items:
        _n=(_i.get('name') or '').lower()
        _e=(_n.rsplit('.',1)[-1] if '.' in _n else '[none]')
        exts[_e]=exts.get(_e,0)+1
    print('ND_RO_YANDEX_SCAN',json.dumps({'items':len(items),'extensions':exts},ensure_ascii=False),flush=True)
    if not items:return []
    terms=nd_query_terms(q)
"""
if old not in code:raise RuntimeError('V14 Yandex diagnostic insertion point not found')
code=code.replace(old,new,1)
code=code.replace('ND_V14_BOOTSTRAP','ND_V15_BOOTSTRAP',1)
code=code.replace('ND_VK_GATEWAY_V14_ND_READONLY_START','ND_VK_GATEWAY_V15_ND_READONLY_START',1)
print('ND_V15_OUTER',flush=True)
exec(compile(code,'nd_vk_gateway_v15_outer.py','exec'))
