from __future__ import annotations

import os

from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._resolve import resolve_notebook
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from nd_oauth.deployment import DeploymentConfig, build_app_from_environ
from nd_oauth.runtime import make_client_factory

config = DeploymentConfig.from_environ()
client_factory = make_client_factory(config.master_token_b64)
mcp_app = build_app_from_environ()

DOCTOR_ENABLED = os.environ.get("VERCEL_ENV", "").strip().lower() == "preview"

def _disabled() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "doctor_relay_disabled"}, status_code=404)

async def doctor_health(request: Request) -> JSONResponse:
    if not DOCTOR_ENABLED:
        return _disabled()
    return JSONResponse({"ok": True, "service": "nd-notebooklm-vercel-doctor-relay", "version": "1.0.0", "provider": "NotebookLM", "provider_credential_configured": bool(config.master_token_b64), "preview_only": True, "native_mcp_preserved": True})

async def doctor_notebooks(request: Request) -> JSONResponse:
    if not DOCTOR_ENABLED:
        return _disabled()
    try:
        async with client_factory() as client:
            items = await client.notebooks.list()
            return JSONResponse({"ok": True, "operation": "notebooks_list", "count": len(items), "notebooks": to_jsonable(items)})
    except Exception as exc:
        return JSONResponse({"ok": False, "operation": "notebooks_list", "error": str(exc)[:1600]}, status_code=502)

async def doctor_sources(request: Request) -> JSONResponse:
    if not DOCTOR_ENABLED:
        return _disabled()
    notebook_ref = request.query_params.get("notebook", "").strip()
    if not notebook_ref:
        return JSONResponse({"ok": False, "error": "missing_notebook"}, status_code=400)
    try:
        async with client_factory() as client:
            notebook_id = await resolve_notebook(client, notebook_ref)
            items = await client.sources.list(notebook_id)
            return JSONResponse({"ok": True, "operation": "sources_list", "notebook_id": notebook_id, "count": len(items), "sources": to_jsonable(items)})
    except Exception as exc:
        return JSONResponse({"ok": False, "operation": "sources_list", "error": str(exc)[:1600]}, status_code=502)

async def doctor_ask(request: Request) -> JSONResponse:
    if not DOCTOR_ENABLED:
        return _disabled()
    notebook_ref = request.query_params.get("notebook", "").strip()
    question = request.query_params.get("q", "").strip()
    if not notebook_ref or not question:
        return JSONResponse({"ok": False, "error": "missing_notebook_or_question"}, status_code=400)
    if len(question) > 4000:
        return JSONResponse({"ok": False, "error": "question_too_long"}, status_code=400)
    try:
        async with client_factory() as client:
            notebook_id = await resolve_notebook(client, notebook_ref)
            result = await client.chat.ask(notebook_id, question)
            return JSONResponse({"ok": True, "operation": "chat_ask", "notebook_id": notebook_id, "result": to_jsonable(result)})
    except Exception as exc:
        return JSONResponse({"ok": False, "operation": "chat_ask", "error": str(exc)[:1600]}, status_code=502)

routes = [
    Route("/doctor/health", doctor_health, methods=["GET"]),
    Route("/doctor/notebooks", doctor_notebooks, methods=["GET"]),
    Route("/doctor/sources", doctor_sources, methods=["GET"]),
    Route("/doctor/ask", doctor_ask, methods=["GET"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes, lifespan=mcp_app.lifespan)
