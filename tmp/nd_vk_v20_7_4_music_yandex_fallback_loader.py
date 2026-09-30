import urllib.request

BASE_COMMIT='a6c8a138c0bff87ba4ad7067a25bf63d639a50df'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_music_free_loader.py'
outer=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

music_anchor="music_code=r'''\n# ---- V20.7 FREE music capability"
music_repl="music_code=r'''\nimport urllib.request, urllib.parse, urllib.error, uuid\n# ---- V20.7 FREE music capability"
if outer.count(music_anchor)!=1:
    raise RuntimeError('v20_7_4_import_anchor_mismatch')
outer=outer.replace(music_anchor,music_repl,1)

redact_anchor="    for secret in (MUSIC_HF_TOKEN,os.environ.get('VK_GROUP_TOKEN','')):"
redact_repl="    for secret in (MUSIC_HF_TOKEN,os.environ.get('VK_GROUP_TOKEN',''),os.environ.get('YANDEX_DISK_TOKEN','')):"
if outer.count(redact_anchor)!=1:
    raise RuntimeError('v20_7_4_redact_anchor_mismatch')
outer=outer.replace(redact_anchor,redact_repl,1)

worker_anchor="    threading.Thread(target=_music_worker,args=(uid,text),daemon=True).start()\n    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'"
worker_repl="    timer=threading.Timer(0.35,_music_worker,args=(uid,text))\n    timer.daemon=True\n    timer.start()\n    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'"
if outer.count(worker_anchor)!=1:
    raise RuntimeError('v20_7_4_ack_anchor_mismatch')
outer=outer.replace(worker_anchor,worker_repl,1)

helper_anchor="\ndef _music_worker(uid,text):"
helper=r'''
def _music_yandex_api(endpoint,params=None,method='GET'):
    token=os.environ.get('YANDEX_DISK_TOKEN','').strip()
    if not token:
        raise RuntimeError('YANDEX_DISK_TOKEN_missing')
    qs=urllib.parse.urlencode(params or {})
    url='https://cloud-api.yandex.net/v1/disk'+endpoint+('?' + qs if qs else '')
    req=urllib.request.Request(
        url,method=method,
        headers={'Authorization':'OAuth '+token,'Accept':'application/json','User-Agent':'Porfirchik-V20.7-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=45) as r:
        raw=r.read()
    return json.loads(raw.decode('utf-8','replace') or '{}')

def _music_yandex_publish(audio):
    folder='disk:/Porfirchik Music'
    try:
        _music_yandex_api('/resources',{'path':folder},'PUT')
    except urllib.error.HTTPError as e:
        if int(getattr(e,'code',0) or 0)!=409:
            raise
    filename='porfirchik-%s-%s.wav'%(time.strftime('%Y%m%d-%H%M%S',time.gmtime()),uuid.uuid4().hex[:8])
    path=folder+'/'+filename
    up=_music_yandex_api('/resources/upload',{'path':path,'overwrite':'false'})
    href=str(up.get('href') or '')
    if not href.startswith('https://'):
        raise RuntimeError('yandex_music_upload_href_missing')
    req=urllib.request.Request(
        href,data=audio,method='PUT',
        headers={'Content-Type':'audio/wav','Content-Length':str(len(audio)),'User-Agent':'Porfirchik-V20.7-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=90) as r:
        r.read()
    _music_yandex_api('/resources/publish',{'path':path},'PUT')
    st=_music_yandex_api('/resources',{'path':path},'GET')
    public_url=str(st.get('public_url') or '')
    if not public_url.startswith('http'):
        raise RuntimeError('yandex_music_public_url_missing')
    state['music_last_yandex_ok']=True
    state['music_last_yandex_path']=path
    return public_url

def _music_worker(uid,text):'''
if outer.count(helper_anchor)!=1:
    raise RuntimeError('v20_7_4_helper_anchor_mismatch')
outer=outer.replace(helper_anchor,"\n"+helper,1)

fallback_anchor="""        except Exception as upload_e:
            # Provider file URL is a bounded fallback so a successful generation is not lost.
            send(uid,'Музыка готова, но VK не принял файл. Временная ссылка: '+audio_url)
            delivered='provider-url-fallback'
            print('MUSIC_VK_UPLOAD_ERROR',_music_clean_error(upload_e),flush=True)"""
fallback_repl="""        except Exception as upload_e:
            print('MUSIC_VK_UPLOAD_ERROR',_music_clean_error(upload_e),flush=True)
            try:
                yandex_url=_music_yandex_publish(audio)
                send(uid,'Музыка готова. Сохранил WAV на Яндекс Диске: '+yandex_url)
                delivered='yandex-public-fallback'
                print('MUSIC_YANDEX_DELIVERY_OK',flush=True)
            except Exception as yandex_e:
                state['music_last_yandex_ok']=False
                state['music_last_yandex_error']=_music_clean_error(yandex_e)
                print('MUSIC_YANDEX_DELIVERY_ERROR',state['music_last_yandex_error'],flush=True)
                send(uid,'Музыка готова. Временная ссылка: '+audio_url)
                delivered='provider-url-fallback'"""
if outer.count(fallback_anchor)!=1:
    raise RuntimeError('v20_7_4_fallback_anchor_mismatch')
outer=outer.replace(fallback_anchor,fallback_repl,1)

compile(outer,'nd_vk_v20_7_4_music_yandex_fallback_loader.py','exec')
print('ND_V20_7_4_MUSIC_YANDEX_FALLBACK_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_v20_7_4_music_yandex_fallback_loader.py','exec'))
