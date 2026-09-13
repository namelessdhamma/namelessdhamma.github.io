import urllib.request

V14='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
PATCH='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/93cfb9f8c6617d920a9e96b8cf69307697a94809/tmp/nd_vk_gateway_v15_provider_probe_patch.pyfrag'

v14=urllib.request.urlopen(V14,timeout=30).read().decode('utf-8')
v14_terminal="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if v14_terminal not in v14:
    raise RuntimeError('V14 terminal exec marker missing')

inner=f"""import urllib.request
v13_terminal="exec(compile(src,'nd_vk_gateway_v13_independent_web.py','exec'))"
if v13_terminal not in src:
    raise RuntimeError('V13 terminal exec marker missing')
provider_patch=urllib.request.urlopen('{PATCH}',timeout=30).read().decode('utf-8')
src=src.replace(v13_terminal,provider_patch,1)
exec(compile(src,'nd_vk_gateway_v15_mcp_provider_probe_v14stage.py','exec'))
"""

v14=v14.replace(v14_terminal,inner,1)
exec(compile(v14,'nd_vk_gateway_v15_mcp_provider_probe_loader.py','exec'))
