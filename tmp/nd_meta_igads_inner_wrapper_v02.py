import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c146bb8dc8d3d42fcd0ea843155d32aeb5c31262/tmp/nd_meta_igads_inner_wrapper_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'
new='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f02a5ae4a18add69ed8c88ba5460aaadbeed7840/tmp/nd_meta_igads_ops_helper_v01.py'
if src.count(old)!=1:
    raise RuntimeError('igads ops helper anchor mismatch')
src=src.replace(old,new,1)
print('ND_META_IGADS_OPS_OUTER_READY',flush=True)
exec(compile(src,'nd_meta_igads_inner_wrapper_v02.py','exec'))
