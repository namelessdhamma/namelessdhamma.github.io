import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from notebooklm_runtime.live_probe_core import (
    decode_master_token,
    is_authorized,
    materialize_master_token,
    refresh_storage_from_master_token,
)


class LiveProbeCoreTests(unittest.TestCase):
    def test_authorization_requires_exact_bearer_token(self):
        self.assertTrue(is_authorized("Bearer probe-secret", "probe-secret"))
        self.assertFalse(is_authorized("Bearer wrong", "probe-secret"))
        self.assertFalse(is_authorized(None, "probe-secret"))

    def test_decode_master_token_round_trips_utf8_json_bytes(self):
        raw = b'{"version":1,"email":"example@example.com"}'
        encoded = base64.b64encode(raw).decode("ascii")
        self.assertEqual(decode_master_token(encoded), raw)

    def test_materialize_master_token_writes_only_profile_file_with_0600(self):
        raw = b'{"version":1}'
        encoded = base64.b64encode(raw).decode("ascii")
        with tempfile.TemporaryDirectory() as tmp:
            path = materialize_master_token(encoded, Path(tmp))
            self.assertEqual(path, Path(tmp) / "profiles" / "default" / "master_token.json")
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_refresh_storage_bootstraps_from_master_token_without_exposing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("notebooklm_runtime.live_probe_core.subprocess.run") as run:
                refresh_storage_from_master_token(home)

            kwargs = run.call_args.kwargs
            command = run.call_args.args[0]
            self.assertEqual(command[-4:], ["auth", "refresh", "--verify"][-4:])
            self.assertEqual(kwargs["env"]["NOTEBOOKLM_HOME"], str(home))
            self.assertEqual(kwargs["env"]["NOTEBOOKLM_PROFILE"], "default")
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["stdout"], -3)
            self.assertEqual(kwargs["stderr"], -3)


if __name__ == "__main__":
    unittest.main()
