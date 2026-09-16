from __future__ import annotations

import json
import os
import http.client
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastmcp import Context, FastMCP
from notebooklm._app.serialize import to_jsonable
from notebooklm.mcp._context import get_client
from notebooklm.mcp._resolve import resolve_notebook, resolve_source
from notebooklm.mcp.server import ClientFactory, create_server

from .blob_provider import BlobBackedOAuthProvider, OAuthStateStore
from .server_app import SERVICE_NAME, SERVICE_VERSION

_YT_TOKEN_URL = "https://oauth2.googleapis.com/token"
_YT_API_BASE = "https://www.googleapis.com/youtube/v3/"
_YT_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3/"
_YT_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2/"


_YT_CREDENTIAL_PATH = Path(os.environ.get("ND_YOUTUBE_CREDENTIAL_PATH", "/data/nd-notebooklm/youtube-credentials.json"))

def _yt_credential_file() -> dict:
    try:
        obj = json.loads(_YT_CREDENTIAL_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def _yt_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        value = str(_yt_credential_file().get(name) or "").strip()
    if not value:
        raise RuntimeError("youtube_missing_" + name.lower())
    return value


def _yt_access_token() -> str:
    form = urllib.parse.urlencode(
        {
            "client_id": _yt_required("ND_YOUTUBE_CLIENT_ID"),
            "client_secret": _yt_required("ND_YOUTUBE_CLIENT_SECRET"),
            "refresh_token": _yt_required("ND_YOUTUBE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _YT_TOKEN_URL,
        data=form,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "ND-YouTube-MCP/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("youtube_token_http_" + str(exc.code) + ":" + detail[:600]) from None
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("youtube_access_token_missing")
    return token


def _yt_http_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    timeout: int = 90,
) -> dict:
    token = _yt_access_token()
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "ND-YouTube-MCP/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json; charset=UTF-8"
    request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw or "{}") if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(detail or "{}")
            message = json.dumps(parsed, ensure_ascii=False)[:1600]
        except Exception:
            message = detail[:1600]
        raise RuntimeError("youtube_http_" + str(exc.code) + ":" + message) from None


def _yt_data_api(
    method: str,
    resource: str,
    *,
    query: dict | None = None,
    payload: dict | None = None,
) -> dict:
    clean = resource.strip().lstrip("/")
    if not clean or ".." in clean or "://" in clean:
        raise RuntimeError("invalid_youtube_resource")
    url = _YT_API_BASE + urllib.parse.quote(clean, safe="/")
    if query:
        url += "?" + urllib.parse.urlencode(
            {str(k): str(v) for k, v in query.items() if v is not None},
            doseq=True,
        )
    return _yt_http_json(method, url, payload=payload)


def _yt_channel() -> dict:
    result = _yt_data_api(
        "GET",
        "channels",
        query={
            "part": "id,snippet,statistics,contentDetails,brandingSettings,status",
            "mine": "true",
            "maxResults": "10",
        },
    )
    items = list(result.get("items") or [])
    if not items:
        raise RuntimeError("youtube_authorized_channel_not_found")
    return items[0]


def _yt_video(video_id: str) -> dict:
    result = _yt_data_api(
        "GET",
        "videos",
        query={"part": "id,snippet,status,statistics,contentDetails", "id": video_id},
    )
    items = list(result.get("items") or [])
    if not items:
        raise RuntimeError("youtube_video_not_found")
    return items[0]


def _parse_json_object(text: str, *, label: str) -> dict:
    try:
        value = json.loads(text or "{}")
    except Exception as exc:
        raise RuntimeError(label + "_invalid_json") from exc
    if not isinstance(value, dict):
        raise RuntimeError(label + "_must_be_object")
    return value


def _parse_json_array(text: str, *, label: str) -> list:
    try:
        value = json.loads(text or "[]")
    except Exception as exc:
        raise RuntimeError(label + "_invalid_json") from exc
    if not isinstance(value, list):
        raise RuntimeError(label + "_must_be_array")
    return value


def _yt_resumable_upload_from_url(
    *,
    media_url: str,
    metadata: dict,
) -> dict:
    if not media_url.startswith(("https://", "http://")):
        raise RuntimeError("media_url_must_be_http")
    source_request = urllib.request.Request(
        media_url,
        headers={"User-Agent": "ND-YouTube-MCP/1.0"},
        method="GET",
    )
    try:
        source = urllib.request.urlopen(source_request, timeout=60)
    except Exception as exc:
        raise RuntimeError("youtube_media_fetch_failed:" + str(exc)[:400]) from None

    try:
        content_length_raw = source.headers.get("Content-Length", "").strip()
        if not content_length_raw.isdigit():
            raise RuntimeError("youtube_media_content_length_required")
        content_length = int(content_length_raw)
        if content_length <= 0:
            raise RuntimeError("youtube_media_empty")
        content_type = (
            source.headers.get("Content-Type", "").split(";", 1)[0].strip()
            or mimetypes.guess_type(urllib.parse.urlparse(media_url).path)[0]
            or "application/octet-stream"
        )

        token = _yt_access_token()
        init_url = _YT_UPLOAD_BASE + "videos?uploadType=resumable&part=snippet,status"
        init_data = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        init_request = urllib.request.Request(
            init_url,
            data=init_data,
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json; charset=UTF-8",
                "Content-Length": str(len(init_data)),
                "X-Upload-Content-Type": content_type,
                "X-Upload-Content-Length": str(content_length),
                "Accept": "application/json",
                "User-Agent": "ND-YouTube-MCP/1.0",
            },
        )
        try:
            with urllib.request.urlopen(init_request, timeout=60) as response:
                session_url = str(response.headers.get("Location") or "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                "youtube_upload_init_http_" + str(exc.code) + ":" + detail[:900]
            ) from None
        if not session_url:
            raise RuntimeError("youtube_upload_session_missing")

        parsed = urllib.parse.urlsplit(session_url)
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, parsed.port, timeout=300)
        request_path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        conn.putrequest("PUT", request_path)
        conn.putheader("Content-Type", content_type)
        conn.putheader("Content-Length", str(content_length))
        conn.putheader("Authorization", "Bearer " + token)
        conn.endheaders()

        sent = 0
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            conn.send(chunk)
            sent += len(chunk)
        if sent != content_length:
            conn.close()
            raise RuntimeError(
                "youtube_upload_length_mismatch:" + str(sent) + "/" + str(content_length)
            )
        response = conn.getresponse()
        raw = response.read().decode("utf-8", "replace")
        status = response.status
        conn.close()
        if status not in (200, 201):
            raise RuntimeError("youtube_upload_http_" + str(status) + ":" + raw[:1200])
        return json.loads(raw or "{}")
    finally:
        try:
            source.close()
        except Exception:
            pass


