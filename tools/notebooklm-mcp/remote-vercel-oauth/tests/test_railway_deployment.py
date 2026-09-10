import unittest
from pathlib import Path

from nd_oauth.railway_deployment import RailwayDeploymentConfig


class RailwayDeploymentConfigTests(unittest.TestCase):
    def test_requires_explicit_public_base_url(self):
        with self.assertRaisesRegex(RuntimeError, "ND_NOTEBOOKLM_OAUTH_BASE_URL"):
            RailwayDeploymentConfig.from_environ(
                {
                    "NOTEBOOKLM_MASTER_TOKEN_B64": "master",
                    "NOTEBOOKLM_MCP_OAUTH_PASSWORD": "x" * 24,
                }
            )

    def test_defaults_use_railway_volume_for_durable_state(self):
        config = RailwayDeploymentConfig.from_environ(
            {
                "ND_NOTEBOOKLM_OAUTH_BASE_URL": "https://backup.example.test/",
                "NOTEBOOKLM_MASTER_TOKEN_B64": "master",
                "NOTEBOOKLM_MCP_OAUTH_PASSWORD": " y" + ("x" * 23) + " ",
            }
        )
        self.assertEqual(config.base_url, "https://backup.example.test")
        self.assertEqual(config.oauth_password, "y" + ("x" * 23))
        self.assertEqual(config.state_path, Path("/tmp/nd-notebooklm-railway-oauth.json"))
        self.assertEqual(config.persistent_dir, Path("/data/nd-notebooklm"))

    def test_allows_explicit_persistent_directory(self):
        config = RailwayDeploymentConfig.from_environ(
            {
                "ND_NOTEBOOKLM_OAUTH_BASE_URL": "https://backup.example.test",
                "NOTEBOOKLM_MASTER_TOKEN_B64": "master",
                "NOTEBOOKLM_MCP_OAUTH_PASSWORD": "x" * 24,
                "ND_NOTEBOOKLM_OAUTH_PERSIST_DIR": "/mnt/backup/oauth",
            }
        )
        self.assertEqual(config.persistent_dir, Path("/mnt/backup/oauth"))


if __name__ == "__main__":
    unittest.main()
