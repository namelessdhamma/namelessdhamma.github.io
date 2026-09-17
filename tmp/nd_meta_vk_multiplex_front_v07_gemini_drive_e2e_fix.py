import json, urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/930ac47d2f46adb1d277f88bc48c529a25431193/tmp/nd_meta_vk_multiplex_front_v06_gemini_drive_e2e.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

patches=[
    ("QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\\nGEMINI_INTROSPECT_URL=", "QSTASH_TOKEN=os.environ.get('QSTASH_TOKEN','').strip()\\nDRIVE_BRIDGE_TOKEN=os.environ.get('ND_DRIVE_BRIDGE_TOKEN','').strip()\\nDRIVE_URL='http://127.0.0.1:3302'\\nGEMINI_INTROSPECT_URL="),
    ("        if not QSTASH_TOKEN:\\n            raise RuntimeError('internal_broker_auth_unconfigured')", "        if not DRIVE_BRIDGE_TOKEN:\\n            raise RuntimeError('drive_bridge_auth_unconfigured')"),
    ("        raw=json.dumps({'tool':tool,'query':query},ensure_ascii=False).encode('utf-8')", "        raw=json.dumps({'tool':tool,'args':{'query':query}},ensure_ascii=False).encode('utf-8')"),
    ("            META+'/invoke',data=raw,method='POST',\\n            headers={'Authorization':'Bearer '+QSTASH_TOKEN,'Content-Type':'application/json','Accept':'application/json','User-Agent':'ND-Gemini-Drive-MCP/1.0'})", "            DRIVE_URL+'/drive/invoke',data=raw,method='POST',\\n            headers={'X-ND-Bridge-Key':DRIVE_BRIDGE_TOKEN,'Content-Type':'application/json','Accept':'application/json','User-Agent':'ND-Gemini-Drive-MCP/1.1'})")
]
for old,new in patches:
    if src.count(old)!=1:
        raise RuntimeError('v07 qualification patch anchor mismatch: '+old[:80])
    src=src.replace(old,new,1)
print('ND_GEMINI_DRIVE_E2E_V07_FIX_READY '+json.dumps({'drive_target':'127.0.0.1:3302/drive/invoke','contract':'X-ND-Bridge-Key + {tool,args}','temporary_qualification':True}),flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v07_gemini_drive_e2e_fix_runtime.py','exec'))
