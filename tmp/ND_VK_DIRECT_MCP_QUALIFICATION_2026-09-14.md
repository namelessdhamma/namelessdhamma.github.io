# ND VK Direct MCP — Qualification Receipt

Date: 2026-09-14
Status: QUALIFICATION_CANDIDATE / CHATGPT_APP_CREATE_RETRY_PENDING

## Objective
Add a direct ChatGPT -> MCP -> VK API path while preserving Make and the existing VK Father runtime as independent fallback paths.

## Implemented
- Qualification branch: `qualify/vk-direct-mcp-v1`.
- Current production front wrapper: `tmp/nd_vk_gateway_v18_mcp_front.py`, commit `74a4b8cfb881f87952c77205c58b78f60840607b`.
- Railway service `nd-qstash-control-v2` runs the MCP front gateway on public port 3000 and the previous VK runtime unchanged on internal port 3001.
- `ND_VK_MCP_ROUTE_TOKEN` is configured server-side.
- Existing VK Callback API behavior is proxied unchanged.
- Existing Make configuration is unchanged.

## Exposed MCP tools
- `vk_status`
- `vk_get_users`
- `vk_get_conversations`
- `vk_get_history`
- `vk_send_message`
- `vk_mark_as_read`

## Bounds
- VK group token remains server-side.
- Peer reads and writes fail closed outside `VK_ALLOWED_USER_IDS`.
- No arbitrary raw VK method is exposed.
- Message sends are bounded to plain text and 3500 characters.
- Tool annotations mark read-only vs write actions.

## Failure and root cause
Initial custom-app creation with no authentication failed because the published MCP route returned HTTP 404. The earlier V15 patch had not produced a live route, even though the surrounding VK deployment remained healthy.

## Live evidence after repair
Railway deployment `015c8c88-7871-499a-b145-f203c10693c3` completed SUCCESS.

Startup:
- `ND_VK_DIRECT_MCP_GATEWAY_START`
- `mcp_configured=true`
- `tool_count=6`
- legacy VK runtime ready on internal port 3001

External MCP probe from an independent cloud runtime:
- `initialize` => HTTP 200, application/json
- negotiated protocol => `2025-06-18`
- `tools/list` => HTTP 200, 6 tools
- `tools/call vk_status` => HTTP 200, `ok=true`
- live direct VK API identity => Nameless Dhamma group `228330620`
- allowed peer count => 2

## Remaining qualification
1. Retry ChatGPT custom-app creation with No Authentication.
2. Confirm ChatGPT tool scan discovers the six tools.
3. Run a read-only conversation/history probe from ChatGPT.
4. Run write probe only on explicit user-directed target/message.
5. Perform reconnect/recovery check.

Do not mark ADOPTED until ChatGPT itself discovers the tools.

## Architecture
Primary target:
`ChatGPT -> ND VK MCP -> VK API`

Preserved fallbacks:
- existing VK Father runtime
- Make

No Make removal or migration is part of this change.
