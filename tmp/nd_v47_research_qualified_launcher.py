import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a9872a6ba0fba807ef6b7e4139e95de14a88c6a/tmp/nd_v46_fail_closed_strong_free_launcher.py'
s=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js'
new='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ae76cf20fcc6fbd503228e77fd23fca160e9d6b9/tmp/nd_safe_tool_broker_v12_front_research_probe.js'
if old not in s:raise RuntimeError('V47 front marker missing')
s=s.replace(old,new,1)
s=s.replace('ND_V46_FAIL_CLOSED_STRONG_FREE_LAUNCHER_READY','ND_V47_RESEARCH_QUALIFIED_LAUNCHER_READY',1)
print('ND_V47_WRAPPER_READY',flush=True)
exec(compile(s,'nd_v47_research_qualified_inner.py','exec'))
