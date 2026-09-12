import importlib.util
import pathlib
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tmp" / "nd_vk_gateway_v54_vault_paths.py"

spec = importlib.util.spec_from_file_location("nd_vk_gateway_v54_vault_paths", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class VaultPathPatchTests(unittest.TestCase):
    def test_synthetic_exact_replacement(self):
        raw = "before\n" + mod.OLD + "\nafter\n"
        patched = mod.patch_v13_source(raw)
        self.assertNotIn(mod.OLD, patched)
        self.assertIn(mod.NEW, patched)

    def test_pinned_v13_still_contains_expected_marker(self):
        with urllib.request.urlopen(mod.V13, timeout=30) as response:
            raw = response.read().decode("utf-8")
        self.assertIn(mod.OLD, raw)
        patched = mod.patch_v13_source(raw)
        self.assertIn(mod.NEW, patched)
        for name in (
            "00 ตอนนี้ — Now.md",
            "01 แผนที่ — Maps.md",
            "02 หัวข้อ — Topics.md",
            "03 การเปลี่ยนแปลง — Changes.md",
        ):
            self.assertIn(name, patched)

    def test_missing_marker_fails_closed(self):
        with self.assertRaises(RuntimeError):
            mod.patch_v13_source("no expected fallback paths here")


if __name__ == "__main__":
    unittest.main()
