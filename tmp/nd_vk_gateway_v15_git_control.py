import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

needle="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if needle not in src:
    raise RuntimeError('V14 exec marker missing')

inject=r'''
control_code=r"""
AGENT_CONTROL_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/qualify/vk-free-minimum-ai/tmp/vk_agent_control.json'
AGENT_UID=-910001
state['agent_control']={'id':None,'op':None,'ok':None,'result':None,'error':None,'at':None}

def agent_control_loop():
    import datetime as _dt
    last_id=None
    while True:
        try:
            req=Request(AGENT_CONTROL_URL+'?t='+str(int(time.time())),headers={'User-Agent':'ND-VK-Agent-Control/1.0','Cache-Control':'no-cache'})
            with urlopen(req,timeout=15) as r:
                cmd=json.loads(r.read(200000).decode('utf-8','replace'))
            cid=str(cmd.get('id') or '')
            if cid and cid!=last_id:
                op=str(cmd.get('op') or 'status'); mode=str(cmd.get('mode') or 'auto'); prompt=str(cmd.get('prompt') or '')[:12000]
                rec={'id':cid,'op':op,'ok':False,'result':None,'error':None,'at':_dt.datetime.now(_dt.timezone.utc).isoformat()}
                try:
                    if op=='status':
                        rec['result']={'phase':state.get('phase'),'last_route':state.get('last_route'),'last_provider':state.get('last_provider'),'last_error':state.get('last_error')}
                    elif op=='reset':
                        history_by_uid.pop(AGENT_UID,None);mode_by_uid.pop(AGENT_UID,None);rec['result']='reset'
                    elif op=='probe':
                        checks={}
                        try:checks['groq']=groq_chat([{'role':'user','content':'Reply exactly OK.'}],GROQ_MODEL,'low',128)
                        except Exception as e:checks['groq_error']=cleanerr(e)
                        try:checks['openrouter']=openrouter_chat([{'role':'user','content':'Reply exactly OK.'}],'low',128,0.0)
                        except Exception as e:checks['openrouter_error']=cleanerr(e)
                        rec['result']=checks
                    elif op=='web':
                        rec['result']=independent_web_research(prompt)[:30000]
                    elif op=='chat':
                        if mode not in ('auto','fast','write','research','deep'):raise RuntimeError('invalid mode')
                        mode_by_uid[AGENT_UID]=mode
                        rec['result']=routed_response(AGENT_UID,prompt or 'Проверка связи.')[:30000]
                    else:
                        raise RuntimeError('unknown op')
                    rec['ok']=True
                except Exception as e:
                    rec['error']=cleanerr(e)
                state['agent_control']=rec
                print('AGENT_CONTROL_RESULT',json.dumps({'id':cid,'op':op,'ok':rec['ok'],'error':rec['error'],'result_chars':len(str(rec['result'] or ''))},ensure_ascii=False),flush=True)
                last_id=cid
        except Exception as e:
            state['agent_control_poll_error']=cleanerr(e)
        time.sleep(20)
"""
if 'class H(BaseHTTPRequestHandler):' not in src: raise RuntimeError('class marker missing')
src=src.replace('class H(BaseHTTPRequestHandler):',control_code+'\nclass H(BaseHTTPRequestHandler):',1)
start_old="threading.Thread(target=startup,daemon=True).start()\nThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
start_new="threading.Thread(target=startup,daemon=True).start()\nthreading.Thread(target=agent_control_loop,daemon=True).start()\nThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
if start_old not in src: raise RuntimeError('startup marker missing')
src=src.replace(start_old,start_new,1)
src=src.replace('ND_VK_GATEWAY_V14_WEB_RECOVERY_START','ND_VK_GATEWAY_V15_GIT_CONTROL_START',1)
exec(compile(src,'nd_vk_gateway_v15_git_control.py','exec'))
'''
src=src.replace(needle,inject,1)
exec(compile(src,'nd_vk_gateway_v15_git_control_loader.py','exec'))
