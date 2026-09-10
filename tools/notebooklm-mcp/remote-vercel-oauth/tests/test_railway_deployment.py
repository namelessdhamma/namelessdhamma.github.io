import base64
import hashlib
import os
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nd_oauth.railway_deployment import RailwayDeploymentConfig


AAD = b"ND_NOTEBOOKLM_RAILWAY_BACKUP_V1"


def encrypt_master(master: str, password: str) -> str:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    ciphertext = AESGCM(key).encrypt(nonce, master.encode("utf-8"), AAD)
    return base64.b64encode(b"ND1" + salt + nonce + ciphertext).decode("ascii")


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
        self.assertEqual(config.master_token_b64, "master")
        self.assertEqual(config.state_path, Path("/tmp/nd-notebooklm-railway-oauth.json"))
        self.assertEqual(config.persistent_dir, Path("/data/nd-notebooklm"))

    def test_decrypts_encrypted_provider_credential(self):
        password = "p" * 32
        encrypted = encrypt_master("provider-master-token", password)
        config = RailwayDeploymentConfig.from_environ(
            {
                "ND_NOTEBOOKLM_OAUTH_BASE_URL": "https://backup.example.test",
                "NOTEBOOKLM_MCP_OAUTH_PASSWORD": password,
                "ND_NOTEBOOKLM_MASTER_TOKEN_AESGCM_B64": encrypted,
            }
        )
        self.assertEqual(config.master_token_b64, "provider-master-token")

    def test_rejects_ambiguous_master_token_sources(self):
        password = "p" * 32
        encrypted = encrypt_master("provider-master-token", password)
        with self.assertRaisesRegex(RuntimeError, "only one"):
            RailwayDeploymentConfig.from_environ(
                {
                    "ND_NOTEBOOKLM_OAUTH_BASE_URL": "https://backup.example.test",
                    "NOTEBOOKLM_MCP_OAUTH_PASSWORD": password,
                    "NOTEBOOKLM_MASTER_TOKEN_B64": "plaintext",
                    "ND_NOTEBOOKLM_MASTER_TOKEN_AESGCM_B64": encrypted,
                }
            )

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
