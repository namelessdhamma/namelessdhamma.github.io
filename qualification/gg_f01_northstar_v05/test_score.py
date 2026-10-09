import unittest,json
from pathlib import Path
P=Path(__file__).parent
A=json.loads((P/'FIRST_LINE_D1_FULL_V3_AUTHENTIC.json').read_text())
BAD=json.loads((P.parent/'gg_northstar_v1/GG_TRUE_VISUAL_HUMAN_VOCAL/qualification/FIRST_LINE_SCORE.json').read_text())
class ScoreIntegrity(unittest.TestCase):
 def test_authority(self):self.assertEqual(A['authority']['source_git_blob_sha'],'2491adff94ae4bfede8399d3f82e06c7db8ec3d6')
 def test_has_melodic_contour(self):
  tones={v for w in A['phrase']['words'] for v in w['pitches']};self.assertGreater(len(tones),3)
 def test_flattened_fixture_is_rejected(self):
  bad={v for w in BAD['phrases'][0]['words'] for v in w['pitches']};self.assertEqual(len(bad),1)
 def test_correct_rhythm_not_legacy_uniform(self):
  durations={d for w in A['phrase']['words'] for d in w['durations']};self.assertIn(720,durations);self.assertIn(240,durations)
 def test_compatible_note_durations(self):
  for w in A['phrase']['words']:
   self.assertEqual(len(w['pitches']),len(w['durations']))
 def test_start(self):
  p=A['phrase'];tick=p['bar']*4*A['ticks_per_beat']+p['offset'];self.assertAlmostEqual(tick/A['ticks_per_beat']*60/A['bpm'],9.1666666667,places=4)
 def test_end(self):
  p=A['phrase'];ticks=sum(sum(w['durations'])+w['rest'] for w in p['words']);sec=ticks/A['ticks_per_beat']*60/A['bpm'];self.assertAlmostEqual(sec,5.55555555556,places=4)
 def test_word_count(self):self.assertEqual(len(A['phrase']['words']),9)
if __name__=='__main__':unittest.main()