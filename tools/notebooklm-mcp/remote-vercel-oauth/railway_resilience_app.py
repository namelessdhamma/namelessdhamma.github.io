from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.railway_deployment import build_railway_app_from_environ
from nd_oauth.full_server import _drive_bridge_call
from resilience_direct_app import (
    bootstrap_exchange,
    bootstrap_import_sealed as direct_bootstrap_import_sealed,
    bootstrap_public_key,
    bootstrap_export_sealed,
    client_factory,
    github as direct_github,
    health,
    verify_oidc,
    _load_master_token_b64,
)


VERCEL_GITHUB_URL = 'https://nd-notebooklm-oauth-mcp.vercel.app/doctor/github'

_RESTART_LOCK = threading.Lock()
_RESTART_SCHEDULED = False

_WATCHDOG_PATH = Path('/data/nd-notebooklm/watchdog.json')
_WATCHDOG_INTERVAL_SECONDS = 300
_RENDER_HEALTH_URL = 'https://nd-notebooklm-direct.onrender.com/health'


async def _watchdog_local_semantic() -> dict:
    try:
        async with client_factory() as client:
            notebooks = await client.notebooks.list()
        return {
            'ok': True,
            'notebook_count': len(notebooks),
            'credential_configured': bool(_load_master_token_b64()),
        }
    except Exception as exc:
        return {
            'ok': False,
            'credential_configured': bool(_load_master_token_b64()),
            'error': str(exc)[:600],
        }


def _watchdog_vercel_semantic() -> dict:
    try:
        # This path authenticates to the Vercel MCP with the existing OAuth
        # password/refresh-token mechanism and therefore does not depend on
        # GitHub Actions OIDC.
        from railway_oauth_bridge_app import _mcp_call
        result = _mcp_call('notebook_list', {'limit': 20})
        return {
            'ok': bool(result.get('ok')),
            'server_info': result.get('serverInfo') or {},
            'error': None,
        }
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:600]}


def _watchdog_render_health() -> dict:
    req = urllib.request.Request(
        _RENDER_HEALTH_URL,
        method='GET',
        headers={
            'Accept': 'application/json',
            'User-Agent': 'nd-notebooklm-railway-watchdog/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode('utf-8', 'replace')
            body = json.loads(raw or '{}')
            credential = bool(body.get('credential_configured'))
            return {
                'ok': response.status == 200 and bool(body.get('ok')) and credential,
                'status': response.status,
                'credential_configured': credential,
                'service': body.get('service'),
                'backend': body.get('backend'),
                'error': None,
            }
    except Exception as exc:
        return {'ok': False, 'status': 0, 'error': str(exc)[:600]}


def _watchdog_write(report: dict) -> None:
    try:
        _WATCHDOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _WATCHDOG_PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp.replace(_WATCHDOG_PATH)
    except Exception as exc:
        print('ND_NOTEBOOKLM_WATCHDOG_PERSIST_ERROR ' + str(exc)[:400], flush=True)


def _watchdog_loop() -> None:
    time.sleep(20)
    while True:
        captured_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            local = asyncio.run(_watchdog_local_semantic())
        except Exception as exc:
            local = {'ok': False, 'error': str(exc)[:600]}
        vercel = _watchdog_vercel_semantic()
        render = _watchdog_render_health()
        checks = {
            'railway-local-semantic': local,
            'vercel-oauth-semantic': vercel,
            'render-health': render,
        }
        healthy = sum(1 for row in checks.values() if row.get('ok'))
        state = (
            'HEALTHY' if healthy == 3
            else 'DEGRADED' if healthy == 2
            else 'SEVERE' if healthy == 1
            else 'CRITICAL'
        )
        report = {
            'captured_at': captured_at,
            'control_plane': 'railway-persistent-watchdog',
            'github_actions_required': False,
            'interval_seconds': _WATCHDOG_INTERVAL_SECONDS,
            'state': state,
            'healthy_checks': healthy,
            'checks': checks,
        }
        _watchdog_write(report)
        print('ND_NOTEBOOKLM_WATCHDOG ' + json.dumps(report, ensure_ascii=False), flush=True)
        time.sleep(_WATCHDOG_INTERVAL_SECONDS)


threading.Thread(
    target=_watchdog_loop,
    name='nd-notebooklm-independent-watchdog',
    daemon=True,
).start()

def _schedule_runtime_reload() -> bool:
    """Restart Railway after a successful credential import so the MCP surface reloads FULL state."""
    global _RESTART_SCHEDULED
    with _RESTART_LOCK:
        if _RESTART_SCHEDULED:
            return False
        _RESTART_SCHEDULED = True

    def _reload() -> None:
        # Leave enough room for the reseed workflow's immediate direct semantic readback.
        time.sleep(30)
        os._exit(75)

    threading.Thread(target=_reload, name='nd-notebooklm-runtime-reload', daemon=True).start()
    return True

async def bootstrap_import_sealed(request: Request) -> JSONResponse:
    response = await direct_bootstrap_import_sealed(request)
    if response.status_code == 200:
        _schedule_runtime_reload()
    return response

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
        Route('/bootstrap/export-sealed', bootstrap_export_sealed, methods=['POST']),
        Mount('/', app=legacy_app),
    ],
    lifespan=legacy_app.lifespan,
)