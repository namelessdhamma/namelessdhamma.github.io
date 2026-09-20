from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from jwt import PyJWKClient
from notebooklm._app.serialize import to_jsonable
from notebooklm._android.auth import NOTEBOOKLM_OAUTH_SPEC
from notebooklm._auth.master_token_types import _master_token_from_legacy_record
from notebooklm._auth.mint_service import MintService
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
        if claims.get("event_name") not in {"push", "issue_comment", "issues", "workflow_dispatch", "schedule"}:
            return None
        return claims
    except Exception:
        return None


config = DeploymentConfig.from_environ()
client_factory = make_client_factory(config.master_token_b64)
mcp_app = build_app_from_environ()

_DRIVE_CANONICAL_TARGETS = {
    "statehead": "1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ",
    "registry": "16TCMHEb9erk4rONK9poi6-62hNfSELKt",
    "durable_root": "1cnJSi9cmYV_P-EBP1Hy780s3m1s6ybli",
}


async def _mint_drive_bearer() -> str:
    raw = base64.b64decode(config.master_token_b64.encode("ascii"), validate=True)
    record = json.loads(raw.decode("utf-8"))
    master = _master_token_from_legacy_record(record)
    try:
        minted = await MintService().mint_oauth(master, NOTEBOOKLM_OAUTH_SPEC)
        if not minted.token:
            raise RuntimeError("drive_bearer_mint_failed")
        return minted.token
    finally:
        del master, raw, record


def _drive_http_sync(
    bearer: str,
    method: str,
    url: str,
    payload: dict | None = None,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + bearer,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "nd-notebooklm-drive-permission-repair/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8", "replace")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError("google_drive_http_" + str(exc.code) + ":" + body[:900]) from None


async def _drive_http(method: str, url: str, payload: dict | None = None) -> dict:
    bearer = await _mint_drive_bearer()
    try:
        return await asyncio.to_thread(_drive_http_sync, bearer, method, url, payload)
    finally:
        bearer = ""


def _drive_file_bytes_sync(bearer: str, file_id: str) -> bytes:
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id, safe="")
        + "?alt=media&supportsAllDrives=true"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": "Bearer " + bearer,
            "User-Agent": "nd-true-memory-canonical-io/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError("google_drive_read_" + str(exc.code) + ":" + body[:900]) from None


async def _drive_file_bytes(file_id: str) -> bytes:
    bearer = await _mint_drive_bearer()
    try:
        return await asyncio.to_thread(_drive_file_bytes_sync, bearer, file_id)
    finally:
        bearer = ""


async def _drive_read_canonical_json(args: dict) -> dict:
    file_id = str(args.get("file_id") or "").strip()
    allowed = {
        _DRIVE_CANONICAL_TARGETS["registry"],
        "1NOSIIePt_ykCs1nDU4A4sEWKpVEfvtW1",
    }
    if file_id not in allowed:
        raise RuntimeError("canonical_read_target_denied")
    raw = await _drive_file_bytes(file_id)
    if len(raw) > 500000:
        raise RuntimeError("canonical_file_too_large")
    text = raw.decode("utf-8-sig")
    parsed = json.loads(text)
    return {
        "file_id": file_id,
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": text,
        "parsed": parsed,
    }


