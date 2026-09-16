import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4536d08d2616e6e4671f4229f2dd949639c5df3e/tmp/nd_github_mcp_front_meta_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old="new=\"UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'\""
new="new=\"UPSTREAM='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ccff300a6700f70997309ec2bc1cfacdf9a8a656/tmp/nd_meta_fb_ig_ads_inner_wrapper_v01.py'\""
if src.count(old)!=1:
    raise RuntimeError('combined front upstream marker not found exactly once')
src=src.replace(old,new,1)
print('ND_META_FB_IG_ADS_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_fb_ig_ads_front_v01_runtime.py','exec'))
