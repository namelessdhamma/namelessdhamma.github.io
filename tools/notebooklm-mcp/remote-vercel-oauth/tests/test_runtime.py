import asyncio
import base64
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from nd_oauth.runtime import make_client_factory, materialize_master_token


class RuntimeTests(unittest.TestCase):
    def test_materializes_master_token_with_private_mode(self):
        raw = b'{"version":1,"email":"test@example.com"}'
        encoded = base64.b64encode(raw).decode("ascii")
        with tempfile.TemporaryDirectory() as tmp:
            path = materialize_master_token(encoded, Path(tmp))
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_factory_prepares_storage_before_opening_client(self):
        events = []
        previous_home = os.environ.get("NOTEBOOKLM_HOME")

        def refresh(home: Path) -> None:
            events.append(("refresh", str(home)))
            self.assertTrue((home / "profiles" / "default" / "master_token.json").exists())

        @asynccontextmanager
        async def client_builder(**kwargs):
            events.append(("client", kwargs, os.environ.get("NOTEBOOKLM_HOME")))
            yield "CLIENT"

        encoded = base64.b64encode(b'{"version":1}').decode("ascii")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            factory = make_client_factory(
                encoded,
                home=home,
                refresh=refresh,
                client_builder=client_builder,
            )

            async def run():
                async with factory() as client:
                    self.assertEqual(client, "CLIENT")

            asyncio.run(run())
            self.assertEqual(events[0], ("refresh", str(home)))
            self.assertEqual(events[1][0], "client")
            self.assertEqual(events[1][1]["profile"], "default")
            self.assertEqual(events[1][1]["backend"], "android")
            self.assertEqual(events[1][2], str(home))

        if previous_home is None:
            os.environ.pop("NOTEBOOKLM_HOME", None)
        else:
            os.environ["NOTEBOOKLM_HOME"] = previous_home


if __name__ == "__main__":
    unittest.main()
