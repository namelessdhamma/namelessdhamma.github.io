# ND NotebookLM Remote MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy and qualify a phone-independent remote Streamable HTTP MCP for NotebookLM, starting with a harmless `nd_ping` tool and then advancing to authenticated NotebookLM read/write only after transport qualification.

**Architecture:** A small standalone Next.js MCP service lives under `tools/notebooklm-mcp/remote-vercel/`. ChatGPT calls it directly over Streamable HTTP. Vercel Hobby is the first deployment target because it has first-class MCP support, substantially larger per-request resources than Cloudflare Workers Free, and a ChatGPT Vercel connector that can automate deployment once the user authorizes it. Enzonic Free and Deplexo Free remain secondary host candidates for the same service if Vercel fails qualification.

**Tech Stack:** Next.js 16.3.4, React 19.2.8, `mcp-handler` 2.1.1, `@modelcontextprotocol/server` 2.0.0, Zod 4.5.4, TypeScript, Vitest, Vercel Hobby.

**Spec:** `docs/superpowers/specs/2026-09-10-notebooklm-remote-mcp-design.md`

## Global Constraints

- Expected recurring infrastructure cost: `$0`.
- Primary runtime must not require Android, browser, Cloud Shell, n8n, Make, Railway, or an always-on user-owned device.
- Primary MCP transport: remote Streamable HTTP.
- Stage A contains no Google/NotebookLM secrets.
- Google auth material must never be committed to Git or emitted in logs/tool output.
- Do not expose the full NotebookLM write surface before read-only and bounded write/read-back qualification.
- GitHub is code/update/control plane, not production secret storage.
- Android/Termux remains a separately maintained backup runtime.

---

### Task 1: Stage-A transport project and failing tests

**Files:**
- Create: `tools/notebooklm-mcp/remote-vercel/package.json`
- Create: `tools/notebooklm-mcp/remote-vercel/tsconfig.json`
- Create: `tools/notebooklm-mcp/remote-vercel/vitest.config.ts`
- Create: `tools/notebooklm-mcp/remote-vercel/tests/ping.test.ts`
- Create: `.github/workflows/notebooklm-remote-mcp-ci.yml`

**Interfaces:**
- Produces expected API contract: `buildPingPayload(): {ok:true; service:string; mode:string; version:string}`.

- [ ] Write a failing unit test that imports `buildPingPayload` from `../src/ping` and checks exact stable fields.
- [ ] Add branch-scoped GitHub Actions CI that installs dependencies and runs `npm test` and `npm run build` in the remote project.
- [ ] Push test-only commit and verify CI fails because `src/ping.ts` does not exist.

### Task 2: Minimal Stage-A MCP server

**Files:**
- Create: `tools/notebooklm-mcp/remote-vercel/src/ping.ts`
- Create: `tools/notebooklm-mcp/remote-vercel/app/api/mcp/route.ts`
- Create: `tools/notebooklm-mcp/remote-vercel/app/api/health/route.ts`
- Create: `tools/notebooklm-mcp/remote-vercel/app/page.tsx`
- Create: `tools/notebooklm-mcp/remote-vercel/app/layout.tsx`

**Interfaces:**
- `buildPingPayload()` returns the qualification payload.
- `/api/mcp` exposes `nd_ping` over stateless Streamable HTTP.
- `/api/health` returns a harmless deployment health/version payload.

- [ ] Implement `buildPingPayload()` minimally so the failing test passes.
- [ ] Register `nd_ping` with `mcp-handler` 2.x using `server.registerTool`.
- [ ] Export the same handler for GET and POST; do not enable legacy SSE/Redis.
- [ ] Add `/api/health` for host-level verification without MCP tooling.
- [ ] Run CI and verify tests/build are green.

### Task 3: Vercel deployment qualification

**Files:**
- Create: `tools/notebooklm-mcp/remote-vercel/README.md`
- Create: `tools/notebooklm-mcp/remote-vercel/qualification-state.json`

**Interfaces:**
- Consumes GitHub branch `notebooklm-remote-mcp` and project root `tools/notebooklm-mcp/remote-vercel`.
- Produces a public HTTPS endpoint ending in `/api/mcp` and a health URL `/api/health`.

