import io, json, urllib.request

V46='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a9872a6ba0fba807ef6b7e4139e95de14a88c6a/tmp/nd_v46_fail_closed_strong_free_launcher.py'
_REAL=urllib.request.urlopen
v46=_REAL(V46,timeout=30).read().decode('utf-8')

SEND_PATCH = r'''
VK_KEYBOARD={
    'one_time':False,
    'inline':False,
    'buttons':[
        [
            {'action':{'type':'text','label':'Что в ND?'},'color':'secondary'},
            {'action':{'type':'text','label':'Книги'},'color':'secondary'}
        ],
        [
            {'action':{'type':'text','label':'Интернет'},'color':'primary'},
            {'action':{'type':'text','label':'Исследовать'},'color':'secondary'}
        ],
        [
            {'action':{'type':'text','label':'Передать Савве'},'color':'secondary'},
            {'action':{'type':'text','label':'Мои передачи'},'color':'secondary'}
        ],
        [
            {'action':{'type':'text','label':'Статус'},'color':'secondary'},
            {'action':{'type':'text','label':'Помощь'},'color':'secondary'}
        ]
    ]
}

def vk_plain_text(value):
    s=str(value or '').replace('\r\n','\n').replace('\r','\n')
    # Markdown emphasis/code/headings do not render usefully in VK messages.
    s=s.replace('**','').replace('__','').replace('```','').replace('`','')
    lines=[]
    for line in s.split('\n'):
        t=line.strip()
        if not t:
            if lines and lines[-1]!='':lines.append('')
            continue
        t=re.sub(r'^#{1,6}\s*','',t)
        t=re.sub(r'^>\s*','',t)
        t=re.sub(r'^[-*+]\s+','',t)
        if re.fullmatch(r'[-_*]{3,}',t):
            continue
        # Markdown links -> readable plain text with the URL preserved.
        t=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'\1 — \2',t)
        lines.append(t)
    out='\n'.join(lines)
    out=re.sub(r'\n{3,}','\n\n',out).strip()
    return out

def send(peer,text):
    text=vk_plain_text(text)
    parts=[]
    while len(text)>3900:
        cut=text.rfind('\n',0,3900)
        if cut<2500:cut=text.rfind(' ',0,3900)
        if cut<2000:cut=3900
        parts.append(text[:cut].strip());text=text[cut:].strip()
    if text:parts.append(text)
    if not parts:parts=['Пустой ответ.']
    results=[]
    for i,part in enumerate(parts[:8]):
        payload={'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':part}
        if i==len(parts[:8])-1:
            payload['keyboard']=json.dumps(VK_KEYBOARD,ensure_ascii=False,separators=(',',':'))
        r=vk('messages.send',payload)
        results.append(r)
    print('VK_SENT',json.dumps({'peer_id':peer,'parts':len(results),'last_result':results[-1] if results else None,'plain_text':True,'keyboard':True},ensure_ascii=False),flush=True)
    return results
'''

BUTTON_PATCH = r'''
        button_map={
            'Что в ND?':'Что сейчас происходит в ND? Назови последние подтверждённые изменения и источники.',
            'Книги':'/книга',
            'Интернет':'/исследовать',
            'Исследовать':'/исследовать',
            'Передать Савве':'/передать',
            'Мои передачи':'/мои',
            'Статус':'/статус',
            'Помощь':'/помощь'
        }
        text=button_map.get(text,text)
'''

PLAIN_SYSTEM = """BASE_SYSTEM += '''\nVK OUTPUT RULES: The user reads this inside VK, not ChatGPT. Use plain text only. Never use Markdown emphasis, headings, code fences, blockquotes, markdown tables or decorative separators. Do not surround words with asterisks, underscores or backticks. Prefer short paragraphs. Use a short numbered list only when it materially improves clarity. Never expose internal ND policy names unless the user explicitly asks for technical diagnostics.'''\n"""

def _patched(req,*args,**kwargs):
    url=req.full_url if hasattr(req,'full_url') else str(req)
    if url.endswith('/tmp/nd_vk_gateway_v8_adaptive.py'):
        with _REAL(req,*args,**kwargs) as r:
            raw=r.read().decode('utf-8')
        marker="WRITE_SYSTEM=BASE_SYSTEM+'''"
        if marker not in raw:raise RuntimeError('V50 base-system marker missing')
        raw=raw.replace(marker,PLAIN_SYSTEM+marker,1)
        a=raw.find('def send(peer,text):')
        b=raw.find('\ndef remember_event',a)
        if a<0 or b<0:raise RuntimeError('V50 send boundary missing')
        raw=raw[:a]+SEND_PATCH+'\n'+raw[b+1:]
        text_marker="        peer=m.get('peer_id');uid=m.get('from_id');text=(m.get('text') or '').strip()\n"
        if text_marker not in raw:raise RuntimeError('V50 button-map marker missing')
        raw=raw.replace(text_marker,text_marker+BUTTON_PATCH,1)
        raw=raw.replace("ND_VK_GATEWAY_V8_ADAPTIVE_START","ND_VK_GATEWAY_V50_PLAIN_KEYBOARD_START",1)
        return io.BytesIO(raw.encode('utf-8'))
    return _REAL(req,*args,**kwargs)

urllib.request.urlopen=_patched
try:
    print('ND_V50_PLAIN_KEYBOARD_LAUNCHER_READY',flush=True)
    exec(compile(v46,'nd_v50_vk_plain_keyboard_inner.py','exec'))
finally:
    urllib.request.urlopen=_REAL
