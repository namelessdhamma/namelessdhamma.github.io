import json, os, subprocess, sys, time, urllib.error, urllib.request

V12='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/52eae2e57468cc39b5d1e7bfd375abb494b45a4f/tmp/nd_meta_vk_multiplex_front_v12_gemini_drive_semantic_fix.py'
path='/tmp/nd-gemini-v12.py'
open(path,'wb').write(urllib.request.urlopen(V12,timeout=30).read())
child=subprocess.Popen([sys.executable,'-u',path],env=dict(os.environ))

health='http://127.0.0.1:3000/gemini/drive/health'
for _ in range(45):
    if child.poll() is not None:
        raise RuntimeError('v12_child_exited_'+str(child.returncode))
    try:
        with urllib.request.urlopen(health,timeout=3) as r:
            if r.status==200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise RuntimeError('v12_local_health_timeout')

url='http://127.0.0.1:3000/gemini/drive/e2e-selftest'
status=0
body=''
try:
    with urllib.request.urlopen(url,timeout=210) as r:
        status=r.status
        body=r.read().decode('utf-8','replace')
except urllib.error.HTTPError as e:
    status=e.code
    body=e.read().decode('utf-8','replace')
except Exception as e:
    status=-1
    body=json.dumps({'error':type(e).__name__+':'+str(e)})
print('ND_GEMINI_E2E_LOCAL_RESULT '+json.dumps({'status':status,'body':body[:4000]},ensure_ascii=False),flush=True)
child.wait()
