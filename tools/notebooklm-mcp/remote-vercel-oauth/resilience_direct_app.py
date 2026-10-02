from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import padding
from jwt import PyJWKClient
from notebooklm import NotebookLMClient
from notebooklm.auth import master_token_bootstrap
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from nd_oauth.runtime import materialize_master_token, refresh_storage
from nd_oauth.file_state import FileOAuthStateStore
from nd_oauth.full_server import create_full_mcp

MASTER_TOKEN_B64 = os.environ.get('NOTEBOOKLM_MASTER_TOKEN_B64', '').strip()
BACKEND = os.environ.get('NOTEBOOKLM_BACKEND', 'android').strip().lower() or 'android'
RUNTIME_NAME = os.environ.get('ND_NOTEBOOKLM_RUNTIME_NAME', 'nd-notebooklm-direct').strip()
HOME = Path(os.environ.get('ND_NOTEBOOKLM_RUNTIME_HOME', '/tmp/nd-notebooklm-direct'))
BOOTSTRAP_SHARED_TOKEN = os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_SHARED_TOKEN', '').strip()
BOOTSTRAP_EMAIL = os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_EMAIL', 'namelessdhamma@gmail.com').strip()
RENDER_PUBLIC_KEY_B64 = os.environ.get('ND_NOTEBOOKLM_RENDER_PUBLIC_KEY_B64', '').strip()
RENDER_PRIVATE_KEY_B64 = os.environ.get('ND_NOTEBOOKLM_RENDER_PRIVATE_KEY_B64', '').strip()
SEALED_MASTER_TOKEN_B64 = os.environ.get('ND_NOTEBOOKLM_SEALED_TOKEN_B64', '').strip()
BOOTSTRAP_X25519_PRIVATE_B64 = os.environ.get('ND_NOTEBOOKLM_BOOTSTRAP_X25519_PRIVATE_B64', '').strip()
X25519_SEALED_ENVELOPE_B64 = os.environ.get('ND_NOTEBOOKLM_X25519_SEALED_ENVELOPE_B64', '').strip()
BUNDLED_X25519_ENVELOPE = Path(__file__).with_name('render_recovery_envelope.json')
PLUGIN_KEY_ENV = 'ND_NOTEBOOKLM_PLUGIN_KEY'
PLUGIN_HEADER = 'x-nd-notebooklm-plugin-key'

_ISSUER = 'https://token.actions.githubusercontent.com'
_AUDIENCE = 'nd-notebooklm-direct'
_REPOSITORY = 'namelessdhamma/nameless-dhamma-vault'
_ACTOR = 'namelessdhamma'
_JWKS = PyJWKClient('https://token.actions.githubusercontent.com/.well-known/jwks')

def _load_master_token_b64() -> str:
    if MASTER_TOKEN_B64:
        return MASTER_TOKEN_B64
    token_file = HOME / 'profiles' / 'default' / 'master_token.json'
    if token_file.exists():
        return base64.b64encode(token_file.read_bytes()).decode('ascii')
    recovery_errors = []
    if X25519_SEALED_ENVELOPE_B64:
        try:
            raw = base64.b64decode(X25519_SEALED_ENVELOPE_B64.encode('ascii'), validate=True)
            envelope = json.loads(raw.decode('utf-8'))
            if not isinstance(envelope, dict):
                raise RuntimeError('sealed_envelope_not_object')
            return _open_sealed(envelope)
        except Exception as exc:
            recovery_errors.append('env_x25519:' + type(exc).__name__)
    if BUNDLED_X25519_ENVELOPE.exists():
        try:
            wrapped = json.loads(BUNDLED_X25519_ENVELOPE.read_text(encoding='utf-8'))
            envelope = wrapped.get('envelope') if isinstance(wrapped, dict) else None
            if not isinstance(envelope, dict):
                raise RuntimeError('bundled_sealed_envelope_missing')
            return _open_sealed(envelope)
        except Exception as exc:
            recovery_errors.append('bundled_x25519:' + type(exc).__name__)
    if SEALED_MASTER_TOKEN_B64 and RENDER_PRIVATE_KEY_B64:
        private_key = serialization.load_pem_private_key(
            base64.b64decode(RENDER_PRIVATE_KEY_B64.encode('ascii')), password=None
        )
        plain = private_key.decrypt(
            base64.b64decode(SEALED_MASTER_TOKEN_B64.encode('ascii')),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        return base64.b64encode(plain).decode('ascii')
    if recovery_errors:
        raise RuntimeError('all_render_credential_recovery_paths_failed:' + ','.join(recovery_errors))
    return ''


def _bootstrap_private_key():
    if BOOTSTRAP_X25519_PRIVATE_B64:
        raw = base64.b64decode(BOOTSTRAP_X25519_PRIVATE_B64.encode('ascii'), validate=True)
        if len(raw) != 32:
            raise RuntimeError('invalid_bootstrap_private_key')
        return x25519.X25519PrivateKey.from_private_bytes(raw)
    existing_secret = (
        os.environ.get('NOTEBOOKLM_MCP_OAUTH_PASSWORD', '').strip()
        or BOOTSTRAP_SHARED_TOKEN
    )
    if not existing_secret:
        return None
    raw = hashlib.sha256(
        b'nd-notebooklm-bootstrap-x25519-v1\0' + existing_secret.encode('utf-8')
    ).digest()
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
    credential_b64 = _load_master_token_b64()
    if not credential_b64:
        raise RuntimeError('credential_unconfigured')
    if BACKEND not in {'android', 'web'}:
        raise RuntimeError('invalid_backend')
    materialize_master_token(credential_b64, HOME)
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
        'credential_configured': bool(_load_master_token_b64()),
        'transport': 'github_actions_oidc_direct',
    })

