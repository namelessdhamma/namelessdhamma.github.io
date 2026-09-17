import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/12b41bdcc52b58781d3dd046842fbdf741ff89fb/tmp/nd_meta_fb_crud_front_v01.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
old='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/5a32a9595d73f83e1def836e2352d9ba93797d53/tmp/nd_meta_fb_crud_inner_wrapper_v01.py'
new='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c146bb8dc8d3d42fcd0ea843155d32aeb5c31262/tmp/nd_meta_igads_inner_wrapper_v01.py'
if src.count(old)!=1:
    raise RuntimeError('igads front inner-wrapper anchor mismatch')
src=src.replace(old,new,1)
print('ND_META_IGADS_V26_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_fb_crud_front_v01_runtime.py','exec'))
