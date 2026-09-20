import shutil
import urllib.request

_OLD_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py"
_NEW_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/a4c560c6137e3d7038702592e8f2db71ecade787/tmp/nd_gateway_linear_bridge_v2_clean_compat.py"

_OLD_V15B = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/98529cbb27ee130b3087e93d5322d613ddf0095f/tmp/nd_vk_gateway_v15b_father_min_profile.py"
_NEW_V17 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6e9c396401af1a642c2bdafffcaa37127960fae6/tmp/nd_vk_gateway_v17_omniroute_reserve.py"

_OLD_RETIREMENT_SHIM = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/eaee6796c4571dbd5aeed2b182c71ec83778688d/tmp/nd_runtime_retirement_sitecustomize_v3.py"

_original_urlopen = urllib.request.urlopen
_original_urlretrieve = urllib.request.urlretrieve

def _swap_url(value):
    if not isinstance(value, str):
        return value
    if value == _OLD_LINEAR:
        return _NEW_LINEAR
    # Exact match only: V16/V17 internally use ?v16base=1 and must remain untouched.
    if value == _OLD_V15B:
        return _NEW_V17
    return value

def _urlopen(value, *args, **kwargs):
    return _original_urlopen(_swap_url(value), *args, **kwargs)

def _urlretrieve(value, filename=None, *args, **kwargs):
    # Retirement entry tries to replace this shim with V3. Preserve the already-loaded V9 bytes locally.
    if isinstance(value, str) and value == _OLD_RETIREMENT_SHIM and filename:
        shutil.copyfile(__file__, filename)
        return (filename, None)
    return _original_urlretrieve(_swap_url(value), filename, *args, **kwargs)

urllib.request.urlopen = _urlopen
urllib.request.urlretrieve = _urlretrieve

print("ND_RUNTIME_OMNIROUTE_SHIM_V9_ACTIVE", flush=True)
