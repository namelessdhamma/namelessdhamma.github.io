from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from notebooklm.mcp._oauth import SelfHostedOAuthProvider, _Pending


class OAuthStateStore(Protocol):
    def restore(self, local_path: Path) -> bool: ...

    def persist(self, local_path: Path) -> None: ...


class BlobBackedOAuthProvider(SelfHostedOAuthProvider):
    """SelfHostedOAuthProvider with serverless-safe durable state mirroring.

    Upstream notebooklm-py persists OAuth clients/tokens to a local JSON file,
    while its short-lived password-login handoff lives only in memory. Vercel
    Functions can route consecutive OAuth requests to different instances, so we
    mirror both state classes to independent durable stores.

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

    def _restore_pending(self) -> bool:
        store = self._durable_pending_store
        if store is None or not store.restore(self._pending_state_path):
            return False
        try:
            raw = json.loads(self._pending_state_path.read_text(encoding="utf-8"))
            items = raw.get("pending", {})
            if not isinstance(items, dict):
                return False
            restored: dict[str, _Pending] = {}
            for sid, item in items.items():
                if not isinstance(sid, str) or not isinstance(item, dict):
                    continue
                client = OAuthClientInformationFull.model_validate(item["client"])
                params = AuthorizationParams.model_validate(item["params"])
                restored[sid] = _Pending(
                    client,
                    params,
                    float(item["expiry"]),
                    int(item["attempts"]),
                )
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return False

        self._pending = restored
        self._prune_pending()
        return True

    def _persist_pending(self) -> None:
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
        }
        self._pending_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._pending_state_path.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        self._pending_state_path.chmod(0o600)
        store.persist(self._pending_state_path)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        login_url = await super().authorize(client, params)
        self._persist_pending()
        return login_url

    async def _login(self, request):
        # A warm Vercel instance may have stale pending state created by another
        # instance. Refresh before both rendering and consuming the login SID.
        self._restore_pending()
        response = await super()._login(request)
        if request.method == "POST":
            # Successful login consumes the SID; failed attempts increment it.
            self._persist_pending()
        return response
