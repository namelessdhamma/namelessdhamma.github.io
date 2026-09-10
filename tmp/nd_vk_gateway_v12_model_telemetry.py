import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c617c9b200cb1637fca544985d35ab2a1b8d9e08/tmp/nd_vk_gateway_v9_free_router.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

repls=[
("OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','')","OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','') or os.environ.get('OpenRouter','')"),
("OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')","OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','nvidia/nemotron-3-ultra-550b-a55b:free')\nOPENROUTER_MODELS=[OPENROUTER_MODEL,'z-ai/glm-5.2:free','minimax/minimax-m2.7:free']"),
("payload={'model':OPENROUTER_MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,","payload={'models':OPENROUTER_MODELS,'messages':messages,'max_tokens':max_tokens,'temperature':temperature,"),
("if not ch:raise RuntimeError('OpenRouter returned no choices')","print('OPENROUTER_MODEL_USED',json.dumps({'model':j.get('model'),'provider':j.get('provider')},ensure_ascii=False),flush=True)\n    if not ch:raise RuntimeError('OpenRouter returned no choices: '+cleanerr(j))"),
("ND_VK_GATEWAY_V9_FREE_ROUTER_START","ND_VK_GATEWAY_V12_MODEL_TELEMETRY_START")
]
for old,new in repls:
    if old not in src:
        raise RuntimeError('Expected V9 pattern not found: '+old[:100])
    src=src.replace(old,new,1)
exec(compile(src,'nd_vk_gateway_v12_model_telemetry.py','exec'))