def _bootstrap_authorized(request: Request) -> bool:
    auth = request.headers.get('authorization', '').strip()
    return bool(BOOTSTRAP_SHARED_TOKEN and auth == 'Bearer ' + BOOTSTRAP_SHARED_TOKEN)


async def bootstrap_exchange(request: Request) -> JSONResponse:
    if not _bootstrap_authorized(request):
        return bad('not_found', 404)
    try:
        payload = await request.json()
    except Exception:
        return bad('invalid_json', 400)
    target = str(payload.get('target') or '').strip().lower()
    oauth_token = str(payload.get('oauth_token') or '').strip()
    if target not in {'railway', 'render'} or not oauth_token:
        return bad('invalid_bootstrap_request', 400)

    if target == 'railway':
        target_home = HOME
    else:
        target_home = Path('/tmp') / ('nd-notebooklm-render-bootstrap-' + secrets.token_hex(8))

    storage_path = target_home / 'profiles' / 'default' / 'storage_state.json'
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        notebook_count = await master_token_bootstrap(
            email=BOOTSTRAP_EMAIL,
            oauth_token=oauth_token,
            storage_path=storage_path,
            verify=True,
            force=True,
        )
        master_path = storage_path.parent / 'master_token.json'
        if not master_path.exists():
            raise RuntimeError('master_token_not_persisted')
        if target == 'railway':
            return JSONResponse({
                'ok': True,
                'target': target,
                'notebook_count': notebook_count,
                'credential_persisted': True,
                'path': 'railway_volume',
            })

        if not RENDER_PUBLIC_KEY_B64:
            raise RuntimeError('render_public_key_unconfigured')
        public_key = serialization.load_pem_public_key(
            base64.b64decode(RENDER_PUBLIC_KEY_B64.encode('ascii'))
        )
        sealed = public_key.encrypt(
            master_path.read_bytes(),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        return JSONResponse({
            'ok': True,
            'target': target,
            'notebook_count': notebook_count,
            'credential_persisted': False,
            'sealed_master_token_b64': base64.b64encode(sealed).decode('ascii'),
            'path': 'render_sealed_handoff',
        })
    except Exception as exc:
        return JSONResponse({'ok': False, 'target': target, 'error': str(exc)[:1200]}, status_code=502)
    finally:
        if target == 'render':
            shutil.rmtree(target_home, ignore_errors=True)


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


async def bootstrap_export_sealed(request: Request) -> JSONResponse:
    claims = verify_oidc(request)
    if claims is None:
        return bad('not_found', 404)
    credential_b64 = _load_master_token_b64()
    if not credential_b64:
        return bad('credential_unconfigured', 503)
    try:
        payload = await request.json()
        public_key_b64 = str(payload.get('recipient_public_key_b64') or '').strip()
        public_key_raw = base64.b64decode(public_key_b64.encode('ascii'), validate=True)
        if len(public_key_raw) != 32:
            raise ValueError('invalid_recipient_public_key')
        recipient = x25519.X25519PublicKey.from_public_bytes(public_key_raw)
        ephemeral = x25519.X25519PrivateKey.generate()
        shared = ephemeral.exchange(recipient)
        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'nd-notebooklm-bootstrap-v1',
        ).derive(shared)
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(aes_key).encrypt(
            nonce,
            credential_b64.encode('utf-8'),
            b'nd-notebooklm-master-token-b64',
        )
        ephemeral_public = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return JSONResponse({
            'ok': True,
            'algorithm': 'X25519+HKDF-SHA256+AESGCM',
            'ephemeral_public_key_b64': base64.b64encode(ephemeral_public).decode('ascii'),
            'nonce_b64': base64.b64encode(nonce).decode('ascii'),
            'ciphertext_b64': base64.b64encode(ciphertext).decode('ascii'),
            'oidc_repository': claims.get('repository'),
            'credential_exposed': False,
        })
    except Exception as exc:
        return JSONResponse({'ok': False, 'error': str(exc)[:1200]}, status_code=400)


