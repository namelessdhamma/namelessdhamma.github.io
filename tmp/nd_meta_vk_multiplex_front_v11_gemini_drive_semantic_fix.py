import json, urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/930ac47d2f46adb1d277f88bc48c529a25431193/tmp/nd_meta_vk_multiplex_front_v06_gemini_drive_e2e.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

env_anchor="QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\\nGEMINI_INTROSPECT_URL="
env_repl="QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\\nDRIVE_URL='http://127.0.0.1:3302'\\nGEMINI_INTROSPECT_URL="
if src.count(env_anchor)!=1:
    raise RuntimeError('v11 env anchor mismatch count='+str(src.count(env_anchor)))
src=src.replace(env_anchor,env_repl,1)

route_anchor="            META+'/invoke',data=raw,method='POST',\\n"
route_repl="            DRIVE_URL+'/invoke',data=raw,method='POST',\\n"
if src.count(route_anchor)!=1:
    raise RuntimeError('v11 semantic route anchor mismatch count='+str(src.count(route_anchor)))
src=src.replace(route_anchor,route_repl,1)

print('ND_GEMINI_DRIVE_E2E_V11_SEMANTIC_FIX_READY '+json.dumps({'drive_target':'127.0.0.1:3302/invoke','auth':'QSTASH_TOKEN bearer','body':'{tool,query}','temporary_qualification':True}),flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v11_gemini_drive_semantic_fix_runtime.py','exec'))
