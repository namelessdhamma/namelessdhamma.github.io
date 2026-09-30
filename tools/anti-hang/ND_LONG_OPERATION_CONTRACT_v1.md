# ND Long-Operation Contract v1 — Candidate

Status: NAM-397 candidate. Not CURRENT authority until adopted through ND publication.

## Purpose

Prevent a long, lost, ambiguous, or opaque external operation from blocking or duplicating the parent ND objective. This contract limits blocking control calls, not cognitive depth, number of useful phases, or number of materially justified capabilities.

## Runtime profiles

Every active external route that can materially wait is classified JIT as one of:

- `BOUNDED_SYNC`: one control call is expected to complete within an explicit end-to-end control deadline.
- `DURABLE_ASYNC`: long work is detached from the control call and exposes stable effect/job identity plus bounded status/result reads.
- `OPAQUE_BLOCKING`: ND cannot reliably interrupt the tool internally; protect the boundary before the call and recover after interruption.

The profile describes transport behavior only. It never changes substantive task ownership.

## Universal invariants

1. External wait is local to the current operation, not completion or failure of the parent objective.
2. A potentially long operation must not hold the foreground merely to wait for worker completion when a durable async interface exists.
3. `SUBMIT != WAIT`: accepted submit returns control with stable identity.
4. `STATUS` and `RESULT` are bounded control reads; no foreground polling loop.
5. Consequential ambiguous outcome becomes `OUTCOME_UNKNOWN`, not automatic failure.
6. `OUTCOME_UNKNOWN -> provider reconciliation -> same effect` before any retry.
7. Never repeat a confirmed effect because a response was lost.
8. Local Stop/request interruption is not remote cancellation. Claim remote cancellation only after provider confirmation.
9. A late result may be preserved as evidence/result but may not revive a superseded owner/task generation.
10. If useful independent work remains, the live owner continues it. If none remains, return `WAIT_EXTERNAL` with a resume trigger instead of keeping a false foreground Working state.
11. Result retrieval may return a provider reference/cursor/chunk. A large artifact need not be materialized in one control call.
12. Expired result URL does not invalidate the result; refresh the reference before considering recomputation.

## Compact continuation

Persist only when restart/cross-chat recovery, ambiguity, concurrency, or a demonstrated failure mode warrants it.

Minimum resumable handle:

- objective_ref
- owner_ref
- phase
- accepted_result_refs
- effect_id
- provider_job_id / request_id when available
- operation_profile
- outcome_state
- observed_at
- next_action
- resume_trigger when waiting
- supersession/generation identity only where late-result races are possible

Do not persist chain-of-thought. Do not publish StateHead on every status read. Provider job state remains provider-owned.

## Ownership

Automation Agent owns the overall objective.
The active substantive Supervisor owns its domain phase.
Generation owns external route/capability selection only as SUPPORT.
True Memory stores a compact continuation only when materially needed.
True Developer implements deadlines, abort, idempotency and reconciliation in controllable adapters.
True Doctor diagnoses ambiguous incidents across client/UI -> tool transport -> adapter -> provider -> worker -> currentness.

Children normally need no transport protocol copy. They return result / pending / exact blocker to their live owner.

## Stop / resume

On a delivered Stop:
- open no new operation on the stopped branch;
- preserve accepted results and effect/job identity when materially needed;
- issue remote cancel only when explicitly supported/authorized;
- otherwise leave the provider job unchanged;
- later recovery resumes/reconciles the same operation before considering replacement.

An undelivered client Stop is a platform incident, not proof that the provider operation stopped.

## Route qualification

For each active route record only:
- runtime profile;
- bounded-control deadline support;
- abort/cancel support;
- stable effect/job identity support;
- reconciliation method;
- bounded result strategy;
- real opaque/provider limitations.

Do not create a global job database, polling daemon, route-specific cognitive agent, or duplicate contract in every skill merely to implement this behavior.