async def github(request: Request) -> JSONResponse:
    claims = verify_oidc(request)
    if claims is None:
        return bad('not_found', 404)
    if not _load_master_token_b64():
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
            'required': ['notebook', 'file_id'],
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
            if not file_id:
                raise ValueError('missing_file_id')
            result = {'notebook_id': nb, 'source': to_jsonable(await client.sources.add_drive(nb, file_id))}
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
        'runtime': 'render-notebooklm-direct',
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
            'runtime': 'render',
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



def build_render_oauth_app():
    base_url = os.environ.get(
        'ND_NOTEBOOKLM_OAUTH_BASE_URL',
        'https://nd-notebooklm-direct.onrender.com',
    ).strip().rstrip('/')
    password = os.environ.get('NOTEBOOKLM_MCP_OAUTH_PASSWORD', '').strip()
    login_password = os.environ.get('ND_NOTEBOOKLM_OAUTH_LOGIN_PASSWORD', '').strip() or password
    if len(password) < 24:
        raise RuntimeError('NOTEBOOKLM_MCP_OAUTH_PASSWORD must be at least 24 characters')
    if len(login_password) < 24:
        raise RuntimeError('ND_NOTEBOOKLM_OAUTH_LOGIN_PASSWORD must be at least 24 characters')

    state_root = Path(
        os.environ.get(
            'ND_NOTEBOOKLM_RENDER_OAUTH_STATE_DIR',
            '/tmp/nd-notebooklm-render-oauth-state',
        )
    )
    state_path = Path(
        os.environ.get(
            'ND_NOTEBOOKLM_OAUTH_STATE_PATH',
            '/tmp/nd-notebooklm-render-oauth.json',
        )
    )
    registry_store = FileOAuthStateStore(state_root / 'oauth-registry.json')
    transient_store = FileOAuthStateStore(state_root / 'oauth-transient.json')

    mcp = create_full_mcp(
        password=password,
        login_password=login_password,
        base_url=base_url,
        state_path=state_path,
        registry_store=registry_store,
        transient_store=transient_store,
        client_factory=client_factory,
        trust_proxy=True,
    )
    return mcp.http_app(
        path='/mcp',
        stateless_http=True,
        json_response=True,
        transport='http',
    )


oauth_app = build_render_oauth_app()


app = Starlette(routes=[Route('/health', health, methods=['GET']), Route('/chatgpt/mcp/health', plugin_mcp_health, methods=['GET']), Route('/chatgpt/mcp', plugin_mcp, methods=['GET', 'POST']), Route('/github', github, methods=['POST']), Route('/bootstrap/exchange', bootstrap_exchange, methods=['POST']), Route('/bootstrap/public-key', bootstrap_public_key, methods=['GET']), Route('/bootstrap/import-sealed', bootstrap_import_sealed, methods=['POST']), Route('/bootstrap/export-sealed', bootstrap_export_sealed, methods=['POST']), Mount('/', app=oauth_app)], lifespan=oauth_app.lifespan)