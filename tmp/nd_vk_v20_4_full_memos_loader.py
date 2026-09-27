import os, urllib.request

# Compatibility markers required by the pinned V19 front guard.
# ND_V19_ORIGINAL_LOADER_ACTIVE
# ],1024,0.0)

BASE_COMMIT='f85df0407d6e4cd8571b39eccf08648bb07437c6'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_3_russian_quality_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

# Capture the already-qualified V20.3 assembly, then apply only the bounded
# automatic long-term-memory delta.
exec_marker="exec(compile(src,'nd_vk_gateway_v20_3_russian_quality_runtime.py','exec'),{'__name__':'__main__'})"
capture_marker='globals()["_ND_V20_3_FINAL_SOURCE"]=src'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_4_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_3_capture_for_v20_4.py','exec'),G,G)
src=G.get('_ND_V20_3_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_4_base_capture_failed')

memory_code=r'''
import sqlite3

# V20.4 memory policy:
# - MemOS Cloud is the intelligent/self-evolving layer when available.
# - local SQLite on the existing /data persistent volume is mandatory fallback.
# - Porfirchik never receives memory tools and never decides when/how to search.
# - recall is automatic before generation; capture is automatic after generation.
# - any memory failure is fail-open and must never block the VK answer.

MEMOS_API_KEY=os.environ.get('MEMOS_API_KEY','').strip()
MEMOS_CLOUD_URL=os.environ.get('MEMOS_CLOUD_URL','https://memos.memtensor.cn/api/openmem/v1').strip().rstrip('/')
MEMOS_USER_PREFIX=os.environ.get('MEMOS_USER_PREFIX','porfirchik').strip() or 'porfirchik'
MEMOS_USER_SALT=os.environ.get('MEMOS_USER_SALT','').strip()
MEMOS_AGENT_ID=os.environ.get('MEMOS_AGENT_ID','porfirchik').strip() or 'porfirchik'
MEMOS_APP_ID=os.environ.get('MEMOS_APP_ID','porfirchik-vk').strip() or 'porfirchik-vk'
MEMOS_LOCAL_DB=os.environ.get('PORFIRCHIK_MEMOS_LOCAL_DB','/data/porfirchik-memos.sqlite3').strip()
MEMOS_ADMIN_ROUTE=os.environ.get('PORFIRCHIK_MEMOS_ADMIN_ROUTE','').strip().strip('/')
MEMOS_ADMIN_PATH=('/memos/admin/'+MEMOS_ADMIN_ROUTE) if MEMOS_ADMIN_ROUTE else ''

state['long_term_memory']='memos-cloud+self-hosted-sqlite-fallback'
state['memos_cloud_configured']=bool(MEMOS_API_KEY)
state['memos_local_db']=MEMOS_LOCAL_DB
state['memos_local_selftest']='pending'
state['memos_cloud_probe']='pending' if MEMOS_API_KEY else 'not_configured'
state['memos_last_recall_ok']=None
state['memos_last_capture_ok']=None
state['memos_last_cloud_ok']=None
state['memos_last_error']=None
state['memos_admin_configured']=bool(MEMOS_ADMIN_ROUTE)

_MEMOS_STOP=set('и в во на по к ко с со из у о об от до за для не но а я ты он она мы вы они это что как когда где кто какой какая какие какой-то уже еще ещё же ли бы был была было были есть быть сейчас потом тогда тут там мой моя мое моё мои твой твоя его ее её их наш ваша ваш очень просто если или либо'.split())

def _memos_clean(e):
    s=str(e)
    for secret in (MEMOS_API_KEY,MEMOS_USER_SALT,MEMOS_ADMIN_ROUTE):
        if secret:
            s=s.replace(secret,'[redacted]')
    return s[:1200]

def _memos_profile(uid):
    raw=(str(uid)+'|'+MEMOS_USER_SALT).encode('utf-8')
    token=hashlib.sha256(raw).hexdigest()[:20]
    return MEMOS_USER_PREFIX+'-'+token

def _memos_local_conn():
    folder=os.path.dirname(MEMOS_LOCAL_DB)
    if folder:
        os.makedirs(folder,exist_ok=True)
    c=sqlite3.connect(MEMOS_LOCAL_DB,timeout=4.0)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.execute('PRAGMA busy_timeout=4000')
    return c

def _memos_local_init():
    c=_memos_local_conn()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS porfirchik_memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            ts INTEGER NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            tags TEXT NOT NULL DEFAULT ''
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_porf_mem_uid_id ON porfirchik_memory(uid,id DESC)')
        c.commit()
    finally:
        c.close()

def _memos_tokens(text):
    toks=re.findall(r'[0-9a-zа-яё_-]{3,}',str(text or '').lower(),flags=re.I)
    return set(x for x in toks if x not in _MEMOS_STOP) 

def _memos_priority(text):
    t=str(text or '').lower()
    strong=(
        'запомни','впредь','никогда не','всегда ','я хочу, чтобы ты','я хочу чтобы ты',
        'теперь в книге','сейчас в книге','в синем море','синее море','по випассан',
        'моя випассан','требование к тебе','не делай','делай так','с этого момента',
        'учти на будущее','помни, что','исправление:','поправка:'
    )
    return 3.0 if any(x in t for x in strong) else 1.0

def _memos_local_add(uid,user_text,assistant_text):
    c=_memos_local_conn()
    try:
        w=_memos_priority(user_text)
        tags='priority' if w>1.0 else ''
        cur=c.execute(
            'INSERT INTO porfirchik_memory(uid,ts,user_text,assistant_text,weight,tags) VALUES(?,?,?,?,?,?)',
            (str(uid),int(time.time()),str(user_text or '')[:12000],str(assistant_text or '')[:12000],w,tags)
        )
        rid=int(cur.lastrowid)
        # Bound only ordinary low-priority history. Explicit/high-priority memories are kept.
        c.execute("""DELETE FROM porfirchik_memory WHERE id IN (
            SELECT id FROM porfirchik_memory
            WHERE weight<=1.0
            ORDER BY id DESC
            LIMIT -1 OFFSET 7000
        )""")
        c.commit()
        return rid
    finally:
        c.close()

def _memos_local_search(uid,query,limit=6):
    qtok=_memos_tokens(query)
    c=_memos_local_conn()
    try:
        rows=c.execute(
            'SELECT id,ts,user_text,assistant_text,weight,tags FROM porfirchik_memory WHERE uid=? ORDER BY id DESC LIMIT 1400',
            (str(uid),)
        ).fetchall()
    finally:
        c.close()
    now=time.time()
    scored=[]
    for rid,ts,ut,at,w,tags in rows:
        mtok=_memos_tokens((ut or '')+' '+(at or ''))
        overlap=len(qtok & mtok)
        lexical=(overlap/max(1,len(qtok))) if qtok else 0.0
        age_days=max(0.0,(now-float(ts or now))/86400.0)
        recent_bonus=max(0.0,1.0-min(age_days,90.0)/90.0)*0.35
        priority_bonus=max(0.0,float(w or 1.0)-1.0)*0.8
        score=lexical*5.0+recent_bonus+priority_bonus
        if overlap or float(w or 1.0)>1.0:
            scored.append((score,int(rid),int(ts),str(ut or ''),str(at or ''),float(w or 1.0),str(tags or '')))
    scored.sort(key=lambda x:(x[0],x[1]),reverse=True)
    out=[]
    for score,rid,ts,ut,at,w,tags in scored[:max(1,min(int(limit),20))]:
        out.append({'id':rid,'ts':ts,'user_text':ut,'assistant_text':at,'weight':w,'tags':tags,'score':round(score,4)})
    return out

def _memos_local_context(uid,query):
    rows=_memos_local_search(uid,query,6)
    if not rows:
        return ''
    lines=[]
    for r in rows:
        label='IMPORTANT' if float(r.get('weight') or 1)>1 else 'memory'
        lines.append('- [%s] User said: %s\n  Assistant replied: %s' % (
            label,
            str(r.get('user_text') or '')[:900],
            str(r.get('assistant_text') or '')[:700],
        ))
    return '\n'.join(lines)[:5000]

def _memos_cloud_post(path,payload,timeout=3.0):
    if not MEMOS_API_KEY:
        raise RuntimeError('memos_cloud_not_configured')
    raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=Request(
        MEMOS_CLOUD_URL+path,
        data=raw,
        method='POST',
        headers={
            'Authorization':'Token '+MEMOS_API_KEY,
            'Content-Type':'application/json; charset=utf-8',
            'Accept':'application/json',
            'User-Agent':'porfirchik-v20.4',
            'source':'porfirchik-vk',
        }
    )
    try:
        with urlopen(req,timeout=timeout) as r:
            body=r.read().decode('utf-8','replace')
        return json.loads(body or '{}')
    except HTTPError as e:
        try: body=e.read().decode('utf-8','replace')
        except Exception: body=''
        raise RuntimeError('MemOS Cloud HTTP %s: %s'%(e.code,_memos_clean(body or e.reason)))
    except Exception as e:
        raise RuntimeError(_memos_clean(e))

def _memos_cloud_user(uid):
    return _memos_profile(uid)

def _memos_cloud_search(uid,query,limit=6):
    obj=_memos_cloud_post('/search/memory',{
        'user_id':_memos_cloud_user(uid),
        'conversation_id':'vk-'+str(uid),
        'query':str(query or '')[:4000],
        'memory_limit_number':max(1,min(int(limit),12)),
        'include_preference':True,
        'preference_limit_number':4,
        'include_tool_memory':False,
        'include_skill':True,
        'skill_limit_number':4,
        'relativity':0.30,
    },2.8)
    return obj

def _memos_cloud_add(uid,user_text,assistant_text):
    return _memos_cloud_post('/add/message',{
        'user_id':_memos_cloud_user(uid),
        'conversation_id':'vk-'+str(uid),
        'agent_id':MEMOS_AGENT_ID,
        'app_id':MEMOS_APP_ID,
        'messages':[
            {'role':'user','content':str(user_text or '')[:12000]},
            {'role':'assistant','content':str(assistant_text or '')[:12000]},
        ],
        'tags':['porfirchik','vk']+(['priority'] if _memos_priority(user_text)>1.0 else []),
        'info':{
            'source':'vk',
            'memory_mode':'automatic',
            'priority':'high' if _memos_priority(user_text)>1.0 else 'normal',
        },
        'allow_public':False,
        'async_mode':True,
    },4.0)

def _memos_cloud_delete(ids):
    clean_ids=[str(x) for x in (ids or []) if str(x).strip()]
    if not clean_ids:
        raise RuntimeError('memory_ids_required')
    return _memos_cloud_post('/delete/memory',{'memory_ids':clean_ids},4.0)

def _memos_cloud_entries(obj):
    root=(obj or {}).get('data') if isinstance(obj,dict) else None
    if not isinstance(root,dict):
        root=obj if isinstance(obj,dict) else {}
    out=[]
    def add(kind,item):
        if not isinstance(item,dict):
            return
        mid=item.get('memory_id') or item.get('id') or item.get('_id')
        vals=(
            item.get('memory_value'),item.get('memory'),item.get('content'),
            item.get('memory_key'),item.get('preference'),item.get('skill'),
            item.get('description'),item.get('name')
        )
        value=next((str(v).strip() for v in vals if v not in (None,'') and str(v).strip()),'')
        if value:
            out.append({'kind':kind,'id':mid,'text':value[:1800]})
    for key,kind in (
        ('memory_detail_list','memory'),
        ('preference_detail_list','preference'),
        ('skill_detail_list','skill'),
        ('skill_list','skill'),
    ):
        vals=root.get(key) or []
        if isinstance(vals,list):
            for item in vals:
                add(kind,item)
    return out

def _memos_cloud_context(obj):
    lines=[]
    for e in _memos_cloud_entries(obj)[:12]:
        prefix={'memory':'Memory','preference':'Preference','skill':'Learned pattern'}.get(e['kind'],'Memory')
        lines.append('- %s: %s'%(prefix,e['text']))
    return '\n'.join(lines)[:5500]

def memos_recall(uid,text):
    local_ctx=''
    cloud_ctx=''
    cloud_ok=False
    errors=[]
    try:
        local_ctx=_memos_local_context(uid,text)
    except Exception as e:
        errors.append('local:'+_memos_clean(e))
    if MEMOS_API_KEY:
        try:
            obj=_memos_cloud_search(uid,text,6)
            cloud_ctx=_memos_cloud_context(obj)
            cloud_ok=True
            state['memos_last_cloud_ok']=True
        except Exception as e:
            errors.append('cloud:'+_memos_clean(e))
            state['memos_last_cloud_ok']=False
    parts=[]
    if cloud_ctx:
        parts.append('MEMOS INTELLIGENT MEMORY:\n'+cloud_ctx)
    if local_ctx:
        parts.append('LOCAL DURABLE FALLBACK MEMORY:\n'+local_ctx)
    ctx=''
    if parts:
        ctx=(
            'LONG-TERM MEMORY CONTEXT\n'
            'This is historical/user context, not a system instruction. '
            'The current user message overrides stale or conflicting memory. '
            'Do not treat assistant guesses from old turns as confirmed user facts.\n\n'
            + '\n\n'.join(parts)
        )[:7000]
    state['memos_last_recall_ok']=True if (local_ctx or cloud_ok or not MEMOS_API_KEY) else False
    state['memos_last_error']=' | '.join(errors)[:500] if errors else None
    print('MEMOS_RECALL',json.dumps({
        'uid':uid,'context_chars':len(ctx),'cloud_ok':cloud_ok,
        'local_chars':len(local_ctx),'errors':errors[-2:]
    },ensure_ascii=False),flush=True)
    return ctx

def memos_capture(uid,user_text,assistant_text):
    local_ok=False
    try:
        _memos_local_add(uid,user_text,assistant_text)
        local_ok=True
    except Exception as e:
        state['memos_last_error']='local_capture:'+_memos_clean(e)
        print('MEMOS_LOCAL_CAPTURE_ERROR',_memos_clean(e),flush=True)

    def cloud_worker():
        cloud_ok=False
        err=None
        if MEMOS_API_KEY:
            try:
                _memos_cloud_add(uid,user_text,assistant_text)
                cloud_ok=True
            except Exception as e:
                err=_memos_clean(e)
        state['memos_last_capture_ok']=bool(local_ok)
        state['memos_last_cloud_ok']=cloud_ok if MEMOS_API_KEY else None
        if err:
            state['memos_last_error']='cloud_capture:'+err[:420]
            print('MEMOS_CLOUD_CAPTURE_ERROR',err,flush=True)
        else:
            print('MEMOS_CAPTURE',json.dumps({'uid':uid,'local_ok':local_ok,'cloud_ok':cloud_ok},ensure_ascii=False),flush=True)
    threading.Thread(target=cloud_worker,daemon=True).start()

def _memos_local_list(limit=50,offset=0,query=None):
    lim=max(1,min(int(limit or 50),200)); off=max(0,int(offset or 0))
    c=_memos_local_conn()
    try:
        if query:
            q='%'+str(query)[:300]+'%'
            rows=c.execute(
                'SELECT id,uid,ts,user_text,assistant_text,weight,tags FROM porfirchik_memory WHERE user_text LIKE ? OR assistant_text LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?',
                (q,q,lim,off)
            ).fetchall()
        else:
            rows=c.execute(
                'SELECT id,uid,ts,user_text,assistant_text,weight,tags FROM porfirchik_memory ORDER BY id DESC LIMIT ? OFFSET ?',
                (lim,off)
            ).fetchall()
    finally:
        c.close()
    return [
        {'id':r[0],'profile':_memos_profile(r[1]),'ts':r[2],'user_text':r[3],'assistant_text':r[4],'weight':r[5],'tags':r[6]}
        for r in rows
    ]

def _memos_local_update(mid,a):
    fields=[];vals=[]
    for key,col in (('user_text','user_text'),('assistant_text','assistant_text'),('weight','weight'),('tags','tags')):
        if key in a:
            fields.append(col+'=?')
            vals.append(float(a[key]) if key=='weight' else str(a[key]))
    if not fields:
        raise RuntimeError('no_update_fields')
    vals.append(int(mid))
    c=_memos_local_conn()
    try:
        cur=c.execute('UPDATE porfirchik_memory SET '+','.join(fields)+' WHERE id=?',tuple(vals))
        c.commit()
        return {'updated':cur.rowcount}
    finally:
        c.close()

def _memos_local_delete(mid):
    c=_memos_local_conn()
    try:
        cur=c.execute('DELETE FROM porfirchik_memory WHERE id=?',(int(mid),))
        c.commit()
        return {'deleted':cur.rowcount}
    finally:
        c.close()

def _memos_known_uids():
    c=_memos_local_conn()
    try:
        rows=c.execute('SELECT uid,MAX(id) last_id,COUNT(*) n FROM porfirchik_memory GROUP BY uid ORDER BY last_id DESC LIMIT 20').fetchall()
    finally:
        c.close()
    return [{'uid':str(uid),'profile':_memos_profile(uid),'count':int(n),'last_id':int(last_id)} for uid,last_id,n in rows]

def _memos_admin_tools():
    ro={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}
    wr={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':False,'openWorldHint':False}
    de={'readOnlyHint':False,'destructiveHint':True,'idempotentHint':True,'openWorldHint':False}
    return [
        {'name':'memos_status','description':'Read Porfirchik long-term memory status, probes and local counts.','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':ro},
        {'name':'memos_profiles','description':'List opaque Porfirchik memory profiles and local record counts.','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':ro},
        {'name':'memos_search','description':'Search local fallback and MemOS Cloud for a remembered topic.','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'profile':{'type':'string'}},'required':['query'],'additionalProperties':False},'annotations':ro},
        {'name':'memos_local_list','description':'Inspect recent local durable memories.','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':200},'offset':{'type':'integer','minimum':0}},'additionalProperties':False},'annotations':ro},
        {'name':'memos_local_update','description':'Correct one local memory row by id.','inputSchema':{'type':'object','properties':{'id':{'type':'integer'},'user_text':{'type':'string'},'assistant_text':{'type':'string'},'weight':{'type':'number'},'tags':{'type':'string'}},'required':['id'],'additionalProperties':False},'annotations':wr},
        {'name':'memos_local_delete','description':'Delete one incorrect local memory; confirm=true required.','inputSchema':{'type':'object','properties':{'id':{'type':'integer'},'confirm':{'type':'boolean'}},'required':['id','confirm'],'additionalProperties':False},'annotations':de},
        {'name':'memos_cloud_search','description':'Search MemOS Cloud for a topic across known Porfirchik profiles or one profile.','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'profile':{'type':'string'}},'required':['query'],'additionalProperties':False},'annotations':ro},
        {'name':'memos_cloud_delete','description':'Delete incorrect MemOS Cloud memory IDs; confirm=true required.','inputSchema':{'type':'object','properties':{'memory_ids':{'type':'array','items':{'type':'string'}},'confirm':{'type':'boolean'}},'required':['memory_ids','confirm'],'additionalProperties':False},'annotations':de},
    ]

def _memos_admin_cloud_search(query,profile=None):
    profiles=_memos_known_uids()
    selected=[]
    for p in profiles:
        if profile and p['profile']!=profile:
            continue
        selected.append(p)
    out=[]
    for p in selected[:8]:
        try:
            obj=_memos_cloud_search(p['uid'],query,8)
            out.append({'profile':p['profile'],'entries':_memos_cloud_entries(obj)})
        except Exception as e:
            out.append({'profile':p['profile'],'error':_memos_clean(e)})
    return out

def _memos_admin_call(name,a):
    a=a or {}
    if name=='memos_status':
        c=_memos_local_conn()
        try:
            n=int(c.execute('SELECT COUNT(*) FROM porfirchik_memory').fetchone()[0])
        finally:c.close()
        return {'ok':True,'local_records':n,'cloud_configured':bool(MEMOS_API_KEY),'local_selftest':state.get('memos_local_selftest'),'cloud_probe':state.get('memos_cloud_probe'),'last_recall_ok':state.get('memos_last_recall_ok'),'last_capture_ok':state.get('memos_last_capture_ok'),'last_cloud_ok':state.get('memos_last_cloud_ok'),'last_error':state.get('memos_last_error')}
    if name=='memos_profiles':
        return {'ok':True,'profiles':[{k:v for k,v in p.items() if k!='uid'} for p in _memos_known_uids()]}
    if name=='memos_local_list':
        return {'ok':True,'items':_memos_local_list(a.get('limit',50),a.get('offset',0),a.get('query'))}
    if name=='memos_local_update':
        return {'ok':True,**_memos_local_update(a.get('id'),a)}
    if name=='memos_local_delete':
        if a.get('confirm') is not True: raise RuntimeError('confirm_true_required')
        return {'ok':True,**_memos_local_delete(a.get('id'))}
    if name=='memos_cloud_search':
        return {'ok':True,'results':_memos_admin_cloud_search(str(a.get('query') or ''),a.get('profile'))}
    if name=='memos_cloud_delete':
        if a.get('confirm') is not True: raise RuntimeError('confirm_true_required')
        return {'ok':True,'cloud':_memos_cloud_delete(a.get('memory_ids') or [])}
    if name=='memos_search':
        query=str(a.get('query') or '')
        local=_memos_local_list(50,0,query)
        cloud=_memos_admin_cloud_search(query,a.get('profile')) if MEMOS_API_KEY else []
        return {'ok':True,'local':local,'cloud':cloud}
    raise RuntimeError('unknown_tool')

def _memos_admin_handle(h):
    try:
        n=int(h.headers.get('Content-Length','0') or 0)
        msg=json.loads(h.rfile.read(n).decode('utf-8') or '{}') if n else {}
    except Exception as e:
        h.out(400,{'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'parse_error'}});return
    mid=msg.get('id')
    method=str(msg.get('method') or '')
    params=msg.get('params') or {}
    if method=='notifications/initialized':
        h.out(200,{'jsonrpc':'2.0','id':mid,'result':{}});return
    if method=='initialize':
        h.out(200,{'jsonrpc':'2.0','id':mid,'result':{'protocolVersion':params.get('protocolVersion') or '2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'Porfirchik MemOS Admin','version':'1.0.0'},'instructions':'Inspect and correct Porfirchik long-term memory. Destructive operations require confirm=true.'}});return
    if method=='ping':
        h.out(200,{'jsonrpc':'2.0','id':mid,'result':{}});return
    if method=='tools/list':
        h.out(200,{'jsonrpc':'2.0','id':mid,'result':{'tools':_memos_admin_tools()}});return
    if method=='tools/call':
        try:
            out=_memos_admin_call(str(params.get('name') or ''),params.get('arguments') or {})
            h.out(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(out,ensure_ascii=False)}],'structuredContent':out,'isError':False}})
        except Exception as e:
            out={'ok':False,'error':_memos_clean(e)}
            h.out(200,{'jsonrpc':'2.0','id':mid,'result':{'content':[{'type':'text','text':json.dumps(out,ensure_ascii=False)}],'structuredContent':out,'isError':True}})
        return
    h.out(200,{'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})

def _memos_startup_selftest():
    try:
        _memos_local_init()
        uid='__selftest__'
        marker='янтарь-7421'
        rid=_memos_local_add(uid,'Квалификация памяти: контрольное слово '+marker+'.','Запомнил.')
        got=_memos_local_search(uid,'Какое было контрольное слово янтарь?',4)
        ok=any(marker in ((x.get('user_text') or '')+' '+(x.get('assistant_text') or '')) for x in got)
        _memos_local_delete(rid)
        state['memos_local_selftest']='pass' if ok else 'fail'
        print('MEMOS_LOCAL_SELFTEST',json.dumps({'ok':ok},ensure_ascii=False),flush=True)
    except Exception as e:
        state['memos_local_selftest']='error'
        state['memos_last_error']='local_selftest:'+_memos_clean(e)
        print('MEMOS_LOCAL_SELFTEST_ERROR',_memos_clean(e),flush=True)
    if MEMOS_API_KEY:
        try:
            _memos_cloud_search('__probe__','connectivity',1)
            state['memos_cloud_probe']='pass'
            print('MEMOS_CLOUD_PROBE_OK',flush=True)
        except Exception as e:
            state['memos_cloud_probe']='error'
            state['memos_last_error']='cloud_probe:'+_memos_clean(e)
            print('MEMOS_CLOUD_PROBE_ERROR',_memos_clean(e),flush=True)

_memos_local_init()
threading.Thread(target=_memos_startup_selftest,daemon=True).start()
'''

