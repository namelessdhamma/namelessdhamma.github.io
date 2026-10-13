# Porfirchik V20.7.25 — scoped short-term VK history repair.
# Pin both predecessors; do not change the provider, MemOS or callback topology.
import os
import urllib.request
_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'
_V22=_URL+'60c7c079248574529bf0805e06737caa11a58196/tmp/nd_vk_v20_7_22_private_free_openrouter_loader.py'
_HELPER=_URL+'958475f07337f48e8c8e63841b51fa07d87f5f7c/tmp/nd_vk_history_budget_v25.py'
base=urllib.request.urlopen(_V22,timeout=30).read().decode('utf-8')
helper=urllib.request.urlopen(_HELPER,timeout=30).read().decode('utf-8')
patch=helper+r'''
import json as _v25_json
def vk_recent_context(uid,current_text):
    try:
        r=vk('messages.getHistory',{'peer_id':int(uid),'count':30,'offset':0},20)
        items=(r.get('items') or []) if isinstance(r,dict) else []
        selected=select_recent_vk_messages(items,current_text)
        print('VK_HISTORY_RECOVERED',_v25_json.dumps({
            'uid':uid,'messages':len(selected),
            'chars':sum(len(m['content']) for m in selected),
            'truncated_messages':sum('…[сокращено]…' in m['content'] for m in selected),
            'policy':'fair-ten-message-v25'
        },ensure_ascii=False),flush=True)
        return selected
    except Exception as e:
        print('VK_HISTORY_RECOVERY_ERROR',cleanerr(e),flush=True)
        return []
'''
anchor="\ncompile(s,'v20722_wrapper.py','exec')\n"
if base.count(anchor)!=1:
    raise RuntimeError('v25 predecessor compile anchor mismatch')
insert=(
    "if s.count(_anchor)!=1:raise RuntimeError('v25 router patch anchor mismatch')\n"
    "s=s.replace(_anchor,'router_patch_code += '+repr("+repr(patch)+")+'\\n'+_anchor,1)\n"
)
base=base.replace(anchor,"\n"+insert+anchor,1)
compile(base,'v25_history_budget_wrapper.py','exec')
print('ND_V20_7_25_HISTORY_BUDGET_WRAPPER_READY',flush=True)
exec(compile(base,'v25_history_budget_wrapper.py','exec'),{'__name__':'__main__','os':os})
