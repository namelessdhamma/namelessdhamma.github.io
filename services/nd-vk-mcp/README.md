# ND VK MCP

Direct, bounded VK API adapter for ChatGPT / MCP clients.

## Architecture

ChatGPT -> Streamable HTTP MCP -> VK API

This service is additive. Existing Make, VK Father runtime, and VK Router Control remain unchanged.

## Security

- VK token is server-side only.
- MCP endpoint is mounted behind a high-entropy secret path from `ND_VK_MCP_ROUTE_TOKEN`.
- Read/write peer operations fail closed outside `VK_ALLOWED_USER_IDS`.
- No generic raw VK API method is exposed.

## Tools

- `vk_status`
- `vk_get_users`
- `vk_get_conversations`
- `vk_get_history`
- `vk_send_message`
- `vk_mark_as_read`

## Runtime

Railway root directory: `/services/nd-vk-mcp`

Start command:

```
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Health: `/health`

MCP: `/<ND_VK_MCP_ROUTE_TOKEN>/mcp`
