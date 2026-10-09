import sys,unittest,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from human_vocal_opening import SR,START,END,VOCAL_BEGIN,apply_style,metrics,ramp
class Opening(unittest.TestCase):
 def setUp(self):
  self.y=np.sin(np.arange(round((END-START)*SR))*2*np.pi*220/SR)*.19
 def test_ref_immutable(self):
  a=self.y.copy();self.assertTrue(np.array_equal(a,apply_style(a,'golden_z10')))
 def test_conserved_duration(self):
  for sty in ('gentle_emergence','airy_emergence'):
   self.assertEqual(len(self.y),len(apply_style(self.y,sty)))
 def test_zero_not_turned_into_voice(self):
  for sty in ('gentle_emergence','airy_emergence'):
   self.assertLess(np.max(np.abs(apply_style(np.zeros_like(self.y),sty))),1e-12)
 def test_no_clipping_of_sine(self):
  for sty in ('gentle_emergence','airy_emergence'):
   self.assertLess(metrics(apply_style(self.y,sty))['peak'],.95)
 def test_onset_silent_to_soft(self):
  t=START+np.arange(len(self.y))/SR
  g=ramp(t,[(START,1),(VOCAL_BEGIN,.6),(END,1)])
  self.assertTrue((g>=.5999).all())
 def test_no_finite_errors(self):
  for sty in ('golden_z10','gentle_emergence','airy_emergence'):
   self.assertTrue(np.all(np.isfinite(apply_style(self.y,sty))))
 def test_no_type_mode(self):
  with self.assertRaises(ValueError):apply_style(self.y,'second_voice_overlay')
if __name__=='__main__':unittest.main()