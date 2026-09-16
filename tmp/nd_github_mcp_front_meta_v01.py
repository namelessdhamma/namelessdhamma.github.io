import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/cbd3279fa9fa0eec25609a438883d9660077d681/tmp/nd_github_mcp_front_v1.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6c051774bffff04055a9479d7b95178f5fd9fb60/tmp/nd_gateway_linear_bridge_v2b_father_profile.py'"
new="UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/56238b495cbdbad9f3bbd576afa024ad8ec11f4f/tmp/nd_meta_inner_wrapper_v01.py'"
if src.count(old)!=1:
    raise RuntimeError('current GitHub MCP front upstream marker not found exactly once')
src=src.replace(old,new,1)
print('ND_GITHUB_MCP_FRONT_META_V01_READY',flush=True)
exec(compile(src,'nd_github_mcp_front_meta_v01_runtime.py','exec'))
