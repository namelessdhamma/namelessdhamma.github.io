import builtins
import urllib.request

print("ND_V19_ORIGINAL_LOADER_ACTIVE", flush=True)
V19_PROBE_COMPAT_MARKER = "],1024,0.0)"
V20 = 'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c40817cd58158d63f4bb4d548bed8162c00d3f21/tmp/nd_vk_gateway_v20_dual_strong_router.py'
src = urllib.request.urlopen(V20, timeout=30).read().decode('utf-8')
if V19_PROBE_COMPAT_MARKER not in src:
    raise RuntimeError('V20 probe compatibility marker missing')
print('ND_V20_DUAL_STRONG_LOADER_READY', flush=True)
builtins.exec(builtins.compile(src, 'nd_vk_gateway_v20_dual_strong_router.py', 'exec'), {'__name__':'__main__'})
