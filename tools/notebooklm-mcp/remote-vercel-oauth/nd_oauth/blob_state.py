from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class BlobOAuthStateStore:
    """Mirror the OAuth registry/token JSON between /tmp and private Vercel Blob.

    The Vercel SDK import is lazy so unit tests do not require platform packages.
    The object stores only the OAuth provider's already-serialized JSON; it never
    receives the Google master token.
    """

    def __init__(
        self,
        pathname: str,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pathname = pathname
        self._client_factory = client_factory or self._default_client_factory

    @staticmethod
    def _default_client_factory() -> Any:
        from vercel.blob import BlobClient

        return BlobClient()

    @staticmethod
    def _read_stream(stream: Any) -> bytes:
        return b"".join(stream)

    @staticmethod
    def _safe_shape(raw: bytes) -> str:
        """Return structural OAuth-state diagnostics without exposing credentials."""
        try:
            data = json.loads(raw)
        except Exception:
            return f"bytes={len(raw)} json=invalid sha={hashlib.sha256(raw).hexdigest()[:12]}"
        if not isinstance(data, dict):
            return f"bytes={len(raw)} json=nonobject sha={hashlib.sha256(raw).hexdigest()[:12]}"
        clients = data.get("clients", {}) if isinstance(data.get("clients", {}), dict) else {}
        client_hashes = sorted(hashlib.sha256(str(cid).encode()).hexdigest()[:12] for cid in clients)
        access = data.get("access_tokens", {}) if isinstance(data.get("access_tokens", {}), dict) else {}
        refresh = data.get("refresh_tokens", {}) if isinstance(data.get("refresh_tokens", {}), dict) else {}
        pending = data.get("pending", {}) if isinstance(data.get("pending", {}), dict) else {}
        codes = data.get("auth_codes", {}) if isinstance(data.get("auth_codes", {}), dict) else {}
        return (
            f"bytes={len(raw)} clients={len(clients)} client_hashes={client_hashes} "
            f"access={len(access)} refresh={len(refresh)} pending={len(pending)} codes={len(codes)} "
            f"sha={hashlib.sha256(raw).hexdigest()[:12]}"
        )

    def restore(self, local_path: Path) -> bool:
        client = self._client_factory()
        try:
            try:
                result = client.get(self.pathname, access="private", use_cache=False)
            except Exception as exc:
                # The official SDK returns None for a missing blob on get(); older
                # runtime versions may raise a typed not-found error. Treat only a
                # clearly named not-found condition as an empty first boot.
                if type(exc).__name__ == "BlobNotFoundError":
                    return False
                raise
            if result is None or getattr(result, "status_code", None) != 200:
                return False
            stream = getattr(result, "stream", None)
            if stream is None:
                return False
            raw = self._read_stream(stream)
            logger.info("OAuth blob restore %s: %s", self.pathname, self._safe_shape(raw))
            local_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            local_path.write_bytes(raw)
            local_path.chmod(0o600)
            return True
        finally:
            client.close()

    def persist(self, local_path: Path) -> None:
        raw = local_path.read_bytes()
        logger.info("OAuth blob persist %s: %s", self.pathname, self._safe_shape(raw))
        client = self._client_factory()
        try:
            client.put(
                self.pathname,
                raw,
                access="private",
                content_type="application/json",
                add_random_suffix=False,
                overwrite=True,
                cache_control_max_age=60,
            )
        finally:
            client.close()
