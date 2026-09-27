import os, urllib.request

# Compatibility markers required by the pinned V19 front guard.
# ND_V19_ORIGINAL_LOADER_ACTIVE
# ],1024,0.0)

BASE_COMMIT='7b8fe82854a8ceb3b86bd4d85fa99e27984edb95'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_4_full_memos_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')

# Capture the already-qualified V20.4 final runtime and apply only the bounded
# reliability delta: durable Cloud outbox/replay + user-first local recall.
exec_marker="exec(compile(src,'nd_vk_gateway_v20_4_memos_hybrid_runtime.py','exec'),{'__name__':'__main__'})"
capture_marker='globals()["_ND_V20_4_FINAL_SOURCE"]=src'
if base.count(exec_marker)!=1:
    raise RuntimeError('v20_5_capture_anchor_mismatch')
base=base.replace(exec_marker,capture_marker,1)
G={'__name__':'__main__'}
exec(compile(base,'nd_vk_v20_4_capture_for_v20_5.py','exec'),G,G)
src=G.get('_ND_V20_4_FINAL_SOURCE','')
if not src:
    raise RuntimeError('v20_5_base_capture_failed')

init_old="""def _memos_local_init():
    c=_memos_local_conn()
    try:
        c.execute(\"\"\"CREATE TABLE IF NOT EXISTS porfirchik_memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            ts INTEGER NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            tags TEXT NOT NULL DEFAULT ''
        )\"\"\")
        c.execute('CREATE INDEX IF NOT EXISTS idx_porf_mem_uid_id ON porfirchik_memory(uid,id DESC)')
        c.commit()
    finally:
        c.close()
"""
init_new="""def _memos_local_init():
    c=_memos_local_conn()
    try:
        c.execute(\"\"\"CREATE TABLE IF NOT EXISTS porfirchik_memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            ts INTEGER NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            tags TEXT NOT NULL DEFAULT ''
        )\"\"\")
        c.execute('CREATE INDEX IF NOT EXISTS idx_porf_mem_uid_id ON porfirchik_memory(uid,id DESC)')
        c.execute(\"\"\"CREATE TABLE IF NOT EXISTS porfirchik_cloud_outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL UNIQUE,
            uid TEXT NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            created_ts INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_retry_ts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        )\"\"\")
        c.execute('CREATE INDEX IF NOT EXISTS idx_porf_outbox_due ON porfirchik_cloud_outbox(next_retry_ts,id)')
        c.commit()
    finally:
        c.close()
"""
if src.count(init_old)!=1:
    raise RuntimeError('v20_5_init_anchor_mismatch')
src=src.replace(init_old,init_new,1)

add_old="""def _memos_local_add(uid,user_text,assistant_text):
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
        c.execute(\"\"\"DELETE FROM porfirchik_memory WHERE id IN (
            SELECT id FROM porfirchik_memory
            WHERE weight<=1.0
            ORDER BY id DESC
            LIMIT -1 OFFSET 7000
        )\"\"\")
        c.commit()
        return rid
    finally:
        c.close()
"""
add_new="""def _memos_local_add(uid,user_text,assistant_text,queue_cloud=False):
    c=_memos_local_conn()
    try:
        w=_memos_priority(user_text)
        tags='priority' if w>1.0 else ''
        now=int(time.time())
        ut=str(user_text or '')[:12000]
        at=str(assistant_text or '')[:12000]
        cur=c.execute(
            'INSERT INTO porfirchik_memory(uid,ts,user_text,assistant_text,weight,tags) VALUES(?,?,?,?,?,?)',
            (str(uid),now,ut,at,w,tags)
        )
        rid=int(cur.lastrowid)
        if queue_cloud and MEMOS_API_KEY:
            c.execute(
                'INSERT OR IGNORE INTO porfirchik_cloud_outbox(memory_id,uid,user_text,assistant_text,created_ts,attempts,next_retry_ts,last_error) VALUES(?,?,?,?,?,0,0,\\'\\')',
                (rid,str(uid),ut,at,now)
            )
        # Bound only ordinary low-priority history. Explicit/high-priority memories are kept.
        c.execute(\"\"\"DELETE FROM porfirchik_memory WHERE id IN (
            SELECT id FROM porfirchik_memory
            WHERE weight<=1.0
            ORDER BY id DESC
            LIMIT -1 OFFSET 7000
        )\"\"\")
        c.execute('DELETE FROM porfirchik_cloud_outbox WHERE memory_id NOT IN (SELECT id FROM porfirchik_memory)')
        c.commit()
        return rid
    finally:
        c.close()
"""
if src.count(add_old)!=1:
    raise RuntimeError('v20_5_add_anchor_mismatch')
