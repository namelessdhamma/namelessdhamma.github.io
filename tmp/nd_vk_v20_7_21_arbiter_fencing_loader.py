import os,urllib.request
BASE_COMMIT='a0cc8129643ea35ca0e2ba5c938785ba09e5eb6b'
BASE_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+BASE_COMMIT+'/tmp/nd_vk_v20_7_20_strongest_russian_all_paths_loader.py'
base=urllib.request.urlopen(BASE_URL,timeout=30).read().decode('utf-8')
old="exec(compile(s,'v20720_wrapper.py','exec'),{'__name__':'__main__'})"
if base.count(old)!=1: raise RuntimeError('v20721_capture_anchor_missing')
G={'__name__':'__main__'}
exec(compile(base.replace(old,"globals()['_V20721_S']=s",1),'v20721_capture.py','exec'),G,G)
s=G.get('_V20721_S','')
if not s: raise RuntimeError('v20721_base_capture_failed')

arbiter_patch=r'''
# V20.7.21 — Cloudflare-authoritative ingress/outbound fencing adapter.
# Default remains legacy. Shadow/cutover/managed are explicit rollout states.
import contextvars as _arb_cv
import hmac as _arb_hmac
import io as _arb_io
import urllib.request as _arb_ur

_ARB_MODE=os.environ.get('PORFIRCHIK_ARB_MODE','legacy').strip().lower() or 'legacy'
if _ARB_MODE not in ('legacy','shadow','cutover','managed'):
    raise RuntimeError('invalid PORFIRCHIK_ARB_MODE')
_ARB_OWNER=os.environ.get('PORFIRCHIK_ARB_OWNER','RAILWAY').strip().upper() or 'RAILWAY'
if _ARB_OWNER not in ('RAILWAY','RENDER'):
    raise RuntimeError('invalid PORFIRCHIK_ARB_OWNER')
_ARB_CTX=_arb_cv.ContextVar('porfirchik_arbiter_ctx',default=None)
_ARB_LANE=_arb_cv.ContextVar('porfirchik_arbiter_lane',default='event')
_ARB_SEND_SEQ=_arb_cv.ContextVar('porfirchik_arbiter_send_seq',default=0)
state['arbiter_adapter']='v20.7.21'
state['arbiter_mode']=_ARB_MODE
state['arbiter_owner']=_ARB_OWNER
state['arbiter_outbound_authority']='cloudflare' if _ARB_MODE in ('cutover','managed') else ('shadow' if _ARB_MODE=='shadow' else 'direct-vk')
state['arbiter_shadow_outputs']=0
state['arbiter_fence_rejections']=0
state['arbiter_internal_errors']=0

def _arb_clean(x):
    s=str(x)
    for secret in (TOKEN,):
        if secret:s=s.replace(secret,'[redacted]')
    return s[:500]

def _arb_body(obj):
    return json.dumps(obj,ensure_ascii=False,separators=(',',':'))

def _arb_sig(ts,owner,epoch,event,lane,body_text):
    body_hash=hashlib.sha256(body_text.encode('utf-8')).hexdigest()
    canonical='\n'.join(('nd-porfirchik-arbiter-v1',str(ts),str(owner),str(epoch),str(event),str(lane),body_hash))
    return _arb_hmac.new(TOKEN.encode('utf-8'),canonical.encode('utf-8'),hashlib.sha256).hexdigest()

def _arb_consteq(a,b):
    try:return _arb_hmac.compare_digest(str(a),str(b))
    except Exception:return False

def _arb_call(path,payload,ctx,lane=None,timeout=15.0):
    origin=str((ctx or {}).get('origin') or '').strip().rstrip('/')
    if not origin.startswith('https://'):
        raise RuntimeError('arbiter_origin_invalid')
    body=_arb_body(payload)
    ts=str(int(time.time()*1000))
    owner=str((ctx or {}).get('owner') or _ARB_OWNER)
    epoch=str((ctx or {}).get('epoch') or '')
    event=str((ctx or {}).get('event_key') or '')
    lane=str(lane or _ARB_LANE.get() or 'event')
    sig=_arb_sig(ts,owner,epoch,event,lane,body)
    req=_arb_ur.Request(origin+path,data=body.encode('utf-8'),method='POST',headers={
        'Content-Type':'application/json; charset=utf-8','Accept':'application/json',
        'X-ND-Timestamp':ts,'X-ND-Owner':owner,'X-ND-Epoch':epoch,
        'X-ND-Event':event,'X-ND-Lane':lane,'X-ND-Signature':sig,
        'User-Agent':'Porfirchik-Arbiter-Adapter/20.7.21',
    })
    try:
        with _arb_ur.urlopen(req,timeout=timeout) as r:
            raw=r.read(200000).decode('utf-8','replace')
            obj=json.loads(raw or '{}') if raw else {}
            return int(getattr(r,'status',200) or 200),obj
    except Exception as e:
        code=int(getattr(e,'code',0) or 0)
        raw=''
        try:raw=e.read(100000).decode('utf-8','replace')
        except Exception:pass
        if code:
            try:return code,json.loads(raw or '{}')
            except Exception:return code,{'ok':False,'error':_arb_clean(raw or e)}
        raise

def _arb_split(text):
    text=str(text or '')
    parts=[]
    while len(text)>3900:
        cut=text.rfind('\n',0,3900)
        if cut<2500:cut=text.rfind(' ',0,3900)
        if cut<2000:cut=3900
        parts.append(text[:cut].strip());text=text[cut:].strip()
    if text:parts.append(text)
    return parts or ['(пустой ответ)']

def _arb_outbound(peer,text):
    ctx=_ARB_CTX.get()
    # Legacy/direct traffic stays untouched until the callback cutover.
    if not ctx:
        if _ARB_MODE=='managed':
            state['arbiter_fence_rejections']+=1
            raise RuntimeError('managed_mode_requires_signed_arbiter_context')
        return _v20721_direct_vk_send(peer,text)
    lane=str(_ARB_LANE.get() or 'event')
    call_index=int(_ARB_SEND_SEQ.get() or 0)
    _ARB_SEND_SEQ.set(call_index+1)
    parts=_arb_split(text)
    if _ARB_MODE=='shadow':
        state['arbiter_shadow_outputs']+=len(parts)
        print('ARB_SHADOW_OUTBOUND',json.dumps({'event':ctx.get('event_key'),'lane':lane,'call':call_index,'parts':len(parts)},ensure_ascii=False),flush=True)
        return [{'shadow':True,'parts':len(parts)}]
    results=[]
    for part_index,part in enumerate(parts):
        output_key='%s|%s|send:%s|part:%s'%(ctx['event_key'],lane,call_index,part_index)
        payload={'event_key':ctx['event_key'],'output_key':output_key,'peer_id':int(peer),'message':part,'owner':ctx['owner'],'epoch':int(ctx['epoch']),'lane':lane}
        last=None
        for attempt in range(3):
            try:
                code,obj=_arb_call('/internal/outbound',payload,ctx,lane,18.0)
                last=(code,obj)
                if code==200 and obj.get('ok'):
                    results.append(obj.get('vk_result'))
                    break
                if code==409:
                    state['arbiter_fence_rejections']+=1
                    print('ARB_STALE_OUTBOUND_REJECTED',json.dumps({'event':ctx['event_key'],'lane':lane,'epoch':ctx['epoch']},ensure_ascii=False),flush=True)
                    raise RuntimeError('arbiter_stale_fence')
            except RuntimeError:
                raise
            except Exception as e:
                last=(0,{'error':_arb_clean(e)})
            if attempt<2:time.sleep(0.4*(attempt+1))
        else:
            state['arbiter_internal_errors']+=1
            raise RuntimeError('arbiter_outbound_failed:'+_arb_clean(last))
    print('ARB_OUTBOUND_OK',json.dumps({'event':ctx['event_key'],'lane':lane,'parts':len(results),'epoch':ctx['epoch']},ensure_ascii=False),flush=True)
    return results

def _arb_notify(path,payload,ctx,lane,timeout=8.0):
    if _ARB_MODE=='shadow':return True
    try:
        code,obj=_arb_call(path,payload,ctx,lane,timeout)
        if code==409:
            state['arbiter_fence_rejections']+=1
            return False
        return code==200 and bool(obj.get('ok'))
    except Exception as e:
        state['arbiter_internal_errors']+=1
        print('ARB_NOTIFY_ERROR',json.dumps({'path':path,'type':type(e).__name__},ensure_ascii=False),flush=True)
        return False

def _arb_complete(ctx,error=None):
    return _arb_notify('/internal/complete',{'event_key':ctx['event_key'],'owner':ctx['owner'],'epoch':ctx['epoch'],'error':_arb_clean(error) if error else None},ctx,'event')

def _arb_job_id(ctx,lane):return str(ctx['event_key'])+'|job|'+str(lane)

def _arb_job_start(ctx,lane):
    return _arb_notify('/internal/job-start',{'event_key':ctx['event_key'],'job_id':_arb_job_id(ctx,lane),'owner':ctx['owner'],'epoch':ctx['epoch'],'lane':lane},ctx,lane)

def _arb_job_complete(ctx,lane,error=None):
    return _arb_notify('/internal/job-complete',{'event_key':ctx['event_key'],'job_id':_arb_job_id(ctx,lane),'owner':ctx['owner'],'epoch':ctx['epoch'],'lane':lane,'error':_arb_clean(error) if error else None},ctx,lane)

# Preserve the complete current Yandex/music validation chain; replace only its final VK sink.
if '_base_music_send' not in globals():
    raise RuntimeError('v20721_base_music_send_missing')
_v20721_direct_vk_send=_base_music_send
_base_music_send=_arb_outbound

# In managed/cutover mode the backend must never create or reclaim a VK callback.
_v20721_register=register
def register():
    if _ARB_MODE in ('managed','cutover'):
        gid=resolve_gid();state['group_id']=gid;state['callback_server_id']=None;state['callback_configured']=False
        print('ARB_CALLBACK_SELF_REGISTRATION_DISABLED',json.dumps({'mode':_ARB_MODE,'owner':_ARB_OWNER,'group_id':gid},ensure_ascii=False),flush=True)
        return
    return _v20721_register()

# Signed dispatch authentication. We restore the request body after verification so the
# unchanged V20.7.20 callback parser remains authoritative for VK event semantics.
_v20721_do_POST=H.do_POST
def _v20721_arb_do_POST(self):
    event=str(self.headers.get('X-ND-Event') or '').strip()
    if not event:
        if _ARB_MODE=='managed':
            self.out(403,'forbidden','text/plain; charset=utf-8');return
        return _v20721_do_POST(self)
    try:
        n=int(self.headers.get('Content-Length','0') or 0)
        raw=self.rfile.read(n)
        self.rfile=_arb_io.BytesIO(raw)
        ts=str(self.headers.get('X-ND-Timestamp') or '')
        owner=str(self.headers.get('X-ND-Owner') or '').upper()
        epoch=int(self.headers.get('X-ND-Epoch') or 0)
        lane=str(self.headers.get('X-ND-Lane') or 'event')
        origin=str(self.headers.get('X-ND-Arbiter-Origin') or '').strip().rstrip('/')
        supplied=str(self.headers.get('X-ND-Signature') or '')
        if owner!=_ARB_OWNER or epoch<1 or not origin.startswith('https://'):
            raise RuntimeError('arbiter_context_invalid')
        if abs(int(time.time()*1000)-int(ts))>180000:
            raise RuntimeError('arbiter_signature_stale')
        body_text=raw.decode('utf-8','replace')
        expected=_arb_sig(ts,owner,epoch,event,lane,body_text)
        if not _arb_consteq(expected,supplied):
            raise RuntimeError('arbiter_signature_invalid')
        ctx={'event_key':event,'owner':owner,'epoch':epoch,'origin':origin,'attempt':str(self.headers.get('X-ND-Attempt') or '')}
        tok=_ARB_CTX.set(ctx);tok_lane=_ARB_LANE.set('event');tok_seq=_ARB_SEND_SEQ.set(0)
        try:return _v20721_do_POST(self)
        finally:
            _ARB_SEND_SEQ.reset(tok_seq);_ARB_LANE.reset(tok_lane);_ARB_CTX.reset(tok)
    except Exception as e:
        state['arbiter_internal_errors']+=1
        print('ARB_DISPATCH_REJECTED',json.dumps({'type':type(e).__name__,'error':_arb_clean(e)},ensure_ascii=False),flush=True)
        self.out(403,'forbidden','text/plain; charset=utf-8')
H.do_POST=_v20721_arb_do_POST

# Propagate the signed fencing context into the unchanged async reply/music threads.
# Background music gets its own job lane so failback waits for it and stale completion is fenced.
if not getattr(threading.Thread,'_nd_arbiter_context_patch',False):
    _arb_thread_start_original=threading.Thread.start
    def _arb_thread_start(self,*a,**kw):
        ctxmeta=_ARB_CTX.get()
        target=getattr(self,'_target',None)
        if not ctxmeta or target is None:
            return _arb_thread_start_original(self,*a,**kw)
        parent_ctx=_arb_cv.copy_context()
        name=str(getattr(target,'__name__','thread') or 'thread')
        if name=='reply':lane='event'
        elif '_music_link_repair_worker' in name:lane='music-link'
        elif '_music_worker' in name:lane='music'
        else:lane='child:'+name[:48]
        targs=getattr(self,'_args',())
        tkwargs=getattr(self,'_kwargs',{})
        def invoke():
            ltok=_ARB_LANE.set(lane);stok=_ARB_SEND_SEQ.set(0);err=None
            try:
                if lane.startswith('music') and not _arb_job_start(ctxmeta,lane):
                    print('ARB_STALE_JOB_SKIPPED',json.dumps({'event':ctxmeta['event_key'],'lane':lane},ensure_ascii=False),flush=True)
                    return None
                return target(*targs,**tkwargs)
            except Exception as e:
                err=e;raise
            finally:
                try:
                    if lane=='event':_arb_complete(ctxmeta,err)
                    elif lane.startswith('music'):_arb_job_complete(ctxmeta,lane,err)
                finally:
                    _ARB_SEND_SEQ.reset(stok);_ARB_LANE.reset(ltok)
        self._target=lambda:parent_ctx.run(invoke)
        self._args=();self._kwargs={}
        return _arb_thread_start_original(self,*a,**kw)
    threading.Thread.start=_arb_thread_start
    threading.Thread._nd_arbiter_context_patch=True

print('ND_V20_7_21_ARBITER_FENCING_READY',json.dumps({'mode':_ARB_MODE,'owner':_ARB_OWNER,'outbound':state['arbiter_outbound_authority']},ensure_ascii=False),flush=True)
'''

anchor="hook='router_patch_code='+repr(router_patch_code)"
if s.count(anchor)!=1: raise RuntimeError('v20721_patch_anchor_missing')
s=s.replace(anchor,'router_patch_code += '+repr(arbiter_patch)+'\n'+anchor,1)
compile(s,'v20721_wrapper.py','exec')
print('ND_V20_7_21_WRAPPER_READY',flush=True)
if os.environ.get('ND_VK_ASSEMBLE_ONLY','').strip()=='1':
    print('ND_V20_7_21_ASSEMBLE_ONLY_PASS',flush=True)
else:
    exec(compile(s,'v20721_wrapper.py','exec'),{'__name__':'__main__','os':os})
