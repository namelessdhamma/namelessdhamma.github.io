import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/e1fdbc500903ce58f8913e24d361d8d5cd1d3e65/tmp/nd_vk_gateway_v23_nd_readonly_ranked.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker='code=code.replace("ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START","ND_VK_GATEWAY_V23_ND_READONLY_RANKED_START",1)'
if marker not in outer:
    raise RuntimeError('V23 injection marker not found')
extra = r'''
# V27: add the dedicated Google Drive authority gateway to the V13 read-only source.
google_ro_code = r"""
def google_gateway_context(q):
    base=os.environ.get('ND_GOOGLE_GATEWAY_URL','').rstrip('/')
    key=os.environ.get('QSTASH_TOKEN','')
    if not base or not key:return []
    try:
        u=base+'/nd/context?q='+quote((q or '')[:5000],safe='')
        req=Request(u,method='GET',headers={'Authorization':'Bearer '+key,'Accept':'application/json','User-Agent':'nd-vk-google-proxy/1.0'})
        with urlopen(req,timeout=40) as r:j=json.loads(r.read().decode('utf-8','replace'))
        pieces=[]
        for p in (j.get('pieces') or []):
            label=str(p.get('label') or 'Google Drive ND context')
            text=str(p.get('text') or '').strip()
            if text:pieces.append((label,text[:9000]))
        print('ND_RO_GOOGLE_CONTEXT',json.dumps({'statehead_status':j.get('statehead_status'),'registry_version':j.get('registry_version'),'components':j.get('component_count'),'selected_components':j.get('selected_components'),'pieces':len(pieces)},ensure_ascii=False),flush=True)
        return pieces
    except Exception as e:
        print('ND_RO_GOOGLE_ERROR',cleanerr(e),flush=True)
        return []

def google_gateway_probe():
    time.sleep(6)
    p=google_gateway_context('ND architecture StateHead Registry current skills')
    print('ND_GOOGLE_PROXY_PROBE',json.dumps({'ok':bool(p),'pieces':len(p),'mutations':False},ensure_ascii=False),flush=True)

"""
def_marker='insert_before="def heuristic_route(text):\\n"'
if def_marker not in code:raise RuntimeError('V27 insert_before definition marker not found')
code=code.replace(def_marker,"google_ro_code="+repr(google_ro_code)+"\\n"+def_marker,1)

needle="src=src.replace(insert_before,ro_code+insert_before,1)"
if needle not in code:raise RuntimeError('V27 ro_code injection marker not found')
code=code.replace(needle,"src=src.replace(insert_before,ro_code+google_ro_code+insert_before,1)",1)

old_pieces="    pieces=[]\\n    try:pieces.extend(github_nd_context(q))\\n"
new_pieces="    pieces=[]\\n    try:pieces.extend(google_gateway_context(q))\\n    except Exception as e:print('ND_RO_GOOGLE_ERROR',cleanerr(e),flush=True)\\n    try:pieces.extend(github_nd_context(q))\\n"
if old_pieces not in code:raise RuntimeError('V27 ND pieces marker not found')
code=code.replace(old_pieces,new_pieces,1)

old_ndish="any(x in low for x in ('nd','nameless','архитект','statehead','registry','агент','книга','глава','рассказ','черновик','чистовик','сон том'))"
new_ndish="any(x in low for x in ('nd','nameless','архитект','statehead','registry','агент','книга','глава','рассказ','черновик','чистовик','сон том','скил','skill','плагин','plugin','инструмент','tool','памят','memory','автомат','automation','connector','подключ'))"
if old_ndish in code:code=code.replace(old_ndish,new_ndish,1)

code=code.replace("if used+len(chunk)>18000:chunk=chunk[:max(0,18000-used)]","if used+len(chunk)>22000:chunk=chunk[:max(0,22000-used)]",1)
code=code.replace("if used>=18000:break","if used>=22000:break",1)

thread_marker="threading.Thread(target=nd_ro_probe,daemon=True).start()\\n"
if thread_marker in code:
    code=code.replace(thread_marker,thread_marker+"threading.Thread(target=google_gateway_probe,daemon=True).start()\\n",1)
code=code.replace("ND_VK_GATEWAY_V13_ND_READONLY_START","ND_VK_GATEWAY_V27_ND_GOOGLE_PROXY_START",1)
'''
outer=outer.replace(marker,marker+"\n"+extra,1)
outer=outer.replace("ND_VK_GATEWAY_V23_ND_READONLY_RANKED_START","ND_VK_GATEWAY_V27_ND_GOOGLE_PROXY_RANKED_START",1)
outer=outer.replace("ND_V23_BOOTSTRAP","ND_V27_BOOTSTRAP",1)
outer=outer.replace("ND_V23_OUTER","ND_V27_OUTER",1)
outer=outer.replace("nd_vk_gateway_v23_outer.py","nd_vk_gateway_v27_outer.py",1)
print('ND_V27_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_gateway_v27_loader.py','exec'))
