import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/781315e321a69386c8fe4b48bd511d3e7d9acad6/tmp/nd_meta_inner_wrapper_v02_adsfix.py'
HELPER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/109d71428b455f28eed4a0e599368dd0003d4e1d/tmp/nd_meta_extended_helper_v01.py'

outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
final_outer_exec="exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))"
if outer.count(final_outer_exec)!=1:
    raise RuntimeError('extended v2 inner final exec marker not found exactly once')

stage="\n".join([
    "helper_ns={}",
    "helper_src=urllib.request.urlopen("+repr(HELPER)+",timeout=30).read().decode('utf-8')",
    "exec(compile(helper_src,'nd_meta_extended_helper_v01.py','exec'),helper_ns)",
    "src=helper_ns['patch_linear_wrapper_source'](src)",
    "print('ND_META_EXTENDED_STAGE_V2_READY',flush=True)",
    final_outer_exec,
])
outer=outer.replace(final_outer_exec,stage,1)
print('ND_META_EXTENDED_OUTER_V2_READY',flush=True)
exec(compile(outer,'nd_meta_extended_inner_wrapper_v02_outer.py','exec'))
