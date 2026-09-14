from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = b"ND1"
AAD = b"ND_NOTEBOOKLM_RAILWAY_BACKUP_V1"

master = os.environ.get("NOTEBOOKLM_MASTER_TOKEN_B64", "").strip()
password = os.environ.get("NOTEBOOKLM_MCP_OAUTH_PASSWORD", "").strip()

if not master:
    raise SystemExit("ND_EXPORT_ERROR missing NOTEBOOKLM_MASTER_TOKEN_B64")
if len(password) < 24:
    raise SystemExit("ND_EXPORT_ERROR missing/short NOTEBOOKLM_MCP_OAUTH_PASSWORD")

salt = secrets.token_bytes(16)
nonce = secrets.token_bytes(12)
key = hashlib.scrypt(
    password.encode("utf-8"),
    salt=salt,
    n=2**14,
    r=8,
    p=1,
    dklen=32,
)
ciphertext = AESGCM(key).encrypt(nonce, master.encode("utf-8"), AAD)
payload = PREFIX + salt + nonce + ciphertext
wrapped = base64.b64encode(payload).decode("ascii")
print("ND_NOTEBOOKLM_RAILWAY_WRAPPED_MASTER=" + wrapped, flush=True)
