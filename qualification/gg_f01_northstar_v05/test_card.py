import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from vocal_card import decide
class Map(unittest.TestCase):
 def event(self,**kw):
  e=dict(selected_identity='GG-VFS-F01',score_and_lyrics_verified=True,single_singer_isolated_vocal=True,
   source_lexical_pass=True,source_sings_melody=True,expressive_source_qualified=True,
   wants_rvc=False,post_rvc_passes=0,needs_actual_whisper=False,verified_actual_whisper=False,
   modified_candidate_lexical_pass=True,passed_perceptual_comparison=True,
   has_independent_backing=True,human_accepted=False)
  e.update(kw);return e
 def test_identity(self):self.assertEqual('REJECT',decide(self.event(selected_identity='a_different_voice'))['status'])
 def test_lyrics_gate(self):self.assertIn('RU_PHONEMES',decide(self.event(score_and_lyrics_verified=False))['next'])
 def test_single_voice(self):self.assertIn('CONTINUOUS',decide(self.event(single_singer_isolated_vocal=False))['next'])
 def test_missing_ne(self):self.assertIn('UPSTREAM',decide(self.event(source_lexical_pass=False))['next'])
 def test_singing(self):self.assertIn('NOT_TTS',decide(self.event(source_sings_melody=False))['next'])
 def test_expressive(self):self.assertIn('EXPRESSIVE_SOURCE',decide(self.event(expressive_source_qualified=False))['next'])
 def test_double_rvc(self):self.assertEqual('BLOCK',decide(self.event(post_rvc_passes=1,wants_rvc=True))['status'])
 def test_whisper(self):self.assertIn('PHYSIOLOGICAL',decide(self.event(needs_actual_whisper=True))['next'])
 def test_rvc(self):self.assertIn('ONE_PASS',decide(self.event(wants_rvc=True))['next'])
 def test_new_asr(self):self.assertIn('INDEPENDENT',decide(self.event(modified_candidate_lexical_pass=False))['next'])
 def test_listening(self):self.assertIn('LISTEN',decide(self.event(passed_perceptual_comparison=False))['next'])
 def test_backing(self):self.assertEqual('BLOCK',decide(self.event(has_independent_backing=False))['status'])
 def test_human(self):self.assertEqual('REVIEW',decide(self.event(human_accepted=False))['status'])
 def test_accept_only_by_person(self):self.assertEqual('ARTISTICALLY_APPROVED_BY_HUMAN',decide(self.event(human_accepted=True))['status'])
 def test_no_60(self):self.assertIsNone(json.loads((Path(__file__).parent/'SINGER_F01_PROFILE.json').read_text())['strict_song_duration_target'])
if __name__=='__main__':unittest.main()