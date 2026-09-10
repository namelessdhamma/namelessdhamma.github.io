import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/008a543afe418003e7b0b35f43f4bee187fdc10d/tmp/nd_vk_gateway_v15_nd_readonly_diag.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="        if '/сон том 2/' not in pl:continue\n"
if old not in code:raise RuntimeError('V15 path filter not found')
code=code.replace(old,'',1)
code=code.replace('ND_V15_BOOTSTRAP','ND_V16_BOOTSTRAP',1)
code=code.replace('ND_VK_GATEWAY_V15_ND_READONLY_START','ND_VK_GATEWAY_V16_ND_READONLY_START',1)
code=code.replace("if text:out.append(('Yandex Disk: '+p,text[:7000]))", "if text:\n                print('ND_RO_YANDEX_READ_OK',json.dumps({'ext':p.rsplit('.',1)[-1].lower() if '.' in p else 'none','chars':len(text)},ensure_ascii=False),flush=True)\n                out.append(('Yandex Disk: '+p,text[:7000]))",1)
print('ND_V16_OUTER',flush=True)
exec(compile(code,'nd_vk_gateway_v16_outer.py','exec'))
