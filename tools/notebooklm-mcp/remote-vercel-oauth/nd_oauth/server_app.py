from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore

SERVICE_NAME = "nd-notebooklm-oauth-mcp"
SERVICE_VERSION = "0.1.0"


def create_mcp(
    *,
    password: str,
    base_url: str,
    state_path: Path,
    registry_store: OAuthStateStore,
    transient_store: OAuthStateStore,
    trust_proxy: bool = False,
) -> FastMCP:
    """Create the isolated OAuth qualification MCP surface.

    This server deliberately exposes only a safe authenticated ping until the
    OAuth transport is live-qualified. NotebookLM account access is added only
    after the OAuth control plane is proven end-to-end.
    """
    auth = BlobBackedOAuthProvider(
        password=password,
        base_url=base_url,
        state_path=state_path,
        state_store=registry_store,
        pending_store=transient_store,
        trust_proxy=trust_proxy,
    )
    mcp = FastMCP(name="ND NotebookLM OAuth MCP", auth=auth)

    @mcp.tool
    def nd_ping_secure() -> str:
        return json.dumps(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "mode": "oauth-qualification",
                "version": SERVICE_VERSION,
            },
            separators=(",", ":"),
        )

    return mcp
