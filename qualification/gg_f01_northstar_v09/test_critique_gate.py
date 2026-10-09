import unittest
from critique_gate import inspect_signal,decide,OBSERVED_USER_FEEDBACK
class GateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rows=inspect_signal()
 def test_source_weak_meeting(self):
  by={x['word']:x for x in self.rows}
  self.assertLess(by['встретились']['source_vocal_minus_music_db'],-4)
 def test_large_regression_from_v3(self):
  by={x['word']:x for x in self.rows}
  self.assertLess(by['встретились']['source_vocal_minus_v3_db'],-6)
 def test_quiet_first_part_of_my(self):
  by={x['word']:x for x in self.rows}
  self.assertLess(by['мы']['early_minus_late_db'],-9)
 def test_asr_exact_cannot_override_negative_human_feedback(self):
  x=decide(self.rows,asr_result='EXACT');self.assertEqual(x['status'],'REJECT')
 def test_semantically_correct_asr_cannot_silence_phonetic_failure(self):
  x=decide(self.rows,asr_result='EXACT'); self.assertIn('HUMAN_PHONETIC_REJECT',[f['code'] for f in x['failures']]);self.assertIn('видятся',[f['word'] for f in x['failures']])
 def test_unqualified_does_not_become_accepted_without_feedback(self):
  x=decide(self.rows,feedback={});self.assertNotEqual(x['status'],'ACCEPTED')
 def test_human_singing_reject_includes_vstret(self):
  x=decide(self.rows);self.assertIn('HUMAN_NOT_SUNG',[f['code'] for f in x['failures']])
 def test_dont_claim_voice_creation(self):
  x=decide(self.rows);self.assertEqual(x['next_action'],'SOURCE_PERFORMANCE_REPAIR_REQUIRED_BEFORE_ANY_MIX_OR_GAIN_CHANGES')
if __name__=='__main__':unittest.main()