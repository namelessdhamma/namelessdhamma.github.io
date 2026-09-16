from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.railway_deployment import build_railway_app_from_environ
from nd_oauth.full_server import _drive_bridge_call
from resilience_direct_app import (
    bootstrap_exchange,
    bootstrap_import_sealed,
    bootstrap_public_key,
    github as direct_github,
    health,
    verify_oidc,
    _load_master_token_b64,
)


VERCEL_GITHUB_URL = 'https://nd-notebooklm-oauth-mcp.vercel.app/doctor/github'

def _relay_to_vercel(body: bytes, vercel_oidc: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        VERCEL_GITHUB_URL,
        data=body,
        method='POST',
        headers={
            'Authorization': 'Bearer ' + vercel_oidc,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'nd-notebooklm-railway-oidc-relay/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read().decode('utf-8', 'replace')
            return response.status, json.loads(raw or '{}')
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {'ok': False, 'error': 'upstream_http_' + str(exc.code)}
    except Exception as exc:
        return 502, {'ok': False, 'error': str(exc)[:500]}

async def github_relay(request: Request) -> JSONResponse:
    # First authenticate the Railway hop itself with the existing direct-runtime OIDC token.
    claims = verify_oidc(request)
    if claims is None:
        return JSONResponse({'ok': False, 'error': 'not_found'}, status_code=404)

    # Prefer a truly independent local credential whenever one becomes available.
    if _load_master_token_b64():
        return await direct_github(request)

    # Otherwise preserve route continuity without re-authenticating Google:
    # GitHub mints a second, short-lived OIDC token for the already-qualified
    # Vercel NotebookLM provider bridge and Railway forwards only this request.
    vercel_oidc = request.headers.get('x-nd-vercel-oidc', '').strip()
    if not vercel_oidc:
        return JSONResponse(
            {'ok': False, 'error': 'upstream_oidc_missing', 'relay': 'railway_to_vercel'},
            status_code=503,
        )
    body = await request.body()
    status, data = await asyncio.to_thread(_relay_to_vercel, body, vercel_oidc)
    if isinstance(data, dict):
        data.setdefault('relay', 'railway_to_vercel')
        data.setdefault('railway_oidc_repository', claims.get('repository'))
    return JSONResponse(data, status_code=status)


_DRIVE_GITHUB_READ_TOOLS = {
    'drive_get_metadata',
    'drive_get_currentness_token',
    'docs_read',
}

async def drive_github(request: Request) -> JSONResponse:
    claims = verify_oidc(request)
    if claims is None:
        return JSONResponse({'ok': False, 'error': 'not_found'}, status_code=404)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'invalid_json'}, status_code=400)
    tool = str(payload.get('tool') or '').strip()
    args = payload.get('args') or {}
    if tool not in _DRIVE_GITHUB_READ_TOOLS:
        return JSONResponse({'ok': False, 'error': 'tool_not_allowed'}, status_code=400)
    if not isinstance(args, dict):
        return JSONResponse({'ok': False, 'error': 'invalid_args'}, status_code=400)
    try:
        result = await asyncio.to_thread(_drive_bridge_call, tool, args)
        return JSONResponse({
            'ok': True,
            'tool': tool,
            'result': result,
            'oidc_repository': claims.get('repository'),
            'mutation': False,
        })
    except Exception as exc:
        return JSONResponse({'ok': False, 'tool': tool, 'error': str(exc)[:1600]}, status_code=502)


legacy_app = build_railway_app_from_environ()

app = Starlette(
    routes=[
        Route('/health', health, methods=['GET']),
        Route('/github', github_relay, methods=['POST']),
        Route('/drive/github', drive_github, methods=['POST']),
        Route('/bootstrap/exchange', bootstrap_exchange, methods=['POST']),
        Route('/bootstrap/public-key', bootstrap_public_key, methods=['GET']),
        Route('/bootstrap/import-sealed', bootstrap_import_sealed, methods=['POST']),
        Mount('/', app=legacy_app),
    ],
    lifespan=legacy_app.lifespan,
)
