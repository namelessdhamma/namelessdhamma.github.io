# ND VK Intelligence Router — Qualification Handoff

Status: **CANDIDATE HARNESS / NOT PRODUCTION**

## Goal

Replace brand/vendor-fixed routing with evidence-driven task-fit routing for the father's VK interface. Primary roles: `research`, `literary`, `critic/reviewer`, `long-context`, `general`, `fast-strong`.

No candidate receives production answer-authority from reputation, country, vendor, parameter count, benchmark claims, or this document. Promotion requires live ND-specific comparison against the current production baseline.

## Fresh 2026-09-13 discovery

Static OpenRouter model pages observed during discovery expose exact `:free` pages for:

- `nvidia/nemotron-3-super-120b-a12b:free`
- `inclusionai/ring-2.6-1t:free`
- `inclusionai/ling-2.6-1t:free`
- `qwen/qwen3.6-plus:free`
- `minimax/minimax-m3:free`

Static pages are **not** treated as routing authority. The first credential-free CI catalog probe queried the live `https://openrouter.ai/api/v1/models` response and found 19 exact-zero free ids overall. Of the five configured discovery candidates, only `nvidia/nemotron-3-super-120b-a12b:free` satisfied the exact-free gate at that moment. Ring/Ling/Qwen/MiniMax were therefore classified INELIGIBLE_OR_UNKNOWN for that run rather than assumed free.

This discrepancy is retained as evidence for mandatory live pricing/status checks. Both prompt and completion pricing must be numeric zero. A missing/changed entry is fail-closed to INELIGIBLE/UNKNOWN.

`openrouter/free` is intentionally excluded from auditable production qualification because it may choose different free models. It remains useful only for discovery/experimentation.

## Implemented artifacts

- `intelligence-candidates.v1.json` — candidate discovery set, baseline, evidence links, and fail-closed policy.
- `intelligence-suite.v1.json` — representative synthetic Russian research/literary/general tasks with explicit checks.
- `run_intelligence_qualification.py` — live OpenRouter evaluator that:
  - verifies exact zero pricing from the live catalog first;
  - refuses inference if free status cannot be established;
  - never changes production routing;
  - records requested and actually-used model, latency, usage, response, case id and expected checks to JSONL;
  - accepts domain/model filters for bounded comparisons.
- CI validates JSON, Python syntax, performs a catalog-only live eligibility probe without credentials, builds the immutable runtime image, re-audits the built filesystem, compiles packaged Python, performs fail-closed packaged JavaScript syntax checks, and exports the vendor manifest.

## Evaluation method

Research dimensions: factual correctness, contradiction handling, uncertainty calibration, provenance discipline, counterevidence quality, Russian quality.

Literary dimensions: prose quality, voice preservation, subtext, structural judgment, constraint obedience, non-generic variation, Russian quality.

Scoring is 0–4 per dimension. A model must clear the minimum floor on all safety-critical research dimensions and demonstrate repeatable role-specific benefit or meaningful fallback value against the current baseline. One exceptional answer is insufficient.

High-value tasks may later use bounded multi-model patterns (`primary + critic`, `independent solve + compare`, `draft + literary reviewer`) only after the participating role models are individually qualified.

## Readonly vault defect isolated

Fresh inspection of `namelessdhamma/nameless-dhamma-vault` shows the current root orientation files are:

- `00 ตอนนี้ — Now.md`
- `01 แผนที่ — Maps.md`
- `02 หัวข้อ — Topics.md`
- `03 การเปลี่ยนแปลง — Changes.md`

The production gateway's pinned V13 readonly fallback still requests obsolete Russian names (`00 СЕЙЧАС.md`, `01 ТЕМЫ.md`, `02 РЕШЕНИЯ.md`, `03 ИЗМЕНЕНИЯ.md`), explaining the repeated startup 404s and `github=false` probe even though GitHub connectivity itself is healthy.

Qualification-only V54 (`tmp/nd_vk_gateway_v54_vault_paths.py`) applies the smallest possible fail-closed patch to that exact pinned V13 source and replaces only those four fallback paths. Regression coverage checks the pinned V13 marker, all four current paths and failure on marker drift. V54 is not production and does not mutate the vault.

## CI integrity correction

An inherited JavaScript syntax-check step was discovered to call `docker` from inside the already-running runtime container. That container has no Docker CLI, so the step emitted `sh: docker: not found` while the overall job still appeared green. The workflow was corrected to enumerate `/app/**/*.js|*.mjs` inside the container itself and run `node --check` on every file, with `test -s` so an empty file list fails closed. Prior green JS-syntax evidence is therefore superseded by the corrected CI gate.

## Current runtime constraint

The immutable-runtime candidate remains image/build qualified but not live-canary qualified. Railway free-plan capacity rejected creation of a new canary. An existing undeployed `nd-external-intelligence` service was re-inspected and is **not disposable**: it already has its own `/services/nd-external-intelligence` root, uvicorn start command and GLM/ZAI-related variable contract. It was therefore not repurposed.

Railway's AI agent currently reports its own usage limit, so it cannot investigate alternative source-attachment paths during this run. Production V53 remains unchanged and successful.

## Next executable gates

1. Require corrected CI PASS, including the new real JavaScript syntax gate and V54 regression tests.
2. At the next environment with `OPENROUTER_API_KEY`, execute bounded research and literary suites against the then-live eligible set plus current baseline; retain full JSONL evidence.
3. Have True Research adjudicate research dimensions and True Writer adjudicate literary dimensions independently; derive role-specific rankings, not a single global winner.
4. Integrate the qualified V54 readonly-path correction into the packaged immutable runtime dependency graph and live-test `github=true` before any production adoption.
5. Only after model qualification implement a dynamic production map with recent-live-evidence timestamps, provider health/cooldown, exact-free gating, and per-role fallback.
6. Independently continue immutable-runtime live-canary qualification; do not couple model-ranking promotion to an unverified runtime switch.
