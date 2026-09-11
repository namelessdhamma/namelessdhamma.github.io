from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastmcp import Context
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import resolve_notebook, resolve_source
from notebooklm.mcp.server import ClientFactory, create_server

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore
from .server_app import SERVICE_NAME, SERVICE_VERSION


def _drive_bridge_call(tool: str, args: dict) -> object:
    url = os.environ.get("ND_DRIVE_BRIDGE_URL", "").strip()
    token = os.environ.get("ND_DRIVE_BRIDGE_TOKEN", "").strip()
    if not url:
        raise RuntimeError("ND_DRIVE_BRIDGE_URL is not configured")
    if len(token) < 24:
        raise RuntimeError("ND_DRIVE_BRIDGE_TOKEN is not configured")
    req = Request(
        url,
        data=json.dumps({"tool": tool, "args": args}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-ND-Bridge-Key": token,
            "User-Agent": "nd-notebooklm-drive-adapter/1.0",
        },
    )
    try:
        with urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if token:
            body = body.replace(token, "[redacted]")
        raise RuntimeError(f"ND Drive bridge HTTP {exc.code}: {body[:700]}") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError("ND Drive bridge returned an invalid response")
    return payload.get("result")


def _register_drive_tools(mcp) -> None:
    @mcp.tool
    def docs_read(document_id: str) -> object:
        """Read a Google Doc with full text/tabs and the real Docs revisionId."""
        return _drive_bridge_call("docs_read", {"document_id": document_id})

    @mcp.tool
    def docs_append(
        document_id: str,
        text: str,
        expected_revision_id: str | None = None,
    ) -> object:
        """Append text with requiredRevisionId; stale expected revisions fail fast."""
        args = {"document_id": document_id, "text": text}
        if expected_revision_id:
            args["expected_revision_id"] = expected_revision_id
        return _drive_bridge_call("docs_append", args)

    @mcp.tool
    def docs_replace_exact(
        document_id: str,
        old_text: str,
        new_text: str,
        expected_revision_id: str | None = None,
    ) -> object:
        """Replace exactly one text occurrence with requiredRevisionId protection."""
        args = {
            "document_id": document_id,
            "old_text": old_text,
            "new_text": new_text,
        }
        if expected_revision_id:
            args["expected_revision_id"] = expected_revision_id
        return _drive_bridge_call("docs_replace_exact", args)

    @mcp.tool
    def drive_get_metadata(file_id: str) -> object:
        """Return Drive version, modifiedTime, MIME type, capabilities and checksums."""
        return _drive_bridge_call("drive_get_metadata", {"file_id": file_id})

    @mcp.tool
    def drive_get_currentness_token(file_id: str) -> object:
        """Return Drive currentness metadata plus Docs revisionId for native Docs."""
        return _drive_bridge_call("drive_get_currentness_token", {"file_id": file_id})

    @mcp.tool
    def drive_changes_start_token() -> object:
        """Get a Drive changes start page token for repair/reconciliation loops."""
        return _drive_bridge_call("drive_changes_start_token", {})

    @mcp.tool
    def drive_changes_list(page_token: str, page_size: int = 100) -> object:
        """List Drive changes from a page token."""
        return _drive_bridge_call(
            "drive_changes_list",
            {"page_token": page_token, "page_size": page_size},
        )


def _register_source_currentness_tools(mcp) -> None:
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
        }

    @mcp.tool
    async def source_refresh(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM refresh. Success is absence of an exception."""
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

    NotebookLM remains upstream-owned and non-authoritative. This adapter adds
    durable OAuth plus a thin Drive/Docs infrastructure bridge and provider-
    specific source currentness primitives used by ND reconciliation.
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

    _register_drive_tools(mcp)
    _register_source_currentness_tools(mcp)

    @mcp.tool
    def nd_ping_secure() -> str:
        return json.dumps(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "mode": "oauth-qualification",
                "version": SERVICE_VERSION,
                "drive_bridge_configured": bool(
                    os.environ.get("ND_DRIVE_BRIDGE_URL")
                    and os.environ.get("ND_DRIVE_BRIDGE_TOKEN")
                ),
            },
            separators=(",", ":"),
        )

    return mcp
