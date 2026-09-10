from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .blob_state import BlobOAuthStateStore
from .full_server import create_full_mcp
from .runtime import make_client_factory


@dataclass(frozen=True)
class RailwayDeploymentConfig:
    base_url: str
    master_token_b64: str
    oauth_password: str
    state_path: Path = Path("/tmp/nd-notebooklm-railway-oauth.json")
    registry_blob_path: str = "nd-notebooklm-railway/oauth-registry.json"
    transient_blob_path: str = "nd-notebooklm-railway/oauth-transient.json"

    @classmethod
    def from_environ(cls, env: Mapping[str, str] | None = None) -> "RailwayDeploymentConfig":
        source = os.environ if env is None else env

        base_url = source.get("ND_NOTEBOOKLM_OAUTH_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("Missing ND_NOTEBOOKLM_OAUTH_BASE_URL")

        master_token = source.get("NOTEBOOKLM_MASTER_TOKEN_B64", "").strip()
        if not master_token:
            raise RuntimeError("Missing NOTEBOOKLM_MASTER_TOKEN_B64")

        password = source.get("NOTEBOOKLM_MCP_OAUTH_PASSWORD", "").strip()
        if len(password) < 24:
            raise RuntimeError("NOTEBOOKLM_MCP_OAUTH_PASSWORD must be at least 24 characters")

        state_path = Path(
            source.get(
                "ND_NOTEBOOKLM_OAUTH_STATE_PATH",
                "/tmp/nd-notebooklm-railway-oauth.json",
            )
        )
        registry_blob_path = source.get(
            "ND_NOTEBOOKLM_OAUTH_REGISTRY_BLOB",
            "nd-notebooklm-railway/oauth-registry.json",
        ).strip()
        transient_blob_path = source.get(
            "ND_NOTEBOOKLM_OAUTH_TRANSIENT_BLOB",
            "nd-notebooklm-railway/oauth-transient.json",
        ).strip()

        if not registry_blob_path or not transient_blob_path:
            raise RuntimeError("Railway OAuth Blob paths must be non-empty")
        if registry_blob_path == transient_blob_path:
            raise RuntimeError("Railway OAuth registry and transient Blob paths must differ")

        return cls(
            base_url=base_url,
            master_token_b64=master_token,
            oauth_password=password,
            state_path=state_path,
            registry_blob_path=registry_blob_path,
            transient_blob_path=transient_blob_path,
        )


def build_railway_mcp(
    config: RailwayDeploymentConfig,
    *,
    registry_store=None,
    transient_store=None,
    client_factory=None,
):
    """Build an independent Railway runtime using separate durable OAuth namespaces."""
    registry_store = registry_store or BlobOAuthStateStore(config.registry_blob_path)
    transient_store = transient_store or BlobOAuthStateStore(config.transient_blob_path)
    client_factory = client_factory or make_client_factory(config.master_token_b64)

    return create_full_mcp(
        password=config.oauth_password,
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
