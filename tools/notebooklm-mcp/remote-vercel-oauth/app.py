from __future__ import annotations

import base64
import hashlib
import json
import time

import jwt

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jwt import PyJWKClient
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.deployment import DeploymentConfig, build_app_from_environ
from nd_oauth.runtime import make_client_factory

# Public verification key only. The corresponding private signing material stays
# on the Railway Doctor relay and is deterministically derived from its existing
# ND_NOTEBOOKLM_DOCTOR_RELAY_TOKEN secret.
_DOCTOR_PUBLIC_KEY_B64 = "22YCjT7XEUrOdU1Vogl4IsnVTjogmcBjjFGhLlye4dw="
_DOCTOR_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(
    base64.b64decode(_DOCTOR_PUBLIC_KEY_B64)
)
_MAX_SKEW_SECONDS = 90
_GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
_GITHUB_OIDC_AUDIENCE = "nd-notebooklm"
_GITHUB_REPOSITORIES = {"namelessdhamma/namelessdhamma.github.io", "namelessdhamma/nameless-dhamma-vault"}
_GITHUB_ACTOR = "namelessdhamma"
_GITHUB_JWKS = PyJWKClient(
    "https://token.actions.githubusercontent.com/.well-known/jwks"
)


def _verify_github_oidc(request: Request) -> dict | None:
    auth = request.headers.get("authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        signing_key = _GITHUB_JWKS.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_GITHUB_OIDC_AUDIENCE,
            issuer=_GITHUB_OIDC_ISSUER,
        )
        if claims.get("repository") not in _GITHUB_REPOSITORIES:
            return None
        if claims.get("actor") != _GITHUB_ACTOR:
            return None
        if claims.get("event_name") not in {"issue_comment", "issues", "workflow_dispatch"}:
            return None
        return claims
    except Exception:
        return None


config = DeploymentConfig.from_environ()
client_factory = make_client_factory(config.master_token_b64)
mcp_app = build_app_from_environ()


def _canonical(request: Request, body: bytes = b"") -> bytes:
    ts = request.headers.get("x-nd-timestamp", "")
    query = request.url.query or ""
    body_hash = hashlib.sha256(body).hexdigest()
    return (
        ts
        + "\n"
        + request.method.upper()
        + "\n"
        + request.url.path
        + "\n"
        + query
        + "\n"
        + body_hash
    ).encode("utf-8")


async def _verify(request: Request, body: bytes = b"") -> bool:
    ts_raw = request.headers.get("x-nd-timestamp", "").strip()
    sig_raw = request.headers.get("x-nd-signature", "").strip()
    try:
        ts = int(ts_raw)
        if abs(int(time.time()) - ts) > _MAX_SKEW_SECONDS:
            return False
        signature = base64.b64decode(sig_raw, validate=True)
        _DOCTOR_PUBLIC_KEY.verify(signature, _canonical(request, body))
        return True
    except Exception:
        return False


def _deny() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


async def doctor_health(request: Request) -> JSONResponse:
    # Redacted public health probe: no account/notebook information.
    return JSONResponse(
        {
            "ok": True,
            "service": "nd-notebooklm-vercel-doctor-bridge",
            "version": "1.0.0",
            "provider": "NotebookLM",
            "master_token_configured": bool(config.master_token_b64),
            "native_mcp_preserved": True,
            "signed_relay_required": True,
        }
    )


async def doctor_notebooks(request: Request) -> JSONResponse:
    if not await _verify(request):
        return _deny()
    try:
        async with client_factory() as client:
            items = await client.notebooks.list()
            return JSONResponse(
                {
                    "ok": True,
                    "provider": "NotebookLM",
                    "operation": "notebooks_list",
                    "count": len(items),
                    "notebooks": to_jsonable(items),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "notebooks_list", "error": str(exc)[:1200]},
            status_code=502,
        )


async def doctor_sources(request: Request) -> JSONResponse:
    if not await _verify(request):
        return _deny()
    notebook_ref = request.query_params.get("notebook", "").strip()
    if not notebook_ref:
        return JSONResponse({"ok": False, "error": "missing_notebook"}, status_code=400)
    try:
        async with client_factory() as client:
            notebook_id = await resolve_notebook(client, notebook_ref)
            items = await client.sources.list(notebook_id)
            return JSONResponse(
                {
                    "ok": True,
                    "provider": "NotebookLM",
                    "operation": "sources_list",
                    "notebook_id": notebook_id,
                    "count": len(items),
                    "sources": to_jsonable(items),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "sources_list", "error": str(exc)[:1200]},
            status_code=502,
        )


