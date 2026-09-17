import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'
HELPER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'

outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
final_outer_exec="exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))"
if outer.count(final_outer_exec)!=1:
    raise RuntimeError('fb inner final exec marker not found exactly once')

stage="\n".join([
    "helper_ns={}",
    "helper_src=urllib.request.urlopen("+repr(HELPER)+",timeout=30).read().decode('utf-8')",
    "exec(compile(helper_src,'nd_meta_fb_crud_helper_v01.py','exec'),helper_ns)",
    "src=helper_ns['patch_linear_wrapper_source'](src)",
    "print('ND_META_FB_CRUD_STAGE_READY',flush=True)",
    final_outer_exec,
])
outer=outer.replace(final_outer_exec,stage,1)
print('ND_META_FB_CRUD_OUTER_READY',flush=True)
exec(compile(outer,'nd_meta_fb_crud_inner_wrapper_v01_outer.py','exec'))
