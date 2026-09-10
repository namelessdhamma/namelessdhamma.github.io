import asyncio
import tempfile
import unittest
from pathlib import Path

from nd_oauth.deployment import DeploymentConfig, build_mcp


class _MemoryStore:
    def __init__(self):
        self.payload = None

    def restore(self, local_path: Path) -> bool:
        if self.payload is None:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.payload)
        return True

    def persist(self, local_path: Path) -> None:
        self.payload = local_path.read_bytes()


class DeploymentTests(unittest.TestCase):
    def test_config_derives_canonical_origin_from_vercel(self):
        config = DeploymentConfig.from_environ(
            {
                "VERCEL_PROJECT_PRODUCTION_URL": "nd-oauth.example.vercel.app",
                "NOTEBOOKLM_MASTER_TOKEN_B64": "opaque-master-token-b64",
                "NOTEBOOKLM_MCP_OAUTH_PASSWORD": "a-strong-random-password-1234567890",
            }
        )
        self.assertEqual(config.base_url, "https://nd-oauth.example.vercel.app")

    def test_build_mcp_uses_full_surface_and_oauth_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = DeploymentConfig(
                base_url="https://oauth.example.com",
                master_token_b64="opaque",
                oauth_password="a-strong-random-password-1234567890",
                state_path=Path(tmp) / "oauth.json",
            )
            mcp = build_mcp(
                config,
                registry_store=_MemoryStore(),
                transient_store=_MemoryStore(),
                client_factory=None,
            )
            names = {tool.name for tool in asyncio.run(mcp.list_tools())}
            self.assertIn("notebook_list", names)
            self.assertIn("notebook_create", names)
            self.assertIn("nd_ping_secure", names)
            app = mcp.http_app(path="/mcp", stateless_http=True)
            paths = {getattr(route, "path", None) for route in app.routes}
            self.assertIn("/mcp", paths)
            self.assertIn("/authorize", paths)
            self.assertIn("/token", paths)
            self.assertIn("/register", paths)


if __name__ == "__main__":
    unittest.main()