async def doctor_ask(request: Request) -> JSONResponse:
    body = await request.body()
    if not await _verify(request, body):
        return _deny()
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    notebook_ref = str(payload.get("notebook") or "").strip()
    question = str(payload.get("question") or "").strip()
    if not notebook_ref or not question:
        return JSONResponse(
            {"ok": False, "error": "missing_notebook_or_question"}, status_code=400
        )
    if len(question) > 6000:
        return JSONResponse({"ok": False, "error": "question_too_long"}, status_code=400)
    try:
        async with client_factory() as client:
            notebook_id = await resolve_notebook(client, notebook_ref)
            result = await client.chat.ask(notebook_id, question)
            return JSONResponse(
                {
                    "ok": True,
                    "provider": "NotebookLM",
                    "operation": "chat_ask",
                    "notebook_id": notebook_id,
                    "result": to_jsonable(result),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "chat_ask", "error": str(exc)[:1200]},
            status_code=502,
        )



async def github_bridge(request: Request) -> JSONResponse:
    claims = _verify_github_oidc(request)
    if claims is None:
        return _deny()
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    operation = str(payload.get("operation") or "").strip()
    args = payload.get("args") or {}
    if not isinstance(args, dict):
        return JSONResponse({"ok": False, "error": "invalid_args"}, status_code=400)

    try:
        async with client_factory() as client:
            if operation == "notebook_list":
                items = await client.notebooks.list()
                result = {"count": len(items), "notebooks": to_jsonable(items)}

            elif operation == "notebook_get":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                result = {"notebook": to_jsonable(await client.notebooks.get(nb_id))}

            elif operation == "source_list":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                items = await client.sources.list(nb_id)
                result = {"notebook_id": nb_id, "count": len(items), "sources": to_jsonable(items)}

            elif operation == "chat_ask":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                question = str(args.get("question") or "").strip()
                if not question or len(question) > 8000:
                    return JSONResponse({"ok": False, "error": "invalid_question"}, status_code=400)
                answer = await client.chat.ask(nb_id, question)
                result = {"notebook_id": nb_id, "answer": to_jsonable(answer)}

            elif operation == "notebook_create":
                title = str(args.get("title") or "").strip()
                if not title:
                    return JSONResponse({"ok": False, "error": "missing_title"}, status_code=400)
                result = {"notebook": to_jsonable(await client.notebooks.create(title))}

            elif operation == "notebook_rename":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                title = str(args.get("title") or "").strip()
                if not title:
                    return JSONResponse({"ok": False, "error": "missing_title"}, status_code=400)
                result = {"notebook": to_jsonable(await client.notebooks.rename(nb_id, title))}

            elif operation == "notebook_delete":
                if args.get("confirm") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                await client.notebooks.delete(nb_id)
                result = {"deleted_notebook_id": nb_id}

            elif operation == "source_add_text":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                title = str(args.get("title") or "").strip()
                content = str(args.get("content") or "")
                if not title or not content:
                    return JSONResponse({"ok": False, "error": "missing_title_or_content"}, status_code=400)
                src = await client.sources.add_text(nb_id, title, content)
                result = {"notebook_id": nb_id, "source": to_jsonable(src)}

            elif operation == "source_add_url":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                url = str(args.get("url") or "").strip()
                if not url.startswith(("https://", "http://")):
                    return JSONResponse({"ok": False, "error": "invalid_url"}, status_code=400)
                src = await client.sources.add_url(nb_id, url)
                result = {"notebook_id": nb_id, "source": to_jsonable(src)}

            elif operation == "source_delete":
                if args.get("confirm") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                source_id = str(args.get("source_id") or "").strip()
                if not source_id:
                    return JSONResponse({"ok": False, "error": "missing_source_id"}, status_code=400)
                await client.sources.delete(nb_id, source_id)
                result = {"notebook_id": nb_id, "deleted_source_id": source_id}

            else:
                return JSONResponse({"ok": False, "error": "operation_not_allowed"}, status_code=400)

        return JSONResponse({
            "ok": True,
            "provider": "NotebookLM",
            "transport": "github_actions_oidc_to_vercel",
            "operation": operation,
            "result": result,
            "oidc_repository": claims.get("repository"),
        })
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": operation, "error": str(exc)[:1600]},
            status_code=502,
        )

routes = [
    Route("/doctor/health", doctor_health, methods=["GET"]),
    Route("/doctor/github", github_bridge, methods=["POST"]),
    Route("/doctor/notebooks", doctor_notebooks, methods=["GET"]),
    Route("/doctor/sources", doctor_sources, methods=["GET"]),
    Route("/doctor/ask", doctor_ask, methods=["POST"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes)
