import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ba4b4a9430559450d916ab184f048b52f4d7b4eb/tmp/nd_vk_gateway_v17_nd_readonly_complete.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17_BOOTSTRAP',flush=True)"
if marker not in outer: raise RuntimeError('V17 bootstrap marker not found')
inject=r'''
code=code.replace("cand.sort(key=lambda x:(x[0],x[1]),reverse=True)","cand.sort(key=lambda x:(x[0],x[1]),reverse=True)\n    print('ND_RO_YANDEX_TOP',json.dumps([{'score':x[0],'name':(x[2].get('name') or x[1].rsplit('/',1)[-1]),'size':x[2].get('size')} for x in cand[:12]],ensure_ascii=False),flush=True)",1)
code=code.replace("ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START","ND_VK_GATEWAY_V21_ND_READONLY_PATH_DIAG_START",1)
'''
outer=outer.replace(marker,inject+"\nprint('ND_V21_BOOTSTRAP',flush=True)",1)
print('ND_V21_OUTER',flush=True)
exec(compile(outer,'nd_vk_gateway_v21_outer.py','exec'))
