# ND VK Direct MCP — Qualification Receipt

Date: 2026-09-14
Status: QUALIFICATION_CANDIDATE / EXTERNAL_TOOL_SCAN_PENDING

## Objective
Add a direct ChatGPT -> MCP -> VK API path while preserving Make and the existing VK Father runtime as independent fallback paths.

## Implemented
- Qualification branch: `qualify/vk-direct-mcp-v1`.
- Standalone reference MCP: `services/nd-vk-mcp/`.
- Additive production wrapper: `tmp/nd_vk_gateway_v15_direct_mcp.py`, commit `065055f347a50476e9c99c551133558ae26c68a5`.
- Current Railway service `nd-qstash-control-v2` start command points to the V15 wrapper.
- `ND_VK_MCP_ROUTE_TOKEN` is configured server-side.
- Existing VK Callback API behavior is preserved.
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

## Live evidence
Railway deployment `0bbb0c32-f2b2-4827-a116-76690b563f8d` completed SUCCESS.
Startup evidence:
- `VK_READY`
- group_id `228330620`
- callback server configured
- Groq probe PASS
- OpenRouter probe PASS

## Remaining qualification
External ChatGPT custom-app registration must perform:
1. MCP initialize
2. Scan Tools / tools.list => expect 6 tools
3. read-only `vk_status`
4. read-only history/conversation probe
5. write probe only with explicit user-directed target/message
6. reconnect/recovery check

Do not mark ADOPTED until external tool discovery succeeds.

## Architecture
Primary target:
`ChatGPT -> ND VK MCP -> VK API`

Fallbacks remain:
- existing VK Father runtime
- Make

No Make removal or migration is part of this change.
