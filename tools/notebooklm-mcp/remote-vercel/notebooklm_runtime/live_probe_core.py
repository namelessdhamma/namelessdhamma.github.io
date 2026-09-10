from __future__ import annotations

import base64
import hmac
import os
import subprocess
import sys
from pathlib import Path


def is_authorized(authorization_header: str | None, expected_token: str) -> bool:
    if not authorization_header or not expected_token:
        return False
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return False
    supplied = authorization_header[len(prefix) :]
    return hmac.compare_digest(supplied, expected_token)


def decode_master_token(encoded: str) -> bytes:
    return base64.b64decode(encoded.encode("ascii"), validate=True)


def materialize_master_token(encoded: str, home: Path) -> Path:
    raw = decode_master_token(encoded)
    profile_dir = home / "profiles" / "default"
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / "master_token.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def refresh_storage_from_master_token(home: Path) -> None:
    env = os.environ.copy()
    env["NOTEBOOKLM_HOME"] = str(home)
    env["NOTEBOOKLM_PROFILE"] = "default"
    env.pop("NOTEBOOKLM_AUTH_JSON", None)
    subprocess.run(
        [sys.executable, "-m", "notebooklm", "auth", "refresh", "--verify"],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
    )
