# ND NotebookLM Remote MCP — Vercel qualification build

This directory contains the phone-independent Stage-A remote MCP implementation for Nameless Dhamma.

## Current scope

Stage A exposes no Google credentials and no NotebookLM data. It exists only to qualify direct remote Streamable HTTP MCP connectivity from ChatGPT.

Endpoints after deployment:

- `/api/mcp` — MCP endpoint exposing `nd_ping`
- `/api/health` — harmless JSON health/version endpoint

Expected `nd_ping` / health payload:

```json
{
  "ok": true,
  "service": "nd-notebooklm-remote-mcp",
  "mode": "transport-qualification",
  "version": "0.1.0"
}
```

## Local verification

```bash
npm install
npm test
npm run build
```

## Deployment target

Primary qualification host: Vercel Hobby.

Project root in Vercel must be:

```text
tools/notebooklm-mcp/remote-vercel
```

No environment variables or secrets are required for Stage A.

## Promotion rule

Do not add NotebookLM/Google credentials until all Stage-A gates pass:

1. HTTPS health endpoint reachable;
2. ChatGPT custom remote MCP scans tools successfully;
3. `nd_ping` is discovered and callable;
4. call succeeds after idle/cold start;
5. call succeeds after redeploy/restart;
6. no Android, Cloud Shell, or Secure MCP Tunnel participates in the route.

After Stage A passes, Stage B adds only authenticated read-only `notebook_list` first.
