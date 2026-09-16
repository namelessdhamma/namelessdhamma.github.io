import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4536d08d2616e6e4671f4229f2dd949639c5df3e/tmp/nd_github_mcp_front_meta_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="new=\"UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'\""
new="new=\"UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/11b8f7ec0efdcee640742eee2c14c45fbac2d846/tmp/nd_meta_pass2_inner_wrapper_v01.py'\""
if src.count(old)!=1:
    raise RuntimeError('corrected pass2 front upstream marker not found exactly once')
src=src.replace(old,new,1)
print('ND_META_PASS2_FRONT_V2_READY',flush=True)
exec(compile(src,'nd_meta_pass2_front_v02_runtime.py','exec'))