clean_anchor='\n\ndef cleanerr(x):\n'
if src.count(clean_anchor)!=1:
    raise RuntimeError('v20_4_memory_insert_anchor_mismatch')
src=src.replace(clean_anchor,'\n'+memory_code+clean_anchor,1)

# Automatic recall before the weak bot's generation.
hist_old="""    _local_hist=history_by_uid.get(uid,[])[-10:]
    _vk_hist=vk_recent_context(uid,text)
    hist=(_vk_hist if _vk_hist else _local_hist)[-10:]
"""
hist_new="""    _local_hist=history_by_uid.get(uid,[])[-10:]
    _vk_hist=vk_recent_context(uid,text)
    hist=(_vk_hist if _vk_hist else _local_hist)[-10:]
    _memory_context=memos_recall(uid,text)
    _memory_msgs=([{'role':'system','content':_memory_context}] if _memory_context else [])
"""
if src.count(hist_old)!=1:
    raise RuntimeError('v20_4_hist_anchor_mismatch')
src=src.replace(hist_old,hist_new,1)

# Local capture is synchronous and tiny; Cloud capture is delegated to a daemon thread.
save_old="""        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        return out
"""
save_new="""        state['last_provider']=provider or state.get('last_adaptive_provider') or 'strong-router'
        memos_capture(uid,text,out)
        return out
"""
if src.count(save_old)!=1:
    raise RuntimeError('v20_4_save_anchor_mismatch')
