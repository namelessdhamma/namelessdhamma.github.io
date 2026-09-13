# ND True Doctor v0.3 — field integration

Status: QUALIFICATION / FIELD-READY CANDIDATE  
Logical identity: `ND_TRUE_DOCTOR`  
No separate scheduler.

## One Doctor, two invocation adapters

```
                    True Memory
        Shared Doctor Knowledge Namespace
  ┌──────────────────────────────────────────┐
  │ incidents / patterns / profiles / probes │
  │ repair recipes / health / learning       │
  └───────────────────┬──────────────────────┘
                      │
               ND_TRUE_DOCTOR v0.3
          Monitor → Analyze → Plan → Probe
             → Contain/Repair → Verify
                      │
          ┌───────────┴───────────┐
          │                       │
   AUTOMATION adapter      MANUAL_CHAT adapter
   existing 5 cycles       user: "Доктор"
```

Both adapters must use the same Doctor ID, Field Incident Ledger, context revision and learning pipeline.

## Automation field mode

A technical failure inside an existing cycle is an in-band Doctor episode, not a new scheduled job.

1. Preserve the parent objective and evidence.
2. Load current Doctor context from True Memory.
3. Start `AUTOMATION` invocation with cycle/branch/assignment correlation.
4. Run only discriminating probes permitted by current authority.
5. Refine diagnosis.
6. Prefer `CONTINUE_PRIMARY` when the required primary operation is proven healthy.
7. Otherwise contain, use an already-qualified failover, or fail closed as required.
8. Verify the capability **and** parent objective.
9. Persist invocation/probe/outcome/learning receipts.
10. Any material Doctor engineering improvement becomes an Agent candidate; Doctor does not self-assign global work.

## Manual-chat field mode

When the user says `Doctor`, `Доктор`, or `True Doctor` in an ND chat:

1. Recover Doctor bootstrap/current context through True Memory; do not ask the user to retell ND history.
2. Infer the incident from current conversation/tool evidence where possible.
3. Start `MANUAL_CHAT` invocation using the same core and ledger.
4. Diagnose and run safe probes.
5. Execute only already-authorized safe treatment; otherwise route one minimal irreducible gate.
6. Verify the original operation.
7. Persist the same receipts used by automation mode.

## v0.2 capabilities delivered

- `ExpectedToolProfile` data contract.
- `DoctorContextSnapshot`.
- prior-incident retrieval and similarity.
- pattern retrieval.
- capability expectation matching.
- context-supported confidence.
- shared durable identity across invocation modes.
- persistent invocation/learning receipt contract.

## v0.3 capabilities delivered

- explicit `ProbeSpec` registry with risk, cost, mutation class and failure domain.
- tool exposure, control-plane, provider profile, safe read, reversible write, thread/surface canary, runtime, pointer and browser probe interfaces.
- injected probe adapters so ChatGPT/plugin/broker implementations can vary without changing Doctor semantics.
- evidence-based diagnosis refinement.
- negative evidence: a passing independent provider probe can reject a provider-down diagnosis.
- continuity decisions: PRIMARY / DEGRADED / THREAD / SURFACE / FAILOVER / HUMAN_GATE / FAIL_CLOSED.
- validation is mandatory before a repair becomes learning evidence.
- learning candidate creation is proposal-only; production self-mutation is prohibited.
- safe-recipe executor contract supports only explicitly whitelisted recipes with idempotency key.
- broad autonomous mutation remains disabled until v0.4 qualification.

## Field-learned rule 001

Observed 2026-09-13:
- Plugin control plane reported Google Drive `not_installed`.
- Live Google Drive profile/read path passed.

Original v0.3 draft selected failover because an alternate existed. Field evidence showed that was too aggressive.

Current rule:
**INSTALL_CONTROL_PLANE + required primary operation PASS ⇒ CONTINUE_PRIMARY and repair control-plane inconsistency out-of-band.**

Commit: `09503baa9d667b271d0e80f0bcdc1583244e2778`.

## Research design basis

The architecture deliberately combines:
- reconciliation/control loops (desired vs observed state);
- MAPE-K shared knowledge;
- mandatory post-adaptation validation;
- SRE incident lifecycle and learning;
- idempotent retry discipline;
- graceful degradation and independent failure domains;
- durable state independent of ephemeral execution sessions.

## Current durable state

Field Incident Ledger:
`1gLe2caIqgBO2cMr7VRIGyNAJr4BeGxdeb5MKZvmnqAE`

Current v0.3 branch:
`qualify/true-doctor-v0.3`

Core:
`tmp/nd_true_doctor_v03.js`

Regression:
`tmp/nd_true_doctor_v03_selftest.mjs`

## Current safety boundary

Allowed:
- diagnose;
- read-only probes;
- explicitly authorized reversible qualification probes;
- safe containment;
- already-qualified failover;
- bounded/idempotent safe recipe execution when invocation authority allows it.

Not allowed by v0.3 merely because Doctor exists:
- blind plugin reinstall/reconnect;
- speculative permission expansion;
- credential reset;
- production architecture mutation;
- canonical authority change;
- destructive repair;
- Doctor-created global WorkItems;
- self-modification of production rules.

