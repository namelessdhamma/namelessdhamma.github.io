import io, os, subprocess, time, urllib.request, json

# V46 qualification candidate.
# Preserve qualified V42 composition and replace only OpenRouter answer routing.
# Invariants:
# - answer models must be explicitly ND-strong-qualified;
# - OpenRouter model must be verified CURRENTLY free from the live catalog;
# - arbitrary OPENROUTER_MODEL env values are never answer-authority;
# - catalog failure is fail-closed (OpenRouter skipped, outer Groq route may still serve);
# - per-model cooldown limits repeated 429/5xx/provider failures;
# - every attempt records requested/used model telemetry.
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
# V46 keeps a deliberately small explicit quality authority. Discovery never
# grants answer-authority. Additions require a separate ND Russian/father-suite
# qualification before entering this set.
_V46_STRONG_QUALIFIED = (
    'nvidia/nemotron-3-ultra-550b-a55b:free',
)
_V46_CATALOG_TTL = 900
_V46_COOLDOWN_SECONDS = 180
_v46_catalog_cache = {'at': 0.0, 'free_ids': set()}
_v46_cooldown_until = {}

def _v46_zero_price(v):
    try:
        return float(v) == 0.0
    except Exception:
        return str(v).strip() in ('0', '0.0', '0.00')

def _v46_live_free_ids():
    now=time.time()
    if _v46_catalog_cache['free_ids'] and now-_v46_catalog_cache['at'] < _V46_CATALOG_TTL:
        return set(_v46_catalog_cache['free_ids'])
    req=Request(
        'https://openrouter.ai/api/v1/models',
        headers={'User-Agent':'NamelessDhamma-VK/46','HTTP-Referer':'https://namelessdhamma.org','X-Title':'Nameless Dhamma VK Gateway'}
    )
    with urlopen(req,timeout=20) as r:
        obj=json.loads(r.read().decode('utf-8'))
    free_ids=set()
    for item in (obj.get('data') or []):
        mid=str(item.get('id') or '')
        pricing=item.get('pricing') or {}
        if mid.endswith(':free') and _v46_zero_price(pricing.get('prompt')) and _v46_zero_price(pricing.get('completion')):
            free_ids.add(mid)
    _v46_catalog_cache['at']=now
    _v46_catalog_cache['free_ids']=set(free_ids)
    print('OPENROUTER_FREE_CATALOG',json.dumps({'ok':True,'free_count':len(free_ids)},ensure_ascii=False),flush=True)
    return free_ids

def openrouter_chat(messages,effort='high',max_tokens=4200,temperature=0.45):
    if not OPENROUTER_API_KEY:raise RuntimeError('OPENROUTER_API_KEY missing')
    try:
        live_free=_v46_live_free_ids()
    except Exception as e:
        err=cleanerr(e)
        print('OPENROUTER_FREE_CATALOG',json.dumps({'ok':False,'error':err[:500]},ensure_ascii=False),flush=True)
        raise RuntimeError('OpenRouter free eligibility unavailable; fail-closed: '+err[:300])
    now=time.time()
    candidates=[m for m in _V46_STRONG_QUALIFIED if m in live_free and now >= _v46_cooldown_until.get(m,0)]
    if not candidates:
        raise RuntimeError('no currently-free ND-strong-qualified OpenRouter route available')
    extra={'HTTP-Referer':'https://namelessdhamma.org','X-Title':'Nameless Dhamma VK Gateway'}
    errors=[]
    for model in candidates:
        payload={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,
                 'reasoning':{'effort':effort,'exclude':True}}
        try:
            try:
                j=http_json('https://openrouter.ai/api/v1/chat/completions',payload,OPENROUTER_API_KEY,180,extra)
            except Exception as first:
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
            print('OPENROUTER_STRONG_ATTEMPT',json.dumps({'requested_model':model,'ok':True,'used_model':used_model,'free_verified':True,'strong_qualified':True},ensure_ascii=False),flush=True)
            print('OPENROUTER_MODEL_USED',json.dumps({'model':used_model},ensure_ascii=False),flush=True)
            return out
        except Exception as e:
            err=cleanerr(e)
            errors.append(model+': '+err[:260])
            low=err.lower()
            if ('429' in err) or ('500' in err) or ('502' in err) or ('503' in err) or ('504' in err) or ('timeout' in low) or ('provider' in low and 'unavailable' in low):
                _v46_cooldown_until[model]=time.time()+_V46_COOLDOWN_SECONDS
            print('OPENROUTER_STRONG_ATTEMPT',json.dumps({'requested_model':model,'ok':False,'error':err[:500],'free_verified':True,'strong_qualified':True,'cooldown_until':_v46_cooldown_until.get(model,0)},ensure_ascii=False),flush=True)
            continue
    raise RuntimeError('all currently-free ND-strong-qualified OpenRouter routes unavailable: '+' | '.join(errors))
'''

_injection = """
# V46 fail-closed currently-free + strong-qualified OpenRouter routing.
_v46_start=src.find('def openrouter_chat(')
_v46_end=src.find('\\ndef heuristic_route',_v46_start)
if _v46_start < 0 or _v46_end < 0:
    raise RuntimeError('V46 openrouter structural boundary not found')
src=src[:_v46_start]+__V46_FUNCTION__+src[_v46_end:]
print('ND_V46_FAIL_CLOSED_STRONG_FREE_PATCHED',flush=True)
""".replace('__V46_FUNCTION__', repr(_explicit_openrouter))

_exec_marker = "exec(compile(src,'nd_vk_gateway_v12_research_integrity.py','exec'))"

def _patched_urlopen(req, *args, **kwargs):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    if url == V12:
        with _orig_urlopen(req, *args, **kwargs) as r:
            raw = r.read().decode('utf-8')
        if _exec_marker not in raw:
            raise RuntimeError('V46 V12 execution marker not found')
        raw = raw.replace(_exec_marker, _injection + "\n" + _exec_marker, 1)
        return io.BytesIO(raw.encode('utf-8'))
    return _orig_urlopen(req, *args, **kwargs)

urllib.request.urlopen = _patched_urlopen
try:
    src = _orig_urlopen(V42, timeout=30).read().decode('utf-8')
    print('ND_V46_FAIL_CLOSED_STRONG_FREE_LAUNCHER_READY', flush=True)
    exec(compile(src, 'nd_vk_gateway_v42_with_v46_fail_closed_strong_free.py', 'exec'))
finally:
    urllib.request.urlopen = _orig_urlopen
