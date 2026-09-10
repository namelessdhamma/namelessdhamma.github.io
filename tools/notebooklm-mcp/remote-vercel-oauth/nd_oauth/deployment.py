from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .blob_state import BlobOAuthStateStore
from .full_server import create_full_mcp
from .runtime import make_client_factory


@dataclass(frozen=True)
class DeploymentConfig:
    base_url: str
    master_token_b64: str
    oauth_password: str
    state_path: Path = Path("/tmp/nd-notebooklm-oauth.json")

    @classmethod
    def from_environ(cls, env: Mapping[str, str] | None = None) -> "DeploymentConfig":
        source = os.environ if env is None else env

        explicit_base = source.get("ND_NOTEBOOKLM_OAUTH_BASE_URL", "").strip().rstrip("/")
        production_host = source.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip().strip("/")
        if explicit_base:
            base_url = explicit_base
        elif production_host:
            base_url = f"https://{production_host}"
        else:
            raise RuntimeError(
                "Missing ND_NOTEBOOKLM_OAUTH_BASE_URL or VERCEL_PROJECT_PRODUCTION_URL"
            )

        master_token = source.get("NOTEBOOKLM_MASTER_TOKEN_B64", "").strip()
        if not master_token:
            raise RuntimeError("Missing NOTEBOOKLM_MASTER_TOKEN_B64")

        # Vercel CLI/UI secret entry can accidentally preserve surrounding
        # whitespace. Normalize it at the deployment boundary so the connector
        # password entered by a client is compared against the intended value.
        password = source.get("NOTEBOOKLM_MCP_OAUTH_PASSWORD", "").strip()
        if len(password) < 24:
            raise RuntimeError("NOTEBOOKLM_MCP_OAUTH_PASSWORD must be at least 24 characters")

        state_path = Path(
            source.get("ND_NOTEBOOKLM_OAUTH_STATE_PATH", "/tmp/nd-notebooklm-oauth.json")
        )
        return cls(
            base_url=base_url,
            master_token_b64=master_token,
            oauth_password=password,
            state_path=state_path,
        )


def build_mcp(
    config: DeploymentConfig,
    *,
    registry_store=None,
    transient_store=None,
    client_factory=None,
):
    """Build the full upstream NotebookLM MCP with the ND durable OAuth layer."""
    registry_store = registry_store or BlobOAuthStateStore(
        "nd-notebooklm/oauth-registry.json"
    )
    transient_store = transient_store or BlobOAuthStateStore(
        "nd-notebooklm/oauth-transient.json"
    )
    return create_full_mcp(
        password=config.oauth_password,
        base_url=config.base_url,
        state_path=config.state_path,
        registry_store=registry_store,
        transient_store=transient_store,
        client_factory=client_factory,
        trust_proxy=True,
    )


def build_app_from_environ(env: Mapping[str, str] | None = None):
    """Build the Vercel ASGI entrypoint from platform-managed environment state."""
    config = DeploymentConfig.from_environ(env)
    client_factory = make_client_factory(config.master_token_b64)
    mcp = build_mcp(config, client_factory=client_factory)
    return mcp.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        transport="http",
    )
