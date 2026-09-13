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

    def test_context_v36_broker_accepts_structured_args(self):
        raw = "before\n" + mod.V36_BROKER_OLD + "\nafter\n"
        patched, patches = mod.apply_qualified_successor_patches(mod.V36_CONTEXT_PATCH_PIN, raw)
        self.assertNotIn(mod.V36_BROKER_OLD, patched)
        self.assertIn(mod.V36_BROKER_NEW, patched)
        self.assertEqual(patches, ["context_broker_args_v1"])

    def test_context_v9_dispatch_hook_is_inserted_without_touching_v12_markers(self):
        raw = ("import os,json,threading,time,hashlib,random,re\n"
               "from urllib.error import HTTPError\n\n"
               "x\n" + mod.V9_DISPATCH_OLD + "\ny")
        patched, patches = mod.apply_qualified_successor_patches(mod.V9_CONTEXT_PATCH_PIN, raw)
        self.assertIn("import os,json,threading,time,hashlib,random,re", patched)
        self.assertIn("from context_gateway import dispatch as nd_context_dispatch", patched)
        self.assertIn(mod.V9_DISPATCH_NEW, patched)
        self.assertNotIn(mod.V9_DISPATCH_OLD, patched)
        self.assertEqual(patches, ["context_dispatch_hook_v1"])

    def test_non_target_pin_is_unchanged(self):
        raw = "before\n" + mod.VAULT_PATHS_OLD + "\nafter\n"
        patched, patches = mod.apply_qualified_successor_patches(
            "tmp/not-v13.py@0000000000000000000000000000000000000000", raw
        )
        self.assertEqual(patched, raw)
        self.assertEqual(patches, [])

    def test_missing_marker_fails_closed(self):
        for pin in (mod.VAULT_PATH_PATCH_PIN, mod.V36_CONTEXT_PATCH_PIN, mod.V9_CONTEXT_PATCH_PIN):
            with self.assertRaises(RuntimeError):
                mod.apply_qualified_successor_patches(pin, "marker absent")

    def test_duplicate_context_markers_fail_closed(self):
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.V36_CONTEXT_PATCH_PIN, mod.V36_BROKER_OLD + "\n" + mod.V36_BROKER_OLD)
        raw = "from urllib.error import HTTPError\n" + mod.V9_DISPATCH_OLD + "\n" + mod.V9_DISPATCH_OLD
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.V9_CONTEXT_PATCH_PIN, raw)

    def test_duplicate_marker_fails_closed(self):
        raw = mod.VAULT_PATHS_OLD + "\n" + mod.VAULT_PATHS_OLD
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, raw)

    def test_already_patched_source_fails_closed(self):
        with self.assertRaises(RuntimeError):
            mod.apply_qualified_successor_patches(mod.VAULT_PATH_PATCH_PIN, mod.VAULT_PATHS_NEW)


if __name__ == "__main__":
    unittest.main()
