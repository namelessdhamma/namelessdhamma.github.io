# ND VK Gateway Immutable Runtime — Qualification Handoff

Status: **CANDIDATE / NOT PRODUCTION**

## Purpose

Replace the current successful V53 Railway startup chain with an equivalent packaged runtime that does not download executable source from raw GitHub or install OS packages after the container starts.

## Fresh production evidence

- Railway service: `nd-qstash-control-v2` (`7c280018-9102-4357-9965-4a4f88eee93e`)
- Current deployment observed: `b40a76dc-8fbb-4f6e-ae72-04064157dbd4` — `SUCCESS`
- Current source image: `python:3.12-alpine`
- Current start command downloads `tmp/nd_v53_recovery_v13_v42.py` from commit `64b01f98ef8b2a255a5ae15a848554d02ae55d4b` at process startup.
- V53 itself runs `apk add --no-cache nodejs`, then starts broker V13 and gateway V42.

## Dependency-graph result

The observed executable bootstrap graph is now closed for the current V53 chain. The gateway side terminates at standalone `nd_vk_gateway_v9_free_router.py`; the broker side terminates at standalone V2 plus fixed fragments. Exact edges and pins are in `runtime-dependency-lock.v1.json`.

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
- audit rule was regression-corrected after a synthetic test exposed a missed argv-form package install.

Not yet verified:

- full Docker image build in CI/build infrastructure;
- packaged candidate startup with production-compatible environment variables;
- `/health`, `VK_READY`, `allowed_count=2`, model-router, authority/read, Yandex, web and Father Workspace probes against the packaged candidate;
- Railway in-place source switch path and rollback execution.

GitHub Actions did not produce a run immediately after adding the branch-scoped workflow, so CI must not be claimed PASS. Local container network access to GitHub was unavailable, so a full local image build could not be substituted in this run.

## Promotion gate

Do **not** switch production merely because the package builds. Promotion requires all of:

1. image/build PASS;
2. runtime bootstrap audit PASS;
3. candidate health/startup markers PASS;
4. `allowed_count=2` PASS;
5. Groq/OpenRouter strong routing and fail-closed behavior PASS;
6. ND authority + Google Drive + GitHub/Obsidian + Yandex read probes PASS;
7. current-web verified-source probe PASS;
8. canonical mutation DENY PASS;
9. Father Workspace Inbox / Book Draft / Research write + exact read-back + idempotency PASS;
10. rollback pointer to the current successful V53 deployment retained.

Only after these checks should Railway production be switched. After the immutable-runtime frontier is green, resume the intelligence-router research/literary qualification frontier.
