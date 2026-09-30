import urllib.request, json

BASE_COMMIT='9b7da70f9e05188966d52c73f5b55d772267006a'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_4_music_yandex_fallback_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

exec_marker="exec(compile(outer,'nd_vk_v20_7_4_music_yandex_fallback_loader.py','exec'))"
capture_marker='globals()["_ND_V20_7_4R1_SOURCE"]=outer'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_7_4r1_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)

G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_7_4_capture.py','exec'),G,G)
src=G.get('_ND_V20_7_4R1_SOURCE','')
if not src:
    raise RuntimeError('v20_7_4r1_capture_failed')

state_anchor="state['music_last_duration_seconds']=None\n"
state_extra=state_anchor+"""state['music_route']='hf-direct+lightpanda-free-reserve'
state['music_reserve']='existing-lightpanda-cloud'
state['music_last_selected_route']=None
state['music_last_direct_error']=None
"""
if src.count(state_anchor)!=1:
    raise RuntimeError('v20_7_4r1_state_anchor_mismatch')
src=src.replace(state_anchor,state_extra,1)

worker_anchor='\ndef _music_worker(uid,text):'
reserve_code=r'''
def _music_lightpanda_call(name,args):
    route=os.environ.get('ND_LIGHTPANDA_MCP_PATH_TOKEN','').strip()
    if not route:
        raise RuntimeError('music_lightpanda_route_missing')
    url='http://127.0.0.1:5678/nd/lightpanda/mcp/'+urllib.parse.quote(route,safe='')
    payload={
        'jsonrpc':'2.0',
        'id':int(time.time()*1000)%2147483647,
        'method':'tools/call',
        'params':{'name':str(name),'arguments':args or {}},
    }
    req=urllib.request.Request(
        url,
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        method='POST',
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'Porfirchik-V20.7.4r1-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=90) as r:
        obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    result=obj.get('result') or {}
    out=result.get('structuredContent') or {}
    if result.get('isError') or not isinstance(out,dict) or not out.get('ok'):
        raise RuntimeError('music_lightpanda_call_failed:'+str((out or {}).get('error') or (obj.get('error') or {}).get('message') or 'unknown'))
    return out

def _music_generate_lightpanda(prompt,seconds,instrumental):
    _music_lightpanda_call('lightpanda_goto',{
        'url':MUSIC_SPACE_BASE+'/',
        'wait_until':'domcontentloaded',
        'timeout_ms':30000,
    })
    data=[str(prompt),float(seconds),-1,8,bool(instrumental)]
    script="""(async()=>{const d=__DATA__;const s=await fetch('/gradio_api/call/_generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({data:d})});let j={};try{j=await s.json()}catch{};const eid=String(j.event_id||'');if(!s.ok||!eid)return {ok:false,error:'submit_'+s.status};const r=await fetch('/gradio_api/call/_generate/'+encodeURIComponent(eid));const t=await r.text();if(t.includes('event: error'))return {ok:false,error:'provider_error'};let p=null;for(const line of t.split('\\n')){if(line.startsWith('data: ')){try{const c=JSON.parse(line.slice(6));if(Array.isArray(c)&&c.length)p=c}catch{}}}const u=String(p?.[0]?.url||'');return {ok:u.startsWith('https://'),audio_url:u,error:u?'':'no_audio'};})()""".replace('__DATA__',json.dumps(data,ensure_ascii=False))
    out=_music_lightpanda_call('lightpanda_evaluate',{'script':script})
    value=out.get('value') or {}
    if not isinstance(value,dict) or not value.get('ok'):
        raise RuntimeError('music_lightpanda_provider_error:'+str((value or {}).get('error') or 'unknown'))
    audio_url=str(value.get('audio_url') or '').strip()
    if not audio_url.startswith('https://'):
        raise RuntimeError('music_lightpanda_invalid_audio_url')
    areq=urllib.request.Request(audio_url,headers={'Accept':'*/*','User-Agent':'Porfirchik-V20.7.4r1-Music/1.0'})
    with urllib.request.urlopen(areq,timeout=60) as r:
        audio=r.read(MUSIC_MAX_BYTES+1)
    if not audio or len(audio)>MUSIC_MAX_BYTES:
        raise RuntimeError('music_lightpanda_audio_size_invalid')
    return audio,audio_url
'''
if src.count(worker_anchor)!=1:
    raise RuntimeError('v20_7_4r1_worker_anchor_mismatch')
src=src.replace(worker_anchor,'\n'+reserve_code+'\ndef _music_worker(uid,text):',1)

direct_line='        audio,audio_url=_music_generate(prompt,seconds,instrumental)\n'
direct_repl="""        try:
            audio,audio_url=_music_generate(prompt,seconds,instrumental)
            selected_route='hf-direct'
        except Exception as direct_e:
            state['music_last_direct_error']=_music_clean_error(direct_e)
            print('MUSIC_DIRECT_ROUTE_ERROR',state['music_last_direct_error'],flush=True)
            audio,audio_url=_music_generate_lightpanda(prompt,seconds,instrumental)
            selected_route='lightpanda-free-reserve'
            print('MUSIC_LIGHTPANDA_RESERVE_OK',flush=True)
        state['music_last_selected_route']=selected_route
"""
if src.count(direct_line)!=1:
    raise RuntimeError('v20_7_4r1_direct_anchor_mismatch')
src=src.replace(direct_line,direct_repl,1)

src=src.replace("state['adaptive_router']='v20.7-music-free'","state['adaptive_router']='v20.7.4r1-music-lightpanda-reserve'",1)
src=src.replace('ND_VK_GATEWAY_V20_7_MUSIC_FREE_START','ND_VK_GATEWAY_V20_7_4R1_MUSIC_LIGHTPANDA_START',1)

required=(
    "state['music_route']='hf-direct+lightpanda-free-reserve'",
    'def _music_generate_lightpanda(prompt,seconds,instrumental):',
    'MUSIC_LIGHTPANDA_RESERVE_OK',
    "selected_route='lightpanda-free-reserve'",
    "state['adaptive_router']='v20.7.4r1-music-lightpanda-reserve'",
    'ND_VK_GATEWAY_V20_7_4R1_MUSIC_LIGHTPANDA_START',
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_7_4r1_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_7_4r1_music_lightpanda_runtime.py','exec')
print('ND_V20_7_4R1_MUSIC_LIGHTPANDA_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_7_4R1_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_7_4r1_music_lightpanda_runtime.py','exec'),{'__name__':'__main__'})
