import urllib.request

BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c9b857d38df4e196ae3b560347a02d6a2304f9c1/tmp/nd_vk_gateway_v14_web_recovery.py'
src=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')

needle="exec(compile(src,'nd_vk_gateway_v14_web_recovery.py','exec'))"
if needle not in src:
    raise RuntimeError('V14 exec marker missing')

inject=r'''
# V15 authenticated direct agent bridge. Fixed operations only; no shell/arbitrary code execution.
agent_old="""    def do_GET(self):
        p=self.path.split('?',1)[0]
        if p=='/health':self.out(200,state);return
        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL});return
        self.out(404,{'error':'not_found'})
"""
agent_new="""    def do_GET(self):
        import urllib.parse as _ap
        parsed=_ap.urlsplit(self.path); p=parsed.path; aq=_ap.parse_qs(parsed.query)
        ctl=os.environ.get('ND_ROUTER_CONTROL_TOKEN','')
        if p.startswith('/agent/'):
            key=(aq.get('k') or [''])[0]
            if not ctl or key!=ctl:self.out(403,{'ok':False,'error':'forbidden'});return
            op=p[len('/agent/'):]
            try:
                if op=='status':
                    self.out(200,{'ok':True,'state':state,'mode':mode_by_uid.get(-910001,'auto')});return
                if op=='reset':
                    history_by_uid.pop(-910001,None);mode_by_uid.pop(-910001,None);self.out(200,{'ok':True,'reset':True});return
                if op=='probe':
                    checks={}
                    try:checks['groq']=groq_chat([{'role':'user','content':'Reply exactly OK.'}],GROQ_MODEL,'low',128)
                    except Exception as e:checks['groq_error']=cleanerr(e)
                    try:checks['openrouter']=openrouter_chat([{'role':'user','content':'Reply exactly OK.'}],'low',128,0.0)
                    except Exception as e:checks['openrouter_error']=cleanerr(e)
                    self.out(200,{'ok':bool(checks.get('groq') or checks.get('openrouter')),'checks':checks,'state':state});return
                if op=='web':
                    qq=(aq.get('q') or [''])[0][:4000]
                    evidence=independent_web_research(qq)
                    self.out(200,{'ok':True,'evidence':evidence[:30000]});return
                if op=='chat':
                    qq=(aq.get('q') or [''])[0][:12000]
                    mode=(aq.get('mode') or ['auto'])[0]
                    if mode not in ('auto','fast','write','research','deep'):raise RuntimeError('invalid mode')
                    mode_by_uid[-910001]=mode
                    ans=routed_response(-910001,qq or 'Проверка связи.')
                    self.out(200,{'ok':True,'mode':mode,'answer':ans,'state':state});return
                self.out(404,{'ok':False,'error':'unknown_agent_op'});return
            except Exception as e:
                state['last_error']=cleanerr(e);self.out(500,{'ok':False,'error':cleanerr(e),'state':state});return
        if p=='/health':self.out(200,state);return
        if p=='/':self.out(200,{'service':'ND Free Adaptive VK Router','health':'/health','groq':bool(GROQ_API_KEY),'openrouter':bool(OPENROUTER_API_KEY),'openrouter_model':OPENROUTER_MODEL,'agent_bridge':True});return
        self.out(404,{'error':'not_found'})
"""
if agent_old not in src: raise RuntimeError('V9 GET block missing for V15')
src=src.replace(agent_old,agent_new,1)
src=src.replace('ND_VK_GATEWAY_V14_WEB_RECOVERY_START','ND_VK_GATEWAY_V15_AGENT_BRIDGE_START',1)
exec(compile(src,'nd_vk_gateway_v15_agent_bridge.py','exec'))
'''
src=src.replace(needle,inject,1)
exec(compile(src,'nd_vk_gateway_v15_agent_bridge_loader.py','exec'))