def _yt_binary_post_from_url(endpoint: str, media_url: str) -> dict:
    if not media_url.startswith(("https://", "http://")):
        raise RuntimeError("media_url_must_be_http")
    req = urllib.request.Request(media_url, headers={"User-Agent": "ND-YouTube-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as source:
            data = source.read(20 * 1024 * 1024 + 1)
            content_type = (
                source.headers.get("Content-Type", "").split(";", 1)[0].strip()
                or mimetypes.guess_type(urllib.parse.urlparse(media_url).path)[0]
                or "application/octet-stream"
            )
    except Exception as exc:
        raise RuntimeError("youtube_binary_fetch_failed:" + str(exc)[:400]) from None
    if len(data) > 20 * 1024 * 1024:
        raise RuntimeError("youtube_binary_too_large")
    token = _yt_access_token()
    request = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "Accept": "application/json",
            "User-Agent": "ND-YouTube-MCP/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("youtube_binary_http_" + str(exc.code) + ":" + detail[:1000]) from None



def _drive_bridge_call(tool: str, args: dict) -> object:
    url = os.environ.get("ND_DRIVE_BRIDGE_URL", "").strip()
    token = os.environ.get("ND_DRIVE_BRIDGE_TOKEN", "").strip()
    if not url:
        raise RuntimeError("ND_DRIVE_BRIDGE_URL is not configured")
    if len(token) < 24:
        raise RuntimeError("ND_DRIVE_BRIDGE_TOKEN is not configured")
    req = Request(
        url,
        data=json.dumps({"tool": tool, "args": args}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-ND-Bridge-Key": token,
            "User-Agent": "nd-notebooklm-drive-adapter/1.0",
        },
    )
    try:
        with urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if token:
            body = body.replace(token, "[redacted]")
        raise RuntimeError(f"ND Drive bridge HTTP {exc.code}: {body[:700]}") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError("ND Drive bridge returned an invalid response")
    return payload.get("result")


def _register_drive_tools(mcp) -> None:
    @mcp.tool
    def docs_read(document_id: str) -> object:
        """Read a Google Doc with full text/tabs and the real Docs revisionId."""
        return _drive_bridge_call("docs_read", {"document_id": document_id})

    @mcp.tool
    def docs_append(
        document_id: str,
        text: str,
        expected_revision_id: str | None = None,
    ) -> object:
        """Append text with requiredRevisionId; stale expected revisions fail fast."""
        args = {"document_id": document_id, "text": text}
        if expected_revision_id:
            args["expected_revision_id"] = expected_revision_id
        return _drive_bridge_call("docs_append", args)

    @mcp.tool
    def docs_replace_exact(
        document_id: str,
        old_text: str,
        new_text: str,
        expected_revision_id: str | None = None,
    ) -> object:
        """Replace exactly one text occurrence with requiredRevisionId protection."""
        args = {
            "document_id": document_id,
            "old_text": old_text,
            "new_text": new_text,
        }
        if expected_revision_id:
            args["expected_revision_id"] = expected_revision_id
        return _drive_bridge_call("docs_replace_exact", args)

    @mcp.tool
    def drive_get_metadata(file_id: str) -> object:
        """Return Drive version, modifiedTime, MIME type, capabilities and checksums."""
        return _drive_bridge_call("drive_get_metadata", {"file_id": file_id})

    @mcp.tool
    def drive_get_currentness_token(file_id: str) -> object:
        """Return Drive currentness metadata plus Docs revisionId for native Docs."""
        return _drive_bridge_call("drive_get_currentness_token", {"file_id": file_id})

    @mcp.tool
    def drive_changes_start_token() -> object:
        """Get a Drive changes start page token for repair/reconciliation loops."""
        return _drive_bridge_call("drive_changes_start_token", {})

    @mcp.tool
    def drive_changes_list(page_token: str, page_size: int = 100) -> object:
        """List Drive changes from a page token."""
        return _drive_bridge_call(
            "drive_changes_list",
            {"page_token": page_token, "page_size": page_size},
        )


def _register_source_currentness_tools(mcp) -> None:
    @mcp.tool
    async def source_check_freshness(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM freshness check for one source."""
        client = await get_client(ctx)
        nb_id = await resolve_notebook(client, notebook)
        src_id = await resolve_source(client, nb_id, source)
        result = await client.sources.check_freshness(nb_id, src_id)
        return {
            "notebook_id": nb_id,
            "source_id": src_id,
            "freshness": to_jsonable(result),
        }

    @mcp.tool
    async def source_refresh(
        ctx: Context,
        notebook: str,
        source: str,
    ) -> object:
        """Provider-specific NotebookLM refresh. Success is absence of an exception."""
        client = await get_client(ctx)
        nb_id = await resolve_notebook(client, notebook)
        src_id = await resolve_source(client, nb_id, source)
        await client.sources.refresh(nb_id, src_id)
        return {
            "ok": True,
            "notebook_id": nb_id,
            "source_id": src_id,
            "provider_specific": True,
        }


def create_drive_only_mcp(
    *,
    password: str,
    login_password: str | None = None,
    base_url: str,
    state_path: Path,
    registry_store: OAuthStateStore,
    transient_store: OAuthStateStore,
    trust_proxy: bool = False,
):
    """Create the isolated Drive/Docs developer MCP without NotebookLM credentials."""
    auth = BlobBackedOAuthProvider(
        password=password,
        login_password=login_password,
        base_url=base_url,
        state_path=state_path,
        state_store=registry_store,
        pending_store=transient_store,
        trust_proxy=trust_proxy,
    )
    mcp = FastMCP(
        name="ND Google Drive MCP",
        instructions=(
            "Infrastructure access layer for bounded Google Drive/Docs operations. "
            "It is not semantic authority and must not mutate ND StateHead or Registry."
        ),
        auth=auth,
    )
    _register_drive_tools(mcp)

    @mcp.tool
    def nd_ping_secure() -> str:
        return json.dumps(
            {
                "ok": True,
                "service": "nd-google-drive-mcp",
                "mode": "drive-only-fallback",
                "semantic_authority": False,
                "drive_bridge_configured": bool(
                    os.environ.get("ND_DRIVE_BRIDGE_URL")
                    and os.environ.get("ND_DRIVE_BRIDGE_TOKEN")
                ),
            },
            separators=(",", ":"),
        )

    return mcp


def create_full_mcp(
    *,
    password: str,
    login_password: str | None = None,
    base_url: str,
    state_path: Path,
    registry_store: OAuthStateStore,
    transient_store: OAuthStateStore,
    client_factory: ClientFactory | None = None,
    trust_proxy: bool = False,
):
    """Compose notebooklm-py's complete tool surface with durable OAuth.

    NotebookLM remains upstream-owned and non-authoritative. This adapter adds
    durable OAuth plus a thin Drive/Docs infrastructure bridge and provider-
    specific source currentness primitives used by ND reconciliation.
    """
    auth = BlobBackedOAuthProvider(
        password=password,
        login_password=login_password,
        base_url=base_url,
        state_path=state_path,
        state_store=registry_store,
        pending_store=transient_store,
        trust_proxy=trust_proxy,
    )
    mcp = create_server(
        profile="default",
        backend="android",
        client_factory=client_factory,
        auth=auth,
    )

    _register_drive_tools(mcp)
    _register_source_currentness_tools(mcp)

    @mcp.tool
    def nd_ping_secure() -> str:
        return json.dumps(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "mode": "oauth-qualification",
                "version": SERVICE_VERSION,
                "drive_bridge_configured": bool(
                    os.environ.get("ND_DRIVE_BRIDGE_URL")
                    and os.environ.get("ND_DRIVE_BRIDGE_TOKEN")
                ),
            },
            separators=(",", ":"),
        )


    @mcp.tool
    def youtube_account() -> object:
        """Return the currently authorized YouTube channel, handle, statistics and uploads playlist."""
        item = _yt_channel()
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        content = item.get("contentDetails") or {}
        return {
            "id": item.get("id"),
            "title": snippet.get("title"),
            "custom_url": snippet.get("customUrl"),
            "description": snippet.get("description"),
            "country": snippet.get("country"),
            "subscriber_count": stats.get("subscriberCount"),
            "video_count": stats.get("videoCount"),
            "view_count": stats.get("viewCount"),
            "uploads_playlist": ((content.get("relatedPlaylists") or {}).get("uploads")),
            "raw": item,
        }

    @mcp.tool
    def youtube_list_videos(max_results: int = 25, page_token: str = "") -> object:
        """List videos from the authorized channel's uploads playlist."""
        channel = _yt_channel()
        uploads = (((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
        if not uploads:
            raise RuntimeError("youtube_uploads_playlist_missing")
        query = {
            "part": "id,snippet,contentDetails,status",
            "playlistId": uploads,
            "maxResults": max(1, min(int(max_results), 50)),
        }
        if page_token:
            query["pageToken"] = page_token
        return _yt_data_api("GET", "playlistItems", query=query)

    @mcp.tool
    def youtube_get_video(video_id: str) -> object:
        """Read full metadata/status/statistics for one YouTube video."""
        return _yt_video(video_id.strip())

    @mcp.tool
    def youtube_search(
        query: str = "",
        max_results: int = 25,
        page_token: str = "",
        order: str = "date",
    ) -> object:
        """Search videos belonging to the authorized channel."""
        channel = _yt_channel()
        q = {
            "part": "id,snippet",
            "channelId": channel.get("id"),
            "type": "video",
            "maxResults": max(1, min(int(max_results), 50)),
            "order": order or "date",
        }
        if query:
            q["q"] = query
        if page_token:
            q["pageToken"] = page_token
        return _yt_data_api("GET", "search", query=q)

    @mcp.tool
    def youtube_update_video(
        video_id: str,
        title: str = "",
        description: str = "",
        tags_json: str = "",
        category_id: str = "",
        privacy_status: str = "",
        publish_at: str = "",
        made_for_kids: str = "",
    ) -> object:
        """Update video metadata and/or publication status. Blank fields preserve current values."""
        current = _yt_video(video_id.strip())
        snippet = dict(current.get("snippet") or {})
        status = dict(current.get("status") or {})
        if title:
            snippet["title"] = title
        if description:
            snippet["description"] = description
        if tags_json:
            snippet["tags"] = [str(x) for x in _parse_json_array(tags_json, label="tags")]
        if category_id:
            snippet["categoryId"] = str(category_id)
        if privacy_status:
            if privacy_status not in {"private", "public", "unlisted"}:
                raise RuntimeError("invalid_privacy_status")
            status["privacyStatus"] = privacy_status
        if publish_at:
            status["publishAt"] = publish_at
            status["privacyStatus"] = "private"
        if made_for_kids:
            value = made_for_kids.strip().lower()
            if value not in {"true", "false"}:
                raise RuntimeError("made_for_kids_must_be_true_or_false")
            status["selfDeclaredMadeForKids"] = value == "true"
        payload = {"id": video_id.strip(), "snippet": snippet, "status": status}
        return _yt_data_api("PUT", "videos", query={"part": "snippet,status"}, payload=payload)

    @mcp.tool
    def youtube_delete_video(video_id: str, confirm: bool = False) -> object:
        """Delete a YouTube video permanently. Set confirm=true only for an explicit user request."""
        if not confirm:
            raise RuntimeError("confirm_required")
        return _yt_data_api("DELETE", "videos", query={"id": video_id.strip()})

    @mcp.tool
    def youtube_upload_video_from_url(
        media_url: str,
        title: str,
        description: str = "",
        privacy_status: str = "private",
        tags_json: str = "[]",
        category_id: str = "22",
        publish_at: str = "",
        made_for_kids: bool = False,
    ) -> object:
        """Upload a video from an HTTP(S) URL using YouTube resumable upload."""
        if privacy_status not in {"private", "public", "unlisted"}:
            raise RuntimeError("invalid_privacy_status")
        snippet = {"title": title, "description": description, "categoryId": category_id or "22"}
        tags = [str(x) for x in _parse_json_array(tags_json, label="tags")]
        if tags:
            snippet["tags"] = tags
        status = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": bool(made_for_kids),
        }
        if publish_at:
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at
        return _yt_resumable_upload_from_url(
            media_url=media_url,
            metadata={"snippet": snippet, "status": status},
        )

    @mcp.tool
    def youtube_set_thumbnail(video_id: str, image_url: str) -> object:
        """Set a custom thumbnail from an HTTP(S) image URL (max 20 MB through this MCP)."""
        endpoint = _YT_UPLOAD_BASE + "thumbnails/set?" + urllib.parse.urlencode({"videoId": video_id.strip()})
        return _yt_binary_post_from_url(endpoint, image_url)

    @mcp.tool
    def youtube_list_comments(video_id: str, max_results: int = 50, page_token: str = "") -> object:
        """List top-level comment threads for a video."""
        q = {
            "part": "id,snippet,replies",
            "videoId": video_id.strip(),
            "maxResults": max(1, min(int(max_results), 100)),
            "textFormat": "plainText",
        }
        if page_token:
            q["pageToken"] = page_token
        return _yt_data_api("GET", "commentThreads", query=q)

    @mcp.tool
    def youtube_create_comment(video_id: str, text: str) -> object:
        """Create a top-level comment on a video."""
        payload = {
            "snippet": {
                "videoId": video_id.strip(),
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        }
        return _yt_data_api("POST", "commentThreads", query={"part": "snippet"}, payload=payload)

    @mcp.tool
    def youtube_reply_comment(parent_comment_id: str, text: str) -> object:
        """Reply to an existing YouTube comment."""
        payload = {"snippet": {"parentId": parent_comment_id.strip(), "textOriginal": text}}
        return _yt_data_api("POST", "comments", query={"part": "snippet"}, payload=payload)

    @mcp.tool
    def youtube_delete_comment(comment_id: str, confirm: bool = False) -> object:
        """Delete a comment. Set confirm=true only for an explicit user request."""
        if not confirm:
            raise RuntimeError("confirm_required")
        return _yt_data_api("DELETE", "comments", query={"id": comment_id.strip()})

    @mcp.tool
    def youtube_list_playlists(max_results: int = 50, page_token: str = "") -> object:
        """List playlists owned by the authorized channel."""
        q = {
            "part": "id,snippet,status,contentDetails",
            "mine": "true",
            "maxResults": max(1, min(int(max_results), 50)),
        }
        if page_token:
            q["pageToken"] = page_token
        return _yt_data_api("GET", "playlists", query=q)

    @mcp.tool
    def youtube_create_playlist(
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> object:
        """Create a playlist."""
        if privacy_status not in {"private", "public", "unlisted"}:
            raise RuntimeError("invalid_privacy_status")
        return _yt_data_api(
            "POST",
            "playlists",
            query={"part": "snippet,status"},
            payload={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": privacy_status},
            },
        )

    @mcp.tool
    def youtube_delete_playlist(playlist_id: str, confirm: bool = False) -> object:
        """Delete a playlist. Set confirm=true only for an explicit user request."""
        if not confirm:
            raise RuntimeError("confirm_required")
        return _yt_data_api("DELETE", "playlists", query={"id": playlist_id.strip()})

    @mcp.tool
    def youtube_add_to_playlist(playlist_id: str, video_id: str, position: int = -1) -> object:
        """Add a video to a playlist."""
        snippet = {
            "playlistId": playlist_id.strip(),
            "resourceId": {"kind": "youtube#video", "videoId": video_id.strip()},
        }
        if int(position) >= 0:
            snippet["position"] = int(position)
        return _yt_data_api("POST", "playlistItems", query={"part": "snippet"}, payload={"snippet": snippet})

    @mcp.tool
    def youtube_remove_from_playlist(playlist_item_id: str, confirm: bool = False) -> object:
        """Remove a playlist item. Set confirm=true only for an explicit user request."""
        if not confirm:
            raise RuntimeError("confirm_required")
        return _yt_data_api("DELETE", "playlistItems", query={"id": playlist_item_id.strip()})

    @mcp.tool
    def youtube_analytics(
        start_date: str,
        end_date: str,
        metrics: str = "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
        dimensions: str = "day",
        filters: str = "",
        sort: str = "",
    ) -> object:
        """Query YouTube Analytics for the authorized channel."""
        q = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": metrics,
        }
        if dimensions:
            q["dimensions"] = dimensions
        if filters:
            q["filters"] = filters
        if sort:
            q["sort"] = sort
        url = _YT_ANALYTICS_BASE + "reports?" + urllib.parse.urlencode(q)
        return _yt_http_json("GET", url)

    @mcp.tool
    def youtube_api(
        method: str,
        resource: str,
        query_json: str = "{}",
        body_json: str = "{}",
        confirm_destructive: bool = False,
    ) -> object:
        """Low-level full YouTube Data API v3 access for operations not covered by dedicated tools."""
        verb = method.strip().upper()
        if verb not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise RuntimeError("unsupported_http_method")
        if verb == "DELETE" and not confirm_destructive:
            raise RuntimeError("confirm_required")
        query = _parse_json_object(query_json, label="query")
        body = _parse_json_object(body_json, label="body")
        payload = None if verb in {"GET", "DELETE"} else body
        return _yt_data_api(verb, resource, query=query, payload=payload)


    return mcp
