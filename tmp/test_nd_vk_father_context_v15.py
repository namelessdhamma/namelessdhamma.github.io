import os, sys, unittest
from unittest import mock

HERE=os.path.dirname(__file__)
if HERE not in sys.path: sys.path.insert(0,HERE)

import nd_vk_father_context_adapter_v15 as adapter
import nd_vk_father_context_harness_v15 as harness


class AdapterTests(unittest.TestCase):
    def test_v7_normalization_filters_non_auth_and_caps(self):
        payload={
            'statehead_status':'ACTIVE','registry_version':'1.8.1',
            'pieces':[
                {'label':'StateHead','authority':'AUTHORITATIVE','text':'A'*30},
                {'label':'Canonical skill','authority':'CANONICAL','text':'B'*30},
                {'label':'Discovery','authority':'NON_AUTH','text':'SECRET_DISCOVERY'},
            ]
        }
        out=adapter._normalize_nd_context(payload,max_chars=40)
        self.assertEqual(out['statehead_status'],'ACTIVE')
        self.assertEqual(out['registry_version'],'1.8.1')
        self.assertNotIn('SECRET_DISCOVERY',out['text'])
        self.assertTrue(all(s['authority'] in ('AUTHORITATIVE','CANONICAL') for s in out['sources']))
        self.assertLessEqual(len(out['text']),40)
        self.assertFalse(out['provenance_rejected'])

    def test_compact_projection_fails_closed_on_mixed_provenance(self):
        payload={
            'text':'AUTHORITATIVE_TEXT SECRET_NON_AUTH_TEXT',
            'sources':[
                {'source_ref':'StateHead','title':'StateHead','authority':'AUTHORITATIVE'},
                {'source_ref':'Discovery','title':'Discovery','authority':'NON_AUTH'},
            ],
            'statehead_status':'ACTIVE','registry_version':'1.8.1'
        }
        out=adapter._normalize_nd_context(payload,max_chars=1000)
        self.assertEqual(out['text'],'')
        self.assertEqual(out['sources'],[])
        self.assertTrue(out['provenance_rejected'])

    def test_compact_projection_accepts_only_governed_sources(self):
        payload={
            'text':'governed text',
            'sources':[
                {'source_ref':'StateHead','title':'StateHead','authority':'authoritative'},
                {'source_ref':'System','title':'System','authority':'canonical'},
            ]
        }
        out=adapter._normalize_nd_context(payload,max_chars=1000)
        self.assertEqual(out['text'],'governed text')
        self.assertEqual([s['authority'] for s in out['sources']],['AUTHORITATIVE','CANONICAL'])
        self.assertFalse(out['provenance_rejected'])

    def test_hydrate_user_isolates_and_orders(self):
        rows=[
            {'sender_vk_id':'101','operation':'append','kind':'conversation_turn','status':'committed','created_at':'2026-09-14T01:00:00Z','content_chunk':'{"role":"user","content":"A1"}'},
            {'sender_vk_id':'202','operation':'append','kind':'conversation_turn','status':'committed','created_at':'2026-09-14T01:01:00Z','content_chunk':'{"role":"user","content":"B1"}'},
            {'sender_vk_id':'101','operation':'append','kind':'conversation_turn','status':'committed','created_at':'2026-09-14T01:02:00Z','content_chunk':'{"role":"assistant","content":"A2"}'},
        ]
        with mock.patch.object(adapter,'read_context_rows',return_value=rows):
            a=adapter.hydrate_user(101)
            b=adapter.hydrate_user(202)
        self.assertEqual([x['content'] for x in a],['A1','A2'])
        self.assertEqual([x['content'] for x in b],['B1'])

    def test_append_uses_post_form_not_query(self):
        seen={}
        def fake(url,**kwargs):
            seen.update({'url':url,**kwargs})
            return {'ok':True,'row':7}
        with mock.patch.object(adapter,'APPEND_URL','https://example.invalid/hook'), mock.patch.object(adapter,'_json_request',side_effect=fake):
            adapter.append_turn(101,'user','private text',event_id='evt-1')
        self.assertEqual(seen['url'],'https://example.invalid/hook')
        self.assertEqual(seen['method'],'POST')
        self.assertIn(b'private+text',seen['data'])
        self.assertNotIn('private text',seen['url'])
        self.assertEqual(seen['headers']['Content-Type'],'application/x-www-form-urlencoded')


