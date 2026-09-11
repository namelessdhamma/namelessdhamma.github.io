import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/835a07aa1af8a66ee4b9643a266e012b329b6190/tmp/nd_vk_gateway_v36_father_ux_research.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

# Extend V36 broker client with bounded args payload for sandbox semantic tools.
old_sig="def broker_invoke(tool,q):"
new_sig="def broker_invoke(tool,q,args=None):"
if old_sig not in src: raise RuntimeError('V42 broker signature marker not found')
src=src.replace(old_sig,new_sig,1)
old_payload="payload=json.dumps({'tool':tool,'query':(q or '')[:9000]},ensure_ascii=False).encode()"
new_payload="payload=json.dumps({'tool':tool,'query':(q or '')[:9000],'args':args or {}},ensure_ascii=False).encode()"
if old_payload not in src: raise RuntimeError('V42 broker payload marker not found')
src=src.replace(old_payload,new_payload,1)

# Extend Russian father UX with deterministic durable handoff/list commands.
old_help="Nameless Dhamma — помощник в VK. Просто пишите обычными словами. Умею: обычные вопросы; свежий интернет-поиск с источниками; глубокий анализ; чтение архитектуры ND; чтение и сравнение рассказов и черновиков. Команды: /быстро /глубоко /исследовать /книга /авто /источники /статус /сброс /ктоя. Обычно команды не нужны — режим выбирается автоматически."
new_help="Nameless Dhamma — помощник в VK. Просто пишите обычными словами. Умею: обычные вопросы; свежий интернет-поиск с источниками; глубокий анализ; чтение архитектуры ND; чтение и сравнение рассказов и черновиков; передавать сообщения и рабочие материалы в отдельную безопасную зону ND. Команды: /быстро /глубоко /исследовать /книга /передать /мои /авто /источники /статус /сброс /ктоя. Обычно команды не нужны — режим выбирается автоматически."
if old_help not in src: raise RuntimeError('V42 help marker not found')
src=src.replace(old_help,new_help,1)
old_sources="Источники чтения: ND authority и Google Drive; GitHub и Obsidian; Яндекс.Диск для книг; актуальный веб-поиск. Все подключения к ND только на чтение; изменения запрещены."
new_sources="Источники чтения: ND authority и Google Drive; GitHub и Obsidian; Яндекс.Диск для книг; актуальный веб-поиск. Каноническая ND остаётся только для чтения. Запись разрешена только в изолированную рабочую зону ND Father Workspace для сообщений, черновиков и исследовательских материалов."
if old_sources not in src: raise RuntimeError('V42 sources marker not found')
src=src.replace(old_sources,new_sources,1)
old_status="Система работает. AI: Groq + резерв OpenRouter. ND: чтение Google Drive/StateHead/Registry + GitHub/Obsidian. Книги: Яндекс.Диск, только чтение. Интернет: source-backed web research. Изменения ND запрещены. Режим: %s."
new_status="Система работает. AI: только сильные бесплатные модели Groq/OpenRouter. ND: чтение Google Drive/StateHead/Registry + GitHub/Obsidian. Книги: Яндекс.Диск, только чтение канона. Интернет: source-backed web research. Запись: только изолированный ND Father Workspace; каноническая ND неизменяема из VK. Режим: %s."
if old_status not in src: raise RuntimeError('V42 status marker not found')
src=src.replace(old_status,new_status,1)

needle="""                if text=='/tools':
                    try:send(peer,json.dumps(broker_invoke('tool_catalog',''),ensure_ascii=False,indent=2)[:3800])
                    except Exception as e:send(peer,'Safe Tool Broker unavailable: '+cleanerr(e))
                    return"""
insert="""                low_text=text.lower()
                handoff_prefixes=('передай савве','передай в nd','передай нд','сохрани это для nd','сохрани для nd','сообщи савве')
                if text.startswith('/передать') or any(low_text.startswith(x) for x in handoff_prefixes):
                    msg=''
                    if text.startswith('/передать'):
                        pp=text.split(None,1);msg=pp[1].strip() if len(pp)>1 else ''
                    else:
                        for pfx in handoff_prefixes:
                            if low_text.startswith(pfx):
                                msg=text[len(pfx):].lstrip(' :,-—').strip();break
                    if not msg:
                        send(peer,'Напишите после /передать, что именно нужно сохранить для Саввы / ND.');return
                    idem='vk:'+str(eid or hashlib.sha256((str(uid)+'|'+msg).encode('utf-8')).hexdigest()[:24])
                    args={'idempotency_key':idem,'content':msg,'title':'Сообщение от отца через VK','actor':'father_via_vk','sender_vk_id':str(uid),'gateway_version':'v42-father-handoff','source_refs':[]}
                    try:
                        rr=broker_invoke('sandbox_inbox_submit','',args)
                        if not (isinstance(rr,dict) and rr.get('ok') and rr.get('read_back_verified')):raise RuntimeError('sandbox save was not verified')
                        send(peer,'Сохранено и проверено. Передача в ND создана: %s; статус: %s.'%(rr.get('artifact_id'),rr.get('status','RECEIVED')))
                    except Exception as e:
                        print('FATHER_HANDOFF_ERROR',cleanerr(e),flush=True);send(peer,'Не удалось надёжно сохранить сообщение. Я не буду утверждать, что оно передано. Повторите позже.')
                    return
                if text in ('/мои','/my'):
                    try:
                        rr=broker_invoke('sandbox_list','',{'folder_id':'1LzNiq6PbE7yNZQqnHxexVbMkDpvI56Zl','limit':10})
                        items=(rr or {}).get('items') or []
                        if not items:send(peer,'В папке входящих передач пока нет сохранённых рабочих элементов.');return
                        lines=['Последние передачи в ND:']
                        for x in items[:10]:lines.append('%s — %s — %s'%(x.get('artifact_id','?'),x.get('status','?'),x.get('title','без названия')))
                        send(peer,'\\n'.join(lines)[:3800])
                    except Exception as e:
                        print('FATHER_LIST_ERROR',cleanerr(e),flush=True);send(peer,'Сейчас не удалось прочитать список передач.')
                    return
                if text=='/tools':
                    try:send(peer,json.dumps(broker_invoke('tool_catalog',''),ensure_ascii=False,indent=2)[:3800])
                    except Exception as e:send(peer,'Safe Tool Broker unavailable: '+cleanerr(e))
                    return"""
if needle not in src: raise RuntimeError('V42 command insertion marker not found')
src=src.replace(needle,insert,1)

src=src.replace('ND_V36_WRAPPER_READY','ND_V42_FATHER_HANDOFF_WRAPPER_READY',1)
print('ND_V42_LOADER_READY',flush=True)
exec(compile(src,'nd_vk_gateway_v42_father_handoff_loader.py','exec'))
