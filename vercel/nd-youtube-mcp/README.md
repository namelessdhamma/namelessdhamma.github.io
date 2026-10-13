# ND YouTube MCP — Vercel standalone

Reuses original `runtime/nd_yandex_youtube_mux_mcp_v02.mjs` YouTube command implementation (18 tools). No application credentials or OAuth tokens stored in Git.

Deploy this directory as Vercel project root, `framework = Other/No framework`.

Set these **sensitive Production** environment variables directly in Vercel before activating:
- `ND_YOUTUBE_CLIENT_ID`
- `ND_YOUTUBE_CLIENT_SECRET`
- `ND_YOUTUBE_REFRESH_TOKEN`
- `ND_YOUTUBE_VERCEL_MCP_TOKEN` (a newly generated private endpoint token)

Connect private MCP URL `https://<Vercel host>/api/mcp?token=<ND_YOUTUBE_VERCEL_MCP_TOKEN>` through a private ChatGPT plugin. Do not paste token into public discussion. The MCP uses JSON-RPC `initialize`, `tools/list`, `tools/call`. Write methods require proper Google scopes; destructive calls require `confirm=true`. Use read-account identity match (channel `UC2q1zkWMM-LHiaa5nkB35Zw`) and a private playlist create-read-delete test before production adoption. Never assume a READY deployment proves OAuth validity.

Original team Vercel project provisioning was denied `403 forbidden` on 2026-10-13; this source is a prepared candidate, not a deployed/qualified service.
