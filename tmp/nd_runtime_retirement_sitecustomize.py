import os
import urllib.request

_OLD_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py"
_NEW_LINEAR = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d8dfe49c5a508ceb3c833fd050bd78a1cebfac8b/tmp/nd_gateway_linear_bridge_v2_clean.py"

_original_urlopen = urllib.request.urlopen
_original_urlretrieve = urllib.request.urlretrieve

def _swap_url(value):
    if isinstance(value, str) and value == _OLD_LINEAR:
        return _NEW_LINEAR
    return value

def _urlopen(value, *args, **kwargs):
    return _original_urlopen(_swap_url(value), *args, **kwargs)

def _urlretrieve(value, *args, **kwargs):
    return _original_urlretrieve(_swap_url(value), *args, **kwargs)

urllib.request.urlopen = _urlopen
urllib.request.urlretrieve = _urlretrieve

print("ND_RUNTIME_RETIREMENT_SHIM_ACTIVE", flush=True)\n