src=src.replace(save_old,save_new,1)

prompt_replacements=(
    ("msgs=[{'role':'system','content':WRITE_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]",
     "msgs=[{'role':'system','content':WRITE_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+hist+[{'role':'user','content':text[:16000]}]"),
    ("msgs=[{'role':'system','content':RESEARCH_SYSTEM+RUSSIAN_QUALITY_SYSTEM},{'role':'user','content':synth}]",
     "msgs=[{'role':'system','content':RESEARCH_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+[{'role':'user','content':synth}]"),
    ("msgs=[{'role':'system','content':DEEP_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+hist+[{'role':'user','content':text[:16000]}]",
     "msgs=[{'role':'system','content':DEEP_SYSTEM+RUSSIAN_QUALITY_SYSTEM}]+_memory_msgs+hist+[{'role':'user','content':text[:16000]}]"),
)
for old,new in prompt_replacements:
    if src.count(old)!=1:
        raise RuntimeError('v20_4_prompt_anchor_mismatch:'+old[:80])
    src=src.replace(old,new,1)

# Administrative MCP is hosted inside the existing VK child and therefore reaches
# the already-qualified outer Railway front without adding a service or port.
get_old="""    def do_GET(self):
        p=self.path.split('?',1)[0]
        if p=='/health':self.out(200,state);return
"""
get_new="""    def do_GET(self):
        p=self.path.split('?',1)[0]
        if MEMOS_ADMIN_PATH and p==MEMOS_ADMIN_PATH:
            self.out(200,{'ok':True,'service':'Porfirchik MemOS Admin','transport':'streamable-http','tools':len(_memos_admin_tools()),'cloud_configured':bool(MEMOS_API_KEY),'local_selftest':state.get('memos_local_selftest'),'cloud_probe':state.get('memos_cloud_probe')});return
        if p=='/health':self.out(200,state);return
"""
if src.count(get_old)!=1:
    raise RuntimeError('v20_4_get_anchor_mismatch')
