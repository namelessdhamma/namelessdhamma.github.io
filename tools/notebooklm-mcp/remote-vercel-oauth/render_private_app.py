"""ND NotebookLM Render App: private direct MCP transport, no interactive OAuth.

Only the minimal public health/recipient-public-key endpoints are exposed.
All semantic MCP operations remain gated by the existing constant-time
x-nd-notebooklm-plugin-key check in resilience_direct_app.py.

This does not grant anonymous access to the user's private NotebookLM corpus.
It returns plain MCP JSON/TextContent with no ResourceLink or external
download attachments, matching the existing direct Render MCP surface.
"""
from __future__ import annotations

import os
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from resilience_direct_app import (
    bootstrap_public_key, plugin_mcp, plugin_mcp_health, github, _load_master_token_b64,
)

async def health(request):
    try:
        configured = bool(_load_master_token_b64())
        error = None
    except Exception as exc:
        configured = False
        error = type(exc).__name__
    return JSONResponse({
        "ok": True,
        "service": "nd-notebooklm-render-app",
        "transport": "private-header-mcp",
        "provider_credentials_configured": configured,
        "credential_error_type": error,
        "oauth_login_required": False,
        "file_transfer": "mcp-inline-only",
    })

app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/bootstrap/public-key", bootstrap_public_key, methods=["GET"]),
    Route("/chatgpt/mcp/health", plugin_mcp_health, methods=["GET"]),
    Route("/github", github, methods=["POST"]),
    Route("/chatgpt/mcp", plugin_mcp, methods=["GET","POST"]),
])
