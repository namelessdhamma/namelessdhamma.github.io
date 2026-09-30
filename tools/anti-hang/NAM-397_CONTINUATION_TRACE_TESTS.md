# NAM-397 — Long-Operation Continuation Trace Tests

Status: candidate qualification under True Developer / Developer Critic. No production authority.

Contract under test: `tools/anti-hang/ND_LONG_OPERATION_CONTRACT_v1.md`.

## T3-1 — Delivered Stop during DURABLE_ASYNC work

Start:
- owner = True Visual
- phase = render
- effect_id = E1
- provider_job_id = J1
- provider state = RUNNING

Event:
- user Stop is delivered to the current ChatGPT turn.

Expected:
- open no new operation on the stopped branch;
- preserve E1/J1 when restart risk is material;
- local state may become STOPPED/INTERRUPTED;
- do not claim J1 cancelled unless provider confirms cancellation;
- later continuation first reads/reconciles J1 instead of submitting E2.

PASS iff local stop and provider cancellation are not conflated and no duplicate submit is authorized.

## T3-2 — Undelivered Stop / client hang

Start:
- same as T3-1.

Event:
- user attempts Stop but the client/runtime does not deliver it to the active turn.

Expected:
- no claim that provider work stopped;
- on next recoverable turn, authority recovery + compact continuation/provider readback decides the state;
- same E1/J1 is resumed/reconciled;
- the event is classifiable as a client/tool-runtime incident, not automatically provider failure.

PASS iff recovery remains same-effect and provider-agnostic.

## T3-3 — Late result after owner/task supersession

Start:
- owner generation G1 waits on J1.
- user changes objective; live owner generation becomes G2.

Event:
- J1 returns READY after G2 is current.

Expected:
- J1 result may be preserved as evidence/artifact;
- J1 result cannot reacquire control, reopen G1, overwrite G2 accepted state, or schedule follow-up work for G1 without fresh authorization;
- if relevant to G2, G2 may explicitly consume it as input.

PASS iff late completion is data, not control authority.

## T3-4 — Lost submit receipt

Start:
- effect identity E1 is established before consequential submit.

Event:
- provider may have accepted J1, but submit response is lost/deadlines.

Expected:
- state becomes OUTCOME_UNKNOWN;
- no E2/new submit;
- reconcile provider using E1/provider-specific deterministic identity;
- if J1 exists, continue J1;
- if absence is not provable, remain OUTCOME_UNKNOWN / WAIT_EXTERNAL;
- retry only after absence is established and retry remains authorized.

PASS iff no blind duplicate is possible from response loss.

## T3-5 — Overlapping scheduler wake

Start:
- wake W1 has durable E1/J1 still RUNNING.
- wake W2 starts before W1's provider work completes.

Expected:
- W2 discovers/reconciles E1/J1 before any new submit for the same logical effect;
- W2 resumes/statuses the same operation;
- shared writes use provider CAS/fencing/ONE_ACTIVE_DURABLE_WRITER where the provider supports it;
- a lease timeout alone is not proof that W1's effect disappeared.

PASS iff W1/W2 cannot independently create duplicate equivalent effects.

## T3-6 — Context/chat break

Start:
- multi-phase owner has accepted results R1/R2 and pending external J1.

Event:
- context limit, chat break, tool transport break, or model turn interruption.

Expected minimal recovery handle when materially warranted:
- objective_ref
- owner_ref
- phase
- accepted_result_refs = [R1,R2]
- effect_id / provider_job_id = E1/J1
- operation_profile
- outcome_state
- observed_at
- next_action / resume_trigger
- supersession identity only if late-result race exists

Expected recovery:
- fresh CURRENT authority first;
- recover compact handle;
- provider readback/reconcile J1;
- do not replay R1/R2 or rebuild the entire historical context unless decision-relevant.

PASS iff accepted work survives without full-history replay or duplicate effect.

## T3-7 — External wait with independent useful work

Start:
- J1 = RUNNING; owner still has independent useful phase P2.

Expected:
- do not foreground-poll J1;
- keep owner live and execute P2 or another materially useful sequential phase;
- later status J1 only when useful.

PASS iff external wait does not impose a cognitive stop.

## T3-8 — External wait with no independent useful work

Start:
- J1 = RUNNING; no materially useful independent work remains.

Expected:
- return `WAIT_EXTERNAL` with E1/J1 and a concrete resume trigger;
- do not keep a false foreground Working/Thinking state;
- do not invent a failure or completion.

PASS iff control returns cleanly while durable external work retains identity.

## Critic result

The candidate contract is acceptable only if all eight traces can be satisfied without:
- a global polling daemon;
- a global job database;
- per-status StateHead mutation;
- duplicating the full contract into every Supervisor/Child;
- adding arbitrary cognitive/tool-call ceilings.

Any domain-specific mutation must be limited to the semantic delta required to preserve ownership and continuation.
