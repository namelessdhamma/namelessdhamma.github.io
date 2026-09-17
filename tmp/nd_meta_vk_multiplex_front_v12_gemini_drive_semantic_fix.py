import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/930ac47d2f46adb1d277f88bc48c529a25431193/tmp/nd_meta_vk_multiplex_front_v06_gemini_drive_e2e.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="META+'/invoke'"
new="'http://127.0.0.1:3302/invoke'"
if src.count(old)!=1:
    raise RuntimeError('v12 semantic route literal mismatch count=%d' % src.count(old))
src=src.replace(old,new,1)
print('ND_GEMINI_DRIVE_E2E_V12_SEMANTIC_FIX_READY',flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v12_gemini_drive_semantic_fix_runtime.py','exec'))
