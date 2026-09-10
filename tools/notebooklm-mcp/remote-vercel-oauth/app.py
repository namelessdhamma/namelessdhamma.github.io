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
    # First inspect the Vercel Blob Python SDK success-object contract without
    # serializing any content or credential-bearing values.
    client = BlobOAuthStateStore._default_client_factory()
    try:
        result = client.get(
            "nd-notebooklm/oauth-registry.json",
            access="private",
            use_cache=False,
        )
        result_type = type(result).__name__ if result is not None else None
        public_attrs = sorted(
            name for name in dir(result)
            if result is not None and not name.startswith("_") and name not in {"json", "text", "content"}
        )[:40]
        result_dict_keys = sorted(getattr(result, "__dict__", {}).keys()) if result is not None else []
    finally:
        client.close()

    path = Path("/tmp/nd-notebooklm-oauth-diag.json")
    store = BlobOAuthStateStore("nd-notebooklm/oauth-registry.json")
    restored = store.restore(path)
    base = {
        "result_type": result_type,
        "public_attrs": public_attrs,
        "dict_keys": result_dict_keys,
        "restored": restored,
    }
    if not restored:
        return JSONResponse({"ok": False, **base}, status_code=503)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse({"ok": False, **base, "json": False}, status_code=500)
    clients = data.get("clients", {}) if isinstance(data, dict) else {}
    access = data.get("access_tokens", {}) if isinstance(data, dict) else {}
    refresh = data.get("refresh_tokens", {}) if isinstance(data, dict) else {}
    client_hashes = sorted(hashlib.sha256(str(cid).encode()).hexdigest()[:12] for cid in clients)
    return JSONResponse(
        {
            "ok": True,
            **base,
            "clients": len(clients),
            "client_hashes": client_hashes,
            "access_tokens": len(access),
            "refresh_tokens": len(refresh),
            "expected_reconnect_client_present": "a718f4c7f3de" in client_hashes,
        }
    )


app.routes.append(Route("/__nd_oauth_diag", _oauth_diag, methods=["GET"]))
