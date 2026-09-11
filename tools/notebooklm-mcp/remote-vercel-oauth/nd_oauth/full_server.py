from __future__ import annotations

import json
from pathlib import Path

from notebooklm.mcp.server import ClientFactory, create_server

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore
from .server_app import SERVICE_NAME, SERVICE_VERSION


def create_full_mcp(
    *,
    password: str,
    login_password: str | None = None,
    base_url: str,
    state_path: Path,
    registry_store: OAuthStateStore,
    transient_store: OAuthStateStore,
    client_factory: ClientFactory | None = None,
    trust_proxy: bool = False,
):
    """Compose notebooklm-py's complete tool surface with durable OAuth.

    The NotebookLM implementation remains upstream-owned; this adapter supplies
    only the authentication/state layer required by a multi-instance serverless
    deployment and a harmless versioned qualification tool.
    """
    auth = BlobBackedOAuthProvider(
        password=password,
        login_password=login_password,
        base_url=base_url,
        state_path=state_path,
        state_store=registry_store,
        pending_store=transient_store,
        trust_proxy=trust_proxy,
    )
    mcp = create_server(
        profile="default",
        backend="android",
        client_factory=client_factory,
        auth=auth,
    )

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
