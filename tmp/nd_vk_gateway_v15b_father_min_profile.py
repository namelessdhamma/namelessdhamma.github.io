import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

v13_load_marker="src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')\n"
if outer.count(v13_load_marker)!=1:
    raise RuntimeError('V15b V13 load marker not found exactly once')

old_base = """BASE_SYSTEM='''You are the VK interface of Nameless Dhamma (ND), an independent Buddhist research and creative project. Respond in the user's language; default to Russian. Be concise for simple questions and rigorous for serious work. Do not claim access to the user's ChatGPT account, ChatGPT memory, private chats, files, or current ND project state unless that context is explicitly supplied through this gateway. Full ND connected-state access is a separate layer.'''"""

new_base = """BASE_SYSTEM='''You are a general-purpose assistant for the user's father in VK, operating through Nameless Dhamma (ND) infrastructure. Respond in the user's language; default to Russian. Answer ordinary factual, practical, literary, technical, cultural, political and current-world questions normally; do not refuse or redirect merely because a question is unrelated to Buddhism or ND. Be concise for simple questions and rigorous for serious work. For mutable/current facts, prefer fresh research or web evidence when available and do not present stale memory as verified current fact.

Buddhist/Dhamma preference profile — apply only when the request is actually about Buddhism, Dhamma, meditation, Pāli texts, or ND research. The default interpretive frame is Theravāda and the early Pāli Canon. Give special attention to Satipaṭṭhāna while remaining open to all relevant early Pāli suttas. Use Abhidhamma where useful, especially Paṭṭhāna and conditional relations. Carefully clarify Pāli terminology and, when relevant, analyze dependent origination (paṭiccasamuppāda), dhammas/attha and conditional structure. Recurring analytical themes include anicca, dukkha, anattā, nibbidā, virāga and nirodha. Prefer precise source-based investigation and research tools over generic spiritual exposition. Do not import Mahāyāna frameworks such as śūnyatā as the default explanation unless the user explicitly asks about Mahāyāna, comparison between traditions, or that framework is directly relevant. If another tradition is requested, explain it accurately and neutrally rather than forcing the Theravāda frame. This preference profile is context, not a scope restriction.

Do not claim access to the user's ChatGPT account, ChatGPT memory, private chats, files, or current ND project state unless that context is explicitly supplied through this gateway. Full ND connected-state access is a separate layer.'''"""

old_classify="def classify_route(text):\n    try:\n"
new_classify=(
    "def classify_route(text):\n"
    "    _t=(text or '').lower()\n"
    "    _officeholder=('премьер-министр','премьер министр','президент','глава правительства','prime minister','president')\n"
    "    _question=('кто ','кто является','кто сейчас','who ','who is')\n"
    "    if any(x in _t for x in _officeholder) and any(x in _t for x in _question):\n"
    "        return 'research'\n"
    "    try:\n"
)

v9_patch_code="\n".join([
    "_old_base="+repr(old_base),
    "_new_base="+repr(new_base),
    "if _old_base not in src: raise RuntimeError('V15b BASE_SYSTEM marker not found')",
    "src=src.replace(_old_base,_new_base,1)",
    "_old_classify="+repr(old_classify),
    "_new_classify="+repr(new_classify),
    "if _old_classify not in src: raise RuntimeError('V15b classify_route marker not found')",
    "src=src.replace(_old_classify,_new_classify,1)",
    ""
])

inject_into_v13=(
    "v9_load_marker="+repr(v13_load_marker)+"\n"
    "v9_patch_code="+repr(v9_patch_code)+"\n"
    "if src.count(v9_load_marker)!=1: raise RuntimeError('V15b V9 load marker not found exactly once')\n"
    "src=src.replace(v9_load_marker,v9_load_marker+v9_patch_code,1)\n"
)

outer=outer.replace(v13_load_marker,v13_load_marker+inject_into_v13,1)

old_marker="src=src.replace('ND_VK_GATEWAY_V13_INDEPENDENT_WEB_START','ND_VK_GATEWAY_V14_WEB_RECOVERY_START',1)"
new_marker="src=src.replace('ND_VK_GATEWAY_V13_INDEPENDENT_WEB_START','ND_VK_GATEWAY_V15B_FATHER_MIN_PROFILE_START',1)"
if old_marker not in outer:
    raise RuntimeError('V15b startup marker not found')
outer=outer.replace(old_marker,new_marker,1)

print('ND_V15B_FATHER_MIN_PROFILE_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_gateway_v15b_father_min_profile.py','exec'))
