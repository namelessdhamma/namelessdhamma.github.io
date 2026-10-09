#!/usr/bin/env python3
import json,hashlib,unittest
from pathlib import Path
import numpy as np,soundfile as sf
from build_phrase_repair import ROOT,LOCK,OUT,sha,START,SR
from assemble_full_song import full_decode

class VerifyNewSourceVowel(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.q=json.loads((OUT/'V12_DYA_DONOR_MANIFEST.json').read_text())
  cls.original=full_decode(ROOT/'M3_REVIEW_V3.mp3',2)
  cls.changed,_=sf.read(OUT/'GG_NEZRIMY_FULL_M3_REAL_DYA_SOURCE_DONOR_D_REVIEW.wav',dtype='float32',always_2d=True)
  cls.a=int(round(13.055*SR));cls.b=int(round(13.325*SR))
 def test_all_immutable_sources(self):
  for f,hash in LOCK.items():self.assertEqual(sha(ROOT/f),hash)
 def test_guide_exact(self):self.assertEqual(sha(ROOT/'D1_CLEAN_GUIDE_FULL.wav'),'ea3f0798db4e60927e307467997ea00856bf807d7959a952aa66281182fbc14e')
 def test_one_source_donor_not_vocal_overdub(self):
  self.assertIn('actual D1 guide',self.q['route']);self.assertEqual(self.q['status'],'REVIEW_ONLY_NOT_APPROVED')
 def test_no_change_other_singer_or_music_before_word(self):self.assertTrue(np.array_equal(self.original[:self.a],self.changed[:self.a]))
 def test_no_change_after_word(self):self.assertTrue(np.array_equal(self.original[self.b:],self.changed[self.b:]))
 def test_vowel_edited(self):self.assertGreater(float(np.max(abs(self.changed[self.a:self.b]-self.original[self.a:self.b]))),1e-4)
 def test_original_peak_not_exceeded(self):self.assertLessEqual(float(abs(self.changed).max()),float(abs(self.original).max())+1e-5)
 def test_phoneme_source_phase_matches(self):self.assertGreater(self.q['technical']['donor']['phase_correlation'],.7)
 def test_phase_lag_bounded(self):self.assertLessEqual(abs(self.q['technical']['donor']['phase_alignment_samples']),70)
 def test_clipping_after_edit(self):self.assertTrue(np.isfinite(self.changed).all());self.assertLess(float(abs(self.changed[self.a:self.b]).max()),1.0)
 def test_has_new_fulllength_song(self):self.assertGreater((OUT/'GG_NEZRIMY_FULL_M3_REAL_DYA_SOURCE_DONOR_D_REVIEW.mp3').stat().st_size,8_000_000)
 def test_limits_explicit(self):self.assertIn('ONLY user review',self.q['limitation'])

if __name__=='__main__':unittest.main(verbosity=2)