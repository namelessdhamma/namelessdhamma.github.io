import json
import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/a765f4f95e35cf41b669d3ab1ca48ab45cdc9c5d/tmp/nd_meta_vk_multiplex_front_v04_gemini_drive_mcp.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

anchor="GEMINI_INTROSPECT_URL='https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-gemini-mcp/introspect'\n"
inject=anchor+"GEMINI_SELFTEST_TOKEN=os.environ.get('ND_GEMINI_SELFTEST_TOKEN','').strip()\nGEMINI_MCP_URL='https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-gemini-mcp/mcp'\n"
if src.count(anchor)!=1:
    raise RuntimeError('gemini e2e env anchor mismatch')
src=src.replace(anchor,inject,1)

method_anchor="    def gemini_token_active(self):\n"
method=r'''    def gemini_e2e_selftest(self):
        if not GEMINI_SELFTEST_TOKEN:
            self.send_json(503,{'ok':False,'error':'selftest_disabled'}); return
        payload={
          'jsonrpc':'2.0','id':'railway-e2e-selftest','method':'tools/call',
          'params':{
            'name':'gemini_memory_query',
            'arguments':{
              'query':'From live ND memory in Google Drive, report only the current StateHead status, Capability Registry version, and component count. Do not use prior/model memory.',
              'max_tokens':2048,'temperature':0
            }
          }
        }
        try:
            req=urllib.request.Request(
              GEMINI_MCP_URL,
              data=json.dumps(payload).encode('utf-8'),method='POST',
              headers={
                'Authorization':'Bearer '+GEMINI_SELFTEST_TOKEN,
                'Content-Type':'application/json','Accept':'application/json',
                'MCP-Protocol-Version':'2025-06-18','User-Agent':'ND-Gemini-Drive-E2E/1.0'
              })
            with urllib.request.urlopen(req,timeout=180) as r:
                obj=json.loads(r.read().decode('utf-8','replace') or '{}')
            result=obj.get('result') or {}
            if result.get('isError'):
                self.send_json(502,{'ok':False,'stage':'gemini_memory_query','error':str(((result.get('content') or [{}])[0]).get('text') or 'tool_error')[:700]}); return
            out=result.get('structuredContent') or {}
            self.send_json(200,{
              'ok':bool(out.get('live_drive_retrieval')),
              'provider':out.get('provider'),
              'model':out.get('model'),
              'role':out.get('role'),
              'content':str(out.get('content') or '')[:2000],
              'tools_used':out.get('tools_used') or [],
              'live_drive_retrieval':bool(out.get('live_drive_retrieval')),
              'context_packet_required':out.get('context_packet_required'),
              'tool_access_mode':out.get('tool_access_mode'),
              'write_authority':out.get('write_authority')
            }); return
        except Exception as e:
            self.send_json(502,{'ok':False,'stage':'transport','error':clean(e)}); return

'''
if src.count(method_anchor)!=1:
    raise RuntimeError('gemini e2e method anchor mismatch')
src=src.replace(method_anchor,method+method_anchor,1)

health_anchor="        if path=='/gemini/drive/health':\n"
selftest_inject="        if path=='/gemini/drive/e2e-selftest':\n            self.gemini_e2e_selftest(); return\n"+health_anchor
if src.count(health_anchor)!=1:
    raise RuntimeError('gemini e2e GET anchor mismatch')
src=src.replace(health_anchor,selftest_inject,1)

print('ND_GEMINI_DRIVE_E2E_V05_READY '+json.dumps({'selftest':'/gemini/drive/e2e-selftest','bounded':True}),flush=True)
exec(compile(src,'nd_meta_vk_multiplex_front_v05_gemini_drive_e2e_runtime.py','exec'))
