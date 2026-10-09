import copy,hashlib,json,pathlib,sys,tempfile,unittest
import numpy as np
import soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import gg_human_vocal_mode as m

class TrueVisualHumanVocalMode(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        (self.root/'score.json').write_text('{"id":"s1"}')
        sf.write(self.root/'guide.wav',np.sin(np.linspace(0,50,44100)),44100)
        sf.write(self.root/'candidate.wav',np.sin(np.linspace(0,50,44100)),44100)
        sf.write(self.root/'music.wav',np.ones(44100)*.01,44100)
        sha=m.digest
        self.base={'project':'sample','score':'score.json','raw_voice':'guide.wav','instrumental':'music.wav',
          'target_text':'Мы встретились с тобой','voice_identity':'awata-original','input_voice_rvc_passes':0,
          'score_sha256_expected':sha(self.root/'score.json'),
          'original_asr':{'CER':0.0,'audio_sha256':sha(self.root/'guide.wav'),'text':'Мы встретились с тобой',
                          'engine':'whisper-small','recognized':'Мы встретились с тобой'},
          'candidates':[{'id':'A','CER':0.0,'input_sha256':sha(self.root/'guide.wav'),
                         'voice_identity':'awata-original','sha256':sha(self.root/'candidate.wav'),'audio':'candidate.wav',
                         'rvc_passes':1}],'max_regression_CER':.025}
    def eval(self,edit=None):
        p=copy.deepcopy(self.base)
        if edit: edit(p)
        return m.evaluate(p,self.root)
    def test_lexical_regression_rejected(self):
        self.assertEqual(self.eval(lambda p:p['candidates'][0].update(CER=.12))['status'],'REJECT_ALL')
    def test_accept_only_for_artistic_review(self):
        d=self.eval();self.assertEqual(d['status'],'READY_FOR_ARTISTIC_REVIEW');self.assertFalse(d['released'])
    def test_hash_changed_candidate_refused(self):
        self.assertIn('CANDIDATE_AUDIO_MISSING_OR_HASH_MISMATCH',self.eval(lambda p:p['candidates'][0].update(sha256='0'*64))['issues'])
    def test_first_pass_stale_source_refused(self):
        self.assertIn('CANDIDATE_SOURCE_REVISION_MISMATCH',self.eval(lambda p:p['candidates'][0].update(input_sha256='x'))['issues'])
    def test_double_rvc_rejected(self):
        self.assertEqual(self.eval(lambda p:p['candidates'][0].update(rvc_passes=2))['status'],'REJECT_ALL')
    def test_audio_overlap_rejected(self):
        self.assertEqual(self.eval(lambda p:p['candidates'][0].update(has_overlap=True))['status'],'REJECT_ALL')
    def test_score_mutation_rejected(self):
        self.assertEqual(self.eval(lambda p:p.update(score_sha256_expected='f'*64))['next'],'REBASE_SCORE_AND_RESET_STALE_GATES')
    def test_baked_music_rejected(self):
        self.assertEqual(self.eval(lambda p:p.update(instrumental_contains_vocals=True))['next'],'RECOVER_CLEAN_INSTRUMENTAL')
    def test_existing_processed_source_refused(self):
        self.assertEqual(self.eval(lambda p:p.update(input_voice_rvc_passes=1))['next'],'RECOVER_UNCONVERTED_VOCAL')
    def test_no_asr_routes_to_asr(self):
        self.assertEqual(self.eval(lambda p:p.pop('original_asr'))['next'],'ASR_RAW_GUIDE')
    def test_wrong_asr_source_rejected(self):
        self.assertEqual(self.eval(lambda p:p['original_asr'].update(audio_sha256='bad'))['next'],'ASR_RAW_GUIDE')
    def test_bad_guide_no_downstream_repair(self):
        self.assertEqual(self.eval(lambda p:p['original_asr'].update(CER=.4))['next'],'FIX_RUSSIAN_PHONEMES_AND_SCORE_UPSTREAM')
    def test_missing_qualified_reference_selects_native_not_SoulX(self):
        def edit(p):p['candidates'][0]['CER']=.3;p['qualified_expressive_reference_available']=False
        self.assertEqual(self.eval(edit)['next'],'RENDER_NEW_EXPRESSIVE_NATIVE_PHRASE')
    def test_human_review_unverified_cannot_mix(self):
        def edit(p):p['qualified_review']={'candidate_id':'A','candidate_sha256':p['candidates'][0]['sha256'],
               'artistic_verdict':'ACCEPT','vocal_naturalness':'PASS','russian_diction':'PASS'}
        self.assertEqual(self.eval(edit)['next'],'TRUE_VISUAL_QUALIFY_ACTUAL_PERFORMANCE')
    def test_artistic_pass_but_no_mixer_qa_stops(self):
        def edit(p):p['qualified_review']={'candidate_id':'A','candidate_sha256':p['candidates'][0]['sha256'],
               'artistic_verdict':'ACCEPT','vocal_naturalness':'PASS','russian_diction':'PASS','actual_whisper':'NOT_REQUIRED'}
        self.assertEqual(self.eval(edit)['next'],'RUN_FULL_MIX_AUDIO_QA')
    def test_mix_readiness_never_says_released(self):
        def edit(p):p['qualified_review']={'candidate_id':'A','candidate_sha256':p['candidates'][0]['sha256'],
               'artistic_verdict':'ACCEPT','vocal_naturalness':'PASS','russian_diction':'PASS','actual_whisper':'NOT_REQUIRED'};p['audio_qa_gate']='PASS'
        x=self.eval(edit);self.assertEqual(x['status'],'READY_TO_MIX_REVIEW');self.assertFalse(x['released'])
    def test_effect_log_real_execution_then_reuse(self):
        source=self.root/'guide.wav';out=self.root/'done.txt';ledger=self.root/'state.json'
        step={'worker':'gg_factory','kind':'local_process','inputs':[str(source)],
              'input_sha256':{str(source):m.digest(source)},'outputs':[str(out)],
              'argv':[sys.executable,'-c',f"open({str(out)!r},'w').write('done')"],
              'tool_revision':'pinned-demo-1','timeout_s':30}
        spec=self.root/'step.json';m.jwrite(spec,step)
        self.assertEqual(m.execute_local_step(spec,ledger)['status'],'DRY_RUN')
        self.assertEqual(m.execute_local_step(spec,ledger,permit_effect=True)['status'],'SUCCEEDED')
        self.assertEqual(m.execute_local_step(spec,ledger,permit_effect=True)['status'],'REUSED')
        out.write_text('tampered')
        with self.assertRaisesRegex(RuntimeError,'RECONCILIATION_REQUIRED'):
            m.execute_local_step(spec,ledger,permit_effect=True)
    def test_worker_unknown_refused(self):
        p=self.root/'x.json';m.jwrite(p,{'worker':'third-party-unknown','kind':'local_process'})
        with self.assertRaises(ValueError):m.execute_local_step(p,self.root/'ledger.json')
    def test_timeout_more_than_3min_forbidden(self):
        source=self.root/'guide.wav';out=self.root/'done';p=self.root/'x.json'
        m.jwrite(p,{'worker':'asr','kind':'local_process','inputs':[str(source)],'outputs':[str(out)],
           'input_sha256':{str(source):m.digest(source)},'argv':['python','-c','pass'],
           'timeout_s':300,'tool_revision':'x'})
        with self.assertRaisesRegex(ValueError,'timeout'):
            m.execute_local_step(p,self.root/'l.json',permit_effect=True)

if __name__=='__main__':unittest.main()