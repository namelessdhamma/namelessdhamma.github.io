# ND VK Intelligence Router — Qualification Handoff

Status: **CANDIDATE HARNESS / NOT PRODUCTION**

## Goal

Replace brand/vendor-fixed routing with evidence-driven task-fit routing for the father's VK interface. Primary roles: `research`, `literary`, `critic/reviewer`, `long-context`, `general`, `fast-strong`.

No candidate receives production answer-authority from reputation, country, vendor, parameter count, benchmark claims, or this document. Promotion requires live ND-specific comparison against the current production baseline.

## Fresh 2026-09-13 discovery

OpenRouter's current free-model collection remains active and explicitly describes free endpoints as capacity that may change. Current official model pages observed during this run expose exact `:free` endpoints for:

- `nvidia/nemotron-3-super-120b-a12b:free`
- `inclusionai/ring-2.6-1t:free`
- `inclusionai/ling-2.6-1t:free`
- `qwen/qwen3.6-plus:free`
- `minimax/minimax-m3:free`

These are discovery candidates only. Exact free eligibility is rechecked from `https://openrouter.ai/api/v1/models` at every harness run; both prompt and completion pricing must be numeric zero. A missing/changed entry is fail-closed to INELIGIBLE/UNKNOWN.

`openrouter/free` is intentionally excluded from auditable production qualification because it may choose different free models. It remains useful only for discovery/experimentation.

## Implemented artifacts

- `intelligence-candidates.v1.json` — current candidate set, baseline, evidence links, and policy.
- `intelligence-suite.v1.json` — representative synthetic Russian research/literary/general tasks with explicit checks.
- `run_intelligence_qualification.py` — live OpenRouter evaluator that:
  - verifies exact zero pricing from the live catalog first;
  - refuses inference if free status cannot be established;
  - never changes production routing;
  - records requested and actually-used model, latency, usage, response, case id and expected checks to JSONL;
  - accepts domain/model filters for bounded comparisons.
- CI validates JSON, Python syntax, and performs a catalog-only live eligibility probe without credentials.

## Evaluation method

Research dimensions: factual correctness, contradiction handling, uncertainty calibration, provenance discipline, counterevidence quality, Russian quality.

Literary dimensions: prose quality, voice preservation, subtext, structural judgment, constraint obedience, non-generic variation, Russian quality.

Scoring is 0–4 per dimension. A model must clear the minimum floor on all safety-critical research dimensions and demonstrate repeatable role-specific benefit or meaningful fallback value against the current baseline. One exceptional answer is insufficient.

High-value tasks may later use bounded multi-model patterns (`primary + critic`, `independent solve + compare`, `draft + literary reviewer`) only after the participating role models are individually qualified.

## Current runtime constraint

The immutable-runtime candidate remains image/build qualified but not live-canary qualified. Railway free-plan capacity rejected creation of a new canary. An existing undeployed `nd-external-intelligence` service was re-inspected and is **not disposable**: it already has its own `/services/nd-external-intelligence` root, uvicorn start command and GLM/ZAI-related variable contract. It was therefore not repurposed.

Railway's AI agent currently reports its own usage limit, so it cannot attach/reconfigure that service or investigate alternative source-attachment paths during this run. Production V53 remains unchanged.

## Next executable gates

1. Wait for/inspect CI on `qualify/vk-intelligence-router` and fix any harness/static failure.
2. Run catalog-only eligibility from CI and preserve the exact eligible set as evidence.
3. At the next environment with `OPENROUTER_API_KEY`, execute bounded research and literary suites against the eligible set plus current baseline; retain full JSONL evidence.
4. Have True Research adjudicate research dimensions and True Writer adjudicate literary dimensions independently; compare results and derive role-specific rankings, not a single global winner.
5. Only then implement a dynamic production map with recent-live-evidence timestamps, provider health/cooldown, exact-free gating, and per-role fallback.
6. Independently continue immutable-runtime live-canary qualification; do not couple model-ranking promotion to an unverified runtime switch.
