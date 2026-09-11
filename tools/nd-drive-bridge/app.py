from __future__ import annotations

import hmac
import os
from typing import Any

import google.auth
from fastapi import FastAPI, Header, HTTPException
from googleapiclient.discovery import build
from pydantic import BaseModel, Field

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DOCS_SCOPE = "https://www.googleapis.com/auth/documents"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"

app = FastAPI(title="ND Drive Bridge", version="1.0.0")


class InvokeRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)


def _secret() -> str:
    value = (os.environ.get("ND_DRIVE_BRIDGE_TOKEN") or "").strip()
    if len(value) < 24:
        raise RuntimeError("ND_DRIVE_BRIDGE_TOKEN missing or too short")
    return value


def _authorize(key: str | None) -> None:
    if not key or not hmac.compare_digest(key, _secret()):
        raise HTTPException(status_code=401, detail="unauthorized")


def _writable_ids() -> set[str]:
    return {
        item.strip()
        for item in (os.environ.get("ND_DRIVE_WRITABLE_FILE_IDS") or "").split(",")
        if item.strip()
    }


def _clients():
    credentials, _ = google.auth.default(scopes=[DRIVE_SCOPE, DOCS_SCOPE])
    return (
        build("drive", "v3", credentials=credentials, cache_discovery=False),
        build("docs", "v1", credentials=credentials, cache_discovery=False),
    )


def _flatten(content: list[dict[str, Any]] | None) -> str:
    out: list[str] = []
    for item in content or []:
        for element in (item.get("paragraph") or {}).get("elements", []):
            run = element.get("textRun") or {}
            if run.get("content"):
                out.append(run["content"])
        table = item.get("table") or {}
        for row in table.get("tableRows", []):
            for cell in row.get("tableCells", []):
                out.append(_flatten(cell.get("content")))
                out.append("\t")
            out.append("\n")
        toc = item.get("tableOfContents") or {}
        if toc:
            out.append(_flatten(toc.get("content")))
    return "".join(out)


def _walk_tabs(tabs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tab in tabs or []:
        props = tab.get("tabProperties") or {}
        doc_tab = tab.get("documentTab") or {}
        rows.append(
            {
                "tab_id": props.get("tabId"),
                "title": props.get("title"),
                "parent_tab_id": props.get("parentTabId"),
                "index": props.get("index"),
                "text": _flatten((doc_tab.get("body") or {}).get("content")),
            }
        )
        rows.extend(_walk_tabs(tab.get("childTabs")))
    return rows


def _doc_raw(document_id: str) -> dict[str, Any]:
    _, docs = _clients()
    return (
        docs.documents()
        .get(documentId=document_id, includeTabsContent=True)
        .execute()
    )


def docs_read(document_id: str) -> dict[str, Any]:
    doc = _doc_raw(document_id)
    tabs = _walk_tabs(doc.get("tabs"))
    if not tabs:
        tabs = [
            {
                "tab_id": None,
                "title": None,
                "parent_tab_id": None,
                "index": 0,
                "text": _flatten((doc.get("body") or {}).get("content")),
            }
        ]
    return {
        "document_id": document_id,
        "title": doc.get("title"),
        "revision_id": doc.get("revisionId"),
        "tabs": tabs,
        "text": "\n".join(tab["text"] for tab in tabs),
    }


def drive_get_metadata(file_id: str) -> dict[str, Any]:
    drive, _ = _clients()
    fields = (
        "id,name,mimeType,modifiedTime,version,trashed,webViewLink,parents,"
        "capabilities(canEdit,canDownload,canShare),"
        "md5Checksum,sha1Checksum,sha256Checksum"
    )
    return (
        drive.files()
        .get(fileId=file_id, fields=fields, supportsAllDrives=True)
        .execute()
    )


def drive_get_currentness_token(file_id: str) -> dict[str, Any]:
    meta = drive_get_metadata(file_id)
    token: dict[str, Any] = {
        "file_id": file_id,
        "mime_type": meta.get("mimeType"),
        "drive_version": meta.get("version"),
        "modified_time": meta.get("modifiedTime"),
        "trashed": bool(meta.get("trashed")),
        "md5": meta.get("md5Checksum"),
        "sha1": meta.get("sha1Checksum"),
        "sha256": meta.get("sha256Checksum"),
    }
    if meta.get("mimeType") == GOOGLE_DOC_MIME:
        token["docs_revision_id"] = docs_read(file_id).get("revision_id")
    return token


def _first_tab_end(doc: dict[str, Any]) -> dict[str, Any]:
    tabs = doc.get("tabs") or []
    tab_id = None
    content: list[dict[str, Any]]
    if tabs:
        first = tabs[0]
        tab_id = (first.get("tabProperties") or {}).get("tabId")
        content = ((first.get("documentTab") or {}).get("body") or {}).get("content") or []
    else:
        content = (doc.get("body") or {}).get("content") or []
    location: dict[str, Any] = {
        "index": max(1, int((content[-1] if content else {}).get("endIndex", 1)) - 1)
        if content
        else 1
    }
    if tab_id:
        location["tabId"] = tab_id
    return location


def _require_writable(file_id: str) -> None:
    if file_id not in _writable_ids():
        raise HTTPException(status_code=403, detail="write target denied")


def docs_append(
    document_id: str, text: str, expected_revision_id: str | None = None
) -> dict[str, Any]:
    _require_writable(document_id)
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")
    _, docs = _clients()
    before = _doc_raw(document_id)
    current = before.get("revisionId")
    if expected_revision_id and expected_revision_id != current:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_MISMATCH",
                "expected": expected_revision_id,
                "current": current,
            },
        )
    required = expected_revision_id or current
    response = (
        docs.documents()
        .batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": _first_tab_end(before),
                            "text": text,
                        }
                    }
                ],
                "writeControl": {"requiredRevisionId": required},
            },
        )
        .execute()
    )
    after = docs_read(document_id)
    return {
        "document_id": document_id,
        "before_revision_id": current,
        "after_revision_id": after.get("revision_id"),
        "write_control": response.get("writeControl"),
        "appended_chars": len(text),
    }