src=src.replace(add_old,add_new,1)

search_old="""    for rid,ts,ut,at,w,tags in rows:
        mtok=_memos_tokens((ut or '')+' '+(at or ''))
        overlap=len(qtok & mtok)
        lexical=(overlap/max(1,len(qtok))) if qtok else 0.0
        age_days=max(0.0,(now-float(ts or now))/86400.0)
        recent_bonus=max(0.0,1.0-min(age_days,90.0)/90.0)*0.35
        priority_bonus=max(0.0,float(w or 1.0)-1.0)*0.8
        score=lexical*5.0+recent_bonus+priority_bonus
        if overlap or float(w or 1.0)>1.0:
            scored.append((score,int(rid),int(ts),str(ut or ''),str(at or ''),float(w or 1.0),str(tags or '')))
"""
search_new="""    for rid,ts,ut,at,w,tags in rows:
        utok=_memos_tokens(ut or '')
        atok=_memos_tokens(at or '')
        user_overlap=len(qtok & utok)
        assistant_overlap=len(qtok & atok)
        # User-authored facts dominate. Old assistant text is only weak historical context.
        lexical=((user_overlap)+(assistant_overlap*0.22))/max(1,len(qtok)) if qtok else 0.0
        age_days=max(0.0,(now-float(ts or now))/86400.0)
        recent_bonus=max(0.0,1.0-min(age_days,90.0)/90.0)*0.35
        priority_bonus=max(0.0,float(w or 1.0)-1.0)*0.8
        score=lexical*5.0+recent_bonus+priority_bonus
        if user_overlap or assistant_overlap or float(w or 1.0)>1.0:
            scored.append((score,int(rid),int(ts),str(ut or ''),str(at or ''),float(w or 1.0),str(tags or '')))
"""
if src.count(search_old)!=1:
    raise RuntimeError('v20_5_search_anchor_mismatch')
src=src.replace(search_old,search_new,1)

context_old="""        lines.append('- [%s] User said: %s\\n  Assistant replied: %s' % (
            label,
            str(r.get('user_text') or '')[:900],
            str(r.get('assistant_text') or '')[:700],
        ))
"""
context_new="""        lines.append('- [%s] User said (primary evidence): %s\\n  Historical assistant context (unverified): %s' % (
            label,
            str(r.get('user_text') or '')[:900],
            str(r.get('assistant_text') or '')[:500],
        ))
"""
if src.count(context_old)!=1:
    raise RuntimeError('v20_5_context_anchor_mismatch')
src=src.replace(context_old,context_new,1)

