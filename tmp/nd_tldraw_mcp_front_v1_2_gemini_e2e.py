import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/3a2da853bdd88b65e9e4dee6d39e8094a52dede7/tmp/nd_tldraw_mcp_front_v1.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
if src.count(marker)!=1:
    raise RuntimeError('tldraw serve marker mismatch count='+str(src.count(marker)))
inject=r'''
def _gemini_e2e_once():
    ready=False
    for _ in range(45):
        try:
            with urllib.request.urlopen(INNER+'/gemini/drive/health',timeout=3) as r:
                if r.status==200:
                    ready=True
                    break
        except Exception:
            pass
        time.sleep(1)
    if not ready:
        print('ND_GEMINI_E2E_TLDRAW_RESULT '+json.dumps({'status':-1,'error':'inner_health_timeout'}),flush=True)
        return
    time.sleep(3)
    try:
        with urllib.request.urlopen(INNER+'/gemini/drive/e2e-selftest',timeout=240) as r:
            body=r.read().decode('utf-8','replace')
            print('ND_GEMINI_E2E_TLDRAW_RESULT '+json.dumps({'status':r.status,'body':body[:8000]},ensure_ascii=False),flush=True)
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        print('ND_GEMINI_E2E_TLDRAW_RESULT '+json.dumps({'status':e.code,'body':body[:8000]},ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_GEMINI_E2E_TLDRAW_RESULT '+json.dumps({'status':-1,'error':type(e).__name__+':'+str(e)},ensure_ascii=False),flush=True)

threading.Thread(target=_gemini_e2e_once,daemon=True).start()
'''
src=src.replace(marker,inject+'\n'+marker,1)
print('ND_TLDRAW_GEMINI_E2E_WRAPPER_READY',flush=True)
exec(compile(src,'nd_tldraw_mcp_front_v1_2_gemini_e2e_runtime.py','exec'))
