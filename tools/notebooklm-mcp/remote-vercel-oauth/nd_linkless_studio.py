"""Render-native NotebookLM Studio export with NO external file links.

All exports are authenticated MCP tool results. Large files are streamed through
bounded base64 chunks. A short-lived private temp file is created per request and
removed even after errors; no signed URL, resource_link, public download route,
or persistent plaintext output is created.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import tempfile
from pathlib import Path

from fastmcp import Context
from notebooklm._app import download as download_core
from notebooklm.exceptions import ValidationError
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import reject_non_canonical_id, resolve_artifact, resolve_notebook
from notebooklm.mcp.tools._studio_download import (
    _DOWNLOAD_SPECS,
    _KIND_TO_DOWNLOAD_KEY,
    _passthrough_download_notebook,
    _resolve_artifact_id,
    download_extension,
    download_filename,
    download_mime_type,
)

DEFAULT_BYTES = 64 * 1024
MAX_BYTES = 96 * 1024
TEXT_ARTIFACTS = frozenset({"report", "data-table"})


def install(mcp) -> None:
    """Replace the single broken upstream remote download without other tool changes."""
    mcp.remove_tool("studio_download")

    async def fetch_chunk(
        ctx: Context,
        notebook: str,
        artifact: str | None,
        artifact_type: str | None,
        artifact_id: str | None,
        output_format: str | None,
        offset: int,
        max_bytes: int,
    ) -> dict:
        if type(offset) is not int or offset < 0:
            raise ValidationError("offset must be a nonnegative integer")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ValidationError(f"max_bytes must be 1..{MAX_BYTES}")
        if artifact is not None and (artifact_type is not None or artifact_id is not None):
            raise ValidationError("Choose artifact or artifact_type/artifact_id, not both")
        if artifact is None and artifact_type is None:
            raise ValidationError("Provide artifact or artifact_type")

        client = get_client(ctx)
        nb_id = await resolve_notebook(client, notebook)
        title = None

        if artifact is not None:
            resolved_id = await resolve_artifact(client, nb_id, artifact)
            items = await client.artifacts.list(nb_id)
            match = next((a for a in items if a.id.lower() == resolved_id.lower()), None)
            if match is None:
                raise ValidationError("Artifact not found in this notebook")
            if not match.is_completed:
                raise ValidationError("Artifact generation is not complete")
            artifact_type = _KIND_TO_DOWNLOAD_KEY.get(match.kind)
            if artifact_type is None:
                raise ValidationError("Artifact type cannot be exported")
            artifact_id = resolved_id
            title = match.title

        spec = _DOWNLOAD_SPECS.get(artifact_type)
        if spec is None:
            raise ValidationError(f"Unsupported Studio export kind: {artifact_type}")
        if output_format is not None:
            if not spec.format_choices or output_format not in spec.format_choices:
                raise ValidationError("Unsupported output_format for this artifact kind")

        if artifact is None and artifact_id is not None:
            reject_non_canonical_id(artifact_id, "artifact")
            typed = await client.artifacts.list(nb_id, spec.kind)
            completed = [{"id": a.id, "title": a.title} for a in typed if a.is_completed]
            artifact_id = _resolve_artifact_id(completed, artifact_id)
            title = next((c["title"] for c in completed if c["id"] == artifact_id), None)

        with tempfile.TemporaryDirectory(prefix="nd-nblm-export-") as tmp:
            target = Path(tmp) / ("export" + download_extension(spec, output_format))
            args = {
                "notebook_id": nb_id,
                "output_path": str(target),
                "latest": artifact_id is None,
            }
            if artifact_id is not None:
                args["artifact_id"] = artifact_id
            if output_format is not None:
                args[spec.format_param_name] = output_format
            plan = download_core.build_download_plan(spec, args, cwd=Path.cwd())
            result = await download_core.execute_download(
                plan,
                client,
                notebook_resolver=_passthrough_download_notebook,
                artifact_resolver=_resolve_artifact_id,
            )
            if result.outcome != download_core.DownloadOutcome.SINGLE_DOWNLOADED:
                raise ValidationError(f"Artifact not downloadable yet: {result.outcome.value}")
            file_path = Path(result.output_path or str(target))

            def read_bounded():
                sha = hashlib.sha256()
                with file_path.open("rb") as stream:
                    while True:
                        buf = stream.read(1024 * 1024)
                        if not buf:
                            break
                        sha.update(buf)
                    size = stream.tell()
                    if offset > size:
                        raise ValidationError("offset exceeds artifact size")
                    stream.seek(offset)
                    block = stream.read(max_bytes)
                return sha.hexdigest(), size, block

            sha, size, block = await asyncio.to_thread(read_bounded)

        selected = result.artifact or {}
        if isinstance(selected, dict):
            artifact_id = selected.get("id") or artifact_id
            title = selected.get("title") or title
        end = offset + len(block)
        output = {
            "status": "inline_complete" if end >= size else "inline_chunk",
            "notebook_id": nb_id,
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "filename": download_filename(spec, title, output_format),
            "mime_type": download_mime_type(spec, output_format),
            "size_bytes": size,
            "sha256": sha,
            "offset": offset,
            "next_offset": end,
            "eof": end >= size,
            "encoding": "base64",
            "data_base64": base64.b64encode(block).decode("ascii"),
            "delivery": "authenticated_mcp_inline_no_external_link",
        }
        if artifact_type in TEXT_ARTIFACTS:
            try:
                output["content"] = block.decode("utf-8-sig" if offset == 0 else "utf-8")
                output["content_complete"] = offset == 0 and end >= size
            except UnicodeDecodeError:
                output["content_complete"] = False
        return output

    @mcp.tool
    async def studio_download(
        ctx: Context,
        notebook: str,
        artifact: str | None = None,
        artifact_type: str | None = None,
        path: str | None = None,
        output_format: str | None = None,
        artifact_id: str | None = None,
    ) -> dict:
        """Export an artifact inline (no link). For large results use studio_export_chunk."""
        # Backward-compatible chunk paging for clients whose tool catalog was
        # cached before studio_export_chunk appeared. This is NOT a filesystem
        # path: the sole accepted control format is nd-inline-chunk:<offset>.
        # Ordinary paths remain ignored; never write to a client-provided path.
        offset = 0
        if path is not None and path.startswith("nd-inline-chunk:"):
            value = path[len("nd-inline-chunk:"):]
            if not value.isascii() or not value.isdecimal() or (
                len(value) > 1 and value.startswith("0")
            ) or len(value) > 12:
                raise ValidationError("Invalid inline chunk offset")
            offset = int(value)
        return await fetch_chunk(
            ctx, notebook, artifact, artifact_type, artifact_id, output_format,
            offset, DEFAULT_BYTES,
        )

    @mcp.tool
    async def studio_export_chunk(
        ctx: Context,
        notebook: str,
        artifact_type: str,
        artifact_id: str | None = None,
        output_format: str | None = None,
        offset: int = 0,
        max_bytes: int = DEFAULT_BYTES,
    ) -> dict:
        """Continue a large Studio export using inline authenticated base64 chunks."""
        return await fetch_chunk(
            ctx, notebook, None, artifact_type, artifact_id, output_format,
            offset, max_bytes,
        )
