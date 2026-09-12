# ND VK Gateway Immutable Runtime — Qualification Handoff

Status: **CANDIDATE / IMAGE-BUILD QUALIFIED / NOT PRODUCTION**

## Purpose

Replace the current successful V53 Railway startup chain with an equivalent packaged runtime that does not download executable source from raw GitHub or install OS packages after the container starts.

## Fresh production evidence

- Railway service: `nd-qstash-control-v2` (`7c280018-9102-4357-9965-4a4f88eee93e`)
- Current deployment observed: `b40a76dc-8fbb-4f6e-ae72-04064157dbd4` — `SUCCESS`
- Current source image: `python:3.12-alpine`
- Current start command downloads `tmp/nd_v53_recovery_v13_v42.py` from commit `64b01f98ef8b2a255a5ae15a848554d02ae55d4b` at process startup.
- V53 itself runs `apk add --no-cache nodejs`, then starts broker V13 and gateway V42.
- Fresh production logs still show V53/V13/V42 startup, `VK_READY`, `allowed_count=2`, Google authority PASS, `web_current` with 10 verified source URLs, Father Workspace Inbox/Book Draft safety/idempotency PASS, Research save/read-back PASS, Yandex read PASS, and Groq/OpenRouter probes PASS.
- Known readonly defect remains: four expected GitHub/Obsidian orientation files (`00 СЕЙЧАС.md`, `01 ТЕМЫ.md`, `02 РЕШЕНИЯ.md`, `03 ИЗМЕНЕНИЯ.md`) currently return 404 in the production probe. Yandex and Google authority reads remain healthy.

## Dependency-graph result

The observed executable bootstrap graph is closed for the current V53 chain. The gateway side terminates at standalone `nd_vk_gateway_v9_free_router.py`; the broker side terminates at standalone V2 plus fixed fragments. Exact edges and pins are in `runtime-dependency-lock.v1.json`.

## Candidate implementation

- `vendor_runtime.py` downloads only exact commit-pinned dependencies during **image build**, rewrites the ND raw-GitHub bootstrap namespace to `ndvendor://`, writes source/package SHA-256 evidence, and emits a vendor manifest.
- `run_broker.mjs` resolves `ndvendor://` fetches from the local packaged vendor tree while delegating normal provider/API requests to native `fetch`.
- `run_gateway.py` resolves `ndvendor://` `urllib.request.urlopen` calls from the local packaged vendor tree while delegating normal external API requests to the standard library.
- `start.py` preserves the existing two-process topology: broker on public `$PORT`, VK gateway on inner port 3001, and fail-fast supervision if either process exits.
- Multi-stage `Dockerfile` keeps the vendorizer and dependency lock out of the final runtime image; Python/Node are installed at image-build time, never process-start time.
- `audit_runtime_bootstrap.py` is a fail-closed runtime-tree gate for raw-GitHub executable bootstrap and runtime package-install patterns. Regression tests include the exact V53-style Python argv form `subprocess.run(['apk','add',...])`.

## Verification state

Verified:

- current production deployment remains unchanged and successful;
- exact V53 start configuration recovered from Railway;
- nested V53 dependency graph recovered through standalone terminal sources;
- qualification artifacts persisted on branch `qualify/vk-gateway-runtime`;
- audit rule was regression-corrected after a synthetic test exposed a missed argv-form package install;
- GitHub Actions run `34715874014` for commit `261f1dcf1a5047ed42ff5fe5510d0a85e7124ff2` completed successfully for regression tests + lock validation;
- GitHub Actions run `34718406121` for commit `d2dd851220ee782e53772cc95c5e94239ec50c85` completed successfully with all of: regression tests PASS, dependency lock JSON PASS, full Docker image build PASS, and re-audit of the **built runtime filesystem** PASS;
- therefore the former image-build/network blocker is closed.

Blocked / not yet verified:

- packaged candidate startup with the real production-compatible environment;
- `/health`, packaged `VK_READY`, `allowed_count=2`, model-router, authority/read, Yandex, web and Father Workspace probes against the packaged candidate;
- Railway in-place source switch path and rollback execution.

### Canary resource constraint

A separate Railway service `nd-vk-gateway-canary` was attempted from `namelessdhamma/namelessdhamma.github.io`, branch `qualify/vk-gateway-runtime`, but Railway rejected creation with: `Free plan resource provision limit exceeded. Please upgrade to provision more resources!`.

Do not spend or upgrade automatically. Do not repurpose healthy/meaningful existing services merely to obtain a canary. Existing services observed: `n8n`, production `nd-qstash-control-v2`, `nd-yandex-n8n-gateway`, and undeployed-but-configured `nd-external-intelligence`; the latter already has its own root/start configuration and ZAI/ND-EAI variables and is not treated as disposable.

## Promotion strategy under current resource limit

1. Keep production V53 unchanged while strengthening build/runtime-static gates.
2. Prefer a zero-cost isolated execution path if one becomes available (temporary Railway environment/service without new resource spend, GitHub Actions runtime with safely supplied equivalent environment, or another already-qualified zero-cost container runtime).
3. Do not perform an in-place production switch until the packaged candidate can be live-tested or a deliberately bounded blue/green equivalent is available.
4. If eventually forced to qualify in-place, first preserve the exact current V53 source image + start command + deployment ID as rollback authority, then use the smallest reversible switch and immediately run the full promotion gate; rollback on first failed invariant.

## Promotion gate

Do **not** switch production merely because the package builds. Promotion requires all of:

1. image/build PASS — **VERIFIED**;
2. runtime bootstrap audit PASS — **VERIFIED on built image**;
3. candidate health/startup markers PASS;
4. `allowed_count=2` PASS;
5. Groq/OpenRouter strong routing and fail-closed behavior PASS;
6. ND authority + Google Drive + GitHub/Obsidian + Yandex read probes PASS;
7. current-web verified-source probe PASS;
8. canonical mutation DENY PASS;
9. Father Workspace Inbox / Book Draft / Research write + exact read-back + idempotency PASS;
10. rollback pointer to successful V53 deployment `b40a76dc-8fbb-4f6e-ae72-04064157dbd4` retained.

After the immutable-runtime frontier is green, resume the intelligence-router research/literary qualification frontier.
