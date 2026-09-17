import urllib.request

CANONICAL_FRONT='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/12b41bdcc52b58781d3dd046842fbdf741ff89fb/tmp/nd_meta_fb_crud_front_v01.py'
RUNTIME_SUFFIX='/tmp/nd_meta_provider_runtime_v01.py'
_orig_urlopen=urllib.request.urlopen

class _BytesResponse:
    def __init__(self, data):
        self._data=data
    def read(self):
        return self._data
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False

def _urlopen_v26(req, *args, **kwargs):
    url=getattr(req,'full_url',None) or str(req)
    if not url.endswith(RUNTIME_SUFFIX):
        return _orig_urlopen(req,*args,**kwargs)
    with _orig_urlopen(req,*args,**kwargs) as r:
        src=r.read().decode('utf-8')
    old="'special_ad_categories':json.dumps([])})"
    new="'special_ad_categories':json.dumps([]),'is_adset_budget_sharing_enabled':'false'})"
    if src.count(old)!=1:
        raise RuntimeError('Meta Graph v26 campaign patch anchor mismatch')
    src=src.replace(old,new,1)
    print('ND_META_IGADS_V26_RUNTIME_INTERCEPT',flush=True)
    return _BytesResponse(src.encode('utf-8'))

urllib.request.urlopen=_urlopen_v26
src=_orig_urlopen(CANONICAL_FRONT,timeout=30).read().decode('utf-8')
print('ND_META_IGADS_V26_FRONT_READY',flush=True)
exec(compile(src,'nd_meta_fb_crud_front_v01.py','exec'))