def docs_replace_exact(
    document_id: str,
    old_text: str,
    new_text: str,
    expected_revision_id: str | None = None,
) -> dict[str, Any]:
    _require_writable(document_id)
    if not old_text:
        raise HTTPException(status_code=400, detail="old_text must not be empty")
    before = docs_read(document_id)
    current = before.get("revision_id")
    if expected_revision_id and expected_revision_id != current:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_MISMATCH",
                "expected": expected_revision_id,
                "current": current,
            },
        )
    occurrences = before.get("text", "").count(old_text)
    if occurrences != 1:
        raise HTTPException(
            status_code=409,
            detail={"code": "EXACT_MATCH_REQUIRED", "occurrences": occurrences},
        )
    _, docs = _clients()
    response = (
        docs.documents()
        .batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "replaceAllText": {
                            "containsText": {"text": old_text, "matchCase": True},
                            "replaceText": new_text,
                        }
                    }
                ],
                "writeControl": {"requiredRevisionId": expected_revision_id or current},
            },
        )
        .execute()
    )
    after = docs_read(document_id)
    return {
        "document_id": document_id,
        "before_revision_id": current,
        "after_revision_id": after.get("revision_id"),
        "write_control": response.get("writeControl"),
        "replaced_occurrences": 1,
    }


def drive_changes_start_token() -> dict[str, Any]:
    drive, _ = _clients()
    result = drive.changes().getStartPageToken(supportsAllDrives=True).execute()
    return {"start_page_token": result["startPageToken"]}


def drive_changes_list(page_token: str, page_size: int = 100) -> dict[str, Any]:
    drive, _ = _clients()
    return (
        drive.changes()
        .list(
            pageToken=page_token,
            pageSize=max(1, min(int(page_size), 1000)),
            includeRemoved=True,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            restrictToMyDrive=False,
            spaces="drive",
            fields=(
                "nextPageToken,newStartPageToken,"
                "changes(removed,fileId,time,changeType,"
                "file(id,name,mimeType,modifiedTime,version,trashed,parents))"
            ),
        )
        .execute()
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "nd-drive-bridge",
        "mode": "infrastructure-access-layer",
        "semantic_authority": False,
        "writable_targets": len(_writable_ids()),
    }


@app.post("/invoke")
def invoke(
    request: InvokeRequest,
    x_nd_bridge_key: str | None = Header(default=None),
):
    _authorize(x_nd_bridge_key)
    a = request.args
    tool = request.tool
    if tool == "docs_read":
        return {"result": docs_read(str(a["document_id"]))}
    if tool == "docs_append":
        return {
            "result": docs_append(
                str(a["document_id"]),
                str(a["text"]),
                str(a["expected_revision_id"]) if a.get("expected_revision_id") else None,
            )
        }
    if tool == "docs_replace_exact":
        return {
            "result": docs_replace_exact(
                str(a["document_id"]),
                str(a["old_text"]),
                str(a.get("new_text", "")),
                str(a["expected_revision_id"]) if a.get("expected_revision_id") else None,
            )
        }
    if tool == "drive_get_metadata":
        return {"result": drive_get_metadata(str(a["file_id"]))}
    if tool == "drive_get_currentness_token":
        return {"result": drive_get_currentness_token(str(a["file_id"]))}
    if tool == "drive_changes_start_token":
        return {"result": drive_changes_start_token()}
    if tool == "drive_changes_list":
        return {
            "result": drive_changes_list(
                str(a["page_token"]), int(a.get("page_size", 100))
            )
        }
    raise HTTPException(status_code=404, detail="tool denied")
