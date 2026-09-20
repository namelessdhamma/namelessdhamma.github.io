from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from fastmcp import Context
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import resolve_notebook, resolve_source
from notebooklm.mcp.server import ClientFactory, create_server

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore
from .server_app import SERVICE_NAME, SERVICE_VERSION


async def _read_registry_exact_via_client(client) -> dict:
    file_id = "16TCMHEb9erk4rONK9poi6-62hNfSELKt"
    session = getattr(client, "_android_session", None)
    bearer_provider = getattr(client, "_android_bearer_provider", None)
    if session is None or bearer_provider is None:
        raise RuntimeError("android_drive_bearer_unavailable")
    async with session.operation_scope("nd.registry_exact_recovery") as lease:
        credential = await bearer_provider.get(lease.epoch)
        token = credential.token
        url = (
            "https://www.googleapis.com/drive/v3/files/"
            + urllib.parse.quote(file_id, safe="")
            + "?alt=media&supportsAllDrives=true"
        )
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": "Bearer " + token,
                "User-Agent": "nd-true-writer-registry-recovery/1.0",
            },
        )
        try:
            raw = await __import__("asyncio").to_thread(
                lambda: urllib.request.urlopen(req, timeout=60).read()
            )
        finally:
            token = ""
    if len(raw) > 500000:
        raise RuntimeError("registry_recovery_too_large")
    text = raw.decode("utf-8-sig")
    parsed = json.loads(text)
    return {
        "file_id": file_id,
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text_b64": base64.b64encode(raw).decode("ascii"),
        "registry_version": parsed.get("version"),
        "component_count": len(parsed.get("components") or []),
    }


def create_full_mcp(
    *,
    password: str,
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
    async def source_check_freshness(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM freshness check for one source."""
        client = await get_client(ctx)
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
        client = await get_client(ctx)
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
        client = await get_client(ctx)
        recovery = await _read_registry_exact_via_client(client)
        return json.dumps(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "mode": "oauth-qualification",
                "version": SERVICE_VERSION,
                "registry_exact_recovery": recovery,
            },
            separators=(",", ":"),
        )

    return mcp