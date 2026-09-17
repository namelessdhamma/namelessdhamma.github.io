import io
import urllib.request

BASE_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/531be60e38d4e0c7b3bbbf03f423f03699bab6ad/tmp/nd_meta_graph_full_front_v01.py'
TARGET_HELPER='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'

_orig_urlopen=urllib.request.urlopen
helper_src=_orig_urlopen(TARGET_HELPER,timeout=30).read().decode('utf-8')
old="_meta.PAGE_ID+'/promotable_posts'"
new="_meta.PAGE_ID+'/posts'"
if helper_src.count(old)!=1:
    raise RuntimeError('facebook posts v26 list anchor mismatch')
helper_src=helper_src.replace(old,new,1)
helper_bytes=helper_src.encode('utf-8')

def _patched_urlopen(req,*args,**kwargs):
    url=req.full_url if hasattr(req,'full_url') else str(req)
    if url==TARGET_HELPER:
        return io.BytesIO(helper_bytes)
    return _orig_urlopen(req,*args,**kwargs)

urllib.request.urlopen=_patched_urlopen
front_src=_orig_urlopen(BASE_FRONT,timeout=30).read().decode('utf-8')
print('ND_META_FB_LIST_V26_PATCH_READY',flush=True)
exec(compile(front_src,'nd_meta_fb_list_v26_front_v01.py','exec'))

