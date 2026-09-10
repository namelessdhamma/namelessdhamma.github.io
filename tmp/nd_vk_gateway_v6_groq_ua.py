import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f1bcf5d7ca5462a8e0eb7e91debdb57c8f6be316/tmp/nd_vk_gateway_v5_groq.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="headers={'Content-Type':'application/json','Authorization':'Bearer '+GROQ_API_KEY}"
new="headers={'Content-Type':'application/json','Authorization':'Bearer '+GROQ_API_KEY,'User-Agent':'groq-python/1.0','Accept':'application/json'}"
if old not in src:
    raise RuntimeError('Expected Groq request header pattern not found')
src=src.replace(old,new,1)
src=src.replace('ND_VK_GATEWAY_V5_GROQ_START','ND_VK_GATEWAY_V6_GROQ_UA_START',1)
exec(compile(src,'nd_vk_gateway_v6_groq_ua.py','exec'))
