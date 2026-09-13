# ND True Doctor v0.1 — qualification prototype

Status: QUALIFICATION / NON-PRODUCTION.

## Purpose
First executable trial of the ND-wide incident Doctor. It classifies failures and proposes bounded repair routes. It does not execute side effects.

## Current interface
- `doctorDiagnose(input)`
- `doctorRepair(input)`
- `classifyIncident(input)`
- `discriminatingProbe(failureClass)`
- `repairRoute(input, diagnosis)`
- `createIncidentEnvelope(input)`

## Authority
True Doctor is not a second Agent and not a second Developer. ND Automation Agent remains global WorkItem authority. Material repair implementation remains under valid Agent/Developer authority.

## v0.1 evidence
Regression fixtures cover:
1. Google Drive install/control-plane divergence with live backend.
2. Linear schema/runtime divergence.
3. Browserless post-timeout reclaim limitation.
4. OAuth/auth failure.
5. rate/quota failure.
6. thread-local failure.
7. read/write asymmetry.
8. UNKNOWN fallback.

The live ChatGPT qualification run on 2026-09-13 loaded the exact branch file and executed the same fixture set: 8/8 primary classifications PASS; four representative repair routes returned non-empty actions + verification and remained `mutation_allowed=false`.

## Deliberate limits
- No automatic provider/plugin mutation.
- No production broker integration yet.
- No autonomous WorkItem creation.
- No learned rule writes yet.
- No assumption that documentation overrides repeated ND runtime evidence.

Next increments are governed by the durable True Doctor development plan and field evidence.
