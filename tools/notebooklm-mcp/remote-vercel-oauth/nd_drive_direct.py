from __future__ import annotations

import base64
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


_TOKEN_LOCK = threading.Lock()
_TOKEN_CACHE: dict[str, object] = {}
SCOPES = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _credential() -> tuple[str, bytes]:
    email = os.environ.get("ND_GOOGLE_CLIENT_EMAIL", "").strip()
    raw_b64 = os.environ.get("ND_GOOGLE_PRIVATE_KEY_B64", "").strip()
    if not email or not raw_b64:
        raise RuntimeError("google service-account env missing")
    try:
        raw = base64.b64decode(raw_b64)
    except Exception as exc:
        raise RuntimeError("google private key base64 invalid") from exc
    try:
        obj = json.loads(raw.decode("utf-8"))
        email = str(obj.get("client_email") or email).strip()
        raw = str(obj.get("private_key") or "").encode("utf-8")
    except Exception:
        pass
    if not email or b"BEGIN PRIVATE KEY" not in raw:
        raise RuntimeError("google service-account material incomplete")
    return email, raw


def _access_token() -> str:
    email, pem = _credential()
    now = int(time.time())
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(email)
        if isinstance(cached, dict) and int(cached.get("exp", 0)) > now + 90:
            return str(cached["token"])
        header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _b64u(json.dumps({
            "iss": email,
            "scope": SCOPES,
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3500,
        }, separators=(",", ":")).encode())
        unsigned = (header + "." + payload).encode()
        key = serialization.load_pem_private_key(pem, password=None)
        sig = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
        assertion = header + "." + payload + "." + _b64u(sig)
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            obj = json.loads(response.read().decode("utf-8") or "{}")
        token = str(obj.get("access_token") or "")
        if not token:
            raise RuntimeError("google access token missing")
        _TOKEN_CACHE[email] = {"token": token, "exp": now + int(obj.get("expires_in") or 3500)}
        return token


