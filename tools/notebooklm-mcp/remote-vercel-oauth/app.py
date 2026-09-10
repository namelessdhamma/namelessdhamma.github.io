from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Route

from nd_oauth.deployment import DeploymentConfig, build_app_from_environ
from nd_oauth.runtime import make_client_factory


async def _nd_qualification(_request):
    """Temporary, non-sensitive read qualification. Remove after verification."""
    try:
        config = DeploymentConfig.from_environ()
        factory = make_client_factory(
            config.master_token_b64,
            home=Path("/tmp/nd-notebooklm-qualification"),
        )
        async with factory() as client:
            await client.notebooks.list()
        return JSONResponse({"ok": True, "notebooklm_read": True})
    except Exception as exc:  # Never return credential-bearing exception text.
        return JSONResponse(
            {"ok": False, "error_type": type(exc).__name__},
            status_code=500,
        )


app = build_app_from_environ()
app.router.routes.insert(0, Route("/nd-qualification", _nd_qualification, methods=["GET"]))
