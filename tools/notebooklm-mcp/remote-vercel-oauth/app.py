from __future__ import annotations

import base64
import hashlib
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
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


routes = [
    Route("/doctor/health", doctor_health, methods=["GET"]),
    Route("/doctor/notebooks", doctor_notebooks, methods=["GET"]),
    Route("/doctor/sources", doctor_sources, methods=["GET"]),
    Route("/doctor/ask", doctor_ask, methods=["POST"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes)
