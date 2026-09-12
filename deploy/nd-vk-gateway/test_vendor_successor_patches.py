import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
MODULE_PATH = ROOT / "vendor_runtime.py"

spec = importlib.util.spec_from_file_location("vendor_runtime", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class VendorSuccessorPatchTests(unittest.TestCase):
    def test_exact_v13_marker_is_replaced_once(self):
        raw = "before\n" + mod.VAULT_PATHS_OLD + "\nafter\n"
        patched, patches = mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, raw)
        self.assertNotIn(mod.VAULT_PATHS_OLD, patched)
        self.assertIn(mod.VAULT_PATHS_NEW, patched)
        self.assertEqual(patches, ["readonly_vault_orientation_paths_v54"])

    def test_non_target_pin_is_unchanged(self):
        raw = "before\n" + mod.VAULT_PATHS_OLD + "\nafter\n"
        patched, patches = mod.apply_qualified_successor_patches(
            "tmp/not-v13.py@0000000000000000000000000000000000000000", raw
        )
        self.assertEqual(patched, raw)
        self.assertEqual(patches, [])

    def test_missing_marker_fails_closed(self):
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, "marker absent")

    def test_duplicate_marker_fails_closed(self):
        raw = mod.VAULT_PATHS_OLD + "\n" + mod.VAULT_PATHS_OLD
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, raw)

    def test_already_patched_source_fails_closed(self):
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, mod.VAULT_PATHS_NEW)


if __name__ == "__main__":
    unittest.main()
