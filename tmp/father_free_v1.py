import os, urllib.request
os.environ['GROQ_MODEL']='openai/gpt-oss-120b'
os.environ['GROQ_RESEARCH_MODEL']='groq/compound'
os.environ['OPENROUTER_MODEL']='openrouter/free'
os.environ['ND_READONLY_ENABLED']='0'
url='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/8100fde7de32c3e6d873c55d0894c484e2639120/tmp/nd_vk_gateway_v12_research_integrity.py'
src=urllib.request.urlopen(url,timeout=30).read().decode('utf-8')
print('FATHER_FREE_V1_READY',flush=True)
exec(compile(src,'father_free_v1.py','exec'))
