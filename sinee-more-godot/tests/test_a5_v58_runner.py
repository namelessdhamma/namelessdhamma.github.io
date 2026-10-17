"""Fail-closed qualification log parsing; no fake Godot engine success."""
import unittest
from tools.run_a5_v58_godot_qualification import assess_full_match_log


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.good = ''.join(f'BLUE_SEA_FULL_MATCH_CASE_PASS world={w} rule={m}\n'
                            for w in range(7) for m in ('C', 'D', 'CD'))
        self.good += 'BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21 worlds=7 modes=C,D,CD\n'

    def test_01_complete(self):
        self.assertTrue(assess_full_match_log(self.good, 0)['pass'])

    def test_02_missing_case(self):
        self.assertFalse(assess_full_match_log(self.good.replace('world=6 rule=CD', 'world=6 rule=UNKNOWN'), 0)['pass'])

    def test_03_duplicate_case(self):
        self.assertFalse(assess_full_match_log(self.good.replace('world=6 rule=CD', 'world=0 rule=C'), 0)['pass'])

    def test_04_missing_summary(self):
        self.assertFalse(assess_full_match_log(self.good.split('BLUE_SEA_FULL_MATCH_SUITE_PASS')[0], 0)['pass'])

    def test_05_nonzero_exit(self):
        self.assertFalse(assess_full_match_log(self.good, 1)['pass'])

    def test_06_engine_error(self):
        self.assertFalse(assess_full_match_log(self.good + 'SCRIPT ERROR: runtime fail\n', 0)['pass'])

    def test_07_false_summary(self):
        self.assertFalse(assess_full_match_log('BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21', 0)['pass'])

if __name__ == '__main__':
    unittest.main()
