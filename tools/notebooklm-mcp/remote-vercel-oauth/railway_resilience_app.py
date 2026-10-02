from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook

from nd_oauth.railway_deployment import build_railway_app_from_environ
from nd_oauth.full_server import _drive_bridge_call
from nd_drive_direct import bridge_authorized, direct_drive_call, drive_health as direct_drive_health
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
PLUGIN_KEY_ENV = 'ND_NOTEBOOKLM_PLUGIN_KEY'
PLUGIN_HEADER = 'x-nd-notebooklm-plugin-key'

_RESTART_LOCK = threading.Lock()
_RESTART_SCHEDULED = False

_WATCHDOG_PATH = Path('/data/nd-notebooklm/watchdog.json')
_WATCHDOG_INTERVAL_SECONDS = 300
_RENDER_HEALTH_URL = 'https://nd-notebooklm-direct.onrender.com/health'
_VERCEL_HEALTH_URL = 'https://nd-notebooklm-oauth-mcp.vercel.app/doctor/health'


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


def _watchdog_vercel_provider_health() -> dict:
    req = urllib.request.Request(
        _VERCEL_HEALTH_URL,
        method='GET',
        headers={
            'Accept': 'application/json',
            'User-Agent': 'nd-notebooklm-railway-watchdog/1.1',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode('utf-8', 'replace')
            body = json.loads(raw or '{}')
            configured = bool(body.get('master_token_configured'))
            return {
                'ok': response.status == 200 and bool(body.get('ok')) and configured,
                'status': response.status,
                'master_token_configured': configured,
                'service': body.get('service'),
                'provider': body.get('provider'),
                'error': None,
            }
    except Exception as exc:
        return {'ok': False, 'status': 0, 'error': str(exc)[:600]}


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
        vercel = _watchdog_vercel_provider_health()
        render = _watchdog_render_health()
        checks = {
            'railway-local-semantic': local,
            'vercel-provider-health': vercel,
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

async def watchdog_status(request: Request) -> JSONResponse:
    try:
        if not _WATCHDOG_PATH.exists():
            return JSONResponse({
                'ok': False,
                'state': 'STARTING',
                'control_plane': 'railway-persistent-watchdog',
            }, status_code=503)
        data = json.loads(_WATCHDOG_PATH.read_text(encoding='utf-8'))
        return JSONResponse({'ok': True, **data})
    except Exception as exc:
        return JSONResponse({
            'ok': False,
            'state': 'UNKNOWN',
            'control_plane': 'railway-persistent-watchdog',
            'error': str(exc)[:300],
        }, status_code=503)


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



_NOTEBOOKLM_MCP_TOOLS = [
    {
        'name': 'notebook_list',
        'description': 'List NotebookLM notebooks visible to the current ND provider account.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'notebook_get',
        'description': 'Get one NotebookLM notebook by ID or resolvable title.',
        'inputSchema': {
            'type': 'object',
            'properties': {'notebook': {'type': 'string'}},
            'required': ['notebook'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_list',
        'description': 'List sources in one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {'notebook': {'type': 'string'}},
            'required': ['notebook'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_fulltext',
        'description': 'Read provider-extracted full text for one source.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'source_id': {'type': 'string'},
            },
            'required': ['notebook', 'source_id'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'chat_ask',
        'description': 'Ask a source-grounded question in one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'question': {'type': 'string'},
            },
            'required': ['notebook', 'question'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'notebook_create',
        'description': 'Create a disposable or production NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {'title': {'type': 'string'}},
            'required': ['title'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'notebook_rename',
        'description': 'Rename one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'title': {'type': 'string'},
            },
            'required': ['notebook', 'title'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'notebook_delete',
        'description': 'Delete one NotebookLM notebook. Requires confirm=true.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'confirm': {'type': 'boolean'},
            },
            'required': ['notebook', 'confirm'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_add_text',
        'description': 'Add a text source to one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'title': {'type': 'string'},
                'content': {'type': 'string'},
            },
            'required': ['notebook', 'title', 'content'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_add_url',
        'description': 'Add a public URL source to one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'url': {'type': 'string'},
            },
            'required': ['notebook', 'url'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_add_drive',
        'description': 'Add a Google Drive source to one NotebookLM notebook.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'file_id': {'type': 'string'},
                'title': {'type': 'string'},
            },
            'required': ['notebook', 'file_id', 'title'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'source_delete',
        'description': 'Delete one NotebookLM source. Requires confirm=true.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'notebook': {'type': 'string'},
                'source_id': {'type': 'string'},
                'confirm': {'type': 'boolean'},
            },
            'required': ['notebook', 'source_id', 'confirm'],
            'additionalProperties': False,
        },
    },
]


def _plugin_authorized(request: Request) -> bool:
    expected = os.environ.get(PLUGIN_KEY_ENV, '').strip()
    supplied = request.headers.get(PLUGIN_HEADER, '').strip()
    return len(expected) >= 24 and bool(supplied) and hmac.compare_digest(expected, supplied)


async def _plugin_execute(operation: str, args: dict) -> dict:
    if not _load_master_token_b64():
        raise RuntimeError('credential_unconfigured')
    async with client_factory() as client:
        if operation == 'notebook_list':
            items = await client.notebooks.list()
            result = {'count': len(items), 'notebooks': to_jsonable(items)}
        elif operation == 'notebook_get':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            result = {'notebook': to_jsonable(await client.notebooks.get(nb))}
        elif operation == 'source_list':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            items = await client.sources.list(nb)
            result = {'notebook_id': nb, 'count': len(items), 'sources': to_jsonable(items)}
        elif operation == 'source_fulltext':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            sid = str(args.get('source_id') or '').strip()
            if not sid:
                raise ValueError('missing_source_id')
            result = {
                'notebook_id': nb,
                'source_id': sid,
                'fulltext': to_jsonable(await client.sources.get_fulltext(nb, sid)),
            }
        elif operation == 'chat_ask':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            question = str(args.get('question') or '').strip()
            if not question:
                raise ValueError('missing_question')
            result = {'notebook_id': nb, 'answer': to_jsonable(await client.chat.ask(nb, question))}
        elif operation == 'notebook_create':
            title = str(args.get('title') or '').strip()
            if not title:
                raise ValueError('missing_title')
            result = {'notebook': to_jsonable(await client.notebooks.create(title))}
        elif operation == 'notebook_rename':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            title = str(args.get('title') or '').strip()
            if not title:
                raise ValueError('missing_title')
            result = {'notebook': to_jsonable(await client.notebooks.rename(nb, title))}
        elif operation == 'notebook_delete':
            if args.get('confirm') is not True:
                raise ValueError('confirm_required')
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            await client.notebooks.delete(nb)
            result = {'deleted_notebook_id': nb}
        elif operation == 'source_add_text':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            title = str(args.get('title') or '').strip()
            content = str(args.get('content') or '')
            if not title or not content:
                raise ValueError('missing_title_or_content')
            result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_text(nb, title, content))}
        elif operation == 'source_add_url':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            url = str(args.get('url') or '').strip()
            if not url.startswith(('https://', 'http://')):
                raise ValueError('invalid_url')
            result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_url(nb, url))}
        elif operation == 'source_add_drive':
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            file_id = str(args.get('file_id') or args.get('document_id') or '').strip()
            title = str(args.get('title') or '').strip()
            if not file_id:
                raise ValueError('missing_file_id')
            if not title:
                raise ValueError('missing_title')
            result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_drive(nb, file_id, title))}
        elif operation == 'source_delete':
            if args.get('confirm') is not True:
                raise ValueError('confirm_required')
            nb = await resolve_notebook(client, str(args.get('notebook') or ''))
            source_id = str(args.get('source_id') or '').strip()
            if not source_id:
                raise ValueError('missing_source_id')
            await client.sources.delete(nb, source_id)
            result = {'notebook_id': nb, 'deleted_source_id': source_id}
        else:
            raise ValueError('operation_not_allowed')
    return {
        'ok': True,
        'provider': 'NotebookLM',
        'runtime': 'railway-notebooklm-direct',
        'operation': operation,
        'result': result,
    }


