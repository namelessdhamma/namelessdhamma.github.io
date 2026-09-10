from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from notebooklm import NotebookLMClient


def materialize_master_token(encoded: str, home: Path) -> Path:
    """Materialize the Google master token only inside ephemeral runtime storage."""
    raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    profile_dir = home / "profiles" / "default"
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = profile_dir / "master_token.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def refresh_storage(home: Path) -> None:
    """Derive NotebookLM storage_state.json from the durable master credential."""
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


def make_client_factory(
    master_token_b64: str,
    *,
    home: Path = Path("/tmp/nd-notebooklm-runtime"),
    refresh: Callable[[Path], None] = refresh_storage,
    client_builder: Callable[..., Any] = NotebookLMClient.from_storage,
):
    """Return the client-factory seam expected by notebooklm.mcp.create_server.

    Preparation is done when the MCP lifespan starts rather than at module import,
    keeping builds and OAuth discovery independent of Google network availability.
    The process-wide NOTEBOOKLM_HOME is intentionally pinned to one account/home;
    every function instance serves the same configured ND NotebookLM account.
    """

    @asynccontextmanager
    async def factory():
        if not master_token_b64:
            raise RuntimeError("NotebookLM master credential is not configured")
        materialize_master_token(master_token_b64, home)
        os.environ["NOTEBOOKLM_HOME"] = str(home)
        os.environ["NOTEBOOKLM_PROFILE"] = "default"
        os.environ.pop("NOTEBOOKLM_AUTH_JSON", None)
        await asyncio.to_thread(refresh, home)

        async with client_builder(
            profile="default",
            backend="android",
            timeout=30.0,
            server_error_max_retries=1,
            rate_limit_max_retries=1,
        ) as client:
            yield client

    return factory
