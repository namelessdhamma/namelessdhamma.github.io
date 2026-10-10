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

from notebooklm.mcp.server import create_server
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
            if len(secret) < 24 or not supplied or not hmac.compare_digest(secret, supplied):
                response = JSONResponse(
                    {"ok": False, "error": "unauthorized"}, status_code=401
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def health(request):
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
        "connection_state": "backend-only; ChatGPT App not rebound",
    })


async def native_catalog(request):
    """OIDC-only, non-sensitive readback of registered native tools."""
    if verify_oidc(request) is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    result = await native_mcp.get_tools()
    names = sorted(result.keys())
    return JSONResponse({
        "ok": True, "count": len(names), "tools": names,
        "external_file_transfer": False,
    })


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/bootstrap/public-key", bootstrap_public_key, methods=["GET"]),
        Route("/chatgpt/mcp/health", plugin_mcp_health, methods=["GET"]),
        Route("/github", github, methods=["POST"]),
        Route("/github/native-catalog", native_catalog, methods=["GET"]),
        Route("/chatgpt/mcp", plugin_mcp, methods=["GET", "POST"]),
        Mount("/native", app=HeaderGuard(native_asgi)),
    ],
    lifespan=native_asgi.lifespan,
)
