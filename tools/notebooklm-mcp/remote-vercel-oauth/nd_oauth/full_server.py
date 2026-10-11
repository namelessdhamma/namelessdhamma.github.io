from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy
from fastmcp.server.providers.proxy import ProxyClient

from fastmcp import Context
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._context import get_client
from notebooklm.mcp._filelink import FileTransferConfig
from notebooklm.mcp._resolve import resolve_notebook, resolve_source
from notebooklm.mcp.server import ClientFactory, create_server

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore
from .server_app import SERVICE_NAME, SERVICE_VERSION


def create_full_mcp(
    *,
    password: str,
    base_url: str,
    state_path: Path,
    registry_store: OAuthStateStore,
    transient_store: OAuthStateStore,
    client_factory: ClientFactory | None = None,
    file_transfer: FileTransferConfig | None = None,
    trust_proxy: bool = False,
    render_proxy_url: str | None = None,
    render_proxy_key: str | None = None,
):
    """Compose notebooklm-py's complete tool surface with durable OAuth.

    The NotebookLM implementation remains upstream-owned; this adapter supplies
    only the authentication/state layer required by a multi-instance serverless
    deployment and a harmless versioned qualification tool.
    """
    auth = BlobBackedOAuthProvider(
        password=password,
        base_url=base_url,
        state_path=state_path,
        state_store=registry_store,
        pending_store=transient_store,
        trust_proxy=trust_proxy,
    )
    if render_proxy_url and render_proxy_key:
        # Keep the SAME durable OAuth provider and ChatGPT App identity.
        # Only execution goes to private Render; never forward caller bearer tokens
        # or cookies to the backend. Render requires its independent service key.
        transport = StreamableHttpTransport(
            render_proxy_url,
            headers={"x-nd-notebooklm-plugin-key": render_proxy_key},
        )
        backend = ProxyClient(transport)
        remote = create_proxy(backend, name="ND-NotebookLM-Render")
        # FastMCP 3.4.2 unconditionally enables incoming-header forwarding
        # in ProxyClient and create_proxy; explicitly disable it AFTER both
        # constructors to prevent ChatGPT bearer tokens leaking to Render.
        backend.transport.forward_incoming_headers = False
        mcp = FastMCP(
            "ND NotebookLM OAuth Edge",
            auth=auth,
        )
        mcp.mount(remote)
        # Native Render owns the 41 tool schemas; no Vercel-side file links.
        return mcp
    mcp = create_server(
        profile="default",
        backend="android",
        client_factory=client_factory,
        file_transfer=file_transfer,
        auth=auth,
    )

    @mcp.tool
    async def source_check_freshness(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM freshness check for one source."""
        client = get_client(ctx)
        nb_id = await resolve_notebook(client, notebook)
        src_id = await resolve_source(client, nb_id, source)
        result = await client.sources.check_freshness(nb_id, src_id)
        return {
            "notebook_id": nb_id,
            "source_id": src_id,
            "freshness": to_jsonable(result),
            "provider_specific": True,
        }

    @mcp.tool
    async def source_refresh(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM refresh; success means no exception."""
        client = get_client(ctx)
        nb_id = await resolve_notebook(client, notebook)
        src_id = await resolve_source(client, nb_id, source)
        await client.sources.refresh(nb_id, src_id)
        return {
            "ok": True,
            "notebook_id": nb_id,
            "source_id": src_id,
            "provider_specific": True,
        }

    @mcp.tool
    async def nd_ping_secure(ctx: Context) -> str:
        """Harmless authenticated service/version health check."""
        return json.dumps(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "mode": "secure-health",
                "version": SERVICE_VERSION,
            },
            separators=(",", ":"),
        )

    return mcp
