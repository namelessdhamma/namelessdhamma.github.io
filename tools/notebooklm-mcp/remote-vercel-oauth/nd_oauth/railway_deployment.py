from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .file_state import FileOAuthStateStore
from .full_server import create_full_mcp
from .runtime import make_client_factory


_ENCRYPTED_MASTER_ENV = "ND_NOTEBOOKLM_MASTER_TOKEN_AESGCM_B64"
_ENCRYPTED_MASTER_PREFIX = b"ND1"
_ENCRYPTED_MASTER_AAD = b"ND_NOTEBOOKLM_RAILWAY_BACKUP_V1"


def _load_master_token(source: Mapping[str, str], password: str) -> str:
    plaintext = source.get("NOTEBOOKLM_MASTER_TOKEN_B64", "").strip()
    encrypted = source.get(_ENCRYPTED_MASTER_ENV, "").strip()
    if plaintext and encrypted:
        raise RuntimeError("Configure only one NotebookLM master-token source")
    if plaintext:
        return plaintext
    if not encrypted:
        raise RuntimeError(
            f"Missing NOTEBOOKLM_MASTER_TOKEN_B64 or {_ENCRYPTED_MASTER_ENV}"
        )

    try:
        payload = base64.b64decode(encrypted, validate=True)
        if not payload.startswith(_ENCRYPTED_MASTER_PREFIX):
            raise ValueError("invalid encrypted credential prefix")
        body = payload[len(_ENCRYPTED_MASTER_PREFIX) :]
        if len(body) < 16 + 12 + 16:
            raise ValueError("encrypted credential payload too short")
        salt, nonce, ciphertext = body[:16], body[16:28], body[28:]
        key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = AESGCM(key).decrypt(nonce, ciphertext, _ENCRYPTED_MASTER_AAD)
        master = raw.decode("utf-8").strip()
        if not master:
            raise ValueError("empty decrypted credential")
        return master
    except Exception as exc:
        raise RuntimeError("Unable to decrypt Railway NotebookLM credential") from exc


@dataclass(frozen=True)
class RailwayDeploymentConfig:
    base_url: str
    master_token_b64: str
    oauth_password: str
    login_password: str
    state_path: Path = Path("/tmp/nd-notebooklm-railway-oauth.json")
    persistent_dir: Path = Path("/data/nd-notebooklm")

    @classmethod
    def from_environ(cls, env: Mapping[str, str] | None = None) -> "RailwayDeploymentConfig":
        source = os.environ if env is None else env

        base_url = source.get("ND_NOTEBOOKLM_OAUTH_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("Missing ND_NOTEBOOKLM_OAUTH_BASE_URL")

        password = source.get("NOTEBOOKLM_MCP_OAUTH_PASSWORD", "").strip()
        if len(password) < 24:
            raise RuntimeError("NOTEBOOKLM_MCP_OAUTH_PASSWORD must be at least 24 characters")

        master_token = _load_master_token(source, password)

        login_password = source.get("ND_NOTEBOOKLM_OAUTH_LOGIN_PASSWORD", "").strip() or password
        if len(login_password) < 24:
            raise RuntimeError("ND_NOTEBOOKLM_OAUTH_LOGIN_PASSWORD must be at least 24 characters")

        state_path = Path(
            source.get(
                "ND_NOTEBOOKLM_OAUTH_STATE_PATH",
                "/tmp/nd-notebooklm-railway-oauth.json",
            )
        )
        persistent_dir = Path(
            source.get(
                "ND_NOTEBOOKLM_OAUTH_PERSIST_DIR",
                "/data/nd-notebooklm",
            )
        )

        return cls(
            base_url=base_url,
            master_token_b64=master_token,
            oauth_password=password,
            login_password=login_password,
            state_path=state_path,
            persistent_dir=persistent_dir,
        )


def build_railway_mcp(
    config: RailwayDeploymentConfig,
    *,
    registry_store=None,
    transient_store=None,
    client_factory=None,
):
    """Build the Railway standby with Railway-owned durable OAuth state."""
    registry_store = registry_store or FileOAuthStateStore(
        config.persistent_dir / "oauth-registry.json"
    )
    transient_store = transient_store or FileOAuthStateStore(
        config.persistent_dir / "oauth-transient.json"
    )
    client_factory = client_factory or make_client_factory(config.master_token_b64)

    return create_full_mcp(
        password=config.oauth_password,
        login_password=config.login_password,
        base_url=config.base_url,
        state_path=config.state_path,
        registry_store=registry_store,
        transient_store=transient_store,
        client_factory=client_factory,
        trust_proxy=True,
    )


def build_railway_app_from_environ(env: Mapping[str, str] | None = None):
    config = RailwayDeploymentConfig.from_environ(env)
    mcp = build_railway_mcp(config)
    return mcp.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        transport="http",
    )
