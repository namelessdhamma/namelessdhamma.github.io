# ND NotebookLM — Phone-independent Remote MCP Plan

Date: 2026-09-10
Status: research/qualification only
Branch: notebooklm-mcp-bootstrap

## Decision

Primary target is no longer an always-on Android/Termux runtime.

Target architecture:

```text
ChatGPT
  -> remote Streamable HTTP MCP endpoint
  -> NotebookLM adapter
  -> consumer NotebookLM
```

Android/Termux remains a separately maintained backup path only.

## Verified architectural fact

OpenAI's current ChatGPT developer-mode documentation states that ChatGPT connects to remote MCP servers directly. Secure MCP Tunnel is needed when an MCP server is local/private and is not directly reachable as a remote endpoint.

Therefore a qualified remote MCP endpoint can potentially remove both the always-on user device and the continuously running tunnel-client from the primary path.

Reference:
https://help.openai.com/en/articles/12584461

## First host candidate: Cloudflare Workers

Cloudflare currently documents deployment of remote MCP servers using Streamable HTTP and recommends a stateless handler for new servers.

References:
https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/
https://developers.cloudflare.com/agents/model-context-protocol/protocol/transport/

Why test it first:
- native remote MCP documentation;
- stateless Streamable HTTP;
- on-demand execution rather than an always-on daemon;
- Workers Free plan exists;
- no phone/runtime process required after deployment;
- Git-based deployment/update path is possible.

Material risk:
- Workers Free currently allows only 10 ms CPU time per HTTP request and 128 MB memory. Network wait time does not count as CPU time, but NotebookLM authentication/request parsing may still exceed the CPU budget.
- Therefore Cloudflare is a qualification target, not yet a production recommendation.

Current Free-plan references:
https://developers.cloudflare.com/workers/platform/limits/
https://developers.cloudflare.com/workers/platform/pricing/

## Experiment 1 — remote MCP transport only

Do not move Google credentials yet.

Build the smallest possible remote MCP endpoint with one harmless tool such as `nd_ping` returning a fixed JSON payload.

Qualification gates:
1. deploy to a free remote endpoint;
2. configure a temporary ChatGPT custom MCP app against that endpoint;
3. Scan Tools succeeds;
4. ChatGPT discovers `nd_ping`;
5. ChatGPT invokes `nd_ping` successfully after the host has been idle;
6. repeat after cold start / scale-to-zero conditions if applicable.

PASS means the phone and Secure MCP Tunnel are not structurally required for the primary architecture.

## Experiment 2 — NotebookLM adapter feasibility

Only after Experiment 1 passes:
1. identify the minimum subset of notebooklm-py behavior required for account auth and notebook operations;
2. determine whether it can run in the selected serverless runtime directly;
3. if Python/FastMCP is too heavy, implement a small runtime-native adapter instead of reproducing the full local Python stack;
4. store auth material only in managed secrets, never in Git;
5. run read-only NotebookLM test;
6. run bounded create/read-back test;
7. test credential refresh after idle/cold start.

## Fallback host class

If Cloudflare Free cannot meet CPU/runtime requirements, keep the same remote Streamable HTTP MCP design and move only the host. Do not fall back immediately to an always-on daemon.

Next host classes to qualify:
- serverless Node/Python functions with a larger per-request CPU/runtime budget;
- free scale-to-zero container services;
- other MCP-native remote hosting platforms.

## Success condition

A primary runtime is qualified only when:
- no Android/browser is required;
- no always-on local process is required;
- recurring infrastructure cost is expected to remain $0;
- ChatGPT can directly discover and call MCP tools;
- NotebookLM auth survives idle/cold start;
- read and write/read-back pass;
- recovery after restart/cold start is demonstrated;
- the pattern is reusable for additional ND direct MCP/API integrations.
