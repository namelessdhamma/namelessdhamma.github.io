import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4861bf8228e4e4f19f7db98ef1970c4f41338cb6/tmp/nd_gateway_linear_bridge_v1.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

load_marker="s=urllib.request.urlopen(U,timeout=30).read().decode()\n"
if src.count(load_marker)!=1:
    raise RuntimeError('V2b linear bridge load marker not found exactly once')

old_gateway="GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'"
new_gateway="GATEWAY_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/98529cbb27ee130b3087e93d5322d613ddf0095f/tmp/nd_vk_gateway_v15b_father_min_profile.py'"

patch=(
    "old_gateway="+repr(old_gateway)+"\n"
    "new_gateway="+repr(new_gateway)+"\n"
    "if s.count(old_gateway)!=1: raise RuntimeError('V2b active V14 gateway marker not found exactly once')\n"
    "s=s.replace(old_gateway,new_gateway,1)\n"
    "print('ND_FATHER_MIN_PROFILE_ROUTE_PATCH_V2B_READY',flush=True)\n"
)

src=src.replace(load_marker,load_marker+patch,1)
print('ND_LINEAR_BRIDGE_V2B_FATHER_PROFILE_WRAPPER_READY',flush=True)
exec(compile(src,'nd_gateway_linear_bridge_v2b_father_profile.py','exec'))
