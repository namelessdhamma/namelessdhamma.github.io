import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/065055f347a50476e9c99c551133558ae26c68a5/tmp/nd_vk_gateway_v15_direct_mcp.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

marker="exec(compile(wrapper,'nd_vk_gateway_v15_direct_mcp.py','exec'))"
if marker not in outer:
    raise RuntimeError('V15 exec marker missing')

addon=r'''
# ---- ND BROWSERLESS RAILWAY RELAY v1: additive bounded read-only fallback ----
bl_patch=r"""
BROWSERLESS_API_TOKEN=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
BL_RELAY_TOKEN=os.environ.get('ND_BROWSERLESS_RELAY_TOKEN','').strip()
BL_PROFILES_PATH=('/browserless/profiles/'+BL_RELAY_TOKEN) if BL_RELAY_TOKEN else ''

def browserless_profiles_relay():
    if not BROWSERLESS_API_TOKEN:
        return {'ok':False,'provider':'Browserless','error':'browserless_not_configured'}
    import urllib.parse as _up, urllib.request as _ur
    url='https://production-sfo.browserless.io/profiles?limit=20&offset=0&token='+_up.quote(BROWSERLESS_API_TOKEN,safe='')
    try:
        req=_ur.Request(url,headers={'Accept':'application/json','User-Agent':'ND-True-Doctor-Railway-Relay/1.0'})
        with _ur.urlopen(req,timeout=30) as r:
            raw=r.read().decode('utf-8')
        data=json.loads(raw)
        return {'ok':True,'provider':'Browserless','operation':'profiles_list','data':data}
    except Exception as e:
        msg=str(e)
        if BROWSERLESS_API_TOKEN:
            msg=msg.replace(BROWSERLESS_API_TOKEN,'[REDACTED]').replace(_up.quote(BROWSERLESS_API_TOKEN,safe=''),'[REDACTED]')
        return {'ok':False,'provider':'Browserless','operation':'profiles_list','error':msg}

"""
anchor="class H(BaseHTTPRequestHandler):\n"
if anchor not in src:
    raise RuntimeError('handler anchor missing for Browserless relay')
src=src.replace(anchor,bl_patch+"\n"+anchor,1)

old_root="""        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL,'direct_mcp_configured':bool(MCP_ROUTE_TOKEN)});return
"""
new_root="""        if BL_RELAY_TOKEN and p==BL_PROFILES_PATH:
            self.out(200,browserless_profiles_relay());return
        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL,'direct_mcp_configured':bool(MCP_ROUTE_TOKEN),'browserless_relay_configured':bool(BROWSERLESS_API_TOKEN and BL_RELAY_TOKEN)});return
"""
if old_root not in src:
    raise RuntimeError('V15 root anchor missing for Browserless relay')
src=src.replace(old_root,new_root,1)
# ---- end Browserless relay patch ----
'''
needle2="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if needle2 not in wrapper:
    raise RuntimeError('V14 inner exec marker missing from V15 wrapper')
wrapper=wrapper.replace(needle2,bl_patch+"\n"+needle2,1)
'''

outer=outer.replace(marker,addon+"\n"+marker,1)
exec(compile(outer,'nd_vk_gateway_v16_browserless_relay.py','exec'))
