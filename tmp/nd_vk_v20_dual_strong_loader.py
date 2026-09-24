import builtins
import urllib.request

V20 = 'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/676c2e5fb10495411a3cc920e7f5271f7638cba1/tmp/nd_vk_gateway_v20_dual_strong_router.py'
src = urllib.request.urlopen(V20, timeout=30).read().decode('utf-8')
print('ND_V20_DUAL_STRONG_LOADER_READY', flush=True)
builtins.exec(builtins.compile(src, 'nd_vk_gateway_v20_dual_strong_router.py', 'exec'), {'__name__':'__main__'})
