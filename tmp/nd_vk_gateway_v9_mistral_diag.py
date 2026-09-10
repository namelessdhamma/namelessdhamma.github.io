import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/780b2c6b283f7f0ed9e5b598d5109215cdf58c48/tmp/nd_vk_gateway_v8_adaptive.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="""    except HTTPError as e:\n        try:body=e.read().decode('utf-8','replace')\n        except Exception:body=''\n        raise RuntimeError('HTTP %s: %s'%(e.code,cleanerr(body)))"""
new="""    except HTTPError as e:\n        try:body=e.read().decode('utf-8','replace')\n        except Exception:body=''\n        try:\n            rh={k:v for k,v in e.headers.items() if k.lower().startswith('x-ratelimit') or k.lower() in ('retry-after','x-request-id')}\n        except Exception:\n            rh={}\n        raise RuntimeError('HTTP %s: %s | rate_headers=%s'%(e.code,cleanerr(body),cleanerr(rh)))"""
if old not in src:
    raise RuntimeError('Expected HTTPError block not found')
src=src.replace(old,new,1)
src=src.replace('ND_VK_GATEWAY_V8_ADAPTIVE_START','ND_VK_GATEWAY_V9_MISTRAL_DIAG_START',1)
exec(compile(src,'nd_vk_gateway_v9_mistral_diag.py','exec'))
