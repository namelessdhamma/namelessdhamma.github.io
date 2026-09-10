import tempfile
import unittest
from pathlib import Path

from nd_oauth.blob_state import BlobOAuthStateStore


class _Blob:
    def __init__(self, stream):
        self.status_code = 200
        self.stream = stream


class _BlobWithoutStatus:
    def __init__(self, stream):
        self.stream = stream


class _FakeClient:
    def __init__(self, existing=None, *, expose_status=True):
        self.existing = existing
        self.expose_status = expose_status
        self.put_calls = []

    def get(self, path, *, access, use_cache):
        if self.existing is None:
            return None
        stream = iter([self.existing[:3], self.existing[3:]])
        if self.expose_status:
            return _Blob(stream)
        return _BlobWithoutStatus(stream)

    def put(self, path, body, **kwargs):
        self.put_calls.append((path, body, kwargs))
        return object()

    def close(self):
        pass


class BlobStateTests(unittest.TestCase):
    def test_restore_writes_private_state_with_mode_0600(self):
        client = _FakeClient(b'{"clients":{}}')
        store = BlobOAuthStateStore("oauth/state.json", client_factory=lambda: client)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth_state.json"
            self.assertTrue(store.restore(path))
            self.assertEqual(path.read_bytes(), b'{"clients":{}}')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_restore_accepts_current_vercel_download_object_without_status_code(self):
        client = _FakeClient(b'{"clients":{"chatgpt":{}}}', expose_status=False)
        store = BlobOAuthStateStore("oauth/state.json", client_factory=lambda: client)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth_state.json"
            self.assertTrue(store.restore(path))
            self.assertEqual(path.read_bytes(), b'{"clients":{"chatgpt":{}}}')

    def test_restore_missing_blob_is_clean_first_boot(self):
        store = BlobOAuthStateStore("oauth/state.json", client_factory=lambda: _FakeClient())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth_state.json"
            self.assertFalse(store.restore(path))
            self.assertFalse(path.exists())

    def test_persist_uses_private_overwrite_and_no_random_suffix(self):
        client = _FakeClient()
        store = BlobOAuthStateStore("oauth/state.json", client_factory=lambda: client)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth_state.json"
            path.write_bytes(b'{"refresh_tokens":{}}')
            store.persist(path)
        self.assertEqual(len(client.put_calls), 1)
        target, body, options = client.put_calls[0]
        self.assertEqual(target, "oauth/state.json")
        self.assertEqual(body, b'{"refresh_tokens":{}}')
        self.assertEqual(options["access"], "private")
        self.assertTrue(options["overwrite"])
        self.assertFalse(options["add_random_suffix"])


if __name__ == "__main__":
    unittest.main()
