import base64
import urllib.request

BASE_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/531be60e38d4e0c7b3bbbf03f423f03699bab6ad/tmp/nd_meta_graph_full_front_v01.py'
INNER_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/265208ec1eb0b32e4bfd2f49f6c44b542e279bab/tmp/nd_meta_graph_full_inner_v01.py'
HELPER_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f0753632bf1286406c7684b99596a87507632e21/tmp/nd_meta_graph_full_helper_v01.py'
BASE_HELPER_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1a57bcf1528d2bf0def720fa142b64ebdacdd510/tmp/nd_meta_fb_crud_helper_v01.py'

def _fetch(url):
    return urllib.request.urlopen(url,timeout=30).read().decode('utf-8')

def _data_url(src):
    return 'data:text/plain;base64,'+base64.b64encode(src.encode('utf-8')).decode('ascii')

base_helper=_fetch(BASE_HELPER_URL)
old_edge="_meta.PAGE_ID+'/promotable_posts'"
new_edge="_meta.PAGE_ID+'/posts'"
if base_helper.count(old_edge)!=1:
    raise RuntimeError('facebook posts v26 list anchor mismatch')
base_helper=base_helper.replace(old_edge,new_edge,1)

helper=_fetch(HELPER_URL)
old_base="BASE='"+BASE_HELPER_URL+"'"
new_base="BASE='"+_data_url(base_helper)+"'"
if helper.count(old_base)!=1:
    raise RuntimeError('meta graph helper base anchor mismatch')
helper=helper.replace(old_base,new_base,1)

inner=_fetch(INNER_URL)
if inner.count(HELPER_URL)!=1:
    raise RuntimeError('meta graph inner helper anchor mismatch')
inner=inner.replace(HELPER_URL,_data_url(helper),1)

front=_fetch(BASE_FRONT)
if front.count(INNER_URL)!=1:
    raise RuntimeError('meta graph front inner anchor mismatch')
front=front.replace(INNER_URL,_data_url(inner),1)

print('ND_META_FB_LIST_V26_PATCH_READY',flush=True)
exec(compile(front,'nd_meta_fb_list_v26_front_v01.py','exec'))
