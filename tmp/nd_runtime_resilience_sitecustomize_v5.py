import urllib.request

_OLD_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py"
_NEW_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/a4c560c6137e3d7038702592e8f2db71ecade787/tmp/nd_gateway_linear_bridge_v2_clean_compat.py"

_OLD_V15B = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/98529cbb27ee130b3087e93d5322d613ddf0095f/tmp/nd_vk_gateway_v15b_father_min_profile.py"
_NEW_V16B = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1fe0909e022c3415efd83cf74ce21b30317fd60e/tmp/nd_vk_gateway_v16b_resilience_memory.py"

_original_urlopen = urllib.request.urlopen
_original_urlretrieve = urllib.request.urlretrieve

def _swap_url(value):
    if isinstance(value, str):
        if value == _OLD_LINEAR:
            return _NEW_LINEAR
        if value == _OLD_V15B:
            return _NEW_V16B
    return value

def _urlopen(value, *args, **kwargs):
    return _original_urlopen(_swap_url(value), *args, **kwargs)

def _urlretrieve(value, *args, **kwargs):
    return _original_urlretrieve(_swap_url(value), *args, **kwargs)

urllib.request.urlopen = _urlopen
urllib.request.urlretrieve = _urlretrieve

print("ND_RUNTIME_RESILIENCE_SHIM_V5_ACTIVE", flush=True)
