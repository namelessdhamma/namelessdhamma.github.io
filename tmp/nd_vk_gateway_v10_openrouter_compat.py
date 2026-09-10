import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c617c9b200cb1637fca544985d35ab2a1b8d9e08/tmp/nd_vk_gateway_v9_free_router.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','')"
new="OPENROUTER_API_KEY=os.environ.get('OPENROUTER_API_KEY','') or os.environ.get('OpenRouter','')"
if old not in src:
    raise RuntimeError('Expected OpenRouter env pattern not found')
src=src.replace(old,new,1)
src=src.replace('ND_VK_GATEWAY_V9_FREE_ROUTER_START','ND_VK_GATEWAY_V10_OPENROUTER_COMPAT_START',1)
exec(compile(src,'nd_vk_gateway_v10_openrouter_compat.py','exec'))
