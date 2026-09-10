import asyncio
import tempfile
import unittest
from pathlib import Path

from nd_oauth.full_server import create_full_mcp


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


class FullServerTests(unittest.TestCase):
    def test_registers_real_notebooklm_tools_behind_oauth(self):
        with tempfile.TemporaryDirectory() as tmp:
            mcp = create_full_mcp(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=Path(tmp) / "oauth.json",
                registry_store=_MemoryStore(),
                transient_store=_MemoryStore(),
                client_factory=None,
            )

            names = {tool.name for tool in asyncio.run(mcp.list_tools())}
            self.assertIn("notebook_list", names)
            self.assertIn("notebook_create", names)
            self.assertIn("notebook_delete", names)
            self.assertIn("nd_ping_secure", names)

            app = mcp.http_app(path="/mcp", stateless_http=True)
            paths = {getattr(route, "path", None) for route in app.routes}
            self.assertIn("/mcp", paths)
            self.assertIn("/authorize", paths)
            self.assertIn("/token", paths)
            self.assertIn("/register", paths)
            self.assertIn("/login", paths)
            self.assertTrue(any(path and path.startswith("/.well-known/") for path in paths))


if __name__ == "__main__":
    unittest.main()
