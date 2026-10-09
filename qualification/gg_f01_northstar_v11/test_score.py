"""Pre-render independent tests, no bank required."""
import ast, json, pathlib, math, unittest
ROOT=pathlib.Path(__file__).parent
score=json.loads((ROOT/'AUTHENTIC_FIRST_LINE.json').read_text())
raw=(ROOT/'render_true_singer.py').read_text()
tree=ast.parse(raw)
class Check(unittest.TestCase):
 def test_song_source(self):
  self.assertEqual(score['authority']['source_git_blob_sha'],'2491adff94ae4bfede8399d3f82e06c7db8ec3d6')
 def test_words(self):
  self.assertEqual(' '.join(w['text'] for w in score['phrase']['words']),'мы встретились с тобой как люди видятся во сне')
 def test_notes(self):
  ns=[p for w in score['phrase']['words'] for p in w['pitches']]
  self.assertEqual(len(ns),15)
  self.assertGreater(max(ns)-min(ns),4)
 def test_unequal_notes(self):
  self.assertGreater(len({d for w in score['phrase']['words'] for d in w['durations']}),1)
 def test_no_unlicensed_sample(self):
  self.assertNotIn('Mimosa_Dark',raw)
  self.assertNotIn('Human-B.wav',raw)
 def test_one_embedded_singer(self):
  self.assertIn("SINGER='embeds/5_mature'",raw)
 def test_no_whisper(self):
  self.assertIn("'whisper':'NOT_ATTEMPTED'",raw)
 def test_real_new_song_synthesis(self):
  self.assertIn('ac.predict(',raw)
  self.assertIn('vc.predict(',raw)
 def test_first_line_phone(self):
  self.assertIn("('дя'",raw)
  self.assertIn("('тся'",raw)
 def test_consonant_repair(self):
  self.assertIn("selected[12]=['ru/t','ru/s','ru/a']",raw)
  self.assertIn("selected[11][1]=='ru/a'",raw)
 def test_no_gimmicks(self):
  self.assertNotIn('librosa.effects.pitch_shift',raw)
  self.assertNotIn('random.uniform',raw)
 def test_confidence(self):
  self.assertIn("'artistic_status':'UNREVIEWED'",raw)
if __name__=='__main__':unittest.main()