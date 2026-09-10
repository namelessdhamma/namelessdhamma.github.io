import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ba4b4a9430559450d916ab184f048b52f4d7b4eb/tmp/nd_vk_gateway_v17_nd_readonly_complete.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17_BOOTSTRAP',flush=True)"
if marker not in code:raise RuntimeError('V17 bootstrap marker not found')
inject=r'''
code=code.replace("cand.sort(key=lambda x:(x[0],x[1]),reverse=True)", "cand.sort(key=lambda x:(x[0],x[1]),reverse=True)\n    print('ND_RO_YANDEX_CAND',json.dumps({'count':len(cand),'top_scores':[x[0] for x in cand[:5]],'top_exts':[(x[1].rsplit('.',1)[-1].lower() if '.' in x[1] else 'none') for x in cand[:5]]},ensure_ascii=False),flush=True)",1)
code=code.replace("data=ro_get_bytes(href,None,45,6000000)", "data=ro_get_bytes(href,None,45,6000000)\n            print('ND_RO_YANDEX_DOWNLOAD',json.dumps({'bytes':len(data),'zip_magic':data[:2]==b'PK','ext':p.rsplit('.',1)[-1].lower() if '.' in p else 'none'},ensure_ascii=False),flush=True)",1)
code=code.replace("text=docx_text(data) if p.lower().endswith('.docx') else data.decode('utf-8','replace')", "text=docx_text(data) if p.lower().endswith('.docx') else data.decode('utf-8','replace')\n            print('ND_RO_YANDEX_PARSE',json.dumps({'chars':len(text),'ext':p.rsplit('.',1)[-1].lower() if '.' in p else 'none'},ensure_ascii=False),flush=True)",1)
'''
code=code.replace(marker,inject+"\nprint('ND_V18_BOOTSTRAP',flush=True)",1)
code=code.replace('ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START','ND_VK_GATEWAY_V18_ND_READONLY_DIAG_START',1)
print('ND_V18_OUTER',flush=True)
exec(compile(code,'nd_vk_gateway_v18_outer.py','exec'))