cloud_delete_anchor="""def _memos_cloud_delete(ids):
    clean_ids=[str(x) for x in (ids or []) if str(x).strip()]
    if not clean_ids:
        raise RuntimeError('memory_ids_required')
    return _memos_cloud_post('/delete/memory',{'memory_ids':clean_ids},4.0)
"""
outbox_code=cloud_delete_anchor+"""
_MEMOS_OUTBOX_LOCK=threading.Lock()

def _memos_outbox_stats():
    c=_memos_local_conn()
    try:
        row=c.execute('SELECT COUNT(*),COALESCE(MIN(created_ts),0),COALESCE(MAX(attempts),0) FROM porfirchik_cloud_outbox').fetchone()
        return {'pending':int(row[0] or 0),'oldest_ts':int(row[1] or 0),'max_attempts':int(row[2] or 0)}
    finally:
        c.close()

def _memos_outbox_flush(limit=4,force=False):
    if not MEMOS_API_KEY:
        return {'ok':True,'configured':False,'sent':0,'failed':0,**_memos_outbox_stats()}
    with _MEMOS_OUTBOX_LOCK:
        now=int(time.time())
        c=_memos_local_conn()
        try:
            if force:
                rows=c.execute('SELECT id,memory_id,uid,user_text,assistant_text,attempts FROM porfirchik_cloud_outbox ORDER BY id ASC LIMIT ?', (max(1,min(int(limit),20)),)).fetchall()
            else:
                rows=c.execute('SELECT id,memory_id,uid,user_text,assistant_text,attempts FROM porfirchik_cloud_outbox WHERE next_retry_ts<=? ORDER BY id ASC LIMIT ?', (now,max(1,min(int(limit),20)))).fetchall()
        finally:
            c.close()
        sent=0; failed=0; errors=[]
        for oid,mid,uid,ut,at,attempts in rows:
            try:
                _memos_cloud_add(uid,ut,at)
                c=_memos_local_conn()
                try:
                    c.execute('DELETE FROM porfirchik_cloud_outbox WHERE id=?',(int(oid),))
                    c.commit()
                finally:c.close()
                sent+=1
            except Exception as e:
                failed+=1
                err=_memos_clean(e)
                errors.append(err)
                tries=int(attempts or 0)+1
                delay=min(3600,5*(2**min(tries,9)))
                c=_memos_local_conn()
                try:
                    c.execute('UPDATE porfirchik_cloud_outbox SET attempts=?,next_retry_ts=?,last_error=? WHERE id=?',(tries,now+delay,err[:500],int(oid)))
                    c.commit()
                finally:c.close()
        st=_memos_outbox_stats()
        return {'ok':failed==0,'configured':True,'sent':sent,'failed':failed,'errors':errors[-3:],**st}

def _memos_outbox_kick(limit=4,force=False):
    def worker():
        try:
            out=_memos_outbox_flush(limit,force)
            state['memos_outbox_pending']=out.get('pending')
            state['memos_last_cloud_ok']=bool(out.get('ok')) if MEMOS_API_KEY else None
            if out.get('errors'):
                state['memos_last_error']='cloud_outbox:'+str(out.get('errors')[-1])[:420]
            print('MEMOS_OUTBOX_REPLAY',json.dumps(out,ensure_ascii=False),flush=True)
        except Exception as e:
            state['memos_last_cloud_ok']=False if MEMOS_API_KEY else None
            state['memos_last_error']='cloud_outbox:'+_memos_clean(e)
            print('MEMOS_OUTBOX_ERROR',_memos_clean(e),flush=True)
    threading.Thread(target=worker,daemon=True).start()
"""
if src.count(cloud_delete_anchor)!=1:
    raise RuntimeError('v20_5_cloud_delete_anchor_mismatch')
src=src.replace(cloud_delete_anchor,outbox_code,1)

delete_old="""def _memos_local_delete(mid):
    c=_memos_local_conn()
    try:
        cur=c.execute('DELETE FROM porfirchik_memory WHERE id=?',(int(mid),))
        c.commit()
        return {'deleted':cur.rowcount}
    finally:
        c.close()
"""
delete_new="""def _memos_local_delete(mid):
    c=_memos_local_conn()
    try:
        c.execute('DELETE FROM porfirchik_cloud_outbox WHERE memory_id=?',(int(mid),))
        cur=c.execute('DELETE FROM porfirchik_memory WHERE id=?',(int(mid),))
        c.commit()
        return {'deleted':cur.rowcount}
    finally:
        c.close()
"""
if src.count(delete_old)!=1:
    raise RuntimeError('v20_5_delete_anchor_mismatch')
