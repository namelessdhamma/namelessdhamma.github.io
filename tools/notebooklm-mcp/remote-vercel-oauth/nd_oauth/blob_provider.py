from __future__ import annotations

from pathlib import Path
from typing import Protocol

from notebooklm.mcp._oauth import SelfHostedOAuthProvider


class OAuthStateStore(Protocol):
    def restore(self, local_path: Path) -> bool: ...

    def persist(self, local_path: Path) -> None: ...


class BlobBackedOAuthProvider(SelfHostedOAuthProvider):
    """SelfHostedOAuthProvider with its durable registry mirrored externally.

    Upstream notebooklm-py intentionally persists OAuth clients/tokens to a local
    JSON file. Vercel Functions have ephemeral filesystems, so restore the JSON
    before upstream initialization and mirror every upstream state write to the
    durable store. The Google master token is not handled by this class.
    """

    def __init__(
        self,
        *,
        password: str,
        base_url: str,
        state_path: Path,
        state_store: OAuthStateStore,
        trust_proxy: bool = False,
    ) -> None:
        self._durable_state_store = state_store
        state_store.restore(state_path)
        super().__init__(
            password=password,
            base_url=base_url,
            state_path=state_path,
            trust_proxy=trust_proxy,
        )

    def _write_state_file(self, data):
        super()._write_state_file(data)
        if self._state_path is not None and self._state_path.exists():
            self._durable_state_store.persist(self._state_path)
