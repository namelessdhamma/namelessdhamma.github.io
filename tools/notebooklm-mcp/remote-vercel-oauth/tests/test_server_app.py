import asyncio
import tempfile
import unittest
from pathlib import Path

from nd_oauth.server_app import create_mcp


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


class ServerAppTests(unittest.TestCase):
    def test_surface_is_narrow_and_http_app_contains_oauth_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mcp = create_mcp(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=Path(tmp) / "oauth.json",
                registry_store=_MemoryStore(),
                transient_store=_MemoryStore(),
            )

            tools = asyncio.run(mcp.list_tools())
            self.assertEqual([tool.name for tool in tools], ["nd_ping_secure"])

            app = mcp.http_app(path="/mcp", stateless_http=True)
            paths = {getattr(route, "path", None) for route in app.routes}
            self.assertIn("/mcp", paths)
            self.assertIn("/authorize", paths)
            self.assertIn("/token", paths)
            self.assertIn("/register", paths)
            self.assertIn("/login", paths)
            self.assertTrue(any(path and path.startswith("/.well-known/") for path in paths))

    def test_ping_payload_is_safe_and_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            mcp = create_mcp(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=Path(tmp) / "oauth.json",
                registry_store=_MemoryStore(),
                transient_store=_MemoryStore(),
            )
            tool = asyncio.run(mcp.get_tool("nd_ping_secure"))
            result = asyncio.run(tool.run({}))
            self.assertEqual(result.content[0].text, '{"ok":true,"service":"nd-notebooklm-oauth-mcp","mode":"oauth-qualification","version":"0.1.0"}')


if __name__ == "__main__":
    unittest.main()
