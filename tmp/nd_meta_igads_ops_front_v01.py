import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d319b0f9742d3118b1dd3b1b230a32ba9c662424/tmp/nd_meta_igads_v26_front_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c146bb8dc8d3d42fcd0ea843155d32aeb5c31262/tmp/nd_meta_igads_inner_wrapper_v01.py'
new='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/e1f714ce542dc0c8cb7010b817903e489026f954/tmp/nd_meta_igads_inner_wrapper_v02.py'
if src.count(old)!=1:
    raise RuntimeError('igads ops front inner-wrapper anchor mismatch')
src=src.replace(old,new,1)
print('ND_META_IGADS_OPS_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_igads_ops_front_v01.py','exec'))
