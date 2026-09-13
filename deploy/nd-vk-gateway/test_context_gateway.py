import hashlib, json, unittest
import context_gateway as cg


class Broker:
    def __init__(self):
        self.items={}; self.idem={}; self.calls=[]
    def _aid(self,key): return 'ND-NOTE-'+hashlib.sha256(('create|shared_notes|'+key).encode()).hexdigest()[:20]
    def invoke(self,tool,q='',args=None):
        a=args or {}; self.calls.append((tool,dict(a)))
        if tool=='sandbox_list':
            return {'ok':True,'items':[{'artifact_id':k,'title':'VK Conversation Context State','version':v['version']} for k,v in self.items.items()]}
        if tool=='sandbox_shared_note':
            key=a['idempotency_key']; aid=self.idem.get(key) or self._aid(key); self.idem[key]=aid
            if aid not in self.items:self.items[aid]={'content':a['content'],'version':1}
            return {'ok':True,'artifact_id':aid,'version':self.items[aid]['version'],'read_back_verified':True}
        if tool=='sandbox_update':
            aid=a['artifact_id']; self.items[aid]={'content':a['content'],'version':self.items[aid]['version']+1}
            return {'ok':True,'artifact_id':aid,'version':self.items[aid]['version'],'read_back_verified':True}
        if tool=='sandbox_read':
            x=self.items[a['artifact_id']]; return {'ok':True,'artifact_id':a['artifact_id'],'version':x['version'],'content':x['content']}
        raise AssertionError(tool)


class ContextGatewayQualification(unittest.TestCase):
    def setUp(self):
        cg.reset_process_cache_for_tests(); self.b=Broker(); self.captured=[]
    def responder(self,uid,text,history):
        self.captured.append((uid,text,json.loads(json.dumps(history,ensure_ascii=False))))
        return 'Ответ '+str(len(self.captured))

    def test_A_long_story_uses_bounded_packet_not_growing_history(self):
        modes={452972559:'auto'}; hist={}
        for i in range(24):
            cg.dispatch(452972559,f'рассказ 16: правка {i}',f'e{i}',self.responder,hist,self.b.invoke,modes)
        self.assertEqual(hist,{})
        packet=json.loads(self.captured[-1][2][0]['content'].split('\n',1)[1])
        self.assertEqual(packet['thread_id'],'story:16')
        self.assertLessEqual(packet['estimated_tokens'],packet['budget'])
        self.assertLessEqual(len(packet['layers'].get('recent_verbatim',[])),12)

    def test_B_web_side_trip_does_not_pollute_story_return(self):
        modes={452972559:'auto'}; hist={}
        cg.dispatch(452972559,'рассказ 16: поправь начало','s1',self.responder,hist,self.b.invoke,modes)
        cg.dispatch(452972559,'какая сегодня погода в Мурманске?','w1',self.responder,hist,self.b.invoke,modes)
        cg.dispatch(452972559,'вернёмся к рассказу 16, на чём остановились?','s2',self.responder,hist,self.b.invoke,modes)
        blob=json.dumps(self.captured[-1][2],ensure_ascii=False).casefold()
        self.assertNotIn('погода',blob); self.assertIn('рассказ 16',blob)

    def test_G_ambiguous_request_returns_minimal_clarification_without_model_call(self):
        modes={452972559:'auto'}; hist={}
        cg.dispatch(452972559,'рассказ 16: работаем','s1',self.responder,hist,self.b.invoke,modes)
        n=len(self.captured)
        out=cg.dispatch(452972559,'сделай как в прошлый раз','a1',self.responder,hist,self.b.invoke,modes)
        self.assertEqual(len(self.captured),n)
        self.assertIn('уточните',out.casefold())

    def test_H_restart_discovers_same_durable_artifact(self):
        modes={452972559:'auto'}; hist={}
        cg.dispatch(452972559,'рассказ 16: первая правка','s1',self.responder,hist,self.b.invoke,modes)
        aid=next(iter(self.b.items))
        cg.reset_process_cache_for_tests()
        cg.dispatch(452972559,'вернёмся к рассказу 16, на чём остановились?','s2',self.responder,hist,self.b.invoke,modes)
        self.assertEqual(len(self.b.items),1)
        reads=[a for t,a in self.b.calls if t=='sandbox_read' and a.get('artifact_id')==aid]
        self.assertGreaterEqual(len(reads),2)
        blob=json.dumps(self.captured[-1][2],ensure_ascii=False)
        self.assertIn('первая правка',blob)

    def test_broker_boundary_is_server_fixed_and_no_parent_override(self):
        modes={452972559:'auto'}; hist={}
        cg.dispatch(452972559,'обычный вопрос','g1',self.responder,hist,self.b.invoke,modes)
        create=next(a for t,a in self.b.calls if t=='sandbox_shared_note')
        self.assertNotIn('folder_id',create); self.assertNotIn('parent_id',create)


if __name__=='__main__': unittest.main()
