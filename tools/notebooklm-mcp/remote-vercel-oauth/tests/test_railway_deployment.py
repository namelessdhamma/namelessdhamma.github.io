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

    def test_defaults_use_separate_backup_blob_namespaces(self):
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
        self.assertEqual(
            config.registry_blob_path,
            "nd-notebooklm-railway/oauth-registry.json",
        )
        self.assertEqual(
            config.transient_blob_path,
            "nd-notebooklm-railway/oauth-transient.json",
        )
        self.assertNotEqual(config.registry_blob_path, config.transient_blob_path)

    def test_rejects_same_registry_and_transient_blob_path(self):
        with self.assertRaisesRegex(RuntimeError, "must differ"):
            RailwayDeploymentConfig.from_environ(
                {
                    "ND_NOTEBOOKLM_OAUTH_BASE_URL": "https://backup.example.test",
                    "NOTEBOOKLM_MASTER_TOKEN_B64": "master",
                    "NOTEBOOKLM_MCP_OAUTH_PASSWORD": "x" * 24,
                    "ND_NOTEBOOKLM_OAUTH_REGISTRY_BLOB": "same.json",
                    "ND_NOTEBOOKLM_OAUTH_TRANSIENT_BLOB": "same.json",
                }
            )


if __name__ == "__main__":
    unittest.main()