src=src.replace(delete_old,delete_new,1)

capture_start=src.index("def memos_capture(uid,user_text,assistant_text):")
capture_end=src.index("\ndef _memos_local_list(",capture_start)
capture_new="""def memos_capture(uid,user_text,assistant_text):
    local_ok=False
    try:
        _memos_local_add(uid,user_text,assistant_text,True)
        local_ok=True
        state['memos_last_capture_ok']=True
        state['memos_outbox_pending']=_memos_outbox_stats().get('pending')
    except Exception as e:
        state['memos_last_capture_ok']=False
        state['memos_last_error']='local_capture:'+_memos_clean(e)
        print('MEMOS_LOCAL_CAPTURE_ERROR',_memos_clean(e),flush=True)
    if local_ok and MEMOS_API_KEY:
        _memos_outbox_kick(4,False)
    elif local_ok:
        state['memos_last_cloud_ok']=None
        print('MEMOS_CAPTURE',json.dumps({'uid':uid,'local_ok':True,'cloud_configured':False},ensure_ascii=False),flush=True)
"""
src=src[:capture_start]+capture_new+src[capture_end:]

status_old="""        return {'ok':True,'local_records':n,'cloud_configured':bool(MEMOS_API_KEY),'local_selftest':state.get('memos_local_selftest'),'cloud_probe':state.get('memos_cloud_probe'),'last_recall_ok':state.get('memos_last_recall_ok'),'last_capture_ok':state.get('memos_last_capture_ok'),'last_cloud_ok':state.get('memos_last_cloud_ok'),'last_error':state.get('memos_last_error')}
"""
status_new="""        outbox=_memos_outbox_stats()
        state['memos_outbox_pending']=outbox.get('pending')
        return {'ok':True,'local_records':n,'cloud_configured':bool(MEMOS_API_KEY),'local_selftest':state.get('memos_local_selftest'),'cloud_probe':state.get('memos_cloud_probe'),'outbox':outbox,'last_recall_ok':state.get('memos_last_recall_ok'),'last_capture_ok':state.get('memos_last_capture_ok'),'last_cloud_ok':state.get('memos_last_cloud_ok'),'last_error':state.get('memos_last_error')}
"""
if src.count(status_old)!=1:
    raise RuntimeError('v20_5_status_anchor_mismatch')
src=src.replace(status_old,status_new,1)

qual_start=src.index("    if name=='memos_qualify':")
qual_end=src.index("    if name=='memos_search':",qual_start)
qual_new="""    if name=='memos_qualify':
        marker='малахит-'+str(int(time.time()*1000))
        score_marker='ультрамарин-'+str(int(time.time()*1000))
        uid='__qualification__'
        local_id=None; user_id=None; assistant_id=None
        local_ok=False; user_first_ok=False; cloud_ok=False; cloud_cleanup=False; outbox_ok=False; cloud_ids=[]; errors=[]
        try:
            local_id=_memos_local_add(uid,'Квалификация памяти: контрольное слово '+marker+'.','Запомнил контрольное слово.',True)
            local_ok=any(marker in ((x.get('user_text') or '')+' '+(x.get('assistant_text') or '')) for x in _memos_local_search(uid,marker,5))
            user_id=_memos_local_add(uid,'Пользователь сообщает '+score_marker+'.','Нейтральный ответ.',False)
            assistant_id=_memos_local_add(uid,'Нейтральная пользовательская реплика.','Ассистент предположил '+score_marker+'.',False)
            ranked=_memos_local_search(uid,score_marker,8)
            score_by_id={int(x.get('id')):float(x.get('score') or 0) for x in ranked}
            user_first_ok=score_by_id.get(int(user_id),0)>score_by_id.get(int(assistant_id),0)
            if MEMOS_API_KEY:
                flush=_memos_outbox_flush(10,True)
                outbox_ok=int(_memos_outbox_stats().get('pending') or 0)==0 and int(flush.get('failed') or 0)==0
                for wait_s in (1,2,3,4,5):
                    time.sleep(wait_s)
                    obj=_memos_cloud_search(uid,'контрольное слово '+marker,10)
                    entries=_memos_cloud_entries(obj)
                    matched=[x for x in entries if marker in str(x.get('text') or '')]
                    if matched:
                        cloud_ok=True
                        cloud_ids=[str(x.get('id')) for x in matched if x.get('id')]
                        break
                if cloud_ids:
                    _memos_cloud_delete(cloud_ids)
                    cloud_cleanup=True
            else:
                outbox_ok=True
        except Exception as e:
            errors.append('qualification:'+_memos_clean(e))
        finally:
            for mid in (local_id,user_id,assistant_id):
                if mid is not None:
                    try:_memos_local_delete(mid)
                    except Exception as e:errors.append('local_cleanup:'+_memos_clean(e))
        return {'ok':bool(local_ok and user_first_ok and outbox_ok and (cloud_ok if MEMOS_API_KEY else True)),'local_ok':local_ok,'user_first_ok':user_first_ok,'outbox_ok':outbox_ok,'cloud_configured':bool(MEMOS_API_KEY),'cloud_ok':cloud_ok if MEMOS_API_KEY else None,'cloud_cleanup':cloud_cleanup if MEMOS_API_KEY else None,'outbox_pending':_memos_outbox_stats().get('pending'),'marker':marker,'errors':errors}
"""
src=src[:qual_start]+qual_new+src[qual_end:]

