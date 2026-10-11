"""ND Render NotebookLM private MCP app.

Preserves the existing 12-tool inline JSON interface and adds the full
upstream NotebookLM native MCP tool set under a private header-authorized
mount. The upstream file transfer broker is deliberately NOT configured,
so native Studio tools do not emit signed external attachment links.

Private NotebookLM data are never served to anonymous callers.
"""
from __future__ import annotations

import hmac
import os
import asyncio

from fastmcp import Client, Context
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import resolve_notebook, resolve_source

from notebooklm.mcp.server import create_server
from nd_linkless_studio import install as install_linkless_studio
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from resilience_direct_app import (
    _load_master_token_b64,
    bootstrap_public_key,
    client_factory,
    github,
    plugin_mcp,
    plugin_mcp_health,
    verify_oidc,
)

_KEY_ENV = "ND_NOTEBOOKLM_PLUGIN_KEY"
_KEY_HEADER = b"x-nd-notebooklm-plugin-key"

native_mcp = create_server(
    profile="default",
    backend="android",
    client_factory=client_factory,
    file_transfer=None,
)
# Keep full parity with the three ND-specific Vercel extension tools.
# These run in the Render process with its own provider credentials.
@native_mcp.tool
async def source_check_freshness(ctx: Context, notebook: str, source: str) -> object:
    """Check provider freshness for a NotebookLM source (Render execution)."""
    client = get_client(ctx)
    nb_id = await resolve_notebook(client, notebook)
    src_id = await resolve_source(client, nb_id, source)
    return {
        "notebook_id": nb_id,
        "source_id": src_id,
        "freshness": to_jsonable(await client.sources.check_freshness(nb_id, src_id)),
        "provider_specific": True,
        "executed_by": "render-private",
    }


@native_mcp.tool
async def source_refresh(ctx: Context, notebook: str, source: str) -> object:
    """Refresh a NotebookLM source in Render; no second replay on ambiguity."""
    client = get_client(ctx)
    nb_id = await resolve_notebook(client, notebook)
    src_id = await resolve_source(client, nb_id, source)
    await client.sources.refresh(nb_id, src_id)
    return {
        "ok": True,
        "notebook_id": nb_id,
        "source_id": src_id,
        "provider_specific": True,
        "executed_by": "render-private",
    }


@native_mcp.tool
def nd_ping_secure() -> dict:
    """Authenticated Render MCP capability heartbeat without private source data."""
    return {
        "ok": True, "service": "nd-notebooklm-render-app",
        "runtime": "render-private", "file_transfer": "none",
        "provider": "NotebookLM",
    }


# Replace upstream remote Studio download with authenticated inline export.
install_linkless_studio(native_mcp)

native_asgi = native_mcp.http_app(
    path="/mcp",
    stateless_http=True,
    json_response=True,
    transport="http",
)


class HeaderGuard:
    """Request-independent header authorization for the native MCP mount."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = dict(scope.get("headers", [])).get(_KEY_HEADER, b"")
            secret = os.environ.get(_KEY_ENV, "").encode("utf-8")
            proxy_secret = os.environ.get("ND_NOTEBOOKLM_RENDER_PROXY_SHARED_KEY", "").encode("utf-8")
            private_key_ok = len(secret) >= 24 and bool(supplied) and hmac.compare_digest(secret, supplied)
            proxy_key_ok = len(proxy_secret) >= 40 and bool(supplied) and hmac.compare_digest(proxy_secret, supplied)
            if not (private_key_ok or proxy_key_ok):
                response = JSONResponse(
                    {"ok": False, "error": "unauthorized"}, status_code=401
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def health(request):
    public_tool_count = len(await native_mcp.list_tools())
    try:
        configured = bool(_load_master_token_b64())
    except Exception:
        configured = False
    return JSONResponse({
        "ok": True,
        "service": "nd-notebooklm-render-app",
        "transport": "private-header-mcp",
        "provider_credentials_configured": configured,
        "oauth_login_required": False,
        "file_transfer": "inline-json; no automatic ResourceLinks",
        "native_mcp_available": True,
        "native_tool_count": public_tool_count,
        "connection_state": "backend-only; ChatGPT App not rebound",
    })


async def native_catalog(request):
    """OIDC-only, non-sensitive readback of registered native tools."""
    if verify_oidc(request) is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    result = await native_mcp.list_tools()
    names = sorted(tool.name for tool in result)
    return JSONResponse({
        "ok": True, "count": len(names), "tools": names,
        "external_file_transfer": False,
    })


async def native_read_qualification(request):
    """OIDC-only actual native notebook_list tool call, returning counts only."""
    if verify_oidc(request) is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    try:
        async with Client(native_mcp) as client:
            result = await asyncio.wait_for(
                client.call_tool("notebook_list", {}), timeout=55
            )
        value = result.data
        if not isinstance(value, dict):
            return JSONResponse(
                {"ok": False, "error": "unexpected_provider_shape"},
                status_code=502,
            )
        notebooks = value.get("notebooks", [])
        count = value.get("total", value.get("count"))
        if not isinstance(count, int) and isinstance(notebooks, list):
            count = len(notebooks)
        verified = not result.is_error and isinstance(count, int) and count > 0
        return JSONResponse({
            "ok": verified,
            "provider": "NotebookLM",
            "route": "render-private-native-mcp",
            "operation": "notebook_list",
            "notebook_count": count if verified else None,
            "readback": "native_mcp_tool_call",
        }, status_code=200 if verified else 502)
    except Exception as exc:
        return JSONResponse({
            "ok": False, "error_type": type(exc).__name__,
            "route": "render-private-native-mcp",
        }, status_code=502)


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/bootstrap/public-key", bootstrap_public_key, methods=["GET"]),
        Route("/chatgpt/mcp/health", plugin_mcp_health, methods=["GET"]),
        Route("/github", github, methods=["POST"]),
        Route("/github/native-catalog", native_catalog, methods=["GET"]),
        Route("/github/native-read-check", native_read_qualification, methods=["GET"]),
        Route("/chatgpt/mcp", plugin_mcp, methods=["GET", "POST"]),
        Mount("/native", app=HeaderGuard(native_asgi)),
    ],
    lifespan=native_asgi.lifespan,
)
