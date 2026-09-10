# ND NotebookLM Remote MCP — Host Qualification Snapshot

Date: 2026-09-10
Branch: `notebooklm-remote-mcp`
Status: implementation selection

## Selection rule

Primary goal is not merely a free machine. The preferred host must support the phone-independent architecture:

```text
ChatGPT -> remote Streamable HTTP MCP -> NotebookLM adapter -> NotebookLM
```

with expected recurring infrastructure cost of $0 and minimal human maintenance.

## Current ranking

### #1 — Vercel Hobby / remote Streamable HTTP MCP

Why first:
- Vercel explicitly supports hosting MCP servers and stateless HTTP transport through `mcp-handler`;
- `mcp-handler` 2.x implements current MCP SDK v2 and stateless Streamable HTTP;
- Hobby Functions currently allow up to 300 seconds per invocation with Standard compute around 1 vCPU / 2 GB;
- current Hobby included compute is far larger than the expected low-volume ND qualification workload;
- no always-on daemon is needed;
- Git push / deployment / rollback are first-class;
- a Vercel connector is available in ChatGPT, allowing deployment/inspection to be automated after one-time account authorization;
- the same remote-MCP pattern can host future ND service adapters.

Main unresolved gate:
- live ChatGPT remote-MCP discovery/call and later NotebookLM auth compatibility must be proven.

### #2 — Enzonic Free / persistent custom process or remote HTTP service

Why strong:
- current provider pages advertise no-card free hosting, long-running Node/Python/custom-binary processes, environment-variable vault, GitHub auto-deploy, crash restart, persistent SSD, and 24/7 operation for bot/custom-app classes;
- resource allowance is materially larger than edge-worker limits;
- can host either a remote HTTP MCP or the legacy tunnel-client + stdio MCP path.

Why not first:
- provider documentation currently contains conflicting free-tier descriptions across product pages (some free classes hibernate while other bot/cloud pages advertise 24/7);
- smaller/newer provider with less operational evidence than Vercel;
- no connected ChatGPT deployment tool is currently available, so first account/deploy setup would require more manual interaction.

### #3 — Deplexo Free / always-on GitHub container

Why strong:
- current provider page advertises free forever hobby hosting with no credit card;
- GitHub-to-container deployment;
- always-on/no-cold-start containers;
- managed secrets/environment variables and restart/redeploy/rollback controls.

Why not first:
- service is explicitly open beta;
- overnight qualification found a small free resource envelope (about 0.25 CPU / 128 MB class), which may be enough for a lightweight Node MCP but is riskier for NotebookLM adapter logic;
- no connected ChatGPT deployment tool is currently available.

## Lower-priority candidates

### Cloudflare Workers Free

Excellent stateless remote-MCP transport fit, but current Free CPU limit is 10 ms per request with 128 MB RAM. Keep as a lightweight transport/adapter candidate, not first NotebookLM end-to-end host.

### Render Free

Supports Docker/Node/Python and no-card deployment, but free web services spin down after 15 minutes and cold start is documented around one minute. Good fallback test host, weaker fit for interactive MCP latency.

### Koyeb Free

512 MB / 0.1 vCPU free instance with scale-to-zero after one hour and approximately 1–5 second deep-sleep wake. However Starter access requires a valid payment method and free instances are explicitly not positioned for production use. Lower priority under ND no-card/free-first policy.

### Deno Deploy Free

Attractive on-demand runtime with large request quota and 512 MB memory, but verified Free-plan capabilities may remain restricted until credit-card verification and the runtime is less compatible with reusing Python provider behavior. Keep for a future lightweight native TypeScript adapter.

## Decision

Implement Stage A on Vercel first.

If the Vercel transport or NotebookLM adapter fails for a host-specific reason, preserve the remote Streamable HTTP design and move the same service to Enzonic, then Deplexo. Do not return to Android or a permanent local tunnel merely because one remote host fails.

Android/Termux remains an independent backup-runtime project only.

## Evidence URLs

- OpenAI developer mode / remote MCP: https://help.openai.com/en/articles/12584461
- Vercel MCP hosting: https://vercel.com/changelog/mcp-server-support-on-vercel
- Vercel MCP template: https://vercel.com/templates/ai/model-context-protocol-mcp-with-next-js
- Vercel function limits: https://vercel.com/changelog/higher-defaults-and-limits-for-vercel-functions-running-fluid-compute
- mcp-handler: https://www.npmjs.com/package/mcp-handler
- Enzonic web hosting: https://enzonic.com/web-hosting
- Enzonic bot hosting: https://enzonic.com/discord-bots
- Deplexo: https://deplexo.com/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Render free services: https://render.com/docs/free
- Koyeb free instance: https://www.koyeb.com/docs/reference/instances
- Deno Deploy pricing: https://deno.com/deploy/pricing
