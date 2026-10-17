"""CI qualification must be self-contained and exercise 746x280 geometry.

This is source-level qualification only. No native Godot, screenshots, or
real-phone gameplay is asserted by these checks.
"""
from pathlib import Path
import re
import unittest

PROJECT = Path(__file__).resolve().parents[2]
CI = PROJECT / ".github/workflows/a5-seven-worlds-native-qualification.yml"
GAME = PROJECT / "sinee-more-godot/scripts/main.gd"


class NativeQualificationPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = CI.read_text()
        cls.game = GAME.read_text()

    def test_explicit_numpy_install_for_existing_vision_regressions(self):
        self.assertRegex(self.ci, r"pip install[^\n]*\bnumpy\b")
        self.assertIn("import numpy as np", self.ci)
        for version in (124, 130):
            path = PROJECT / f"sinee-more-godot/tests/test_a5_v{version}_" 
            self.assertTrue(any(p.read_text().find("import numpy") >= 0 for p in path.parent.glob(path.name + "*.py")))

    def test_native_smoke_uses_phone_viewport(self):
        self.assertRegex(self.ci, r"--nd-run-smoke --nd-test-size=746x280")

    def test_native_full_match_uses_phone_viewport(self):
        self.assertRegex(self.ci, r"--nd-run-full-match --nd-test-size=746x280")

    def test_capture_is_windowed_and_uses_dummy_audio(self):
        self.assertIn("xvfb-run", self.ci)
        capture = (PROJECT / "sinee-more-godot/tools/a5_native_seven_world_capture.py").read_text()
        self.assertIn('"--audio-driver", "Dummy"', capture)
        self.assertIn('"--windowed"', capture)

    def test_main_accepts_both_runtime_modes_and_test_viewport(self):
        self.assertIn('"--nd-run-smoke"', self.game)
        self.assertIn('"--nd-run-full-match"', self.game)
        self.assertIn('"--nd-test-size="', self.game)

    def test_workflow_is_branch_only_non_deploying(self):
        self.assertIn("contents: read", self.ci)
        self.assertIn("a5/seven-worlds-native-*", self.ci)
        self.assertNotIn("deploy-pages", self.ci)
        self.assertNotIn("contents: write", self.ci)


if __name__ == "__main__":
    unittest.main()
