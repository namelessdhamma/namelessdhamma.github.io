# ND NotebookLM Direct MCP — Production Qualification

Date: 2026-09-10
Status: **PRODUCTION_QUALIFIED**

## Qualified route

`ChatGPT → OAuth → https://nd-notebooklm-oauth-mcp.vercel.app/mcp → Vercel FastAPI → notebooklm-py 0.8.2 → consumer NotebookLM`

Production project: `nd-notebooklm-oauth-mcp`
Production branch: `notebooklm-remote-mcp`
Qualified implementation commit: `ba523fca535211daeb9e1e32b458b27132a85fb0`
Qualified Vercel deployment: `dpl_4qEfaU3bhn2JeiDwcTQ3ZUBW7jhb`

## Qualification evidence

1. OAuth discovery, dynamic client registration, authorization, password-gated bootstrap login, token exchange, and authenticated MCP requests completed successfully from ChatGPT.
2. ChatGPT discovered the MCP tool surface and executed real NotebookLM calls.
3. Read-only notebook listing succeeded against the consumer account.
4. Independent metadata read succeeded for test notebook `56978e5f-2cd1-4188-93d9-c19d236a814f` (`ND MCP Test — 2026-09-09`).
5. The known source `ND MCP Gemini Chat Test Source` was returned from the real NotebookLM backend.
6. Vercel Blob persistence was validated for OAuth client registry, access token, refresh token, pending login state, and authorization-code handoff without exposing credential values.
7. A controlled production redeploy was performed; the existing ChatGPT authorization remained usable and the same NotebookLM metadata call succeeded after redeploy without reauthorization.
8. Cold-start/serverless reconstruction was exercised on fresh production instances: durable OAuth state was read from Vercel Blob and the NotebookLM Google credential path initialized successfully.
9. Temporary diagnostic endpoint `/__nd_oauth_diag` was removed and returns 404 in production.
10. OAuth authorization-server metadata and protected-resource metadata both return 200 from the stable production domain.
11. Final OAuth MCP CI run on the qualified code passed all 20 unit tests and pinned import checks.
12. Final Vercel deployment is READY and recent runtime error-cluster check reports no runtime errors.

## Defects found and closed during qualification

- Startup rejected the rotated connector password because a local minimum-length guard was stricter than the selected password. Guard corrected.
- Production OAuth password value was re-applied exactly and redeployed.
- Serverless OAuth sessions initially lost registered clients after instance replacement. Root cause: the current Vercel Python Blob SDK returns downloaded bytes through `GetBlobResult.content`, while the adapter expected a stream-only contract. Restore logic now supports the current buffered-content contract with a stream fallback and regression coverage.
- Packaging CI exposed a missing Vercel function duration budget. `vercel.json` now keeps Fluid Compute enabled and sets `app.py` `maxDuration` to 90 seconds.

## Security / operating position

- The Google/NotebookLM master credential remains platform-managed and is not exposed through MCP tool output, source control, or this qualification record.
- The connector password remains a bootstrap/recovery authorization gate; it is not required for normal calls while the issued OAuth client/access/refresh state remains valid.
- OAuth state is durable in private Vercel Blob storage; the master Google credential is kept outside that OAuth state.
- The custom MCP is a capability boundary, not an ND architecture authority or StateHead.

## Known product constraint

The custom developer MCP works in ordinary eligible ChatGPT chats. The System project conversation used during development returned `FORBIDDEN: This conversation does not support developer MCPs`; this is a ChatGPT conversation-context restriction rather than a failure of the NotebookLM MCP route.

## Promotion note

The active development branch contains substantial historical NotebookLM experiments (Android/Termux/GCE/Stage-A artifacts) in addition to the qualified Vercel OAuth implementation. Do **not** merge the entire branch to `main` blindly. Main-branch promotion should be a curated Architecture & Version Control operation that adopts the qualified implementation without making obsolete experimental paths canonical.
