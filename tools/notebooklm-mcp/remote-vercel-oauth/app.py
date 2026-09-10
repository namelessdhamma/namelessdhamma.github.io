import hashlib
import json
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Route

from nd_oauth.blob_state import BlobOAuthStateStore
from nd_oauth.deployment import build_app_from_environ


app = build_app_from_environ()


async def _oauth_diag(_request):
    """Temporary qualification probe: structural OAuth state only; never tokens/secrets."""
    path = Path("/tmp/nd-notebooklm-oauth-diag.json")
    store = BlobOAuthStateStore("nd-notebooklm/oauth-registry.json")
    restored = store.restore(path)
    if not restored:
        return JSONResponse({"ok": False, "restored": False}, status_code=503)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "restored": True, "json": False}, status_code=500)
    clients = data.get("clients", {}) if isinstance(data, dict) else {}
    access = data.get("access_tokens", {}) if isinstance(data, dict) else {}
    refresh = data.get("refresh_tokens", {}) if isinstance(data, dict) else {}
    client_hashes = sorted(hashlib.sha256(str(cid).encode()).hexdigest()[:12] for cid in clients)
    return JSONResponse(
        {
            "ok": True,
            "clients": len(clients),
            "client_hashes": client_hashes,
            "access_tokens": len(access),
            "refresh_tokens": len(refresh),
            "expected_reconnect_client_present": "a718f4c7f3de" in client_hashes,
        }
    )


app.routes.append(Route("/__nd_oauth_diag", _oauth_diag, methods=["GET"]))