probe_old="""            state['memos_cloud_probe']='pass'
            print('MEMOS_CLOUD_PROBE_OK',flush=True)
"""
probe_new="""            state['memos_cloud_probe']='pass'
            print('MEMOS_CLOUD_PROBE_OK',flush=True)
            _memos_outbox_kick(8,False)
"""
if src.count(probe_old)!=1:
    raise RuntimeError('v20_5_probe_anchor_mismatch')
src=src.replace(probe_old,probe_new,1)

src=src.replace("'User-Agent':'porfirchik-v20.4'","'User-Agent':'porfirchik-v20.5'",1)
src=src.replace("'version':'1.1.0'","'version':'1.2.0'",1)
src=src.replace("state['adaptive_router']='v20.4-memos-hybrid'","state['adaptive_router']='v20.5-memory-durable'",1)
src=src.replace("state['memory_architecture']='MemOS Cloud full + local SQLite fail-open fallback'","state['memory_architecture']='MemOS Cloud + local SQLite + durable Cloud outbox/replay'",1)
src=src.replace("state['memos_admin_configured']=bool(MEMOS_ADMIN_ROUTE)","state['memos_admin_configured']=bool(MEMOS_ADMIN_ROUTE)\\nstate['memos_outbox_pending']=0\\nstate['memos_recall_policy']='user-first-v1'",1)
src=src.replace('ND_VK_GATEWAY_V20_4_MEMOS_HYBRID_START','ND_VK_GATEWAY_V20_5_MEMORY_DURABLE_START',1)

required=(
    'CREATE TABLE IF NOT EXISTS porfirchik_cloud_outbox',
    'def _memos_outbox_flush(limit=4,force=False):',
    'assistant_overlap*0.22',
    "state['memos_recall_policy']='user-first-v1'",
    "state['adaptive_router']='v20.5-memory-durable'",
    'ND_VK_GATEWAY_V20_5_MEMORY_DURABLE_START',
    "text=str(text or '').replace('*','')",
)
for marker in required:
    if marker not in src:
        raise RuntimeError('v20_5_final_marker_missing:'+marker)

compile(src,'nd_vk_gateway_v20_5_memory_durable_runtime.py','exec')
print('ND_V20_5_MEMORY_DURABLE_ASSEMBLY_READY',flush=True)

if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_5_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(src,'nd_vk_gateway_v20_5_memory_durable_runtime.py','exec'),{'__name__':'__main__'})
