import urllib.request

BASE_COMMIT='a6c8a138c0bff87ba4ad7067a25bf63d639a50df'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_music_free_loader.py'
outer=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

music_anchor="music_code=r'''\n# ---- V20.7 FREE music capability"
music_repl="music_code=r'''\nimport urllib.request, urllib.parse, uuid\n# ---- V20.7 FREE music capability"
if outer.count(music_anchor)!=1:
    raise RuntimeError('v20_7_3_music_import_anchor_mismatch')
outer=outer.replace(music_anchor,music_repl,1)

worker_anchor="    threading.Thread(target=_music_worker,args=(uid,text),daemon=True).start()\n    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'"
worker_repl="    timer=threading.Timer(0.35,_music_worker,args=(uid,text))\n    timer.daemon=True\n    timer.start()\n    ack='Запускаю бесплатную генерацию музыки. Пришлю WAV сюда отдельным сообщением, когда он будет готов.'"
if outer.count(worker_anchor)!=1:
    raise RuntimeError('v20_7_3_ack_order_anchor_mismatch')
outer=outer.replace(worker_anchor,worker_repl,1)

diag_anchor="    file_token=str(uploaded.get('file') or '')\n    if not file_token:\n        raise RuntimeError('vk_music_upload_missing_file')"
diag_repl="    file_token=str(uploaded.get('file') or '')\n    if not file_token:\n        _diag={'keys':sorted([str(k) for k in uploaded.keys()]),'error':str(uploaded.get('error') or uploaded.get('error_descr') or uploaded.get('message') or '')[:240]}\n        state['music_last_upload_diag']=_diag\n        print('MUSIC_VK_UPLOAD_RESPONSE',json.dumps(_diag,ensure_ascii=False),flush=True)\n        raise RuntimeError('vk_music_upload_missing_file')"
if outer.count(diag_anchor)!=1:
    raise RuntimeError('v20_7_3_upload_diag_anchor_mismatch')
outer=outer.replace(diag_anchor,diag_repl,1)

compile(outer,'nd_vk_v20_7_3_music_upload_diag_loader.py','exec')
print('ND_V20_7_3_MUSIC_UPLOAD_DIAG_WRAPPER_READY',flush=True)
exec(compile(outer,'nd_vk_v20_7_3_music_upload_diag_loader.py','exec'))
