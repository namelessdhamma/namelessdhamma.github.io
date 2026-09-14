from __future__ import annotations

import os

from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.railway_deployment import (
    RailwayDeploymentConfig,
    build_railway_app_from_environ,
)
from nd_oauth.runtime import make_client_factory

RELAY_TOKEN = os.environ.get("ND_NOTEBOOKLM_DOCTOR_RELAY_TOKEN", "").strip()

config = RailwayDeploymentConfig.from_environ()
client_factory = make_client_factory(config.master_token_b64)
mcp_app = build_railway_app_from_environ()


def _authorized(request: Request) -> bool:
    if len(RELAY_TOKEN) < 24:
        return False
    supplied = request.headers.get("x-nd-doctor-key", "").strip()
    return bool(supplied) and supplied == RELAY_TOKEN


def _deny() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)


async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "nd-notebooklm-doctor-relay",
            "version": "1.0.0",
            "provider": "NotebookLM",
            "provider_credential_configured": bool(config.master_token_b64),
            "relay_configured": len(RELAY_TOKEN) >= 24,
            "native_mcp_preserved": True,
        }
    )


async def notebooks(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _deny()
    try:
        async with client_factory() as client:
            items = await client.notebooks.list()
            return JSONResponse(
                {
                    "ok": True,
                    "operation": "notebooks_list",
                    "count": len(items),
                    "notebooks": to_jsonable(items),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "notebooks_list", "error": str(exc)[:1500]},
            status_code=502,
        )


async def sources(request: Request) -> JSONResponse:
    if not _authorized(request):
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
                    "operation": "sources_list",
                    "notebook_id": notebook_id,
                    "count": len(items),
                    "sources": to_jsonable(items),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "sources_list", "error": str(exc)[:1500]},
            status_code=502,
        )


async def ask(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _deny()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    notebook_ref = str(body.get("notebook") or "").strip()
    question = str(body.get("question") or "").strip()
    if not notebook_ref or not question:
        return JSONResponse(
            {"ok": False, "error": "missing_notebook_or_question"},
            status_code=400,
        )
    if len(question) > 8000:
        return JSONResponse({"ok": False, "error": "question_too_long"}, status_code=400)
    try:
        async with client_factory() as client:
            notebook_id = await resolve_notebook(client, notebook_ref)
            result = await client.chat.ask(notebook_id, question)
            return JSONResponse(
                {
                    "ok": True,
                    "operation": "chat_ask",
                    "notebook_id": notebook_id,
                    "result": to_jsonable(result),
                }
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "operation": "chat_ask", "error": str(exc)[:1500]},
            status_code=502,
        )


routes = [
    Route("/doctor/health", health, methods=["GET"]),
    Route("/doctor/notebooks", notebooks, methods=["GET"]),
    Route("/doctor/sources", sources, methods=["GET"]),
    Route("/doctor/ask", ask, methods=["POST"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes)
