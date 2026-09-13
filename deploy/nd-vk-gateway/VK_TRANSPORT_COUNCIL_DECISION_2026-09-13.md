# VK Transport Council Decision — 2026-09-13

Status: QUALIFICATION DIRECTION / NOT PRODUCTION

## Invariant
The father uses VK. Everything else in transport/runtime is replaceable.

## Goal
Provide a reliable Russian-speaking ND assistant in one ordinary VK conversation while preserving existing ND authority boundaries and the bounded Father Workspace.

## Decision
- Railway is no longer architectural authority; it is one optional runtime/fallback.
- MCP is useful as an optional VK tool/control adapter, but is not assumed to solve inbound message delivery by itself.
- Preserve the provider-agnostic ND assistant core: bounded context/memory, intent routing, current-web, books, ND reads, Father Workspace, authority guards, and swappable intelligence.
- Qualify multiple thin VK transports/runtimes and promote only by end-to-end evidence.

## Target shape
VK transport -> normalized FatherMessage -> ND Father Assistant Core -> normalized FatherReply -> VK transport.

The core must not depend on Railway, Vercel, Callback API, Long Poll, MCP, or any specific model provider.

## Candidates
A. VK Callback API + small HTTPS runtime. Highest priority.
B. VK Bots Long Poll + minimal worker. High priority fallback/competitor.
C. VK MCP over Streamable HTTP as typed read/send/control adapter. Medium priority; not sole transport unless inbound events are proven.
D. Repaired Railway immutable runtime. Fallback only.
E. Paid strong-model intelligence behind the same transport if free routes fail quality/reliability and spend is separately authorized.

## Qualification
Require: inbound event normalization; sender allowlist; idempotency; ordinary Russian Q&A; current-web with real sources/dates; 20+ turn story continuity; story/web/story switching; Father Workspace research and draft save/read-back; canonical mutation denial; restart/provider-switch recovery; retry without duplicate replies; clean VK plaintext UX.

## Immediate work
1. Put a transport-neutral FatherMessage/FatherReply interface around the current context-memory candidate.
2. Implement Callback API candidate first.
3. In parallel test Long Poll and VK MCP token/tool behavior.
4. Keep current production only as rollback until a candidate passes server-side E2E.
5. Then run one user VK smoke test; involve father only after that passes.

## Verdict
RETAIN: VK UX, bounded context/memory, Father Workspace, authority guards, intelligence-router work.
REVISE: transport/runtime and model-provider assumptions.
REJECT: infrastructure-first optimization and wrapper-on-wrapper repair as the default path.
