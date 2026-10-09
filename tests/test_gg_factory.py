import json, tempfile, unittest, pathlib, sys, numpy as np, soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tools.gg_factory import get_phrases, acoustic_report, check_declared_lineage, collect, audition, guarded_mix, savejson, sha256

class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.r=pathlib.Path(self.tmp.name)
        score={'title':'X','bpm':120,'ticks_per_beat':480,'phrases':[
            {'id':'v1l1','bar':0,'offset':0,'words':[{'text':'мы','pitches':[60],'durations':[480],'rest':0}]}]}
        savejson(self.r/'score.json',score)
        y=np.zeros(48000,dtype=np.float32);y[3000:13000]=np.sin(np.arange(10000)*2*np.pi/200)*.2
        for name in ('guide.wav','selected.wav','vfs.wav','instrumental.wav'):
            sf.write(self.r/name,y,48000)
        for name in ('guide','rvc_selection','post_vfs_asr','audio','qualification'):
            savejson(self.r/(name+'.json'),{'status':'PASS','blockers':[]})
        self.recipe={'song':'X','score':'score.json','stems':{'guide':'guide.wav','selected_vocal':'selected.wav',
                      'vfs_vocal':'vfs.wav','instrumental':'instrumental.wav'},
                      'gate_reports':{x:x+'.json' for x in ('guide','rvc_selection','post_vfs_asr','audio','qualification')},
                      'lineage':{'source_type':'raw_singing','rvc_passes':1,'contains_baked_vocal':False,
                                 'vocals_on_instrumental':False,'sample_origin':'official_language_guide'}}
        savejson(self.r/'recipe.json',self.recipe)
    def test_phrase_boundaries(self):
        ph=get_phrases(json.loads((self.r/'score.json').read_text()))[0]
        self.assertEqual(ph['id'],'v1l1');self.assertEqual(ph['end'],.5)
    def test_acoustic_real_samples(self):
        q=acoustic_report(self.r/'guide.wav');self.assertEqual(q['channels'],1)
        self.assertEqual(q['sample_rate'],48000);self.assertFalse(q['pcm_clipping_risk'])
    def test_five_gates_pass_but_no_human(self):
        q=collect(self.r/'recipe.json');self.assertEqual(q['machine_gate'],'PASS')
        self.assertEqual(q['artistic_status'].startswith('UNREVIEWED'),True)
        with self.assertRaises(RuntimeError):guarded_mix(self.r/'recipe.json',self.r/'notwritten.mp3',self.r/'missing.json')
    def test_explicit_review_is_hash_bound(self):
        savejson(self.r/'review.json',{'song':'X','reviewer':'human','verdict':'ACCEPT','recipe_sha256':'wrong'})
        with self.assertRaisesRegex(RuntimeError,'revision'):guarded_mix(self.r/'recipe.json',self.r/'out.mp3',self.r/'review.json')
    def test_synthetic_mixing_with_explicit_review_and_evidence(self):
        machine=collect(self.r/'recipe.json')
        vocal=self.r/'vfs.wav'; music=self.r/'instrumental.wav'
        savejson(self.r/'review.json',{
            'song':'X','reviewer':'TEST_FIXTURE_NOT_A_USER','verdict':'ACCEPT',
            'recipe_sha256':sha256(self.r/'recipe.json'),
            'evidence_sha256':machine['evidence_sha256'],
            'vocal_sha256':sha256(vocal),'instrumental_sha256':sha256(music)})
        # Proves runnable assembly but this fixture is not a real GG artistic review.
        rendered=guarded_mix(self.r/'recipe.json',self.r/'test_only.mp3',self.r/'review.json')
        self.assertGreater(rendered.stat().st_size,1000)
        self.assertTrue(rendered.with_suffix('.manifest.json').exists())

    def test_reject_one_lexical_failure(self):
        savejson(self.r/'post_vfs_asr.json',{'status':'REJECT','blockers':[{'id':'v1l1','cer':.5}]})
        r=collect(self.r/'recipe.json');self.assertEqual(r['machine_gate'],'REJECT')
        self.assertTrue(any('post_vfs_asr' in x for x in r['qa_blockers']))
    def test_reject_double_rvc_and_baked_master(self):
        self.recipe['lineage']['rvc_passes']=2;self.recipe['lineage']['contains_baked_vocal']=True
        savejson(self.r/'recipe.json',self.recipe)
        self.assertEqual(collect(self.r/'recipe.json')['machine_gate'],'REJECT')
    def test_context_audition_writes_once(self):
        p=audition(self.r/'recipe.json',self.r/'listen.wav','v1l1')
        z=acoustic_report(p);self.assertGreater(z['duration_s'],1.0)
        self.assertTrue(p.with_suffix('.json').exists())
    def test_reject_undocumented_guide_clipping(self):
        y=np.ones(48000,dtype=np.float32)
        sf.write(self.r/'guide.wav',y,48000)
        self.assertTrue(collect(self.r/'recipe.json')['qa_blockers'])

if __name__=='__main__':unittest.main()