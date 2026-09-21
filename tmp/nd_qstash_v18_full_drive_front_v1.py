import json, os, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

PORT=int(os.environ.get('PORT','3000'))
VK_PORT=int(os.environ.get('ND_QSTASH_V18_INNER_PORT','3001'))
DRIVE_PORT=int(os.environ.get('ND_DRIVE_BRIDGE_PORT','3002'))
VK_URL='http://127.0.0.1:%d' % VK_PORT
DRIVE_URL='http://127.0.0.1:%d' % DRIVE_PORT
DRIVE_SOURCE=os.environ.get('ND_DRIVE_BRIDGE_SOURCE','').strip()
BRIDGE_TOKEN=os.environ.get('ND_DRIVE_BRIDGE_TOKEN','').strip()
V18_LOADER=os.environ.get('ND_VK_V18_FIXED_LOADER','')

if not V18_LOADER:
    raise RuntimeError('ND_VK_V18_FIXED_LOADER missing')
if not DRIVE_SOURCE:
    raise RuntimeError('ND_DRIVE_BRIDGE_SOURCE missing')
if not BRIDGE_TOKEN:
    raise RuntimeError('ND_DRIVE_BRIDGE_TOKEN missing')

vk_env=dict(os.environ)
vk_env['PORT']=str(VK_PORT)
vk_child=subprocess.Popen([sys.executable,'-u','-c',V18_LOADER],env=vk_env)
print('ND_QSTASH_V18_CHILD_LAUNCHED '+json.dumps({'port':VK_PORT}),flush=True)

