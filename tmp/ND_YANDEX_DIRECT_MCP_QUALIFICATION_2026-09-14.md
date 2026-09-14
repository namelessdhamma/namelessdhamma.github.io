# ND Yandex Disk Direct MCP — Qualification Receipt

Date: 2026-09-14
Status: QUALIFICATION_CANDIDATE / CHATGPT_APP_BINDING_PENDING

## Objective
Add a direct ChatGPT -> MCP -> Yandex Disk API path while leaving Make as an independent fallback.

## Runtime reuse
No new Railway service was created.
The existing service `nd-yandex-n8n-gateway` was inspected first and found to be unconfigured: its UI was still at the initial `Set up owner account` screen with no usable workflow state.
It was therefore reused for the direct Yandex Disk MCP runtime.

## Implementation
- Branch: `qualify/yandex-direct-mcp-v1`
- MCP source: `tmp/nd_yandex_direct_mcp_read_v1.mjs`
- Current implementation commit: `bbc520e39607ffffdce0b92399858fbb518235ff`
- Railway deployment: `57e08f0e-911e-4880-89b8-51c062f8ac8f`
- Service: `nd-yandex-n8n-gateway`
- Secret route is provided by server-side `ND_YANDEX_MCP_ROUTE_TOKEN`.
- Yandex OAuth token remains server-side in `YANDEX_DISK_TOKEN`.

## Current tools
Read:
- `yandex_status`
- `yandex_list`
- `yandex_stat`
- `yandex_read_text`
- `yandex_get_download_url`

Bounded writes:
- `yandex_write_text`
- `yandex_mkdir`
- `yandex_copy`
- `yandex_move`

## Live evidence
Initial read-only deployment:
- MCP initialize: HTTP 200
- tools/list: HTTP 200
- yandex_status: PASS
- transport: `DIRECT_YANDEX_DISK_API`
- root listing: PASS
- root contained `disk:/сон том 2`

Current deployment:
- status: SUCCESS
- startup marker: `ND_YANDEX_DIRECT_MCP_START`
- `token_present=true`
- `mcp_configured=true`
- tool_count: 9

## Remaining qualification
1. Create the ChatGPT custom MCP app with No Authentication.
2. Confirm ChatGPT discovers 9 tools.
3. Run read-only status/list in ChatGPT.
4. Run a bounded reversible write test only when requested.
5. Add delete/publish/unpublish only if later justified.

## Architecture
Primary:
`ChatGPT -> ND Yandex Disk MCP -> Yandex Disk API`

Fallback:
`Make -> Yandex Disk`

Make was not removed or modified.