def _rpc_result(request_id, result: dict) -> dict:
    return {'jsonrpc': '2.0', 'id': request_id, 'result': result}


def _rpc_error(request_id, code: int, message: str) -> dict:
    return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}}


async def plugin_mcp_health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            'ok': bool(_load_master_token_b64()) and len(os.environ.get(PLUGIN_KEY_ENV, '').strip()) >= 24,
            'service': 'nd-notebooklm-chatgpt-mcp',
            'provider': 'NotebookLM',
            'runtime': 'railway',
            'transport': 'streamable-http',
            'auth': PLUGIN_HEADER,
            'tools': len(_NOTEBOOKLM_MCP_TOOLS),
        }
    )


async def plugin_mcp(request: Request):
    if not _plugin_authorized(request):
        return JSONResponse({'ok': False, 'error': 'unauthorized'}, status_code=401)
    if request.method == 'GET':
        return Response(
            ': nd-notebooklm-chatgpt-mcp\n\n',
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'Connection': 'keep-alive'},
        )
    try:
        msg = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, 'Parse error'), status_code=400)

    request_id = msg.get('id')
    method = str(msg.get('method') or '')
    if method == 'initialize':
        protocol = str((msg.get('params') or {}).get('protocolVersion') or '2025-06-18')
        return JSONResponse(
            _rpc_result(
                request_id,
                {
                    'protocolVersion': protocol,
                    'capabilities': {'tools': {'listChanged': False}},
                    'serverInfo': {'name': 'ND NotebookLM Direct', 'version': '1.0.0'},
                    'instructions': (
                        'Nameless Dhamma NotebookLM semantic workspace. '
                        'NotebookLM is nonauthoritative; CURRENT authority remains NAM-143 -> bound CURRENT Registry. '
                        'Use provider readback after consequential writes and never blind-retry ambiguous mutations.'
                    ),
                },
            )
        )
    if method == 'ping':
        return JSONResponse(_rpc_result(request_id, {}))
    if method == 'tools/list':
        return JSONResponse(_rpc_result(request_id, {'tools': _NOTEBOOKLM_MCP_TOOLS}))
    if method == 'tools/call':
        params = msg.get('params') or {}
        operation = str(params.get('name') or '')
        args = params.get('arguments') or {}
        if not isinstance(args, dict):
            args = {}
        if operation not in {tool['name'] for tool in _NOTEBOOKLM_MCP_TOOLS}:
            result = {
                'content': [{'type': 'text', 'text': 'tool_denied'}],
                'structuredContent': {'ok': False, 'error': 'tool_denied'},
                'isError': True,
            }
            return JSONResponse(_rpc_result(request_id, result))
        try:
            payload = await _plugin_execute(operation, args)
            result = {
                'content': [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)}],
                'structuredContent': payload,
                'isError': False,
            }
        except Exception as exc:
            message = str(exc)[:1600]
            result = {
                'content': [{'type': 'text', 'text': message}],
                'structuredContent': {'ok': False, 'operation': operation, 'error': message},
                'isError': True,
            }
        return JSONResponse(_rpc_result(request_id, result))
    if method.startswith('notifications/'):
        return Response(status_code=202, headers={'Cache-Control': 'no-store'})
    return JSONResponse(_rpc_error(request_id, -32601, 'Method not found'))



