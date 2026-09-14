from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from jwt import PyJWKClient
from notebooklm import NotebookLMClient
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nd_oauth.runtime import materialize_master_token, refresh_storage

MASTER_TOKEN_B64 = os.environ.get('NOTEBOOKLM_MASTER_TOKEN_B64', '').strip()
BACKEND = os.environ.get('NOTEBOOKLM_BACKEND', 'android').strip().lower() or 'android'
RUNTIME_NAME = os.environ.get('ND_NOTEBOOKLM_RUNTIME_NAME', 'nd-notebooklm-direct').strip()
HOME = Path(os.environ.get('ND_NOTEBOOKLM_RUNTIME_HOME', '/tmp/nd-notebooklm-direct'))

_ISSUER = 'https://token.actions.githubusercontent.com'
_AUDIENCE = 'nd-notebooklm-direct'
_REPOSITORY = 'namelessdhamma/nameless-dhamma-vault'
_ACTOR = 'namelessdhamma'
_JWKS = PyJWKClient('https://token.actions.githubusercontent.com/.well-known/jwks')

def _bootstrap_private_key():
    if not BOOTSTRAP_X25519_PRIVATE_B64:
        return None
    raw = base64.b64decode(BOOTSTRAP_X25519_PRIVATE_B64.encode('ascii'), validate=True)
    if len(raw) != 32:
        raise RuntimeError('invalid_bootstrap_private_key')
    return x25519.X25519PrivateKey.from_private_bytes(raw)


def _bootstrap_public_key_b64() -> str:
    key = _bootstrap_private_key()
    if key is None:
        return ''
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode('ascii')


def _open_sealed(envelope: dict) -> str:
    key = _bootstrap_private_key()
    if key is None:
        raise RuntimeError('bootstrap_private_key_unconfigured')
    peer = x25519.X25519PublicKey.from_public_bytes(
        base64.b64decode(str(envelope.get('ephemeral_public_key_b64') or '').encode('ascii'), validate=True)
    )
    nonce = base64.b64decode(str(envelope.get('nonce_b64') or '').encode('ascii'), validate=True)
    ciphertext = base64.b64decode(str(envelope.get('ciphertext_b64') or '').encode('ascii'), validate=True)
    shared = key.exchange(peer)
    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'nd-notebooklm-bootstrap-v1',
    ).derive(shared)
    plain = AESGCM(aes_key).decrypt(
        nonce,
        ciphertext,
        b'nd-notebooklm-master-token-b64',
    )
    return plain.decode('utf-8')


def verify_oidc(request: Request) -> dict | None:
    auth = request.headers.get('authorization', '').strip()
    if not auth.lower().startswith('bearer '):
        return None
    token = auth[7:].strip()
    try:
        key = _JWKS.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['RS256'], audience=_AUDIENCE, issuer=_ISSUER)
        if claims.get('repository') != _REPOSITORY:
            return None
        if claims.get('actor') != _ACTOR:
            return None
        if claims.get('event_name') not in {'push', 'workflow_dispatch', 'schedule'}:
            return None
        return claims
    except Exception:
        return None

@asynccontextmanager
async def client_factory():
    if not MASTER_TOKEN_B64:
        raise RuntimeError('credential_unconfigured')
    if BACKEND not in {'android', 'web'}:
        raise RuntimeError('invalid_backend')
    materialize_master_token(MASTER_TOKEN_B64, HOME)
    os.environ['NOTEBOOKLM_HOME'] = str(HOME)
    os.environ['NOTEBOOKLM_PROFILE'] = 'default'
    os.environ.pop('NOTEBOOKLM_AUTH_JSON', None)
    await asyncio.to_thread(refresh_storage, HOME)
    async with NotebookLMClient.from_storage(
        profile='default', backend=BACKEND, timeout=30.0,
        server_error_max_retries=1, rate_limit_max_retries=1
    ) as client:
        yield client

def bad(error: str, status: int) -> JSONResponse:
    return JSONResponse({'ok': False, 'error': error}, status_code=status)

async def health(request: Request) -> JSONResponse:
    return JSONResponse({
        'ok': True,
        'service': RUNTIME_NAME,
        'provider': 'NotebookLM',
        'backend': BACKEND,
        'credential_configured': bool(MASTER_TOKEN_B64),
        'transport': 'github_actions_oidc_direct',
    })

async def bootstrap_public_key(request: Request) -> JSONResponse:
    public_key = _bootstrap_public_key_b64()
    if not public_key:
        return JSONResponse({'ok': False, 'error': 'bootstrap_key_unconfigured'}, status_code=503)
    return JSONResponse({
        'ok': True,
        'service': RUNTIME_NAME,
        'algorithm': 'X25519+HKDF-SHA256+AESGCM',
        'public_key_b64': public_key,
    })