def _drive_create_json_sync(
    bearer: str,
    name: str,
    parent_id: str,
    content: bytes,
) -> dict:
    boundary = "ndcanonicalboundary"
    meta = json.dumps(
        {
            "name": name,
            "mimeType": "application/json",
            "parents": [parent_id],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    crlf = bytes([13, 10])
    bnd = boundary.encode("ascii")
    body = (
        b"--" + bnd + crlf
        + b"Content-Type: application/json; charset=UTF-8" + crlf + crlf
        + meta + crlf
        + b"--" + bnd + crlf
        + b"Content-Type: application/json" + crlf + crlf
        + content + crlf
        + b"--" + bnd + b"--" + crlf
    )
    url = (
        "https://www.googleapis.com/upload/drive/v3/files"
        "?uploadType=multipart&supportsAllDrives=true"
        "&fields=id,name,mimeType,modifiedTime,version,parents,md5Checksum,sha1Checksum,sha256Checksum,webViewLink"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + bearer,
            "Content-Type": "multipart/related; boundary=" + boundary,
            "Content-Length": str(len(body)),
            "User-Agent": "nd-true-memory-canonical-io/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("google_drive_create_" + str(exc.code) + ":" + detail[:900]) from None


def _drive_delete_sync(bearer: str, file_id: str) -> None:
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id, safe="")
        + "?supportsAllDrives=true"
    )
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={
            "Authorization": "Bearer " + bearer,
            "User-Agent": "nd-true-memory-canonical-io/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("google_drive_delete_" + str(exc.code) + ":" + detail[:900]) from None


async def _drive_create_immutable_json(args: dict) -> dict:
    if args.get("confirm") is not True:
        raise RuntimeError("confirm_required")
    name = str(args.get("name") or "").strip()
    if not re.fullmatch(r"ND_[A-Za-z0-9_.-]{1,180}\.json", name):
        raise RuntimeError("invalid_canonical_json_name")
    content_text = str(args.get("content") or "")
    raw = content_text.encode("utf-8")
    if not raw or len(raw) > 500000:
        raise RuntimeError("invalid_canonical_json_content")
    json.loads(content_text)
    parent_id = _DRIVE_CANONICAL_TARGETS["durable_root"]
    bearer = await _mint_drive_bearer()
    created_id = ""
    try:
        meta = await asyncio.to_thread(
            _drive_create_json_sync,
            bearer,
            name,
            parent_id,
            raw,
        )
        created_id = str(meta.get("id") or "")
        if not created_id:
            raise RuntimeError("drive_create_missing_id")
        readback = await asyncio.to_thread(_drive_file_bytes_sync, bearer, created_id)
        if readback != raw:
            await asyncio.to_thread(_drive_delete_sync, bearer, created_id)
            created_id = ""
            raise RuntimeError("drive_create_readback_mismatch")
        sha256 = hashlib.sha256(readback).hexdigest()
        return {
            "file_id": created_id,
            "name": name,
            "parent_id": parent_id,
            "byte_length": len(readback),
            "sha256": sha256,
            "metadata": meta,
            "readback_exact": True,
        }
    finally:
        bearer = ""


async def _drive_permissions(file_id: str) -> list[dict]:
    fields = urllib.parse.quote(
        "permissions(id,type,role,emailAddress,displayName,deleted)",
        safe=",()",
    )
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id, safe="")
        + "/permissions?supportsAllDrives=true&fields="
        + fields
    )
    data = await _drive_http("GET", url)
    return list(data.get("permissions") or [])


async def _drive_metadata_user(file_id: str) -> dict:
    fields = urllib.parse.quote(
        "id,name,mimeType,modifiedTime,version,trashed,parents,capabilities(canEdit,canShare)",
        safe=",()",
    )
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id, safe="")
        + "?supportsAllDrives=true&fields="
        + fields
    )
    return await _drive_http("GET", url)


def _drive_query_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _drive_search_files(*, name: str = "", query: str = "") -> list[dict]:
    if bool(name) == bool(query):
        raise RuntimeError("provide_exactly_one_drive_search_term")
    term = name or query
    if not term or len(term) > 200:
        raise RuntimeError("invalid_drive_search_term")
    escaped = _drive_query_escape(term)
    folder_mime = "application/vnd.google-apps.folder"
    if name:
        drive_q = (
            "name = '" + escaped + "' and trashed = false and mimeType != '" + folder_mime + "'"
        )
    else:
        drive_q = (
            "fullText contains '" + escaped + "' and trashed = false and mimeType != '" + folder_mime + "'"
        )
    fields = urllib.parse.quote(
        "files(id,name,mimeType,modifiedTime,version,trashed,parents,webViewLink)",
        safe=",()",
    )
    url = (
        "https://www.googleapis.com/drive/v3/files?q="
        + urllib.parse.quote(drive_q, safe="")
        + "&pageSize=10&orderBy=modifiedTime%20desc&spaces=drive"
        + "&supportsAllDrives=true&includeItemsFromAllDrives=true&fields="
        + fields
    )
    data = await _drive_http("GET", url)
    return list(data.get("files") or [])


