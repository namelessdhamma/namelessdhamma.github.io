import json
import tempfile
import unittest
from pathlib import Path

from nd_oauth.blob_provider import BlobBackedOAuthProvider


class _MemoryStore:
    def __init__(self, payload: bytes | None = None):
        self.payload = payload
        self.restore_calls = []
        self.persisted = []

    def restore(self, local_path: Path) -> bool:
        self.restore_calls.append(local_path)
        if self.payload is None:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.payload)
        return True

    def persist(self, local_path: Path) -> None:
        self.persisted.append(local_path.read_bytes())


class BlobBackedProviderTests(unittest.TestCase):
    def test_restores_registry_before_upstream_provider_initializes(self):
        payload = json.dumps(
            {
                "clients": {},
                "access_tokens": {},
                "refresh_tokens": {},
                "a2r": {},
                "r2a": {},
            }
        ).encode()
        store = _MemoryStore(payload)
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "oauth.json"
            provider = BlobBackedOAuthProvider(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=state_path,
                state_store=store,
            )
            self.assertEqual(store.restore_calls, [state_path])
            self.assertEqual(provider.clients, {})
            self.assertTrue(state_path.exists())

    def test_upstream_state_write_is_mirrored_to_durable_store(self):
        store = _MemoryStore()
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "oauth.json"
            provider = BlobBackedOAuthProvider(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=state_path,
                state_store=store,
            )
            provider._write_state_file(
                {
                    "clients": {},
                    "access_tokens": {},
                    "refresh_tokens": {},
                    "a2r": {},
                    "r2a": {},
                }
            )
            self.assertEqual(len(store.persisted), 1)
            self.assertEqual(json.loads(store.persisted[0]), {
                "clients": {},
                "access_tokens": {},
                "refresh_tokens": {},
                "a2r": {},
                "r2a": {},
            })


if __name__ == "__main__":
    unittest.main()
