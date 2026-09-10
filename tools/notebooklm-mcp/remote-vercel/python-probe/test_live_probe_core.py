import base64
import os
import tempfile
import unittest
from pathlib import Path

from api._live_probe_core import decode_master_token, is_authorized, materialize_master_token


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


if __name__ == "__main__":
    unittest.main()