def _service_account_permissions(perms: list[dict]) -> list[dict]:
    out = []
    for item in perms:
        email = str(item.get("emailAddress") or "").strip().lower()
        if email.endswith(".iam.gserviceaccount.com") or email.endswith("@developer.gserviceaccount.com"):
            out.append({
                "id": item.get("id"),
                "email": email,
                "role": item.get("role"),
                "type": item.get("type"),
            })
    return out


async def _ensure_permission(file_id: str, email: str, role: str) -> dict:
    perms = await _drive_permissions(file_id)
    current = next(
        (
            p for p in perms
            if str(p.get("emailAddress") or "").strip().lower() == email.lower()
        ),
        None,
    )
    base = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id, safe="")
        + "/permissions"
    )
    if current:
        current_role = str(current.get("role") or "")
        if current_role != role:
            pid = str(current.get("id") or "")
            if not pid:
                raise RuntimeError("permission_id_missing")
            await _drive_http(
                "PATCH",
                base + "/" + urllib.parse.quote(pid, safe="") + "?supportsAllDrives=true",
                {"role": role},
            )
            action = "updated"
        else:
            action = "unchanged"
    else:
        await _drive_http(
            "POST",
            base + "?supportsAllDrives=true&sendNotificationEmail=false",
            {"type": "user", "role": role, "emailAddress": email},
        )
        action = "created"
    after = await _drive_permissions(file_id)
    verified = next(
        (
            p for p in after
            if str(p.get("emailAddress") or "").strip().lower() == email.lower()
        ),
        None,
    )
    if not verified or str(verified.get("role") or "") != role:
        raise RuntimeError("permission_readback_failed")
    return {"action": action, "role": role, "permission_id": verified.get("id")}


async def _drive_permissions_audit() -> dict:
    state_perms = await _drive_permissions(_DRIVE_CANONICAL_TARGETS["statehead"])
    service_accounts = _service_account_permissions(state_perms)
    targets = {}
    for name, file_id in _DRIVE_CANONICAL_TARGETS.items():
        try:
            metadata = await _drive_metadata_user(file_id)
            perms = await _drive_permissions(file_id)
            targets[name] = {
                "file_id": file_id,
                "visible": True,
                "name": metadata.get("name"),
                "service_accounts": _service_account_permissions(perms),
            }
        except Exception as exc:
            targets[name] = {
                "file_id": file_id,
                "visible": False,
                "error": str(exc)[:500],
            }
    return {"statehead_service_accounts": service_accounts, "targets": targets}


async def _drive_repair_railway_rw(args: dict) -> dict:
    if args.get("confirm") is not True:
        raise RuntimeError("confirm_required")
    state_perms = await _drive_permissions(_DRIVE_CANONICAL_TARGETS["statehead"])
    candidates = _service_account_permissions(state_perms)
    if len(candidates) != 1:
        raise RuntimeError("expected_exactly_one_statehead_service_account")
    email = str(candidates[0]["email"])
    changes = {}
    changes["statehead"] = await _ensure_permission(
        _DRIVE_CANONICAL_TARGETS["statehead"], email, "writer"
    )
    changes["registry"] = await _ensure_permission(
        _DRIVE_CANONICAL_TARGETS["registry"], email, "reader"
    )
    changes["durable_root"] = await _ensure_permission(
        _DRIVE_CANONICAL_TARGETS["durable_root"], email, "writer"
    )
    return {
        "service_account_email": email,
        "changes": changes,
        "targets": dict(_DRIVE_CANONICAL_TARGETS),
        "credential_exposed": False,
    }


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


