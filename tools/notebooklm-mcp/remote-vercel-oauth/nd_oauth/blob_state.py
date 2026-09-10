from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


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
            local_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            local_path.write_bytes(raw)
            local_path.chmod(0o600)
            return True
        finally:
            client.close()

    def persist(self, local_path: Path) -> None:
        raw = local_path.read_bytes()
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
