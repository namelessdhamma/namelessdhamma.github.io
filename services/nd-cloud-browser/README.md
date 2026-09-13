# ND Cloud Browser — v0.1 Qualification Runtime

Lifecycle: **QUALIFICATION / NON_ADOPTED**

Purpose: prove a dedicated remote Chromium + Playwright runtime for ND without using the physical HONOR 50.

## Boundary

This component is separate from:
- TinyFish — public/ephemeral interactive browser workflows;
- Firecrawl — extraction/crawl/structured retrieval;
- ND Mobile Chrome / ND Mobile Device — physical-device execution;
- n8n / Safe Tool Broker / external-intelligence — existing role-specific runtimes.

## Current v0.1 surface

Authenticated HTTP qualification API:
- `GET /health`
- `GET /v1/status`
- `POST /v1/open`
- `GET /v1/observe`
- `POST /v1/click-text`
- `POST /v1/type`
- `POST /v1/back`
- `GET /v1/screenshot`
- `POST /v1/close`
- `GET /v1/ledger`

This is **not yet the custom MCP/OAuth surface**.

## Security defaults

- `ND_CLOUD_BROWSER_TOKEN` is mandatory.
- Tool requests use `Authorization: Bearer <token>`.
- Default hostname allowlist is limited to:
  - example.com
  - www.iana.org
  - httpbin.org
  - www.selenium.dev
- Override with `ND_CLOUD_BROWSER_ALLOWED_HOSTS`.
- Typed text is never written to the command ledger.
- Click targets and selectors are represented only by short SHA-256 hashes.
- Logged URLs have credentials, query strings, and fragments removed.
- Optional provenance headers:
  - `X-ND-Chat-Session`
  - `X-ND-Task-ID`
  - `X-ND-Run-ID`
  - `X-ND-Agent`
  - `X-ND-Controller`

## Persistence

The browser is launched with Playwright `launchPersistentContext`.

Expected persistent mount:
- `/data/profile` — Chromium user profile
- `/data/ledger` — append-only qualification command ledger

For Railway qualification, attach a volume at `/data`.

A process restart should close Chromium but retain browser profile state on the mounted volume.

## Required Railway variables

- `ND_CLOUD_BROWSER_TOKEN` — secret, generated outside Git
- `ND_CLOUD_BROWSER_ALLOWED_HOSTS` — qualification allowlist
- `PORT` — supplied by Railway

No passwords, cookies, OAuth tokens, browser storage, or user credentials belong in GitHub/Drive/Linear.

## Qualification gates

1. health/status
2. open/read/click/type/back/screenshot
3. set test cookie
4. restart service
5. verify cookie survives restart
6. process-kill/reconnect
7. bounded parallel request behavior
8. ledger provenance
9. downloads/uploads
10. authenticated-site test with user-approved non-secret handling
11. custom MCP + OAuth/DCR layer
12. True Version adoption

Production adoption remains outside this branch.
