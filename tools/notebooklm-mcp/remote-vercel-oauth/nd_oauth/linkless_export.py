"""ChatGPT-safe NotebookLM Studio export without MCP ResourceLink attachments.

The upstream remote studio_download always exposes an expiring ResourceLink,
which prompts ChatGPT to obtain an external file even for ordinary JSON/text.
This adapter preserves metadata and bounded inline text, and supplies an
explicit authenticated linkless chunk tool for EVERY artifact kind.

No OAuth, permission, signed-file endpoint, or Google provider security is
disabled. Binary chunks are base64-encoded inside authenticated MCP responses.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import os
import tempfile
from pathlib import Path

from fastmcp import Context
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from notebooklm._app import download as download_core
from notebooklm.exceptions import ValidationError
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import resolve_notebook
from notebooklm.mcp.tools import _studio_download as download_tools
from notebooklm.mcp.tools import studio as studio_tools

_CHUNK_MAX_BYTES = 96 * 1024
_TEXT_KINDS = frozenset({"report", "data-table"})


def _linkless_broker(
    cfg,
    notebook_id: str,
    artifact_type: str,
    output_format: str | None,
    artifact_id: str | None = None,
    *,
    title: str | None = None,
    inline: tuple[str, int, bool] | None = None,
    size_bytes: int | None = None,
) -> ToolResult:
    """Return no URLs, resource_link blocks, file attachments or signed tokens."""
    spec = download_tools._DOWNLOAD_SPECS[artifact_type]
    data = {
        "status": "inline_ready" if inline is not None else "chunk_export_available",
        "notebook_id": notebook_id,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "output_format": output_format,
        "filename": download_tools.download_filename(spec, title, output_format),
        "mime_type": download_tools.download_mime_type(spec, output_format),
        "size_bytes": size_bytes,
        "delivery": "authenticated_mcp_inline_only",
        "next_tool": "studio_export_chunk",
    }
    if inline is not None:
        content, char_count, truncated = inline
        data.update(content=content, char_count=char_count, truncated=truncated)
        explanation = content + (
            "\n[Truncated. Use studio_export_chunk to get the complete original file.]"
            if truncated else ""
        )
    else:
        explanation = (
            "No file was downloaded by ChatGPT. For the complete artifact use "
            "studio_export_chunk with the same notebook/type/id/format. "
            "The payload is transferred in authenticated inline chunks, "
            "without an external file link."
        )
    return ToolResult(
        content=[TextContent(type="text", text=explanation)],
        structured_content=data,
    )


def install_linkless_exports(mcp) -> None:
    """Install once for the dedicated ND Vercel MCP process."""
    # studio.py imports _broker_download directly; patch BOTH references.
    # This adapter never signs any file URL for Studio tool output.
    studio_tools._broker_download = _linkless_broker
    download_tools._broker_download = _linkless_broker

    @mcp.tool
    async def studio_export_chunk(
        ctx: Context,
        notebook: str,
        artifact_type: str,
        artifact_id: str | None = None,
        output_format: str | None = None,
        offset: int = 0,
        max_bytes: int = _CHUNK_MAX_BYTES,
    ) -> dict:
        """Return a Studio file as authenticated inline bytes without download links.

        Supports all upstream downloadable kinds and output formats.
        For JSON/CSV/report text, a decoded 'content' is included if the chunk
        has valid UTF-8 boundaries; 'data_base64' is always exact for every kind.
        Continue from next_offset until eof. Verify sha256 across all chunks.
        Provider download executes fresh on each chunk (no persistent file
        replicas); avoid exporting huge media piecemeal unless necessary.
        """
        if artifact_type not in download_tools._DOWNLOAD_SPECS:
            raise ValidationError(
                f"Unsupported Studio type: {artifact_type!r}"
            )
        spec = download_tools._DOWNLOAD_SPECS[artifact_type]
        if output_format is not None:
            choices = spec.format_choices
            if not choices or output_format not in choices:
                raise ValidationError(
                    f"Invalid {output_format!r} format for {artifact_type!r}"
                )
        if type(offset) is not int or offset < 0:
            raise ValidationError("offset must be a nonnegative integer")
        if type(max_bytes) is not int or not 1 <= max_bytes <= _CHUNK_MAX_BYTES:
            raise ValidationError(
                f"max_bytes must be between 1 and {_CHUNK_MAX_BYTES}"
            )
        candidate = get_client(ctx)
        client = await candidate if inspect.isawaitable(candidate) else candidate
        nb_id = await resolve_notebook(client, notebook)

        with tempfile.TemporaryDirectory(prefix="nd-nblm-linkless-") as folder:
            suffix = download_tools.download_extension(spec, output_format)
            target = Path(folder) / ("artifact" + suffix)
            args: dict = {
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
                notebook_resolver=download_tools._passthrough_download_notebook,
                artifact_resolver=download_tools._resolve_artifact_id,
            )
            if result.outcome != download_core.DownloadOutcome.SINGLE_DOWNLOADED:
                return {
                    "status": "artifact_not_ready",
                    "artifact_type": artifact_type,
                    "artifact_id": artifact_id,
                    "delivery": "authenticated_mcp_inline_only",
                }
            served = Path(result.output_path or str(target))
            # Bounded processing: only read chunk into memory; hash the full
            # file incrementally to detect any cross-call artifact mutation.
            def read_exact():
                h = hashlib.sha256()
                with served.open("rb") as fh:
                    while True:
                        b = fh.read(1024 * 1024)
                        if not b:
                            break
                        h.update(b)
                    size = fh.tell()
                    fh.seek(offset)
                    chunk = fh.read(max_bytes)
                return h.hexdigest(), size, chunk
            sha, size, chunk = await asyncio.to_thread(read_exact)

        if offset > size:
            raise ValidationError("offset is greater than the artifact size")
        next_offset = offset + len(chunk)
        payload = {
            "status": "inline_chunk",
            "notebook_id": nb_id,
            "artifact_type": artifact_type,
            "artifact_id": result.artifact.get("id") if isinstance(result.artifact, dict) else artifact_id,
            "output_format": output_format,
            "mime_type": download_tools.download_mime_type(spec, output_format),
            "filename": download_tools.download_filename(
                spec,
                result.artifact.get("title") if isinstance(result.artifact, dict) else None,
                output_format,
            ),
            "size_bytes": size,
            "sha256": sha,
            "offset": offset,
            "next_offset": next_offset,
            "eof": next_offset >= size,
            "encoding": "base64",
            "data_base64": base64.b64encode(chunk).decode("ascii"),
            "delivery": "authenticated_mcp_inline_only",
        }
        if artifact_type in _TEXT_KINDS:
            try:
                payload["content"] = chunk.decode("utf-8-sig" if offset == 0 else "utf-8")
            except UnicodeDecodeError:
                # Bytes remain losslessly available in data_base64.
                pass
        return payload
