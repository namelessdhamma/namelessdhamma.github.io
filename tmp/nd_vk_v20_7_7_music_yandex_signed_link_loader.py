import urllib.request

# Porfirchik V20.7.7: FREE ACE-Step generation via configured route,
# private Yandex storage, signed gateway download link, no VK file upload.

BASE_COMMIT='a6c8a138c0bff87ba4ad7067a25bf63d639a50df'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_music_free_loader.py'
outer=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

music_anchor="music_code=r'''\n# ---- V20.7 FREE music capability"
music_repl="music_code=r'''\nimport urllib.request, urllib.parse, urllib.error, uuid, base64, hashlib\n# ---- V20.7 FREE music capability"
if outer.count(music_anchor)!=1:
    raise RuntimeError('v20_7_7_import_anchor_mismatch')
outer=outer.replace(music_anchor,music_repl,1)

redact_anchor="    for secret in (MUSIC_HF_TOKEN,os.environ.get('VK_GROUP_TOKEN','')):"
redact_repl="    for secret in (MUSIC_HF_TOKEN,os.environ.get('VK_GROUP_TOKEN',''),os.environ.get('YANDEX_DISK_TOKEN','')):"
if outer.count(redact_anchor)!=1:
    raise RuntimeError('v20_7_7_redact_anchor_mismatch')
outer=outer.replace(redact_anchor,redact_repl,1)

state_anchor="state['music_last_duration_seconds']=None\n"
state_repl=state_anchor+"""state['music_delivery']='private-yandex-signed-gateway-link'
state['music_vk_file_upload']=False
state['music_last_yandex_ok']=None
state['music_last_yandex_path']=None
state['music_last_yandex_error']=None
"""
if outer.count(state_anchor)!=1:
    raise RuntimeError('v20_7_7_state_anchor_mismatch')
outer=outer.replace(state_anchor,state_repl,1)

worker_anchor="    threading.Thread(target=_music_worker,args=(uid,text),daemon=True).start()\n    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'"
worker_repl="    timer=threading.Timer(0.35,_music_worker,args=(uid,text))\n    timer.daemon=True\n    timer.start()\n    ack='Запускаю бесплатную генерацию музыки. Когда она будет готова, сохраню WAV на Яндекс Диск и пришлю сюда ссылку.'"
if outer.count(worker_anchor)!=1:
    raise RuntimeError('v20_7_7_ack_anchor_mismatch')
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
        headers={'Authorization':'OAuth '+token,'Accept':'application/json','User-Agent':'Porfirchik-V20.7.7-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=45) as r:
        raw=r.read()
    return json.loads(raw.decode('utf-8','replace') or '{}')

def _music_signed_link(path):
    base=os.environ.get('VK_PUBLIC_BASE_URL','').strip().rstrip('/')
    vk_token=os.environ.get('VK_GROUP_TOKEN','').strip()
    if not base.startswith('https://'):
        raise RuntimeError('music_public_base_missing')
    if not vk_token:
        raise RuntimeError('music_link_signer_missing')
    encoded=base64.urlsafe_b64encode(str(path).encode('utf-8')).decode('ascii').rstrip('=')
    sig=hashlib.sha256(('music-link:'+vk_token+':'+encoded).encode('utf-8')).hexdigest()[:32]
    return base+'/porfirchik/music/'+sig+'/'+encoded

def _music_yandex_store(audio):
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
        headers={'Content-Type':'audio/wav','Content-Length':str(len(audio)),'User-Agent':'Porfirchik-V20.7.7-Music/1.0'}
    )
    with urllib.request.urlopen(req,timeout=90) as r:
        r.read()
    st=_music_yandex_api('/resources',{'path':path},'GET')
    if int(st.get('size') or 0)<=0:
        raise RuntimeError('yandex_music_stat_invalid')
    state['music_last_yandex_ok']=True
    state['music_last_yandex_path']=path
    state['music_last_yandex_error']=None
    return path

def _music_worker(uid,text):'''
if outer.count(helper_anchor)!=1:
    raise RuntimeError('v20_7_7_helper_anchor_mismatch')
outer=outer.replace(helper_anchor,"\n"+helper,1)

delivery_anchor="""        audio,audio_url=_music_generate(prompt,seconds,instrumental)
        try:
            _music_vk_upload(uid,audio,'porfirchik-music-%s.wav'%int(time.time()))
            delivered='vk-document'
        except Exception as upload_e:
            # Provider file URL is a bounded fallback so a successful generation is not lost.
            send(uid,'Музыка готова, но VK не принял файл. Временная ссылка: '+audio_url)
            delivered='provider-url-fallback'
            print('MUSIC_VK_UPLOAD_ERROR',_music_clean_error(upload_e),flush=True)"""
delivery_repl="""        audio,audio_url=_music_generate(prompt,seconds,instrumental)
        try:
            disk_path=_music_yandex_store(audio)
            link=_music_signed_link(disk_path)
            send(uid,'Музыка готова. Сохранил WAV на Яндекс Диске: '+link)
            delivered='yandex-signed-link-primary'
            print('MUSIC_YANDEX_DELIVERY_OK',json.dumps({'path':disk_path},ensure_ascii=False),flush=True)
        except Exception as yandex_e:
            state['music_last_yandex_ok']=False
            state['music_last_yandex_error']=_music_clean_error(yandex_e)
            print('MUSIC_YANDEX_DELIVERY_ERROR',state['music_last_yandex_error'],flush=True)
            send(uid,'Музыка готова, но сейчас не удалось сохранить её на Яндекс Диск. Временная ссылка: '+audio_url)
            delivered='provider-url-fallback'"""
if outer.count(delivery_anchor)!=1:
    raise RuntimeError('v20_7_7_delivery_anchor_mismatch')
outer=outer.replace(delivery_anchor,delivery_repl,1)

outer=outer.replace('ND_VK_GATEWAY_V20_7_MUSIC_FREE_START','ND_VK_GATEWAY_V20_7_7_MUSIC_YANDEX_SIGNED_LINK_START',1)

required=(
    "state['music_delivery']='private-yandex-signed-gateway-link'",
    "state['music_vk_file_upload']=False",
    'def _music_yandex_store(audio):',
    'def _music_signed_link(path):',
    "delivered='yandex-signed-link-primary'",
    'ND_VK_GATEWAY_V20_7_7_MUSIC_YANDEX_SIGNED_LINK_START',
)
for marker in required:
    if marker not in outer:
        raise RuntimeError('v20_7_7_marker_missing:'+marker)

compile(outer,'nd_vk_v20_7_7_music_yandex_signed_link_loader.py','exec')
print('ND_V20_7_7_MUSIC_YANDEX_SIGNED_LINK_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_v20_7_7_music_yandex_signed_link_loader.py','exec'))
