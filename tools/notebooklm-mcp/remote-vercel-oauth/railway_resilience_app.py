from __future__ import annotations

from starlette.applications import Starlette
from starlette.routing import Mount, Route

from nd_oauth.railway_deployment import build_railway_app_from_environ
from resilience_direct_app import bootstrap_exchange, github, health

legacy_app = build_railway_app_from_environ()

app = Starlette(
    routes=[
        Route('/health', health, methods=['GET']),
        Route('/github', github, methods=['POST']),
        Route('/bootstrap/exchange', bootstrap_exchange, methods=['POST']),
        Mount('/', app=legacy_app),
    ],
    lifespan=legacy_app.lifespan,
)
