import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/183b2e6a90f02bdfb6e75e13139a58e639d99b7e/tmp/nd_meta_inner_wrapper_v01.py'
HELPER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'
RUNTIME='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/812763b5f55ccfcfe1d33276ff1e3c1b89b19e61/tmp/nd_meta_provider_runtime_v01.py'
LOCAL_RUNTIME='file:///tmp/nd_meta_provider_runtime_v26.py'

runtime=urllib.request.urlopen(RUNTIME,timeout=30).read().decode('utf-8')
old="'special_ad_categories':json.dumps([])})"
new="'special_ad_categories':json.dumps([]),'is_adset_budget_sharing_enabled':'false'})"
if runtime.count(old)!=1:
    raise RuntimeError('Meta Graph v26 campaign patch anchor mismatch')
runtime=runtime.replace(old,new,1)
with open('/tmp/nd_meta_provider_runtime_v26.py','w',encoding='utf-8') as f:
    f.write(runtime)
print('ND_META_IGADS_V26_RUNTIME_FILE_READY',flush=True)

outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
if RUNTIME not in outer:
    raise RuntimeError('Meta runtime URL not found in base inner wrapper')
outer=outer.replace(RUNTIME,LOCAL_RUNTIME)

final_outer_exec="exec(compile(src,'nd_meta_inner_wrapper_v01_outer.py','exec'))"
if outer.count(final_outer_exec)!=1:
    raise RuntimeError('IGADS inner final exec marker not found exactly once')

stage="\n".join([
    "helper_ns={}",
    "helper_src=urllib.request.urlopen("+repr(HELPER)+",timeout=30).read().decode('utf-8')",
    "exec(compile(helper_src,'nd_meta_fb_crud_helper_v01.py','exec'),helper_ns)",
    "src=helper_ns['patch_linear_wrapper_source'](src)",
    "print('ND_META_FB_CRUD_STAGE_READY',flush=True)",
    final_outer_exec,
])
outer=outer.replace(final_outer_exec,stage,1)
print('ND_META_IGADS_V26_INNER_READY',flush=True)
exec(compile(outer,'nd_meta_igads_v26_inner_wrapper_v01_outer.py','exec'))
