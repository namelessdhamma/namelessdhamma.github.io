import io, urllib.request
V49='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/2beb14af35d3288b644ee32cfb2f939d078d879c/tmp/nd_v49_research_qualified_launcher.py'
V9='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c617c9b200cb1637fca544985d35ab2a1b8d9e08/tmp/nd_vk_gateway_v9_free_router.py'
_orig=urllib.request.urlopen
OLD_SEND="""def send(peer,text):
    text=str(text or '')
    parts=[]
    while len(text)>3900:
        cut=text.rfind('\\n',0,3900)
        if cut<2500:cut=text.rfind(' ',0,3900)
        if cut<2000:cut=3900
        parts.append(text[:cut].strip());text=text[cut:].strip()
    if text:parts.append(text)
    if not parts:parts=['(пустой ответ)']
    results=[]
    for part in parts[:10]:
        r=vk('messages.send',{'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':part});results.append(r)
    print('VK_SENT',json.dumps({'peer_id':peer,'parts':len(results),'last_result':results[-1] if results else None}),flush=True)
    return results
"""
NEW_SEND="""def vk_plain_text(value):
    s=str(value or '')
    s=re.sub(r'```(?:[A-Za-z0-9_+-]+)?\\n?', '', s)
    s=s.replace('```','').replace('`','')
    s=re.sub(r'(?m)^\\s{0,3}#{1,6}\\s*', '', s)
    s=re.sub(r'(?m)^\\s*[-*_]{3,}\\s*$', '', s)
    s=re.sub(r'\\[([^]\\n]+)\\]\\((https?://[^)\\s]+)\\)', r'\\1 — \\2', s)
    s=s.replace('**','').replace('__','')
    s=re.sub(r'(?m)^\\s*[-*]\\s+', '• ', s)
    s=re.sub(r'(?<!\\w)_([^_\\n]+)_(?!\\w)', r'\\1', s)
    s=re.sub(r'(?<!\\*)\\*([^*\\n]+)\\*(?!\\*)', r'\\1', s)
    s=re.sub(r'\\n{3,}', '\\n\\n', s)
    return s.strip()

def vk_keyboard_json():
    return json.dumps({'one_time':False,'inline':False,'buttons':[
        [{'action':{'type':'text','label':'Статус','payload':'{\"nd\":\"status\"}'},'color':'secondary'},{'action':{'type':'text','label':'Интернет','payload':'{\"nd\":\"web\"}'},'color':'primary'}],
        [{'action':{'type':'text','label':'ND','payload':'{\"nd\":\"nd\"}'},'color':'secondary'},{'action':{'type':'text','label':'Книги','payload':'{\"nd\":\"books\"}'},'color':'secondary'}],
        [{'action':{'type':'text','label':'Источники','payload':'{\"nd\":\"sources\"}'},'color':'secondary'}]
    ]},ensure_ascii=False,separators=(',',':'))

def send(peer,text):
    text=vk_plain_text(text)
    parts=[]
    while len(text)>3900:
        cut=text.rfind('\\n',0,3900)
        if cut<2500:cut=text.rfind(' ',0,3900)
        if cut<2000:cut=3900
        parts.append(text[:cut].strip());text=text[cut:].strip()
    if text:parts.append(text)
    if not parts:parts=['(пустой ответ)']
    results=[];keyboard=vk_keyboard_json()
    for part in parts[:10]:
        r=vk('messages.send',{'peer_id':int(peer),'random_id':random.randint(1,2000000000),'message':part,'keyboard':keyboard});results.append(r)
    print('VK_SENT',json.dumps({'peer_id':peer,'parts':len(results),'keyboard':True,'plain_text':True,'last_result':results[-1] if results else None}),flush=True)
    return results
"""
MAP_MARKER="        def reply():\n"
MAP_REPL="""        text={'Статус':'/статус','Интернет':'Проверь актуальные новости в интернете и покажи источники.','ND':'Что сейчас происходит в ND? Покажи последние изменения и источники.','Книги':'Покажи доступные книги и рассказы. Ничего не изменяй.','Источники':'/источники'}.get(text,text)
        def reply():
"""
SYSTEM_OLD="Full ND connected-state access is a separate layer.'''
"
SYSTEM_NEW="Full ND connected-state access is a separate layer. VK OUTPUT RULE: write plain text only. Do not use Markdown, headings with #, bold/italic markers, code fences, tables, or horizontal rules. Prefer short paragraphs and simple numbered lists only when useful.'''
"
def _patch_v9(raw):
    if OLD_SEND not in raw: raise RuntimeError('V50b send marker missing')
    raw=raw.replace(OLD_SEND,NEW_SEND,1)
    if MAP_MARKER not in raw: raise RuntimeError('V50b reply marker missing')
    raw=raw.replace(MAP_MARKER,MAP_REPL,1)
    if SYSTEM_OLD not in raw: raise RuntimeError('V50b system marker missing')
    raw=raw.replace(SYSTEM_OLD,SYSTEM_NEW,1)
    raw=raw.replace('ND_VK_GATEWAY_V9_FREE_ROUTER_START','ND_VK_GATEWAY_V50B_PLAIN_KEYBOARD_START',1)
    return raw
def _urlopen(req,*args,**kwargs):
    url=req.full_url if hasattr(req,'full_url') else str(req)
    if url==V9:
        with _orig(req,*args,**kwargs) as r: raw=r.read().decode('utf-8')
        return io.BytesIO(_patch_v9(raw).encode('utf-8'))
    return _orig(req,*args,**kwargs)
urllib.request.urlopen=_urlopen
try:
    with _orig(V49,timeout=30) as r: code=r.read().decode('utf-8')
    print('ND_V50B_PLAIN_KEYBOARD_WRAPPER_READY',flush=True)
    exec(compile(code,'nd_v50b_vk_plain_keyboard_inner.py','exec'))
finally:
    urllib.request.urlopen=_orig
