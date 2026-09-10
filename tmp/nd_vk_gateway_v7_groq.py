import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f1bcf5d7ca5462a8e0eb7e91debdb57c8f6be316/tmp/nd_vk_gateway_v5_groq.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="headers={'Content-Type':'application/json','Authorization':'Bearer '+GROQ_API_KEY}"
new="headers={'Content-Type':'application/json','Authorization':'Bearer '+GROQ_API_KEY,'User-Agent':'groq-python/1.0','Accept':'application/json'}"
if old not in src: raise RuntimeError('Expected Groq header pattern not found')
src=src.replace(old,new,1)
old_payload="payload={'model':GROQ_MODEL,'messages':messages,'reasoning_effort':reasoning,'max_completion_tokens':max_tokens}"
new_payload="payload={'model':GROQ_MODEL,'messages':messages,'reasoning_effort':reasoning,'max_completion_tokens':max_tokens,'include_reasoning':False}"
if old_payload not in src: raise RuntimeError('Expected Groq payload pattern not found')
src=src.replace(old_payload,new_payload,1)
src=src.replace("groq_chat([{'role':'user','content':'Reply only with OK.'}],'low',16)","groq_chat([{'role':'user','content':'Reply only with OK.'}],'low',256)",1)
src=src.replace('ND_VK_GATEWAY_V5_GROQ_START','ND_VK_GATEWAY_V7_GROQ_START',1)
exec(compile(src,'nd_vk_gateway_v7_groq.py','exec'))
