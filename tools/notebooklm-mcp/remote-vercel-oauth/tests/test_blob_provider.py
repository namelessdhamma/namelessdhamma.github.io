import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

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
        raw = local_path.read_bytes()
        self.persisted.append(raw)
        self.payload = raw


def _client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="chatgpt-test",
        redirect_uris=["https://chatgpt.com/connector/callback"],
    )


def _params() -> AuthorizationParams:
    return AuthorizationParams(
        state="state-1",
        scopes=[],
        code_challenge="challenge-1",
        redirect_uri="https://chatgpt.com/connector/callback",
        redirect_uri_provided_explicitly=True,
        resource=None,
    )


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

    def test_pending_authorize_state_survives_a_fresh_provider_instance(self):
        registry_store = _MemoryStore()
        pending_store = _MemoryStore()

        with tempfile.TemporaryDirectory() as tmp1:
            provider1 = BlobBackedOAuthProvider(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=Path(tmp1) / "oauth.json",
                state_store=registry_store,
                pending_store=pending_store,
            )
            login_url = asyncio.run(provider1.authorize(_client(), _params()))
            sid = parse_qs(urlparse(login_url).query)["sid"][0]
            self.assertIsNotNone(pending_store.payload)

        with tempfile.TemporaryDirectory() as tmp2:
            provider2 = BlobBackedOAuthProvider(
                password="a-strong-random-password-1234567890",
                base_url="https://oauth.example.com",
                state_path=Path(tmp2) / "oauth.json",
                state_store=registry_store,
                pending_store=pending_store,
            )
            self.assertIn(sid, provider2._pending)
            self.assertEqual(provider2._pending[sid].client.client_id, "chatgpt-test")
            self.assertEqual(provider2._pending[sid].params.state, "state-1")


if __name__ == "__main__":
    unittest.main()