subprocess.run(['apk','add','--no-cache','nodejs'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
urllib.request.urlretrieve(DRIVE_SOURCE,'/tmp/nd-drive-full.mjs')
drive_env=dict(os.environ)
drive_env['PORT']=str(DRIVE_PORT)
drive_child=subprocess.Popen(['node','/tmp/nd-drive-full.mjs'],env=drive_env)
print('ND_QSTASH_FULL_DRIVE_CHILD_LAUNCHED '+json.dumps({'port':DRIVE_PORT}),flush=True)

def cleanerr(e):
    s=str(e)
    if BRIDGE_TOKEN:
        s=s.replace(BRIDGE_TOKEN,'[REDACTED]')
    return s[:1000]

def invoke(tool,args):
    raw=json.dumps({'tool':tool,'args':args},ensure_ascii=False).encode()
    req=urllib.request.Request(
        DRIVE_URL+'/drive/invoke',
        data=raw,method='POST',
        headers={'Content-Type':'application/json','X-ND-Bridge-Key':BRIDGE_TOKEN,'User-Agent':'ND-Qstash-Full-Drive-Front/1.0'}
    )
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            obj=json.loads(r.read().decode('utf-8','replace') or '{}')
    except HTTPError as e:
        body=e.read().decode('utf-8','replace')
        raise RuntimeError('HTTP %s: %s'%(e.code,body[:900]))
    if not obj.get('ok'):
        raise RuntimeError('drive invoke failed: '+json.dumps(obj)[:900])
    return obj.get('result') or {}

def full_qualify():
    time.sleep(8)
    root='0AOdPxVrJUuLLUk9PVA'
    created=[]
    rec={'schema':'nd-qstash-full-drive-qualification-v1','ok':False}
    try:
        stamp=str(int(time.time()))
        folder=invoke('drive_create_folder',{'name':'ND QSTASH FULL RW QUAL '+stamp,'parent_id':root})
        fid=folder.get('id'); created.append(fid)
        sub=invoke('drive_create_folder',{'name':'MOVE TARGET','parent_id':fid})
        sid=sub.get('id'); created.append(sid)
        rec['folder_create']=bool(fid and sid)

        raw=invoke('drive_create_raw_file',{'name':'probe.json','mime_type':'application/json','parent_id':fid,'content_text':'{"v":1}'})
        rid=raw.get('id'); created.append(rid)
        rf=invoke('fetch',{'id':rid})
        rec['raw_create_read']='{"v":1}' in str((((rf or {}).get('content') or {}).get('content') or ''))

        rm=invoke('drive_get_metadata',{'file_id':rid})
        rv=str((rm or {}).get('version') or (rm or {}).get('drive_version') or '')
        rep=invoke('drive_replace_content',{'file_id':rid,'content_text':'{"v":2,"ok":true}','mime_type':'application/json','expected_drive_version':rv})
        rec['raw_replace']=bool((rep or {}).get('after_drive_version'))

        rm2=invoke('drive_get_metadata',{'file_id':rid})
        rv2=str((rm2 or {}).get('version') or (rm2 or {}).get('drive_version') or '')
        mv=invoke('drive_update_metadata',{'file_id':rid,'name':'probe-renamed.json','add_parent_id':sid,'remove_parent_id':fid,'expected_drive_version':rv2})
        mf=(mv or {}).get('file') or {}
        rec['rename_move']=mf.get('name')=='probe-renamed.json' and sid in (mf.get('parents') or [])

        doc=invoke('drive_create_native_file',{'name':'probe-doc','kind':'document','parent_id':fid})
        did=doc.get('id'); created.append(did)
        d0=invoke('docs_read',{'document_id':did})
        d1=invoke('docs_batch_update',{'document_id':did,'expected_revision_id':d0.get('revision_id'),'requests':[{'insertText':{'endOfSegmentLocation':{},'text':'FULL DOC WRITE'}}]})
        d2=invoke('docs_read',{'document_id':did})
        rec['docs_batch']='FULL DOC WRITE' in str(d2.get('text') or '') and bool(d1.get('after_revision_id'))

        sh=invoke('drive_create_native_file',{'name':'probe-sheet','kind':'spreadsheet','parent_id':fid})
        shid=sh.get('id'); created.append(shid)
        invoke('sheets_update_values',{'spreadsheet_id':shid,'range':'A1:B2','values':[['a','b'],['1','2']]})
        sr=invoke('sheets_get_values',{'spreadsheet_id':shid,'range':'A1:B2'})
        rec['sheets_values']=(sr or {}).get('values')==[['a','b'],['1','2']]
        invoke('sheets_batch_update',{'spreadsheet_id':shid,'requests':[{'addSheet':{'properties':{'title':'Extra'}}}]})
        sg=invoke('sheets_get',{'spreadsheet_id':shid})
        rec['sheets_batch']='Extra' in [((x.get('properties') or {}).get('title')) for x in ((sg or {}).get('sheets') or [])]

        pr=invoke('drive_create_native_file',{'name':'probe-slides','kind':'presentation','parent_id':fid})
        pid=pr.get('id'); created.append(pid)
        pg0=invoke('slides_get',{'presentation_id':pid}); n0=len((pg0 or {}).get('slides') or [])
        invoke('slides_batch_update',{'presentation_id':pid,'requests':[{'createSlide':{}}]})
        pg1=invoke('slides_get',{'presentation_id':pid})
        rec['slides_batch']=len((pg1 or {}).get('slides') or [])==n0+1

        ch=invoke('drive_list_children',{'folder_id':fid,'top_n':50})
        rec['list_children']=any(x.get('id')==did for x in ((ch or {}).get('results') or []))

        dm=invoke('drive_get_metadata',{'file_id':did})
        dv=str((dm or {}).get('version') or (dm or {}).get('drive_version') or '')
        tr=invoke('drive_update_metadata',{'file_id':did,'trashed':True,'expected_drive_version':dv})
        rec['trash']=bool(((tr or {}).get('file') or {}).get('trashed'))
        dm2=invoke('drive_get_metadata',{'file_id':did})
        dv2=str((dm2 or {}).get('version') or (dm2 or {}).get('drive_version') or '')
        ur=invoke('drive_update_metadata',{'file_id':did,'trashed':False,'expected_drive_version':dv2})
        rec['untrash']=not bool(((ur or {}).get('file') or {}).get('trashed'))

        stale=False
        try:
            invoke('drive_replace_content',{'file_id':rid,'content_text':'SHOULD_NOT_WRITE','mime_type':'application/json','expected_drive_version':rv})
        except Exception as e:
            stale=('DRIVE_VERSION_MISMATCH' in str(e) or '409' in str(e))
        rec['stale_drive_version']=stale
        required=['folder_create','raw_create_read','raw_replace','rename_move','docs_batch','sheets_values','sheets_batch','slides_batch','list_children','trash','untrash','stale_drive_version']
        rec['functional_pass']=all(bool(rec.get(k)) for k in required)
    except Exception as e:
        rec['error']=cleanerr(e)
    finally:
        cleanup=[]
        for file_id in reversed(created):
            if not file_id: continue
            try:
                invoke('drive_delete_file',{'file_id':file_id})
                cleanup.append({'id':file_id,'deleted':True})
            except Exception as e:
                cleanup.append({'id':file_id,'deleted':False,'error':cleanerr(e)})
        rec['cleanup_pass']=bool(cleanup) and all(x.get('deleted') for x in cleanup)
        rec['ok']=bool(rec.get('functional_pass') and rec.get('cleanup_pass'))
        rec['created_count']=len(created)
        print('ND_QSTASH_FULL_DRIVE_QUALIFICATION '+json.dumps(rec,ensure_ascii=False),flush=True)

threading.Thread(target=full_qualify,daemon=True).start()

def proxy(req,res,target):
    n=int(req.headers.get('Content-Length','0') or 0)
    body=req.rfile.read(n) if n else None
    headers={}
    for k,v in req.headers.items():
        if k.lower() in ('host','connection','content-length','transfer-encoding'): continue
        headers[k]=v
    q=urllib.request.Request(target+(req.path or '/'),data=body,headers=headers,method=req.command)
    try:
        with urllib.request.urlopen(q,timeout=180) as r:
            raw=r.read()
            res.send_response(r.status)
            for k,v in r.headers.items():
                if k.lower() in ('connection','transfer-encoding','content-length'): continue
                res.send_header(k,v)
            res.send_header('Content-Length',str(len(raw))); res.end_headers(); res.wfile.write(raw)
    except HTTPError as e:
        raw=e.read()
        res.send_response(e.code)
        for k,v in e.headers.items():
            if k.lower() in ('connection','transfer-encoding','content-length'): continue
            res.send_header(k,v)
        res.send_header('Content-Length',str(len(raw))); res.end_headers(); res.wfile.write(raw)
    except Exception as e:
        raw=json.dumps({'ok':False,'error':'proxy_unavailable','detail':cleanerr(e)}).encode()
        res.send_response(503); res.send_header('Content-Type','application/json'); res.send_header('Content-Length',str(len(raw))); res.end_headers(); res.wfile.write(raw)

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path.split('?',1)[0].startswith('/drive/'): return proxy(self,self,DRIVE_URL)
        return proxy(self,self,VK_URL)
    def do_POST(self):
        if self.path.split('?',1)[0].startswith('/drive/'): return proxy(self,self,DRIVE_URL)
        return proxy(self,self,VK_URL)

print('ND_QSTASH_V18_FULL_DRIVE_FRONT_READY '+json.dumps({'port':PORT,'vk_port':VK_PORT,'drive_port':DRIVE_PORT}),flush=True)
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
