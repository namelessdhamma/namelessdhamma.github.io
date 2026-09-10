import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_vercel_python_entrypoint_is_explicit(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["tool"]["vercel"]["entrypoint"], "app:app")

    def test_serverless_duration_covers_credential_refresh_budget(self):
        data = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertTrue(data["fluid"])
        self.assertGreaterEqual(data["functions"]["app.py"]["maxDuration"], 90)

    def test_entrypoint_builds_application_from_managed_environment(self):
        text = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("build_app_from_environ", text)
        self.assertIn("app =", text)


if __name__ == "__main__":
    unittest.main()