_DRIVE_TOOLS = {
    'drive_get_metadata',
    'drive_get_currentness_token',
    'docs_read',
    'docs_append',
    'docs_replace_exact',
    'drive_changes_start_token',
    'drive_changes_list',
}
_DRIVE_MUTATIONS = {'docs_append', 'docs_replace_exact'}

async def drive_health(request: Request) -> JSONResponse:
    try:
        result = await asyncio.to_thread(direct_drive_health)
        return JSONResponse(result, status_code=200 if result.get('ok') else 503)
    except Exception as exc:
        return JSONResponse({'ok': False, 'route': 'railway_notebooklm_direct_google', 'error': str(exc)[:800]}, status_code=503)

async def drive_invoke(request: Request) -> JSONResponse:
    if not bridge_authorized(request.headers.get('x-nd-bridge-key', '')):
        return JSONResponse({'ok': False, 'error': 'unauthorized'}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'invalid_json'}, status_code=400)
    tool = str(payload.get('tool') or '').strip()
    args = payload.get('args') or {}
    if tool not in _DRIVE_TOOLS:
        return JSONResponse({'ok': False, 'error': 'tool_not_allowed'}, status_code=400)
    if not isinstance(args, dict):
        return JSONResponse({'ok': False, 'error': 'invalid_args'}, status_code=400)
    try:
        result = await asyncio.to_thread(direct_drive_call, tool, args)
        return JSONResponse({'ok': True, 'tool': tool, 'result': result, 'mutation': tool in _DRIVE_MUTATIONS})
    except Exception as exc:
        msg = str(exc)[:1600]
        status = 409 if any(x in msg for x in ('REVISION_MISMATCH', 'EXACT_MATCH_REQUIRED', 'write denied')) else 502
        return JSONResponse({'ok': False, 'tool': tool, 'error': msg}, status_code=status)

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
    if tool not in _DRIVE_TOOLS:
        return JSONResponse({'ok': False, 'error': 'tool_not_allowed'}, status_code=400)
    if not isinstance(args, dict):
        return JSONResponse({'ok': False, 'error': 'invalid_args'}, status_code=400)
    try:
        result = await asyncio.to_thread(direct_drive_call, tool, args)
        return JSONResponse({
            'ok': True,
            'tool': tool,
            'result': result,
            'oidc_repository': claims.get('repository'),
            'mutation': tool in _DRIVE_MUTATIONS,
            'route': 'railway_notebooklm_direct_google',
        })
    except Exception as exc:
        msg = str(exc)[:1600]
        status = 409 if any(x in msg for x in ('REVISION_MISMATCH', 'EXACT_MATCH_REQUIRED', 'write denied')) else 502
        return JSONResponse({'ok': False, 'tool': tool, 'error': msg}, status_code=status)


legacy_app = build_railway_app_from_environ()

app = Starlette(
    routes=[
        Route('/health', health, methods=['GET']),
        Route('/watchdog', watchdog_status, methods=['GET']),
        Route('/chatgpt/mcp/health', plugin_mcp_health, methods=['GET']),
        Route('/chatgpt/mcp', plugin_mcp, methods=['GET', 'POST']),
        Route('/drive/health', drive_health, methods=['GET']),
        Route('/drive/invoke', drive_invoke, methods=['POST']),
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