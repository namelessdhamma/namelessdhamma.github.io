from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from mcp.server.auth.provider import AccessToken, AuthorizationCode, AuthorizationParams, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from notebooklm.mcp._oauth import SelfHostedOAuthProvider, _Pending


class OAuthStateStore(Protocol):
    def restore(self, local_path: Path) -> bool: ...

    def persist(self, local_path: Path) -> None: ...


class BlobBackedOAuthProvider(SelfHostedOAuthProvider):
    """SelfHostedOAuthProvider with serverless-safe durable state mirroring.

    Upstream notebooklm-py persists OAuth clients/access/refresh tokens to a
    local JSON file, while the password-login handoff and authorization codes
    live only in memory. Vercel Functions can route consecutive OAuth requests
    to different instances, so this adapter mirrors both state classes to
    independent durable stores and refreshes durable registry reads on warm
    instances.

    The Google master token is deliberately outside this class.
    """

    def __init__(
        self,
        *,
        password: str,
        base_url: str,
        state_path: Path,
        state_store: OAuthStateStore,
        pending_store: OAuthStateStore | None = None,
        trust_proxy: bool = False,
    ) -> None:
        self._durable_state_store = state_store
        self._durable_pending_store = pending_store
        self._pending_state_path = state_path.with_name(f"{state_path.stem}.pending.json")

        # Upstream loads the registry in SelfHostedOAuthProvider.__init__, so the
        # durable copy must be materialized first.
        state_store.restore(state_path)
        super().__init__(
            password=password,
            base_url=base_url,
            state_path=state_path,
            trust_proxy=trust_proxy,
        )
        self._restore_pending()

    def _write_state_file(self, data):
        super()._write_state_file(data)
        if self._state_path is not None and self._state_path.exists():
            self._durable_state_store.persist(self._state_path)

    def _refresh_registry(self) -> bool:
        """Refresh the persisted OAuth registry into an already-warm instance."""
        if self._state_path is None:
            return False
        if not self._durable_state_store.restore(self._state_path):
            return False
        self._load_state()
        return True

    def _restore_pending(self) -> bool:
        """Restore the short-lived OAuth handoff state from durable storage."""
        store = self._durable_pending_store
        if store is None or not store.restore(self._pending_state_path):
            return False
        try:
            raw = json.loads(self._pending_state_path.read_text(encoding="utf-8"))
            pending_items = raw.get("pending", {})
            code_items = raw.get("auth_codes", {})
            if not isinstance(pending_items, dict) or not isinstance(code_items, dict):
                return False

            restored_pending: dict[str, _Pending] = {}
            for sid, item in pending_items.items():
                if not isinstance(sid, str) or not isinstance(item, dict):
                    continue
                client = OAuthClientInformationFull.model_validate(item["client"])
                params = AuthorizationParams.model_validate(item["params"])
                restored_pending[sid] = _Pending(
                    client,
                    params,
                    float(item["expiry"]),
                    int(item["attempts"]),
                )

            restored_codes: dict[str, AuthorizationCode] = {}
            for code, item in code_items.items():
                if not isinstance(code, str) or not isinstance(item, dict):
                    continue
                restored_codes[code] = AuthorizationCode.model_validate(item)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return False

        self._pending = restored_pending
        self.auth_codes = restored_codes
        self._prune_pending()
        return True

    def _persist_pending(self) -> None:
        """Persist pending login SIDs plus one-time authorization codes."""
        store = self._durable_pending_store
        if store is None:
            return
        self._prune_pending()
        payload = {
            "schema": 1,
            "pending": {
                sid: {
                    "client": entry.client.model_dump(mode="json"),
                    "params": entry.params.model_dump(mode="json"),
                    "expiry": entry.expiry,
                    "attempts": entry.attempts,
                }
                for sid, entry in self._pending.items()
            },
            "auth_codes": {
                code: auth_code.model_dump(mode="json")
                for code, auth_code in self.auth_codes.items()
            },
        }
        self._pending_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._pending_state_path.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        self._pending_state_path.chmod(0o600)
        store.persist(self._pending_state_path)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        self._refresh_registry()
        return await super().get_client(client_id)

    async def load_access_token(self, token: str) -> AccessToken | None:
        self._refresh_registry()
        return await super().load_access_token(token)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        self._refresh_registry()
        return await super().load_refresh_token(client, refresh_token)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        login_url = await super().authorize(client, params)
        self._persist_pending()
        return login_url

    async def _login(self, request):
        # A warm Vercel instance may have stale pending/code state created by
        # another instance. Refresh before both rendering and consuming the SID.
        self._restore_pending()
        response = await super()._login(request)
        if request.method == "POST":
            # Success consumes the SID and creates an auth code; failed attempts
            # update the SID attempt counter. Persist either transition.
            self._persist_pending()
        return response

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        self._restore_pending()
        return await super().load_authorization_code(client, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        token = await super().exchange_authorization_code(client, authorization_code)
        # Parent consumes the one-time code; mirror that deletion so replay cannot
        # succeed on a fresh function instance.
        self._persist_pending()
        return token
