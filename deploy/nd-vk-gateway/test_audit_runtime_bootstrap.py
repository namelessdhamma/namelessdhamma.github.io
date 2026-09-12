import importlib.util
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("audit_runtime_bootstrap.py")
spec = importlib.util.spec_from_file_location("audit_runtime_bootstrap", MODULE_PATH)
audit_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_module)


class RuntimeBootstrapAuditTests(unittest.TestCase):
    def audit_text(self, name: str, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / name).write_text(text, encoding="utf-8")
            return audit_module.audit(root)

    def test_clean_runtime_passes(self):
        self.assertEqual([], self.audit_text("app.py", "print('local runtime')\n"))

    def test_raw_github_runtime_fetch_fails(self):
        violations = self.audit_text(
            "loader.py",
            "u='https://raw.githubusercontent.com/org/repo/commit/runtime.py'\n",
        )
        self.assertTrue(any(v[0] == "RAW_GITHUB_EXECUTABLE_FETCH" for v in violations))

    def test_v53_style_python_argv_apk_install_fails(self):
        violations = self.audit_text(
            "launcher.py",
            "subprocess.run(['apk','add','--no-cache','nodejs'],check=True)\n",
        )
        self.assertTrue(any(v[0] == "RUNTIME_APK_INSTALL_ARGV" for v in violations))

    def test_shell_package_install_fails(self):
        violations = self.audit_text("start.sh", "apk add --no-cache nodejs\n")
        self.assertTrue(any(v[0] == "RUNTIME_APK_INSTALL_SHELL" for v in violations))

    def test_build_recipe_package_install_is_not_runtime_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "Dockerfile").write_text("RUN apk add --no-cache nodejs\n", encoding="utf-8")
            self.assertEqual([], audit_module.audit(root))


if __name__ == "__main__":
    unittest.main()
