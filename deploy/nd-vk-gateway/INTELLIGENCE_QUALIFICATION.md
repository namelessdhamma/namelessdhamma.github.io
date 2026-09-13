# ND VK Intelligence Router — Qualification Handoff

Status: **CANDIDATE HARNESS / DYNAMIC EXACT-FREE DISCOVERY QUALIFIED / NOT PRODUCTION**

## Goal

Replace brand/vendor-fixed routing with evidence-driven task-fit routing for the father's VK interface. Primary roles: `research`, `literary`, `critic/reviewer`, `long-context`, `general`, `fast-strong`.

No candidate receives production answer-authority from reputation, country, vendor, parameter count, benchmark claims, or this document. Promotion requires live ND-specific comparison against the current production baseline.

## Fresh 2026-09-13 live discovery

Static model pages are **not** routing authority. Every qualification run checks `https://openrouter.ai/api/v1/models`; both prompt and completion pricing must be numeric zero and the exact endpoint id must end in `:free`. Missing/changed entries fail closed to INELIGIBLE/UNKNOWN.

GitHub Actions run `34726833384` on commit `91dc4860b5b4ef8abc4634f455baf95843438927` queried the live catalog at `2026-09-13T00:00:19Z` and found 19 exact-zero free endpoints. The dynamic discovery filter retained 17 text-capable endpoints with >=131072 context and reasoning/tool-use signals. Notable qualification candidates include:

- `thinkingmachines/inkling:free` — 1,048,576 context, reasoning/tools advertised by the live catalog;
- `thinkingmachines/inkling-small:free` — 1,048,576 context, reasoning/tools;
- `nvidia/nemotron-3-ultra-550b-a55b:free` — 1,000,000 context, current production OpenRouter baseline;
- `nvidia/nemotron-3.5-lightning:free` — 1,000,000 context;
- `dots-studio/dots-3-note-preview:free` — 512,000 context;
- `inclusionai/ling-3.0-flash-vl:free` — 262,144 context;
- `nex-agi/nex-n2.5-pro:free` — 262,144 context;
- `nvidia/nemotron-3-super-120b-a12b:free` — 262,144 context;
- `poolside/laguna-s-2.1:free` — 262,144 context.

These are **discovery candidates only**. Context/tool/reasoning metadata is not accepted as quality evidence. True Research / True Writer task-suite adjudication is still required.

The older configured discovery set had already drifted: of Ring 2.6, Ling 2.6, Qwen 3.6 Plus, MiniMax M3, and Nemotron 3 Super, only `nvidia/nemotron-3-super-120b-a12b:free` remained exact-free in this live catalog. The harness correctly classified the others INELIGIBLE_OR_UNKNOWN rather than assuming static `:free` pages were current.

`openrouter/free` remains excluded from auditable production qualification because its underlying model selection is opaque/random for this purpose.

## Implemented artifacts

- `intelligence-candidates.v1.json` — baseline and seeded discovery set; no production authority.
- `intelligence-suite.v1.json` — representative synthetic Russian research/literary/general tasks with explicit checks.
- `run_intelligence_qualification.py` — live OpenRouter evaluator that now:
  - verifies exact zero pricing from the live catalog first;
  - records the complete current exact-free id set;
  - derives a broad dynamic discovery pool from current metadata while excluding non-text/narrow endpoints and `openrouter/free`;
  - allows an explicitly requested model to enter **qualification** even if it was not prelisted, but only when the live catalog proves it exact-free;
  - refuses inference when free status cannot be established;
  - never changes production routing;
  - records requested and actually-used model, latency, usage, response, case id, expected checks, and whether the candidate was dynamically discovered.
- CI validates JSON/Python, executes credential-free live catalog discovery, builds the immutable runtime image, re-audits the built filesystem, compiles packaged Python, performs packaged JavaScript syntax checks, and exports the vendor manifest.

## Latest qualification evidence

GitHub Actions run `34726833384` completed **success**. It passed:

1. bootstrap regression tests;
2. V54 vault-path regression tests;
3. dependency lock validation;
4. intelligence harness syntax + live catalog-only execution;
5. full immutable Docker image build;
6. built-filesystem bootstrap audit (`runtime_code_fetches=0`, `runtime_package_installs=0`);
7. packaged Python compilation;
8. packaged JavaScript syntax checks;
9. vendor-manifest artifact export.

The run does **not** qualify any new answer model because no OpenRouter inference credential was supplied to Actions; it qualifies the dynamic discovery/admission mechanism only.

## Evaluation method

Research dimensions: factual correctness, contradiction handling, uncertainty calibration, provenance discipline, counterevidence quality, Russian quality.

Literary dimensions: prose quality, voice preservation, subtext, structural judgment, constraint obedience, non-generic variation, Russian quality.

Scoring is 0–4 per dimension. A model must clear the minimum floor on all safety-critical research dimensions and demonstrate repeatable role-specific benefit or meaningful fallback value against the current baseline. One exceptional answer is insufficient.

High-value tasks may later use bounded multi-model patterns (`primary + critic`, `independent solve + compare`, `draft + literary reviewer`) only after participating role models are individually qualified.

## Current production/runtime evidence

Fresh Railway evidence in this run confirms production V53 deployment `b40a76dc-8fbb-4f6e-ae72-04064157dbd4` remains `SUCCESS` and still boots through the runtime-fetch chain. Logs show `VK_READY`, `allowed_count=2`, Google authority/Registry 1.8.1, `web_current` with 10 verified source URLs, Inbox/Book Draft safety+idempotency, Research save/read-back, Yandex reads, Groq and OpenRouter probes.

The remaining production readonly defect is the four obsolete GitHub orientation filenames in pinned V13; broker-level GitHub connectivity itself is healthy. The immutable runtime branch already contains the build-time successor patch for current vault paths and has image/static qualification, but live packaged `github=true` remains unverified.

Railway free-plan capacity still prevents creation of a separate canary. Existing `nd-external-intelligence` is not disposable and was not repurposed.

## Next executable gates

1. At an environment with the existing OpenRouter credential, run bounded **research** and **literary** suites against the then-live discovery pool, beginning with the production baseline plus a small high-value challenger set (not all models at once); retain JSONL evidence.
2. Have True Research adjudicate research dimensions and True Writer adjudicate literary dimensions independently; derive role-specific rankings rather than a single global winner.
3. Continue seeking a zero-cost isolated live execution path for the immutable image; require live `github=true`, health/startup, routing, authority, Yandex/web and Father Workspace probes before promotion.
4. Only after model qualification implement a dynamic production map with recent-live-evidence timestamps, provider health/cooldown, exact-free gating and per-role fallback.
5. Keep production V53 unchanged until the immutable runtime promotion gate is fully evidence-backed.
