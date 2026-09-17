import json, os, subprocess, sys, time, urllib.error, urllib.request

V12='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/52eae2e57468cc39b5d1e7bfd375abb494b45a4f/tmp/nd_meta_vk_multiplex_front_v12_gemini_drive_semantic_fix.py'
path='/tmp/nd-gemini-v12.py'
open(path,'wb').write(urllib.request.urlopen(V12,timeout=30).read())
child=subprocess.Popen([sys.executable,'-u',path],env=dict(os.environ))

for _ in range(45):
    if child.poll() is not None:
        raise RuntimeError('v12_child_exited_'+str(child.returncode))
    try:
        with urllib.request.urlopen('http://127.0.0.1:3000/gemini/drive/health',timeout=3) as r:
            if r.status==200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise RuntimeError('v12_local_health_timeout')

token=os.environ.get('ND_GEMINI_SELFTEST_TOKEN','').strip()
if not token:
    raise RuntimeError('probe_token_missing')
payload={'jsonrpc':'2.0','id':'v12-direct-probe','method':'tools/call','params':{'name':'nd_authority','arguments':{'query':'Report current ND StateHead status, Capability Registry version, and component count.'}}}
req=urllib.request.Request('http://127.0.0.1:3000/gemini/drive/mcp',data=json.dumps(payload).encode('utf-8'),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json','MCP-Protocol-Version':'2025-06-18'})
status=0
body=''
try:
    with urllib.request.urlopen(req,timeout=150) as r:
        status=r.status
        body=r.read().decode('utf-8','replace')
except urllib.error.HTTPError as e:
    status=e.code
    body=e.read().decode('utf-8','replace')
except Exception as e:
    status=-1
    body=json.dumps({'error':type(e).__name__+':'+str(e)})
print('ND_GEMINI_V12_DIRECT_MCP_PROBE '+json.dumps({'status':status,'body':body[:6000]},ensure_ascii=False),flush=True)
child.wait()