def _google_json(url: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    token = _access_token()
    data = None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "nd-notebooklm-drive-direct/1.0",
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            obj = json.loads(raw or "{}")
        except Exception:
            obj = {"raw": raw[:1200]}
        return exc.code, obj


def _writable_ids() -> set[str]:
    raw = (
        os.environ.get("ND_DRIVE_MCP_WRITABLE_FILE_IDS", "")
        or os.environ.get("ND_DRIVE_WRITABLE_FILE_IDS", "")
    )
    return {x.strip() for x in raw.split(",") if x.strip()}


def _ensure_write(document_id: str) -> None:
    if document_id not in _writable_ids():
        raise RuntimeError("drive docs write denied")


def _collect(elements: list, out: list[str]) -> None:
    for el in elements or []:
        paragraph = el.get("paragraph") or {}
        for pe in paragraph.get("elements", []):
            tr = pe.get("textRun") or {}
            if tr.get("content"):
                out.append(str(tr["content"]))
        table = el.get("table") or {}
        for row in table.get("tableRows", []):
            for cell in row.get("tableCells", []):
                _collect(cell.get("content", []), out)
        toc = el.get("tableOfContents") or {}
        if toc:
            _collect(toc.get("content", []), out)


def _doc_snapshot(document_id: str) -> dict:
    status, doc = _google_json(
        "https://docs.googleapis.com/v1/documents/"
        + urllib.parse.quote(document_id)
        + "?includeTabsContent=true"
    )
    if status != 200:
        raise RuntimeError(f"docs read failed HTTP {status}")
    out: list[str] = []
    tabs = doc.get("tabs") or []
    if tabs:
        def walk(tab: dict) -> None:
            dt = tab.get("documentTab") or {}
            _collect((dt.get("body") or {}).get("content", []), out)
            for child in tab.get("childTabs") or []:
                walk(child)
        for tab in tabs:
            walk(tab)
    else:
        _collect((doc.get("body") or {}).get("content", []), out)
    return {
        "document_id": document_id,
        "title": doc.get("title"),
        "revision_id": doc.get("revisionId"),
        "text": "".join(out),
    }


def _batch(document_id: str, requests: list[dict], expected_revision_id: str | None) -> dict:
    body: dict = {"requests": requests}
    if expected_revision_id:
        body["writeControl"] = {"requiredRevisionId": expected_revision_id}
    status, obj = _google_json(
        "https://docs.googleapis.com/v1/documents/"
        + urllib.parse.quote(document_id)
        + ":batchUpdate",
        method="POST",
        body=body,
    )
    if status != 200:
        msg = json.dumps(obj, ensure_ascii=False)[:1200]
        if expected_revision_id and status in (400, 409):
            raise RuntimeError("REVISION_MISMATCH: " + msg)
        raise RuntimeError(f"docs batchUpdate HTTP {status}: {msg}")
    return obj


def direct_drive_call(tool: str, args: dict) -> object:
    tool = str(tool or "").strip()
    args = args or {}
    if tool in ("drive_get_metadata", "drive_get_currentness_token"):
        fid = str(args.get("file_id") or args.get("document_id") or "").strip()
        if not fid:
            raise RuntimeError("file_id required")
        fields = urllib.parse.quote(
            "id,name,mimeType,modifiedTime,version,trashed,md5Checksum,sha1Checksum,sha256Checksum,parents,capabilities(canEdit)"
        )
        status, meta = _google_json(
            "https://www.googleapis.com/drive/v3/files/"
            + urllib.parse.quote(fid)
            + "?supportsAllDrives=true&fields="
            + fields
        )
        if status != 200:
            raise RuntimeError(f"drive metadata HTTP {status}")
        out = {
            "file_id": fid,
            "name": meta.get("name"),
            "mime_type": meta.get("mimeType"),
            "drive_version": meta.get("version"),
            "modified_time": meta.get("modifiedTime"),
            "trashed": bool(meta.get("trashed", False)),
            "can_edit": bool((meta.get("capabilities") or {}).get("canEdit")),
            "md5": meta.get("md5Checksum"),
            "sha1": meta.get("sha1Checksum"),
            "sha256": meta.get("sha256Checksum"),
        }
        if tool == "drive_get_currentness_token" and meta.get("mimeType") == "application/vnd.google-apps.document":
            out["docs_revision_id"] = _doc_snapshot(fid).get("revision_id")
        return out

    if tool == "docs_read":
        fid = str(args.get("document_id") or "").strip()
        if not fid:
            raise RuntimeError("document_id required")
        return _doc_snapshot(fid)

    if tool == "docs_append":
        fid = str(args.get("document_id") or "").strip()
        _ensure_write(fid)
        before = _doc_snapshot(fid)
        expected = str(args.get("expected_revision_id") or before.get("revision_id") or "")
        _batch(fid, [{"insertText": {"endOfSegmentLocation": {}, "text": str(args.get("text") or "")}}], expected)
        after = _doc_snapshot(fid)
        return {
            "document_id": fid,
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
            "text_length": len(str(after.get("text") or "")),
        }

    if tool == "docs_replace_exact":
        fid = str(args.get("document_id") or "").strip()
        _ensure_write(fid)
        old = str(args.get("old_text") or "")
        new = str(args.get("new_text") or "")
        before = _doc_snapshot(fid)
        count = str(before.get("text") or "").count(old)
        if count != 1:
            raise RuntimeError(f"EXACT_MATCH_REQUIRED: found {count} occurrences")
        expected = str(args.get("expected_revision_id") or before.get("revision_id") or "")
        obj = _batch(fid, [{
            "replaceAllText": {
                "containsText": {"text": old, "matchCase": True},
                "replaceText": new,
            }
        }], expected)
        changed = None
        replies = obj.get("replies") or []
        if replies:
            changed = (replies[0].get("replaceAllText") or {}).get("occurrencesChanged")
        after = _doc_snapshot(fid)
        return {
            "document_id": fid,
            "occurrences_changed": changed,
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
        }

    if tool == "drive_changes_start_token":
        status, obj = _google_json("https://www.googleapis.com/drive/v3/changes/startPageToken?supportsAllDrives=true")
        if status != 200:
            raise RuntimeError(f"drive changes start token HTTP {status}")
        return obj

    if tool == "drive_changes_list":
        page_token = str(args.get("page_token") or "").strip()
        if not page_token:
            raise RuntimeError("page_token required")
        size = max(1, min(1000, int(args.get("page_size") or 100)))
        q = urllib.parse.urlencode({
            "pageToken": page_token,
            "pageSize": size,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,time,file(id,name,mimeType,modifiedTime,version,trashed))",
        })
        status, obj = _google_json("https://www.googleapis.com/drive/v3/changes?" + q)
        if status != 200:
            raise RuntimeError(f"drive changes list HTTP {status}")
        return obj

    raise RuntimeError("tool_not_allowed")


def bridge_authorized(header_value: str) -> bool:
    expected = os.environ.get("ND_DRIVE_BRIDGE_TOKEN", "").strip()
    supplied = str(header_value or "").strip()
    return len(expected) >= 24 and hmac.compare_digest(expected, supplied)


def drive_health() -> dict:
    statehead = os.environ.get(
        "ND_GOOGLE_STATEHEAD_ID",
        "1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ",
    ).strip()
    result = direct_drive_call("drive_get_currentness_token", {"file_id": statehead})
    return {
        "ok": bool(result.get("file_id") == statehead and result.get("docs_revision_id")),
        "route": "railway_notebooklm_direct_google",
        "statehead_id": statehead,
        "drive_version": result.get("drive_version"),
        "docs_revision_present": bool(result.get("docs_revision_id")),
        "can_edit": bool(result.get("can_edit")),
        "writable_file_count": len(_writable_ids()),
    }
