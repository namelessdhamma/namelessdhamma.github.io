from __future__ import annotations

import asyncio
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from notebooklm import NotebookLMClient

from notebooklm_runtime.live_probe_core import (
    is_authorized,
    materialize_master_token,
    refresh_storage_from_master_token,
)


async def _list_notebooks(master_token_b64: str) -> int:
    with tempfile.TemporaryDirectory(prefix="nd-notebooklm-") as tmp:
        home = Path(tmp)
        materialize_master_token(master_token_b64, home)
        refresh_storage_from_master_token(home)

        previous_home = os.environ.get("NOTEBOOKLM_HOME")
        os.environ["NOTEBOOKLM_HOME"] = str(home)
        try:
            async with NotebookLMClient.from_storage(
                profile="default",
                backend="android",
                timeout=30.0,
                server_error_max_retries=1,
                rate_limit_max_retries=1,
            ) as client:
                notebooks = await client.notebooks.list()
                return len(notebooks)
        finally:
            if previous_home is None:
                os.environ.pop("NOTEBOOKLM_HOME", None)
            else:
                os.environ["NOTEBOOKLM_HOME"] = previous_home


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, object]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        probe_token = os.environ.get("ND_PROBE_TOKEN", "")
        if not is_authorized(self.headers.get("authorization"), probe_token):
            self._send(401, {"ok": False, "stage": "B", "error": "unauthorized"})
            return

        master_token_b64 = os.environ.get("NOTEBOOKLM_MASTER_TOKEN_B64", "")
        if not master_token_b64:
            self._send(503, {"ok": False, "stage": "B", "error": "credential_unavailable"})
            return

        try:
            count = asyncio.run(_list_notebooks(master_token_b64))
        except Exception as exc:  # sanitized boundary: never return provider payloads or credentials
            self._send(
                502,
                {
                    "ok": False,
                    "stage": "B",
                    "error": "notebooklm_probe_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return

        self._send(
            200,
            {
                "ok": True,
                "stage": "B",
                "operation": "notebook_list",
                "notebook_count": count,
                "contains_titles": False,
                "contains_credentials": False,
            },
        )