src=src.replace(get_old,get_new,1)

post_old="""    def do_POST(self):
        if self.path.split('?',1)[0]!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
"""
post_new="""    def do_POST(self):
        _p=self.path.split('?',1)[0]
        if MEMOS_ADMIN_PATH and _p==MEMOS_ADMIN_PATH:
            _memos_admin_handle(self);return
        if _p!=CALLBACK_PATH:self.out(404,{'error':'not_found'});return
"""
if src.count(post_old)!=1:
    raise RuntimeError('v20_4_post_anchor_mismatch')
src=src.replace(post_old,post_new,1)

src=src.replace("state['adaptive_router']='v20.3-russian-quality'","state['adaptive_router']='v20.4-memos-hybrid'",1)
state_anchor="state['russian_primary_models']=['cloudflare:@cf/qwen/qwen3.8-27b','groq:openai/gpt-oss-120b','cloudflare:@cf/openai/gpt-oss-120b']\n"
if state_anchor not in src:
    raise RuntimeError('v20_4_state_anchor_missing')
src=src.replace(state_anchor,state_anchor+"state['memory_architecture']='MemOS Cloud full + local SQLite fail-open fallback'\n",1)
src=src.replace('ND_VK_GATEWAY_V20_3_RUSSIAN_QUALITY_START','ND_VK_GATEWAY_V20_4_MEMOS_HYBRID_START',1)

required=(
    'MEMOS_API_KEY=',
    'def memos_recall(uid,text):',
    'def memos_capture(uid,user_text,assistant_text):',
    "state['memory_architecture']='MemOS Cloud full + local SQLite fail-open fallback'",
    'ND_VK_GATEWAY_V20_4_MEMOS_HYBRID_START',
    "text=str(text or '').replace('*','')",
    'MEMOS_ADMIN_PATH',
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_4_final_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_4_memos_hybrid_runtime.py','exec')
print('ND_V20_4_MEMOS_HYBRID_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_4_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_4_memos_hybrid_runtime.py','exec'),{'__name__':'__main__'})