async def doctor_export_sealed(request: Request) -> JSONResponse:
    claims = _verify_github_oidc(request)
    if claims is None:
        return _deny()
    if not config.master_token_b64:
        return JSONResponse({"ok": False, "error": "credential_unconfigured"}, status_code=503)
    try:
        payload = await request.json()
        public_key_b64 = str(payload.get("recipient_public_key_b64") or "").strip()
        public_key_raw = base64.b64decode(public_key_b64.encode("ascii"), validate=True)
        if len(public_key_raw) != 32:
            raise ValueError("invalid_recipient_public_key")
        recipient = x25519.X25519PublicKey.from_public_bytes(public_key_raw)
        ephemeral = x25519.X25519PrivateKey.generate()
        shared = ephemeral.exchange(recipient)
        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"nd-notebooklm-bootstrap-v1",
        ).derive(shared)
        nonce = os.urandom(12)
        ciphertext = AESGCM(aes_key).encrypt(
            nonce,
            config.master_token_b64.encode("utf-8"),
            b"nd-notebooklm-master-token-b64",
        )
        ephemeral_public = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return JSONResponse({
            "ok": True,
            "algorithm": "X25519+HKDF-SHA256+AESGCM",
            "ephemeral_public_key_b64": base64.b64encode(ephemeral_public).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "oidc_repository": claims.get("repository"),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:1200]}, status_code=400)


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


def _normalize_source_ids(raw: object) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise RuntimeError("source_ids_must_be_list")
    source_ids: list[str] = []
    seen: set[str] = set()
    for item in raw:
        source_id = str(item or "").strip()
        if not source_id:
            raise RuntimeError("source_ids_contains_empty")
        if source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)
    if not source_ids:
        raise RuntimeError("source_ids_empty")
    return source_ids


async def _validate_source_ids(client, notebook_id: str, source_ids: list[str] | None) -> None:
    if source_ids is None:
        return
    items = await client.sources.list(notebook_id)
    known_ids: set[str] = set()
    for item in items:
        payload = to_jsonable(item)
        if isinstance(payload, dict):
            source_id = str(payload.get("id") or "").strip()
            if source_id:
                known_ids.add(source_id)
    missing = [source_id for source_id in source_ids if source_id not in known_ids]
    if missing:
        raise RuntimeError("unknown_source_ids:" + ",".join(missing))


def _out_of_scope_citations(answer_payload: object, source_ids: list[str] | None) -> list[str]:
    if source_ids is None or not isinstance(answer_payload, dict):
        return []
    allowed = set(source_ids)
    outside: set[str] = set()
    references = answer_payload.get("references") or []
    if isinstance(references, list):
        for reference in references:
            if not isinstance(reference, dict):
                continue
            source_id = str(reference.get("source_id") or "").strip()
            if source_id and source_id not in allowed:
                outside.add(source_id)
    return sorted(outside)


