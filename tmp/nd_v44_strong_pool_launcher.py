import io, os, subprocess, time, urllib.request

# V44: preserve the already-qualified V42 composition, but intercept only the
# historical V12 source fetch and replace its final OpenRouter function after
# V12 has applied all of its own transformations. This avoids another fragile
# nested string patch against the V42/V36 wrappers.
FRONT = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js"
V42 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"
V12 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/8100fde7de32c3e6d873c55d0894c484e2639120/tmp/nd_vk_gateway_v12_research_integrity.py"

subprocess.run(["apk", "add", "--no-cache", "nodejs"], check=True, stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(FRONT, "/tmp/nd-drive-front.mjs")
front_env = dict(os.environ)
front_env["PORT"] = os.environ.get("PORT", "3000")
front = subprocess.Popen(["node", "/tmp/nd-drive-front.mjs"], env=front_env)
time.sleep(4)
if front.poll() is not None:
    raise RuntimeError("ND Drive front exited during startup")

os.environ["PORT"] = "3001"
_orig_urlopen = urllib.request.urlopen

_explicit_openrouter = r'''
def openrouter_chat(messages,effort='high',max_tokens=4200,temperature=0.45):
    if not OPENROUTER_API_KEY:raise RuntimeError('OPENROUTER_API_KEY missing')
    candidates=[]
    for m in (OPENROUTER_MODEL,'nvidia/nemotron-3-ultra-550b-a55b:free','z-ai/glm-5.2:free','minimax/minimax-m3:free'):
        if m and m not in candidates:candidates.append(m)
    extra={'HTTP-Referer':'https://namelessdhamma.org','X-Title':'Nameless Dhamma VK Gateway'}
    errors=[]
    for model in candidates:
        payload={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,
                 'reasoning':{'effort':effort,'exclude':True}}
        try:
            try:
                j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
            except Exception as first:
                # A model/provider may reject optional reasoning controls. Retry that
                # exact strong model once without them; all other failures advance to
                # the next strong candidate.
                if 'HTTP 400' not in str(first):raise
                payload.pop('reasoning',None)
                j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
            ch=j.get('choices') or []
            if not ch:raise RuntimeError('OpenRouter returned no choices: '+cleanerr(j))
            msg=ch[0].get('message') or {}
            out=(msg.get('content') or '').strip()
            if not out:raise RuntimeError('OpenRouter returned empty content')
            used_model=str(j.get('model') or model)
            state['last_openrouter_model']=used_model
            print('OPENROUTER_STRONG_ATTEMPT',json.dumps({'requested_model':model,'ok':True,'used_model':used_model},ensure_ascii=False),flush=True)
            print('OPENROUTER_MODEL_USED',json.dumps({'model':used_model},ensure_ascii=False),flush=True)
            return out
        except Exception as e:
            err=cleanerr(e)
            errors.append(model+': '+err[:260])
            print('OPENROUTER_STRONG_ATTEMPT',json.dumps({'requested_model':model,'ok':False,'error':err[:500]},ensure_ascii=False),flush=True)
            continue
    raise RuntimeError('all qualified OpenRouter strong-free routes unavailable: '+' | '.join(errors))
'''

_injection = """
# V44 explicit strong-free OpenRouter pool: apply only after V12 has finished
# constructing the V9-derived runtime, then replace the whole function by
# structural boundaries rather than patching an outer wrapper.
_v44_start=src.find('def openrouter_chat(')
_v44_end=src.find('\\ndef heuristic_route',_v44_start)
if _v44_start < 0 or _v44_end < 0:
    raise RuntimeError('V44 openrouter structural boundary not found')
src=src[:_v44_start]+__V44_FUNCTION__+src[_v44_end:]
print('ND_V44_STRONG_POOL_PATCHED',flush=True)
""".replace('__V44_FUNCTION__', repr(_explicit_openrouter))

_exec_marker = "exec(compile(src,'nd_vk_gateway_v12_research_integrity.py','exec'))"

def _patched_urlopen(req, *args, **kwargs):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    if url == V12:
        with _orig_urlopen(req, *args, **kwargs) as r:
            raw = r.read().decode('utf-8')
        if _exec_marker not in raw:
            raise RuntimeError('V44 V12 execution marker not found')
        raw = raw.replace(_exec_marker, _injection + "\n" + _exec_marker, 1)
        return io.BytesIO(raw.encode('utf-8'))
    return _orig_urlopen(req, *args, **kwargs)

urllib.request.urlopen = _patched_urlopen
try:
    src = _orig_urlopen(V42, timeout=30).read().decode('utf-8')
    print('ND_V44_STRONG_POOL_LAUNCHER_READY', flush=True)
    exec(compile(src, 'nd_vk_gateway_v42_with_v44_strong_pool.py', 'exec'))
finally:
    urllib.request.urlopen = _orig_urlopen
