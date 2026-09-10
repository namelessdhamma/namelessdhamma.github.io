import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/bb32a0851e4e6174c7f4eec7af74c2d82be4093d/tmp/nd_vk_gateway_v14_nd_readonly_yandex.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old_filter="        if '/сон том 2/' not in pl:continue\n"
if old_filter not in code:raise RuntimeError('V14 path filter not found')
code=code.replace(old_filter,'',1)
old_point="""    if not items:return []
    terms=nd_query_terms(q)
"""
new_point="""    exts={}
    for _i in items:
        _n=(_i.get('name') or '').lower();_e=(_n.rsplit('.',1)[-1] if '.' in _n else '[none]');exts[_e]=exts.get(_e,0)+1
    print('ND_RO_YANDEX_SCAN',json.dumps({'items':len(items),'extensions':exts},ensure_ascii=False),flush=True)
    if not items:return []
    terms=nd_query_terms(q)
"""
if old_point not in code:raise RuntimeError('V14 scan insertion point not found')
code=code.replace(old_point,new_point,1)
old_append="if text:out.append(('Yandex Disk: '+p,text[:7000]))"
new_append="if text:\n                print('ND_RO_YANDEX_READ_OK',json.dumps({'ext':p.rsplit('.',1)[-1].lower() if '.' in p else 'none','chars':len(text)},ensure_ascii=False),flush=True)\n                out.append(('Yandex Disk: '+p,text[:7000]))"
if old_append not in code:raise RuntimeError('V14 append point not found')
code=code.replace(old_append,new_append,1)
code=code.replace('ND_V14_BOOTSTRAP','ND_V16B_BOOTSTRAP',1)
code=code.replace('ND_VK_GATEWAY_V14_ND_READONLY_START','ND_VK_GATEWAY_V16B_ND_READONLY_START',1)
print('ND_V16B_OUTER',flush=True)
exec(compile(code,'nd_vk_gateway_v16b_outer.py','exec'))
