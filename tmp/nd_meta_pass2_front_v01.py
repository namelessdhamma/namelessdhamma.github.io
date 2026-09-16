import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4536d08d2616e6e4671f4229f2dd949639c5df3e/tmp/nd_github_mcp_front_meta_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old='183b2e6a90f02bdfb6e75e13139a58e639d99b7e'
new='11b8f7ec0efdcee640742eee2c14c45fbac2d846'
if src.count(old)!=1:
    raise RuntimeError('pass2 front inner pin not found exactly once')
src=src.replace(old,new,1)
print('ND_META_PASS2_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_pass2_front_v01_runtime.py','exec'))
