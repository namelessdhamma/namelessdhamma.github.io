import json, tempfile, unittest
import context_memory as m

class ContextMemoryQualification(unittest.TestCase):
    def setUp(self): self.s=m.new_state('452972559')

    def story(self):
        m.add_turn(self.s,'user','вернёмся к рассказу 16',thread_id='story:16')
        m.init_artifact(self.s,'story:16','story16','Исходная фраза.','yandex:story16',['сохранять голос автора'])
        m.set_working_state(self.s,'story:16',objective='редактировать рассказ 16',constraints=['не менять канон напрямую'])

    def test_A_20_turn_story_bounded(self):
        self.story()
        for i in range(24): m.add_turn(self.s,'user',f'правка {i}',thread_id='story:16')
        p=m.build_context_packet(self.s,'нет, предыдущий вариант был лучше; верни последнюю фразу')
        self.assertEqual(p['thread_id'],'story:16'); self.assertLessEqual(len(self.s['threads']['story:16']['recent_turns']),12)
        self.assertLessEqual(p['estimated_tokens'],p['budget']); self.assertGreater(len(self.s['threads']['story:16']['episodes']),0)

    def test_B_story_web_return_no_contamination(self):
        self.story(); m.add_turn(self.s,'user','какая сегодня погода в Мурманске?')
        self.assertEqual(self.s['active_thread_id'],'story:16')  # transient web must not replace active work
        p=m.build_context_packet(self.s,'вернёмся к рассказу 16, на чём остановились?')
        self.assertEqual(p['thread_id'],'story:16'); self.assertNotIn('погода',json.dumps(p,ensure_ascii=False).casefold())

    def test_C_interleaved_threads(self):
        self.story(); m.add_turn(self.s,'user','рассказ 20: посмотрим начало')
        m.add_turn(self.s,'user','исследуй тему память агентов')
        self.assertEqual(m.resolve_thread('вернёмся к рассказу 16',self.s)[0],'story:16')
        self.assertEqual(m.resolve_thread('рассказ 20 продолжим',self.s)[0],'story:20')

    def test_D_exact_versions(self):
        self.story(); v2=m.propose_version(self.s,'story:16','Вариант два.'); v3=m.propose_version(self.s,'story:16','Вариант три.')
        self.assertEqual(m.previous_version(self.s,'story:16')['version_id'],v2)
        m.reject_version(self.s,'story:16',v3); self.assertEqual(self.s['threads']['story:16']['artifact']['current_version'],v2)
        m.accept_version(self.s,'story:16',v2); self.assertEqual(self.s['threads']['story:16']['artifact']['accepted_version'],v2)

    def test_E_fresh_authority_wins(self):
        x=m.merge_fresh_authority('старое','summary:g1','новое','yandex:rev9')
        self.assertEqual(x['value'],'новое'); self.assertEqual(x['superseded_memory']['status'],'STALE_REPAIRED')

    def test_F_long_history_budget(self):
        self.story()
        for i in range(500): m.add_turn(self.s,'user','длинный текст '+str(i)+' '+('x'*300),thread_id='story:16')
        p=m.build_context_packet(self.s,'рассказ 16 продолжим',mode='fast')
        self.assertLessEqual(p['estimated_tokens'],7000); self.assertLessEqual(len(self.s['threads']['story:16']['recent_turns']),12)

    def test_G_ambiguous_minimal_clarification(self):
        self.story(); p=m.build_context_packet(self.s,'сделай как в прошлый раз')
        self.assertTrue(p['needs_clarification']); self.assertEqual(p['thread_id'],'story:16')

    def test_H_restart_provider_portable(self):
        self.story(); m.propose_version(self.s,'story:16','После рестарта.'); raw=json.dumps(self.s,ensure_ascii=False)
        recovered=json.loads(raw); p=m.build_context_packet(recovered,'рассказ 16 продолжим')
        self.assertEqual(p['thread_id'],'story:16'); self.assertTrue(p['provider_agnostic'])
        self.assertEqual(recovered['threads']['story:16']['artifact']['current_version'],'v2')

    def test_I_no_internal_jargon_required(self):
        self.story(); p=m.build_context_packet(self.s,'рассказ 16 продолжим')
        # ContextPacket is internal; father-facing UX can remain ordinary Russian.
        father='Продолжаем рассказ 16. Последний принятый вариант восстановлен.'
        for bad in ('ContextPacket','episodic','semantic_memory','thread_id'): self.assertNotIn(bad,father)
        self.assertFalse(p.get('needs_clarification',False))

    def test_summary_requires_provenance_and_monotonic_generation(self):
        self.story(); self.assertFalse(m.validate_summary(self.s,'story:16','x',[],1))
        self.assertTrue(m.validate_summary(self.s,'story:16','ok',['vk:event:1'],2))
        self.assertFalse(m.validate_summary(self.s,'story:16','stale',['vk:event:0'],1))

if __name__=='__main__': unittest.main()
