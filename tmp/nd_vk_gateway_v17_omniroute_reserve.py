import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ec530d17216b5a4e11f83e1aa06aee351e2fb269/tmp/nd_vk_gateway_v16e_resilience_memory.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

marker='inject="v16_patch_code="+repr(v16_patch_code)'
if outer.count(marker)!=1:
    raise RuntimeError('V17 V16 injection marker mismatch count=%d' % outer.count(marker))

v17_patch_code=r"""
# V17: OmniRoute private-network reserve route. Auxiliary fallback only.
_env_marker="ZAI_MODEL=os.environ.get('ZAI_MODEL','glm-4.6').strip() or 'glm-4.6'\n"
_env_new=_env_marker+"OMNIROUTE_BASE_URL=os.environ.get('OMNIROUTE_BASE_URL','').strip().rstrip('/')\nOMNIROUTE_MODEL=os.environ.get('OMNIROUTE_MODEL','glm/glm-4.7-flash').strip() or 'glm/glm-4.7-flash'\n"
if _env_marker not in src:
    raise RuntimeError('V17 OmniRoute env marker missing')
src=src.replace(_env_marker,_env_new,1)

_omni_func=r'''def omniroute_chat(messages,max_tokens=3000,temperature=0.35):
    if not OMNIROUTE_BASE_URL:
        raise RuntimeError('OMNIROUTE_BASE_URL missing')
    if _provider_blocked('omniroute'):
        raise RuntimeError('OmniRoute circuit open')
    payload={'model':OMNIROUTE_MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':temperature}
    try:
        j=http_json(OMNIROUTE_BASE_URL+'/chat/completions',payload,'',180)
        _provider_success('omniroute')
    except Exception as e:
        _provider_fail('omniroute',e)
        raise
    ch=j.get('choices') or []
    if not ch:
        raise RuntimeError('OmniRoute returned no choices')
    out=((ch[0].get('message') or {}).get('content') or '').strip()
    if not out:
        raise RuntimeError('OmniRoute returned empty content')
    state['last_reserve_provider']='omniroute:'+OMNIROUTE_MODEL
    print('AI_RESERVE_PROVIDER',json.dumps({'provider':'omniroute','model':OMNIROUTE_MODEL},ensure_ascii=False),flush=True)
    return out

'''
_reserve_marker="def reserve_chat(messages,max_tokens=3000,temperature=0.35):\n    errs=[]\n"
_reserve_new="def reserve_chat(messages,max_tokens=3000,temperature=0.35):\n    errs=[]\n    if OMNIROUTE_BASE_URL:\n        try: return omniroute_chat(messages,max_tokens=max_tokens,temperature=temperature)\n        except Exception as e:\n            errs.append('omniroute:'+cleanerr(e))\n            print('OMNIROUTE_RESERVE_ERROR',cleanerr(e),flush=True)\n"
if _reserve_marker not in src:
    raise RuntimeError('V17 reserve marker missing')
src=src.replace(_reserve_marker,_omni_func+_reserve_new,1)

_probe_tail="            else:\n                state['zai_probe']='not_configured'\n            return\n"
_probe_new='''            else:
                state['zai_probe']='not_configured'
            if OMNIROUTE_BASE_URL:
                try:
                    out=omniroute_chat([{'role':'user','content':'Reply exactly OK.'}],64,0.0)
                    state['omniroute_probe']='ok' if out else 'empty'
                    print('OMNIROUTE_PROBE_OK',flush=True)
                except Exception as e:
                    state['omniroute_probe']='error'
                    print('OMNIROUTE_PROBE_ERROR',cleanerr(e),flush=True)
            else:
                state['omniroute_probe']='not_configured'
            return
'''
if _probe_tail not in src:
    raise RuntimeError('V17 startup probe marker missing')
src=src.replace(_probe_tail,_probe_new,1)
"""
inject="v17_patch_code="+repr(v17_patch_code)+"\nv16_patch_code += '\\n'+v17_patch_code\n"
outer=outer.replace(marker,inject+marker,1)

print('ND_V17_OMNIROUTE_RESERVE_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_gateway_v17_omniroute_reserve.py','exec'))
