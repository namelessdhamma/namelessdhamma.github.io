import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/065055f347a50476e9c99c551133558ae26c68a5/tmp/nd_vk_gateway_v15_direct_mcp.py'
wrapper=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

marker="# ---- end direct MCP patch ----\n'''"
if marker not in wrapper:
    raise RuntimeError('V15 patch marker missing')

extra=r"""
old_tail="""threading.Thread(target=startup,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
"""
new_tail="""threading.Thread(target=startup,daemon=True).start()

def mcp_selftest():
    try:
        s1,b1=mcp_dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'nd-selftest','version':'1'}}})
        s2,b2=mcp_dispatch({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        st=mcp_call('vk_status',{})
        ok=(s1==200 and s2==200 and isinstance(b2,dict) and len((((b2.get('result') or {}).get('tools')) or []))>=6 and bool(st.get('ok')))
        state['mcp_probe']='ok' if ok else 'error'
        state['mcp_tool_count']=len((((b2.get('result') or {}).get('tools')) or []))
        print('MCP_SELFTEST_OK' if ok else 'MCP_SELFTEST_FAIL',json.dumps({'http_initialize':s1,'http_tools_list':s2,'tool_count':state['mcp_tool_count'],'vk_status_ok':bool(st.get('ok')),'group_id':st.get('group_id')},ensure_ascii=False),flush=True)
    except Exception as e:
        state['mcp_probe']='error';state['mcp_error']=cleanerr(e)
        print('MCP_SELFTEST_ERROR',cleanerr(e),flush=True)

threading.Thread(target=mcp_selftest,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
"""
if old_tail not in src:
    raise RuntimeError('V15 runtime tail anchor missing')
src=src.replace(old_tail,new_tail,1)
"""
wrapper=wrapper.replace(marker,extra+"\n# ---- end direct MCP patch ----\n'''",1)
exec(compile(wrapper,'nd_vk_gateway_v16_direct_mcp_selftest.py','exec'))
