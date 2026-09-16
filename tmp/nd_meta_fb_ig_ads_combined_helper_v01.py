import urllib.request

BASE_IGADS='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/81a816b1030c2b0da958ca3633aa18e4b0ec4c74/tmp/nd_meta_ig_ads_patch_v01.py'
src=urllib.request.urlopen(BASE_IGADS,timeout=30).read().decode('utf-8')

old="BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/76ac61a8d25aeb4dc789e50e2343fbc100a36152/tmp/nd_meta_fb_crud_patch_v01.py'"
new="BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/33083a14be309fa6717b9fab114fe854a8600e96/tmp/nd_meta_fb_crud_helper_v01.py'"
if src.count(old)!=1:
    raise RuntimeError('IG/Ads base marker not found exactly once')
src=src.replace(old,new,1)

ns={}
exec(compile(src,'nd_meta_ig_ads_patch_v01_rebased.py','exec'),ns)

QUAL_EXT=r"""
META_IGADS_QUALIFY_TRIGGER=os.environ.get('ND_META_IGADS_WRITE_QUALIFY_REV','').strip()

def meta_igads_qualify_once():
    if not META_IGADS_QUALIFY_TRIGGER: return
    time.sleep(10)
    try:
        ig=_meta.instagram_container_probe(META_IGADS_QUALIFY_TRIGGER)
        ads=_meta.campaign_probe(META_IGADS_QUALIFY_TRIGGER)
        out={'ok':bool(ig.get('ok') and ads.get('ok')),'instagram':ig,'ads':ads,'public_instagram_post_created':False,'adsets_created':0,'ads_created':0,'spend_possible':False}
        print('ND_META_IGADS_FULL_QUALIFY '+json.dumps(out,ensure_ascii=False),flush=True)
    except Exception as e:
        print('ND_META_IGADS_FULL_QUALIFY '+json.dumps({'ok':False,'error':str(e)[:700]},ensure_ascii=False),flush=True)
"""

ns['RUNTIME_GLOBALS']=ns['RUNTIME_GLOBALS']+"\n"+QUAL_EXT
RUNTIME_GLOBALS=ns['RUNTIME_GLOBALS']
MCP_METHOD=ns['MCP_METHOD']

def patch_linear_wrapper_source(src):
    runtime_exec="exec(compile(s,'nd_gateway_linear_bridge_v1_runtime.py','exec'))"
    if src.count(runtime_exec)!=1: raise RuntimeError('combined runtime exec marker not found exactly once')
    lines=[
      "runtime_anchor='class H(BaseHTTPRequestHandler):\\n'",
      "if s.count(runtime_anchor)!=1: raise RuntimeError('combined helper class anchor mismatch')",
      "runtime_globals="+repr(RUNTIME_GLOBALS),
      "s=s.replace(runtime_anchor,runtime_globals+runtime_anchor,1)",
      "post_anchor=\"    def do_POST(self):\\n        p=self.path.split('?',1)[0]\\n\"",
      "if s.count(post_anchor)!=1: raise RuntimeError('combined helper do_POST anchor mismatch')",
      "mcp_method="+repr(MCP_METHOD),
      "s=s.replace(post_anchor,mcp_method,1)",
      "server_anchor=\"ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()\"",
      "if s.count(server_anchor)!=1: raise RuntimeError('combined helper server anchor mismatch')",
      "s=s.replace(server_anchor,\"threading.Thread(target=meta_github_bootstrap_once,daemon=True).start()\\nthreading.Thread(target=meta_mcp_selftest_once,daemon=True).start()\\nthreading.Thread(target=meta_fb_qualify_once,daemon=True).start()\\nthreading.Thread(target=meta_igads_qualify_once,daemon=True).start()\\n\"+server_anchor,1)",
      "print('ND_META_FB_IG_ADS_HELPER_READY '+json.dumps({'tools':9,'facebook_crud':True,'comments':True,'instagram_media':True,'ads_campaign':True,'browser':False},ensure_ascii=False),flush=True)",
      runtime_exec,
    ]
    return src.replace(runtime_exec,"\n".join(lines),1)
