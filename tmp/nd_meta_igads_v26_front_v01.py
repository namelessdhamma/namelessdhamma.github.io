import urllib.request

CANONICAL_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/12b41bdcc52b58781d3dd046842fbdf741ff89fb/tmp/nd_meta_fb_crud_front_v01.py'
OLD_INNER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/5a32a9595d73f83e1def836e2352d9ba93797d53/tmp/nd_meta_fb_crud_inner_wrapper_v01.py'
NEW_INNER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1c61acb0987311da9b4665d6f55a7e0bd5d650e9/tmp/nd_meta_igads_v26_inner_wrapper_v01.py'

src=urllib.request.urlopen(CANONICAL_FRONT,timeout=30).read().decode('utf-8')
if src.count(OLD_INNER)!=1:
    raise RuntimeError('Meta Facebook inner wrapper anchor mismatch')
src=src.replace(OLD_INNER,NEW_INNER,1)
print('ND_META_IGADS_V26_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_fb_crud_front_v01.py','exec'))
