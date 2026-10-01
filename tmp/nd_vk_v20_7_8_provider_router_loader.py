import urllib.request

# Backward-compatible router repair. Preserve pinned V20.7.7 music/Yandex.
BASE_COMMIT='e6a27bed628609fb2d2a8f873f04bd66cc9ec9cd'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_7_music_yandex_signed_link_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')
old="exec(compile(outer,'nd_vk_v20_7_7_music_yandex_signed_link_loader.py','exec'))"
if base.count(old)!=1:
    raise RuntimeError('v20_7_8_capture_anchor_mismatch')
G={'__name__':'__main__'}
exec(compile(base.replace(old,'globals()["_ND_V2077_LOADER"]=outer',1),'v20_7_8_capture.py','exec'),G,G)
outer=G.get('_ND_V2077_LOADER','')
if not outer:
    raise RuntimeError('v20_7_8_base_capture_failed')
router_patch_code="# V20.7.8: repair already-connected Groq/OpenRouter routing without enabling paid providers.\n_original_porfirchik_retry_seconds=_retry_seconds\ndef _retry_seconds(err):\n    s=str(err).lower()\n    if 'tokens per minute' in s or 'tpm' in s or ('429' in s and 'retry' in s):\n        m=re.search(r'(?:please\\s+)?try\\s+again\\s+in\\s+([0-9]+(?:\\.[0-9]+)?)\\s*(ms|milliseconds|s|sec|seconds?)',s)\n        if m:\n            n=float(m.group(1))\n            seconds=n/1000.0 if m.group(2).startswith('m') else n\n            return max(1,min(30,int(seconds+1.5)))\n        if 'tokens per minute' in s or 'tpm' in s:\n            return 5\n    return _original_porfirchik_retry_seconds(err)\n\n_original_porfirchik_groq_direct_chat=groq_direct_chat\ndef groq_direct_chat(messages,model,max_tokens=3000,temperature=0.3):\n    # Groq on-demand 120b currently allows 8000 TPM. Avoid reserving 5200+\n    # completion tokens before accounting for the prompt and recent history.\n    budget=min(int(max_tokens),2100)\n    msgs=list(messages or [])\n    estimated_input=sum(max(0,len(str(m.get('content') or ''))//4) for m in msgs)\n    if estimated_input>5300 and len(msgs)>4:\n        msgs=msgs[:1]+msgs[-3:]\n        state['groq_history_compacted']=True\n        print('GROQ_CONTEXT_COMPACTED',json.dumps({'before':len(messages),'after':len(msgs)},ensure_ascii=False),flush=True)\n    return _original_porfirchik_groq_direct_chat(msgs,model,budget,temperature)\n\n_original_porfirchik_adaptive_candidates=_adaptive_candidates\ndef _adaptive_candidates(route):\n    candidates=_original_porfirchik_adaptive_candidates(route)\n    # Prefer independent live routes: Groq first, then only explicit free\n    # OpenRouter models, keeping the inherited emergency path intact.\n    groq=[c for c in candidates if c[0]=='groq']\n    free_or=[c for c in candidates if c[0]=='openrouter' and\n             (str(c[1]).endswith(':free') or str(c[1])=='openrouter/free')]\n    if _configured('openrouter') and OPENROUTER_MODEL and (\n        OPENROUTER_MODEL.endswith(':free') or OPENROUTER_MODEL=='openrouter/free'):\n        free_or.insert(0,('openrouter',OPENROUTER_MODEL))\n    others=[c for c in candidates if c[0] not in ('groq','openrouter')]\n    out=[];seen=set()\n    for c in groq+free_or+others:\n        if c not in seen:\n            out.append(c);seen.add(c)\n    return out\n\nstate['provider_router_patch']='v20.7.8-free-429-cap-and-failover'\nstate['groq_completion_cap']=2100\nstate['groq_history_compacted']=False\nprint('ND_V20_7_8_PROVIDER_ROUTER_READY',flush=True)\n"
hook="""\nrouter_patch_marker="threading.Thread(target=startup,daemon=True).start()\\n"
if src.count(router_patch_marker)!=1:
    raise RuntimeError('v20_7_8_runtime_start_anchor_mismatch')
src=src.replace(router_patch_marker,router_patch_code+'\\n'+router_patch_marker,1)
if 'ND_V20_7_8_PROVIDER_ROUTER_READY' not in src:
    raise RuntimeError('v20_7_8_patch_missing')
"""
hook='router_patch_code='+repr(router_patch_code)+'\n'+hook
compile_anchor="\ncompile(src,'nd_vk_gateway_v20_7_music_free_runtime.py','exec')\n"
if outer.count(compile_anchor)!=1:
    raise RuntimeError('v20_7_8_compile_anchor_mismatch')
outer=outer.replace(compile_anchor,'\n'+hook+compile_anchor,1)
compile(outer,'v20_7_8_outer_loader.py','exec')
print('ND_V20_7_8_ROUTER_WRAPPER_READY',flush=True)
exec(compile(outer,'v20_7_8_outer_loader.py','exec'),{'__name__':'__main__'})