async def bootstrap_import_sealed(request: Request) -> JSONResponse:
    claims = verify_oidc(request)
    if claims is None:
        return bad('not_found', 404)
    try:
        payload = await request.json()
        credential_b64 = _open_sealed(payload)
        materialize_master_token(credential_b64, HOME)
        os.environ['NOTEBOOKLM_HOME'] = str(HOME)
        os.environ['NOTEBOOKLM_PROFILE'] = 'default'
        os.environ.pop('NOTEBOOKLM_AUTH_JSON', None)
        await asyncio.to_thread(refresh_storage, HOME)
        async with NotebookLMClient.from_storage(
            profile='default',
            backend=BACKEND,
            timeout=30.0,
            server_error_max_retries=1,
            rate_limit_max_retries=1,
        ) as client:
            count = len(await client.notebooks.list())
        return JSONResponse({
            'ok': True,
            'service': RUNTIME_NAME,
            'backend': BACKEND,
            'credential_persisted': True,
            'notebook_count': count,
            'oidc_repository': claims.get('repository'),
        })
    except Exception as exc:
        return JSONResponse({'ok': False, 'error': str(exc)[:1200]}, status_code=502)


async def github(request: Request) -> JSONResponse:
    claims = verify_oidc(request)
    if claims is None:
        return bad('not_found', 404)
    if not MASTER_TOKEN_B64:
        return bad('credential_unconfigured', 503)
    try:
        payload = await request.json()
    except Exception:
        return bad('invalid_json', 400)
    operation = str(payload.get('operation') or '').strip()
    args = payload.get('args') or {}
    if not isinstance(args, dict):
        return bad('invalid_args', 400)
    try:
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
                    return bad('missing_source_id', 400)
                result = {'notebook_id': nb, 'source_id': sid, 'fulltext': to_jsonable(await client.sources.get_fulltext(nb, sid))}
            elif operation == 'chat_ask':
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                q = str(args.get('question') or '').strip()
                if not q:
                    return bad('missing_question', 400)
                result = {'notebook_id': nb, 'answer': to_jsonable(await client.chat.ask(nb, q))}
            elif operation == 'notebook_create':
                title = str(args.get('title') or '').strip()
                if not title:
                    return bad('missing_title', 400)
                result = {'notebook': to_jsonable(await client.notebooks.create(title))}
            elif operation == 'notebook_rename':
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                title = str(args.get('title') or '').strip()
                if not title:
                    return bad('missing_title', 400)
                result = {'notebook': to_jsonable(await client.notebooks.rename(nb, title))}
            elif operation == 'notebook_delete':
                if args.get('confirm') is not True:
                    return bad('confirm_required', 400)
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                await client.notebooks.delete(nb)
                result = {'deleted_notebook_id': nb}
            elif operation == 'source_add_text':
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                title = str(args.get('title') or '').strip()
                content = str(args.get('content') or '')
                if not title or not content:
                    return bad('missing_title_or_content', 400)
                result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_text(nb, title, content))}
            elif operation == 'source_add_url':
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                url = str(args.get('url') or '').strip()
                if not url.startswith(('https://', 'http://')):
                    return bad('invalid_url', 400)
                result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_url(nb, url))}
            elif operation == 'source_add_drive':
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                fid = str(args.get('file_id') or '').strip()
                if not fid:
                    return bad('missing_file_id', 400)
                result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_drive(nb, fid))}
            elif operation == 'source_delete':
                if args.get('confirm') is not True:
                    return bad('confirm_required', 400)
                nb = await resolve_notebook(client, str(args.get('notebook') or ''))
                sid = str(args.get('source_id') or '').strip()
                if not sid:
                    return bad('missing_source_id', 400)
                await client.sources.delete(nb, sid)
                result = {'notebook_id': nb, 'deleted_source_id': sid}
            else:
                return bad('operation_not_allowed', 400)
        return JSONResponse({
            'ok': True, 'provider': 'NotebookLM', 'runtime': RUNTIME_NAME,
            'backend': BACKEND, 'operation': operation, 'result': result,
            'oidc_repository': claims.get('repository')
        })
    except Exception as exc:
        return JSONResponse({'ok': False, 'operation': operation, 'error': str(exc)[:1600]}, status_code=502)

app = Starlette(routes=[Route('/health', health, methods=['GET']), Route('/github', github, methods=['POST']), Route('/bootstrap/public-key', bootstrap_public_key, methods=['GET']), Route('/bootstrap/import-sealed', bootstrap_import_sealed, methods=['POST'])])
