import os, urllib.request, urllib.parse, json, re, threading, time, uuid, random

# Porfirchik V20.7: bounded FREE music generation.
# Inherits the fully-qualified V20.6 runtime and adds one external ZeroGPU route.
# No model/GPU is hosted on Railway. No paid fallback is permitted.

BASE_COMMIT='c84fabca9ffcf06f10b4335097e7ba4f6dddf235'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_6_gateway_home_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

exec_marker="exec(compile(src,'nd_vk_gateway_v20_6_home_aware_runtime.py','exec'),{'__name__':'__main__'})"
capture_marker='globals()["_ND_V20_6_FINAL_SOURCE"]=src'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_7_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_6_capture_for_v20_7.py','exec'),G,G)
src=G.get('_ND_V20_6_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_7_base_capture_failed')

music_code=r'''
# ---- V20.7 FREE music capability -------------------------------------------
# Provider: community-maintained thin ACE-Step 1.5 ZeroGPU worker on Hugging Face.
# The model is ACE-Step 1.5; Railway only submits, receives and forwards the file.
# FREE_ONLY: there is intentionally no paid provider fallback.

MUSIC_SPACE_BASE=os.environ.get(
    'PORFIRCHIK_MUSIC_SPACE_BASE',
    'https://2btainment-ace-step.hf.space'
).strip().rstrip('/')
MUSIC_API_NAME='_generate'
MUSIC_DEFAULT_SECONDS=30
MUSIC_MAX_SECONDS=60
MUSIC_MAX_BYTES=25*1024*1024
MUSIC_HF_TOKEN=os.environ.get('HF_TOKEN','').strip()
_MUSIC_LOCK=threading.Lock()
_MUSIC_ACTIVE={}

state['music_generation']='ace-step-v1.5-zerogpu'
state['music_route']='hf-space:2btainment/ace-step'
state['music_free_only']=True
state['music_hosted_on_railway']=False
state['music_default_seconds']=MUSIC_DEFAULT_SECONDS
state['music_max_seconds']=MUSIC_MAX_SECONDS
state['music_active_jobs']=0
state['music_last_ok']=None
state['music_last_error']=None
state['music_last_duration_seconds']=None

def _music_clean_error(e):
    s=str(e)
    for secret in (MUSIC_HF_TOKEN,os.environ.get('VK_GROUP_TOKEN','')):
        if secret:
            s=s.replace(secret,'[redacted]')
    return s[:600]

def _music_intent(text):
    t=str(text or '').strip().lower()
    if t.startswith('/music') or t.startswith('/музыка'):
        return True
    verbs=('сделай','создай','сгенерируй','сочини','сочинить','запиши','сделать','создать','generate','make','compose')
    nouns=('музык','трек','мелоди','песн','саундтрек','джингл','music','track','song','melody','soundtrack','jingle')
    return any(v in t for v in verbs) and any(n in t for n in nouns)

def _music_prompt(text):
    t=str(text or '').strip()
    t=re.sub(r'^/(?:music|музыка)\s*','',t,flags=re.I).strip()
    return (t or 'спокойная атмосферная инструментальная музыка')[:1200]

def _music_duration(text):
    t=str(text or '').lower().replace(',','.')
    m=re.search(r'(\d+(?:\.\d+)?)\s*(?:мин(?:ут[а-я]*)?|minute(?:s)?)',t,re.I)
    if m:
        try:return max(10,min(MUSIC_MAX_SECONDS,int(float(m.group(1))*60)))
        except Exception:pass
    m=re.search(r'(\d{1,3})\s*(?:сек(?:унд[а-я]*)?|seconds?|sec\b)',t,re.I)
    if m:
        try:return max(10,min(MUSIC_MAX_SECONDS,int(m.group(1))))
        except Exception:pass
    return MUSIC_DEFAULT_SECONDS

def _music_is_instrumental(text):
    t=str(text or '').lower()
    return any(x in t for x in (
        'без слов','без вокала','инструментал','instrumental','no vocals','without vocals'
    ))

def _music_headers(content_type=None):
    h={'Accept':'application/json','User-Agent':'Porfirchik-V20.7-Music/1.0'}
    if content_type:h['Content-Type']=content_type
    if MUSIC_HF_TOKEN:h['Authorization']='Bearer '+MUSIC_HF_TOKEN
    return h

def _music_http_json(url,payload=None,timeout=45):
    data=None
    method='GET'
    if payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        method='POST'
    req=urllib.request.Request(
        url,data=data,method=method,
        headers=_music_headers('application/json' if payload is not None else None)
    )
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
    return json.loads(raw.decode('utf-8','replace') or '{}')

def _music_generate(prompt,seconds,instrumental):
    submit=_music_http_json(
        MUSIC_SPACE_BASE+'/gradio_api/call/'+MUSIC_API_NAME,
        {'data':[prompt,float(seconds),-1,8,bool(instrumental)]},
        45
    )
    event_id=str(submit.get('event_id') or '').strip()
    if not event_id:
        raise RuntimeError('music_submit_no_event_id')
    req=urllib.request.Request(
        MUSIC_SPACE_BASE+'/gradio_api/call/'+MUSIC_API_NAME+'/'+urllib.parse.quote(event_id,safe=''),
        headers=_music_headers()
    )
    with urllib.request.urlopen(req,timeout=210) as r:
        stream=r.read().decode('utf-8','replace')
    if 'event: error' in stream:
        raise RuntimeError('music_provider_error_or_free_quota_unavailable')
    payload=None
    for line in stream.splitlines():
        if line.startswith('data: '):
            try:
                candidate=json.loads(line[6:])
                if isinstance(candidate,list) and candidate:
                    payload=candidate
            except Exception:
                pass
    if not payload or not isinstance(payload[0],dict):
        raise RuntimeError('music_provider_no_audio')
    audio_url=str(payload[0].get('url') or '').strip()
    if not audio_url.startswith('https://'):
        raise RuntimeError('music_provider_invalid_audio_url')
    areq=urllib.request.Request(audio_url,headers=_music_headers())
    with urllib.request.urlopen(areq,timeout=60) as r:
        audio=r.read(MUSIC_MAX_BYTES+1)
    if not audio or len(audio)>MUSIC_MAX_BYTES:
        raise RuntimeError('music_audio_size_invalid')
    return audio,audio_url

def _music_vk_api(method,params):
    token=os.environ.get('VK_GROUP_TOKEN','').strip()
    if not token:
        raise RuntimeError('VK_GROUP_TOKEN_missing')
    q=dict(params or {})
    q['access_token']=token
    q['v']=os.environ.get('VK_API_VERSION','5.199')
    req=urllib.request.Request(
        'https://api.vk.com/method/'+method,
        data=urllib.parse.urlencode(q).encode('utf-8'),
        method='POST',
        headers={'User-Agent':'Porfirchik-V20.7-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=35) as r:
        obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    if obj.get('error'):
        raise RuntimeError('VK '+method+': '+str((obj.get('error') or {}).get('error_msg') or 'error'))
    return obj.get('response')

def _music_vk_upload(peer,audio,filename):
    up=_music_vk_api('docs.getMessagesUploadServer',{'peer_id':int(peer),'type':'doc'})
    upload_url=str((up or {}).get('upload_url') or '')
    if not upload_url.startswith('https://'):
        raise RuntimeError('vk_music_no_upload_url')
    boundary='----PorfirchikMusic'+uuid.uuid4().hex
    head=(
        '--'+boundary+'\r\n'
        'Content-Disposition: form-data; name="file"; filename="'+filename+'"\r\n'
        'Content-Type: audio/wav\r\n\r\n'
    ).encode('utf-8')
    body=head+audio+b'\r\n'+('--'+boundary+'--\r\n').encode('utf-8')
    req=urllib.request.Request(
        upload_url,data=body,method='POST',
        headers={
            'Content-Type':'multipart/form-data; boundary='+boundary,
            'Content-Length':str(len(body)),
            'User-Agent':'Porfirchik-V20.7-Music/1.0'
        }
    )
    with urllib.request.urlopen(req,timeout=60) as r:
        uploaded=json.loads(r.read().decode('utf-8','replace') or '{}')
    file_token=str(uploaded.get('file') or '')
    if not file_token:
        raise RuntimeError('vk_music_upload_missing_file')
    saved=_music_vk_api('docs.save',{'file':file_token,'title':filename})
    doc=None
    if isinstance(saved,list) and saved:
        doc=saved[0]
    elif isinstance(saved,dict):
        doc=saved.get('doc') if isinstance(saved.get('doc'),dict) else saved
    if not isinstance(doc,dict) or doc.get('id') is None or doc.get('owner_id') is None:
        raise RuntimeError('vk_music_docs_save_invalid')
    attachment='doc%s_%s'%(doc.get('owner_id'),doc.get('id'))
    if doc.get('access_key'):
        attachment+='_'+str(doc.get('access_key'))
    _music_vk_api('messages.send',{
        'peer_id':int(peer),
        'random_id':random.randint(1,2147483647),
        'message':'Готово. Музыка сгенерирована бесплатно через ACE-Step 1.5.',
        'attachment':attachment,
    })
    return attachment

def _music_worker(uid,text):
    prompt=_music_prompt(text)
    seconds=_music_duration(text)
    instrumental=_music_is_instrumental(text)
    state['music_last_duration_seconds']=seconds
    try:
        audio,audio_url=_music_generate(prompt,seconds,instrumental)
        try:
            _music_vk_upload(uid,audio,'porfirchik-music-%s.wav'%int(time.time()))
            delivered='vk-document'
        except Exception as upload_e:
            # Provider file URL is a bounded fallback so a successful generation is not lost.
            send(uid,'Музыка готова, но VK не принял файл. Временная ссылка: '+audio_url)
            delivered='provider-url-fallback'
            print('MUSIC_VK_UPLOAD_ERROR',_music_clean_error(upload_e),flush=True)
        state['music_last_ok']=True
        state['music_last_error']=None
        print('MUSIC_GENERATION_OK',json.dumps({
            'uid':uid,'seconds':seconds,'instrumental':instrumental,'delivery':delivered
        },ensure_ascii=False),flush=True)
    except Exception as e:
        err=_music_clean_error(e)
        state['music_last_ok']=False
        state['music_last_error']=err
        print('MUSIC_GENERATION_ERROR',err,flush=True)
        send(uid,'Сейчас бесплатный музыкальный генератор недоступен или исчерпал ZeroGPU-лимит. Платный маршрут я не включал.')
    finally:
        with _MUSIC_LOCK:
            _MUSIC_ACTIVE.pop(str(uid),None)
            state['music_active_jobs']=len(_MUSIC_ACTIVE)

_v20_6_routed_response=routed_response

def routed_response(uid,text):
    if not _music_intent(text):
        return _v20_6_routed_response(uid,text)
    key=str(uid)
    with _MUSIC_LOCK:
        if key in _MUSIC_ACTIVE:
            return 'Музыка для тебя уже генерируется. Дождись текущего файла, чтобы не расходовать бесплатную квоту дважды.'
        _MUSIC_ACTIVE[key]=int(time.time())
        state['music_active_jobs']=len(_MUSIC_ACTIVE)
    threading.Thread(target=_music_worker,args=(uid,text),daemon=True).start()
    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'
    try:
        memos_capture(uid,text,ack)
    except Exception:
        pass
    return ack
'''

thread_anchor="threading.Thread(target=startup,daemon=True).start()\n"
if src.count(thread_anchor)!=1:
    raise RuntimeError('v20_7_thread_anchor_mismatch')
src=src.replace(thread_anchor,music_code+'\n'+thread_anchor,1)

src=src.replace("state['adaptive_router']='v20.6-home-aware'","state['adaptive_router']='v20.7-music-free'",1)
src=src.replace('ND_VK_GATEWAY_V20_6_HOME_AWARE_START','ND_VK_GATEWAY_V20_7_MUSIC_FREE_START',1)

required=(
    "state['music_generation']='ace-step-v1.5-zerogpu'",
    "state['music_free_only']=True",
    'def _music_generate(prompt,seconds,instrumental):',
    'def _music_vk_upload(peer,audio,filename):',
    'def routed_response(uid,text):',
    "state['adaptive_router']='v20.7-music-free'",
    'ND_VK_GATEWAY_V20_7_MUSIC_FREE_START',
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_7_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_7_music_free_runtime.py','exec')
print('ND_V20_7_MUSIC_FREE_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_7_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_7_music_free_runtime.py','exec'),{'__name__':'__main__'})