- [ ] Connect/authorize the Vercel ChatGPT connector if not already connected; this is the only user-interactive step expected for Stage A.
- [ ] Create/import a Vercel Hobby project from this GitHub repository and set the project root to `tools/notebooklm-mcp/remote-vercel`.
- [ ] Deploy branch `notebooklm-remote-mcp`.
- [ ] Verify `/api/health` over HTTPS.
- [ ] Verify deployment logs show no secret material and no runtime errors.
- [ ] Record deployment URL and revision in `qualification-state.json` without secrets.

### Task 4: ChatGPT remote-MCP live qualification

**Files:**
- Modify: `tools/notebooklm-mcp/remote-vercel/qualification-state.json`

**Interfaces:**
- Consumes deployed `/api/mcp` URL.
- Produces Stage-A PASS/FAIL evidence.

- [ ] Create a temporary ChatGPT custom MCP app using the remote URL, not Secure MCP Tunnel.
- [ ] Run Scan Tools and confirm `nd_ping` is discovered.
- [ ] Invoke `nd_ping` and verify the exact payload.
- [ ] Repeat after an idle/cold-start interval.
- [ ] Redeploy/restart and repeat discovery/invocation.
- [ ] Mark Stage A PASS only when all live gates succeed without Android/Cloud Shell/tunnel-client.

### Task 5: Host fallback qualification if Vercel fails

**Files:**
- Modify: `tools/notebooklm-mcp/remote-vercel/qualification-state.json`

**Interfaces:**
- Reuses the same remote MCP code unchanged where possible.

- [ ] If Vercel fails for a host-specific reason, deploy the same service to Enzonic Free as candidate #2.
- [ ] If Enzonic cannot be qualified, deploy to Deplexo Free as candidate #3.
- [ ] Keep Cloudflare Workers as a lightweight transport candidate only; its 10 ms/request Free CPU limit makes it lower priority for the NotebookLM adapter.
- [ ] Record specific falsification evidence for each failed host rather than vague rejection.

### Task 6: Stage-B NotebookLM adapter research spike after Stage-A PASS

**Files:**
- Create: `tools/notebooklm-mcp/remote-vercel/docs/notebooklm-adapter-contract.md`

**Interfaces:**
- Defines the smallest provider-facing contract needed for `notebook_list()`.

- [ ] Inspect `notebooklm-py` 0.8.2 source paths used for bearer/master-token auth and notebook listing.
- [ ] Determine whether the provider calls can be reproduced in Node/TypeScript without FastMCP/watchfiles/maturin.
- [ ] Document exact required inputs, Google endpoints/session reconstruction, returned data normalization, and failure classes without storing any secret values.
- [ ] Choose either a small TypeScript adapter or a container/Python fallback based on evidence.

### Task 7: Stage-B secret-safe read-only implementation

**Files:**
- Create/modify only after Task 6 determines the adapter boundary.

**Interfaces:**
- Produces MCP tool `notebook_list()`.

- [ ] Write failing tests for sanitized auth/config loading and notebook-list normalization.
- [ ] Implement managed-secret loading with no Git fallback.
- [ ] Implement `notebook_list()` and explicit sanitized error classes.
- [ ] Provision Google auth only through Vercel managed environment secrets; never paste it into source or ordinary chat.
- [ ] Run live read-only test, cold-start test, and auth-refresh/reconstruction test.

### Task 8: Stage-C bounded write/read-back

**Files:**
- Modify remote adapter and tests after Stage B PASS.

**Interfaces:**
- Produces MCP tool `notebook_create(title)`.

- [ ] Write failing tests for title validation and normalized create result.
- [ ] Implement minimal create operation.
- [ ] Create one qualification notebook with an unmistakable test title.
- [ ] Independently call `notebook_list()` and verify returned ID/title.
- [ ] Repeat after cold start and record evidence.

### Task 9: Production hardening and reusable ND pattern

**Files:**
- Create: `tools/notebooklm-mcp/remote-vercel/REMOTE-MCP-RUNBOOK.md`
- Create: `tools/notebooklm-mcp/remote-vercel/remote-manifest.json`
- Modify: update workflow(s) as justified.

**Interfaces:**
- Produces a reusable ND remote-MCP deployment pattern and last-known-good state.

- [ ] Record host, version, MCP protocol generation, deployment revision, last-known-good revision, and qualification timestamps.
- [ ] Add automated dependency/update checks without auto-promoting unqualified upstream changes.
- [ ] Document rollback and credential-rotation procedures.
- [ ] Keep Android/Termux path as independent fallback, not primary.
- [ ] Propose merge only after live transport and NotebookLM read/write qualification are complete.