async def _reset_current_chat(client, notebook_id: str) -> str | None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id is None:
        return None
    await client.chat.delete_conversation(notebook_id, conversation_id)
    return conversation_id



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
            if operation == "drive_permissions_audit":
                result = await _drive_permissions_audit()

            elif operation == "drive_read_canonical_json":
                result = await _drive_read_canonical_json(args)

            elif operation == "drive_create_immutable_json":
                result = await _drive_create_immutable_json(args)

            elif operation == "drive_repair_railway_rw":
                result = await _drive_repair_railway_rw(args)

            elif operation == "notebook_list":
                items = await client.notebooks.list()
                result = {"count": len(items), "notebooks": to_jsonable(items)}

            elif operation == "notebook_get":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                result = {"notebook": to_jsonable(await client.notebooks.get(nb_id))}

            elif operation == "source_list":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                items = await client.sources.list(nb_id)
                result = {"notebook_id": nb_id, "count": len(items), "sources": to_jsonable(items)}

            elif operation == "source_fulltext":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                source_id = str(args.get("source_id") or "").strip()
                if not source_id:
                    return JSONResponse({"ok": False, "error": "missing_source_id"}, status_code=400)
                fulltext = await client.sources.get_fulltext(nb_id, source_id)
                result = {"notebook_id": nb_id, "source_id": source_id, "fulltext": to_jsonable(fulltext)}

            elif operation == "chat_ask":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                question = str(args.get("question") or "").strip()
                if not question or len(question) > 8000:
                    return JSONResponse({"ok": False, "error": "invalid_question"}, status_code=400)
                source_ids = _normalize_source_ids(args.get("source_ids"))
                await _validate_source_ids(client, nb_id, source_ids)
                conversation_id = str(args.get("conversation_id") or "").strip() or None
                answer = await client.chat.ask(
                    nb_id,
                    question,
                    source_ids=source_ids,
                    conversation_id=conversation_id,
                )
                answer_payload = to_jsonable(answer)
                outside = _out_of_scope_citations(answer_payload, source_ids)
                if outside:
                    return JSONResponse(
                        {
                            "ok": False,
                            "error": "chat_scope_violation",
                            "out_of_scope_source_ids": outside,
                        },
                        status_code=409,
                    )
                result = {
                    "notebook_id": nb_id,
                    "source_ids": source_ids,
                    "answer": answer_payload,
                }

            elif operation == "chat_reset":
                if args.get("confirm") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                deleted_conversation_id = await _reset_current_chat(client, nb_id)
                result = {
                    "notebook_id": nb_id,
                    "deleted_conversation_id": deleted_conversation_id,
                    "fresh_next_ask": True,
                }

            elif operation == "chat_ask_fresh":
                if args.get("confirm_reset") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_reset_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                question = str(args.get("question") or "").strip()
                if not question or len(question) > 8000:
                    return JSONResponse({"ok": False, "error": "invalid_question"}, status_code=400)
                source_ids = _normalize_source_ids(args.get("source_ids"))
                if source_ids is None:
                    return JSONResponse({"ok": False, "error": "source_ids_required"}, status_code=400)
                await _validate_source_ids(client, nb_id, source_ids)
                deleted_conversation_id = await _reset_current_chat(client, nb_id)
                answer = await client.chat.ask(
                    nb_id,
                    question,
                    source_ids=source_ids,
                    conversation_id=None,
                )
                answer_payload = to_jsonable(answer)
                outside = _out_of_scope_citations(answer_payload, source_ids)
                if outside:
                    return JSONResponse(
                        {
                            "ok": False,
                            "error": "chat_scope_violation",
                            "out_of_scope_source_ids": outside,
                        },
                        status_code=409,
                    )
                if isinstance(answer_payload, dict) and bool(answer_payload.get("is_follow_up")):
                    return JSONResponse(
                        {"ok": False, "error": "fresh_conversation_not_established"},
                        status_code=409,
                    )
                result = {
                    "notebook_id": nb_id,
                    "source_ids": source_ids,
                    "deleted_conversation_id": deleted_conversation_id,
                    "fresh_conversation": True,
                    "answer": answer_payload,
                }

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


            elif operation == "source_bind_drive":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                file_id = str(args.get("file_id") or "").strip()
                name = str(args.get("name") or "").strip()
                query = str(args.get("query") or "").strip()
                if sum(1 for value in (file_id, name, query) if value) != 1:
                    return JSONResponse({"ok": False, "error": "provide_exactly_one_drive_selector"}, status_code=400)

                selector = "file_id" if file_id else ("name" if name else "query")
                if file_id:
                    match = await _drive_metadata_user(file_id)
                    if bool(match.get("trashed")):
                        return JSONResponse({"ok": False, "error": "drive_file_trashed"}, status_code=409)
                    if str(match.get("mimeType") or "") == "application/vnd.google-apps.folder":
                        return JSONResponse({"ok": False, "error": "drive_folder_not_supported"}, status_code=400)
                else:
                    matches = await _drive_search_files(name=name, query=query)
                    if not matches:
                        return JSONResponse({"ok": False, "error": "drive_file_not_found"}, status_code=404)
                    if len(matches) > 1:
                        candidates = [
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "mimeType": item.get("mimeType"),
                                "modifiedTime": item.get("modifiedTime"),
                            }
                            for item in matches[:10]
                        ]
                        return JSONResponse(
                            {"ok": False, "error": "drive_file_ambiguous", "count": len(matches), "candidates": candidates},
                            status_code=409,
                        )
                    match = matches[0]
                    file_id = str(match.get("id") or "").strip()

                title = str(args.get("title") or match.get("name") or "").strip()
                if not file_id or not title:
                    return JSONResponse({"ok": False, "error": "drive_match_missing_id_or_title"}, status_code=502)

                existing_items = await client.sources.list(nb_id)
                for existing in existing_items:
                    existing_json = to_jsonable(existing)
                    if (
                        isinstance(existing_json, dict)
                        and str(existing_json.get("drive_document_id") or "").strip() == file_id
                    ):
                        result = {
                            "notebook_id": nb_id,
                            "selector": selector,
                            "match": match,
                            "already_bound": True,
                            "source": existing_json,
                        }
                        break
                else:
                    src = await client.sources.add_drive(nb_id, file_id, title)
                    result = {
                        "notebook_id": nb_id,
                        "selector": selector,
                        "match": match,
                        "already_bound": False,
                        "source": to_jsonable(src),
                    }

            elif operation == "source_add_drive":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                file_id = str(args.get("file_id") or "").strip()
                title = str(args.get("title") or "").strip()
                if not file_id or not title:
                    return JSONResponse({"ok": False, "error": "missing_file_id_or_title"}, status_code=400)
                src = await client.sources.add_drive(nb_id, file_id, title)
                result = {"notebook_id": nb_id, "source": to_jsonable(src)}

            elif operation == "source_check_freshness":
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                source_id = str(args.get("source_id") or "").strip()
                if not source_id:
                    return JSONResponse({"ok": False, "error": "missing_source_id"}, status_code=400)
                is_fresh = await client.sources.check_freshness(nb_id, source_id)
                result = {"notebook_id": nb_id, "source_id": source_id, "is_fresh": bool(is_fresh), "needs_refresh": not bool(is_fresh)}

            elif operation == "source_ensure_fresh":
                if args.get("confirm") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                source_id = str(args.get("source_id") or "").strip()
                if not source_id:
                    return JSONResponse({"ok": False, "error": "missing_source_id"}, status_code=400)
                try:
                    max_checks = int(args.get("max_checks", 8))
                    poll_seconds = float(args.get("poll_seconds", 4.0))
                except (TypeError, ValueError):
                    return JSONResponse({"ok": False, "error": "invalid_poll_settings"}, status_code=400)
                max_checks = max(1, min(max_checks, 10))
                poll_seconds = max(1.0, min(poll_seconds, 5.0))
                initial_fresh = await client.sources.check_freshness(nb_id, source_id)
                final_fresh = bool(initial_fresh)
                refreshed = None
                checks = 0
                if initial_fresh:
                    final_fresh = True
                else:
                    refreshed = await client.sources.refresh(nb_id, source_id)
                    for attempt in range(max_checks):
                        await asyncio.sleep(poll_seconds)
                        checks = attempt + 1
                        final_fresh = await client.sources.check_freshness(nb_id, source_id)
                        if final_fresh:
                            break
                fulltext_ready = False
                if final_fresh:
                    try:
                        await client.sources.get_fulltext(nb_id, source_id)
                        fulltext_ready = True
                    except Exception:
                        fulltext_ready = False
                result = {
                    "notebook_id": nb_id,
                    "source_id": source_id,
                    "initial_fresh": bool(initial_fresh),
                    "refreshed": not bool(initial_fresh),
                    "refresh_result": to_jsonable(refreshed),
                    "is_fresh": bool(final_fresh),
                    "needs_refresh": not bool(final_fresh),
                    "fulltext_ready": fulltext_ready,
                    "checks": checks,
                    "max_checks": max_checks,
                    "poll_seconds": poll_seconds,
                }

            elif operation == "source_sync_drive":
                if args.get("confirm") is not True:
                    return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
                nb_id = await resolve_notebook(client, str(args.get("notebook") or ""))
                source_id = str(args.get("source_id") or "").strip()
                if not source_id:
                    return JSONResponse({"ok": False, "error": "missing_source_id"}, status_code=400)
                refreshed = await client.sources.refresh(nb_id, source_id)
                result = {"notebook_id": nb_id, "source_id": source_id, "refresh_result": to_jsonable(refreshed)}

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
    Route("/doctor/bootstrap/export-sealed", doctor_export_sealed, methods=["POST"]),
    Route("/doctor/github", github_bridge, methods=["POST"]),
    Route("/doctor/notebooks", doctor_notebooks, methods=["GET"]),
    Route("/doctor/sources", doctor_sources, methods=["GET"]),
    Route("/doctor/ask", doctor_ask, methods=["POST"]),
    Mount("/", app=mcp_app),
]

app = Starlette(routes=routes, lifespan=mcp_app.lifespan)