class HarnessTests(unittest.TestCase):
    def test_context_envelope_keeps_provenance_and_excludes_non_auth(self):
        hist=[{'role':'user','content':'hello'},{'role':'assistant','content':'world'}]
        nd={
            'text':'governed context',
            'sources':[
                {'source_ref':'StateHead','title':'StateHead','authority':'AUTHORITATIVE'},
                {'source_ref':'Discovery','title':'Discovery','authority':'NON_AUTH'},
                {'source_ref':'System','title':'System','authority':'CANONICAL'},
            ],
            'statehead_status':'ACTIVE','registry_version':'1.8.1'
        }
        with mock.patch.object(harness,'hydrate_user',return_value=hist), mock.patch.object(harness,'read_nd_context',return_value=nd):
            env=harness.build_context_envelope(101)
        self.assertEqual(env['uid'],'101')
        self.assertEqual(len(env['conversation']),2)
        self.assertEqual([x['authority'] for x in env['nd_context']['sources']],['AUTHORITATIVE','CANONICAL'])
        self.assertFalse(env['policy']['non_auth_injection'])
        summary=harness.qualification_summary(env)
        self.assertEqual(summary['statehead_status'],'ACTIVE')
        self.assertEqual(summary['registry_version'],'1.8.1')
        self.assertEqual(summary['nd_authorities'],['AUTHORITATIVE','CANONICAL'])

    def test_envelope_is_bounded(self):
        hist=[{'role':'user','content':'U'*25000},{'role':'assistant','content':'A'*25000}]
        nd={'text':'N'*20000,'sources':[{'source_ref':'x','title':'x','authority':'AUTHORITATIVE'}]}
        with mock.patch.object(harness,'hydrate_user',return_value=hist), mock.patch.object(harness,'read_nd_context',return_value=nd):
            env=harness.build_context_envelope(101)
        self.assertLessEqual(sum(len(x['content']) for x in env['conversation']),harness.MAX_CONVERSATION_CHARS)
        self.assertLessEqual(len(env['nd_context']['text']),harness.MAX_ND_CHARS)

    def test_response_messages_are_provider_ready_bounded_and_provenanced(self):
        hist=[{'role':'user','content':'old question'},{'role':'assistant','content':'old answer'}]
        nd={
            'text':'governed context',
            'sources':[
                {'source_ref':'StateHead','title':'StateHead','authority':'AUTHORITATIVE'},
                {'source_ref':'System','title':'System','authority':'CANONICAL'},
            ],
            'statehead_status':'ACTIVE','registry_version':'1.8.1'
        }
        with mock.patch.object(harness,'hydrate_user',return_value=hist), mock.patch.object(harness,'read_nd_context',return_value=nd):
            messages,receipt=harness.build_response_messages(101,'X'*(harness.MAX_USER_CHARS+500))
        self.assertEqual(messages[0]['role'],'system')
        self.assertEqual(messages[-1]['role'],'user')
        self.assertEqual(len(messages[-1]['content']),harness.MAX_USER_CHARS)
        governed=messages[1]['content']
        self.assertIn('[AUTHORITATIVE]',governed)
        self.assertIn('[CANONICAL]',governed)
        self.assertNotIn('NON_AUTH',governed)
        self.assertEqual(receipt['nd_authorities'],['AUTHORITATIVE','CANONICAL'])
        self.assertFalse(receipt['non_auth_injection'])
        self.assertFalse(receipt['production_mutation'])


if __name__=='__main__': unittest.main()
