import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/06fc6c8019d837620853eb2bbee253300920b422/tmp/nd_tldraw_mcp_front_v1.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

old="""        canonical=json.dumps(all_tools,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        names=[str(t.get('name') or '') for t in all_tools]
"""
new="""        all_resources=[]
        resource_cursor=None
        resource_pages=0
        while True:
            resource_pages+=1
            if resource_pages>100:
                raise RuntimeError('resources_pagination_guard_exceeded')
            params={} if resource_cursor is None else {'cursor':resource_cursor}
            robj,sid,_=local_mcp_call({'jsonrpc':'2.0','id':'nd-tldraw-resources-%d'%resource_pages,'method':'resources/list','params':params},session_id=sid)
            if not isinstance(robj,dict) or robj.get('error'):
                raise RuntimeError('resources_list_failed:'+json.dumps(robj,ensure_ascii=False)[:1200])
            rpage=(robj.get('result') or {})
            resources=rpage.get('resources') or []
            if not isinstance(resources,list):
                raise RuntimeError('resources_not_list')
            all_resources.extend(resources)
            resource_cursor=rpage.get('nextCursor')
            if not resource_cursor:
                break

        resource_reads=[]
        for i,res in enumerate(all_resources):
            uri=str((res or {}).get('uri') or '')
            if not uri:
                continue
            read_obj,sid,_=local_mcp_call({'jsonrpc':'2.0','id':'nd-tldraw-resource-read-%d'%i,'method':'resources/read','params':{'uri':uri}},session_id=sid)
            if not isinstance(read_obj,dict) or read_obj.get('error'):
                raise RuntimeError('resource_read_failed:'+uri+':'+json.dumps(read_obj,ensure_ascii=False)[:1200])
            contents=((read_obj.get('result') or {}).get('contents') or [])
            summary=[]
            for item in contents:
                text=item.get('text') if isinstance(item,dict) else None
                blob=item.get('blob') if isinstance(item,dict) else None
                payload=(text if isinstance(text,str) else (blob if isinstance(blob,str) else ''))
                summary.append({
                    'uri':(item or {}).get('uri') if isinstance(item,dict) else None,
                    'mimeType':(item or {}).get('mimeType') if isinstance(item,dict) else None,
                    'chars':len(payload),
                    'sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest() if payload else None
                })
            resource_reads.append({'uri':uri,'contents':summary})

        resource_templates=[]
        templates_supported=False
        try:
            tobj,sid,_=local_mcp_call({'jsonrpc':'2.0','id':'nd-tldraw-resource-templates','method':'resources/templates/list','params':{}},session_id=sid)
            if isinstance(tobj,dict) and not tobj.get('error'):
                resource_templates=((tobj.get('result') or {}).get('resourceTemplates') or [])
                templates_supported=True
        except Exception:
            templates_supported=False

        canonical=json.dumps(all_tools,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        resource_canonical=json.dumps(all_resources,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        resource_digest=hashlib.sha256(resource_canonical.encode('utf-8')).hexdigest()
        names=[str(t.get('name') or '') for t in all_tools]
"""
if src.count(old)!=1:
    raise RuntimeError('resource insertion anchor mismatch count=%d'%src.count(old))
src=src.replace(old,new,1)

old2="""            'tool_surface_sha256':digest,
            'serverInfo':result.get('serverInfo') or {},
"""
new2="""            'tool_surface_sha256':digest,
            'resources_paginated_to_exhaustion':True,
            'resource_pages':resource_pages,
            'resources_count':len(all_resources),
            'resources':all_resources,
            'resource_reads':resource_reads,
            'resource_surface_sha256':resource_digest,
            'resource_templates_supported':templates_supported,
            'resource_templates':resource_templates,
            'serverInfo':result.get('serverInfo') or {},
"""
if src.count(old2)!=1:
    raise RuntimeError('resource result anchor mismatch count=%d'%src.count(old2))
src=src.replace(old2,new2,1)

src=src.replace("'version':'1.2.0'","'version':'1.3.0'",1)
src=src.replace("ND_TLDRAW_MCP_RELAY_V1_2_READY","ND_TLDRAW_MCP_RELAY_V1_3_READY",1)
src=src.replace("ND-Tldraw-MCP-Relay/1.2","ND-Tldraw-MCP-Relay/1.3",1)
src=src.replace("tldraw-v1.2","tldraw-v1.3",1)

print('ND_TLDRAW_RESOURCE_QUALIFIER_V2_READY',flush=True)
exec(compile(src,'nd_tldraw_mcp_front_v2_resources_runtime.py','exec'))
