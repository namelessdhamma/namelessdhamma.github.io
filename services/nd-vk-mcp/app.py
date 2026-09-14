import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

VK_API_BASE = "https://api.vk.com/method"
VK_GROUP_TOKEN = os.environ.get("VK_GROUP_TOKEN", "").strip()
VK_API_VERSION = os.environ.get("VK_API_VERSION", "5.199").strip()
ROUTE_TOKEN = os.environ.get("ND_VK_MCP_ROUTE_TOKEN", "").strip()

if not VK_GROUP_TOKEN:
    raise RuntimeError("VK_GROUP_TOKEN is required")
if not ROUTE_TOKEN:
    raise RuntimeError("ND_VK_MCP_ROUTE_TOKEN is required")

def _parse_allowed(raw: str) -> set[int]:
    out: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            continue
    return out

ALLOWED_PEERS = _parse_allowed(os.environ.get("VK_ALLOWED_USER_IDS", ""))

def _require_peer(peer_id: int) -> int:
    peer_id = int(peer_id)
    if not ALLOWED_PEERS:
        raise ValueError("VK peer allow-list is empty; direct messaging is fail-closed")
    if peer_id not in ALLOWED_PEERS:
        raise ValueError(f"peer_id {peer_id} is outside VK_ALLOWED_USER_IDS")
    return peer_id

async def _vk(method: str, **params: Any) -> dict[str, Any]:
    payload = {k: v for k, v in params.items() if v is not None}
    payload["access_token"] = VK_GROUP_TOKEN
    payload["v"] = VK_API_VERSION
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(f"{VK_API_BASE}/{method}", data=payload)
        response.raise_for_status()
        data = response.json()
    if "error" in data:
        err = data["error"]
        return {
            "ok": False,
            "method": method,
            "error_code": err.get("error_code"),
            "error_msg": err.get("error_msg"),
        }
    return {"ok": True, "method": method, "response": data.get("response")}

mcp = FastMCP(
    name="ND VK",
    instructions=(
        "Direct bounded access to the Nameless Dhamma VK community account. "
        "Read and write operations are limited to VK_ALLOWED_USER_IDS. "
        "Use vk_send_message only when the user requests or authorizes sending."
    ),
    stateless_http=True,
    json_response=True,
)

@mcp.tool()
async def vk_status() -> dict[str, Any]:
    """Verify direct VK API reachability without returning message contents."""
    probe = await _vk("messages.getConversations", count=1)
    return {
        "transport": "DIRECT_VK_API",
        "api_version": VK_API_VERSION,
        "allowed_peer_count": len(ALLOWED_PEERS),
        "vk_api": {
            "ok": probe.get("ok", False),
            "error_code": probe.get("error_code"),
            "error_msg": probe.get("error_msg"),
        },
    }

@mcp.tool()
async def vk_get_users(user_ids: list[int] | None = None) -> dict[str, Any]:
    """Read basic VK profile data for allow-listed users."""
    ids = sorted(ALLOWED_PEERS) if user_ids is None else [int(x) for x in user_ids]
    if not ids:
        return {"ok": True, "response": []}
    for user_id in ids:
        _require_peer(user_id)
    return await _vk(
        "users.get",
        user_ids=",".join(str(x) for x in ids),
        fields="first_name,last_name,screen_name",
    )

@mcp.tool()
async def vk_get_conversations(
    count: int = 20,
    offset: int = 0,
    unread_only: bool = False,
) -> dict[str, Any]:
    """Read recent direct conversations, filtered to allow-listed VK user IDs."""
    count = max(1, min(int(count), 100))
    offset = max(0, int(offset))
    result = await _vk(
        "messages.getConversations",
        count=count,
        offset=offset,
        filter="unread" if unread_only else "all",
        extended=0,
    )
    if not result.get("ok"):
        return result
    response = result.get("response") or {}
    items = response.get("items") or []
    filtered = []
    for item in items:
        peer = ((item.get("conversation") or {}).get("peer") or {})
        try:
            peer_id = int(peer.get("id"))
        except (TypeError, ValueError):
            continue
        if peer_id in ALLOWED_PEERS:
            filtered.append(item)
    return {
        "ok": True,
        "method": "messages.getConversations",
        "response": {
            "count": len(filtered),
            "items": filtered,
        },
    }

@mcp.tool()
async def vk_get_history(
    peer_id: int,
    count: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    """Read message history for one allow-listed VK peer."""
    peer_id = _require_peer(peer_id)
    count = max(1, min(int(count), 100))
    offset = max(0, int(offset))
    return await _vk(
        "messages.getHistory",
        peer_id=peer_id,
        count=count,
        offset=offset,
        rev=0,
    )

@mcp.tool()
async def vk_send_message(
    peer_id: int,
    message: str,
    reply_to: int | None = None,
) -> dict[str, Any]:
    """Send a plain-text VK message to one allow-listed peer."""
    peer_id = _require_peer(peer_id)
    message = str(message).strip()
    if not message:
        raise ValueError("message must not be empty")
    if len(message) > 3500:
        raise ValueError("message exceeds bounded MCP limit of 3500 characters")
    return await _vk(
        "messages.send",
        peer_id=peer_id,
        message=message,
        reply_to=reply_to,
        random_id=secrets.randbelow(2_147_483_646) + 1,
    )

@mcp.tool()
async def vk_mark_as_read(peer_id: int) -> dict[str, Any]:
    """Mark messages from one allow-listed VK peer as read."""
    peer_id = _require_peer(peer_id)
    return await _vk("messages.markAsRead", peer_id=peer_id)

async def health(_: Any) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "nd-vk-mcp",
            "transport": "streamable-http",
            "mcp_path": "/<secret>/mcp",
            "allowed_peer_count": len(ALLOWED_PEERS),
        }
    )

@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Mount(f"/{ROUTE_TOKEN}", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)
