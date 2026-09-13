# ND VK Father — Conversation Context / Memory Decision

Status: **QUALIFICATION CANDIDATE / NOT PRODUCTION**
Date: 2026-09-13
Branch: `qualify/vk-context-memory`

## Decision

**RETAIN:** one ordinary VK chat for the father, automatically partitioned into logical threads; bounded recent verbatim turns; durable provider-agnostic working state; exact artifact/version state; selective episodic/semantic retrieval; fresh authority/evidence overlay; explicit ContextPacket budget; post-turn state delta.

**REVISE:** rolling-summary-only designs. Summaries remain derived navigation aids with source refs and monotonic generation. They never own manuscript versions, ND facts, current-web facts, or acceptance/rejection history.

**REJECT:** replaying the entire VK transcript; one global summary for all topics; process-RAM-only memory; vector similarity as sole retrieval; provider-native memory as authority; timestamp/majority-based conflict resolution; model-generated memory overriding fresh ND/Yandex/web/artifact sources.

## Evidence basis

This design aligns with current True Memory: durable logical objects rather than chat continuity; bounded/source-aware retrieval; fresh authority outranks summaries; projection/state recovery is provider-independent. It also preserves True Writer semantics: Preserve Set/baseline before mutation, incremental commits, rollback, authorial intent and literary constraints. External research converges on bounded short-term state + durable long-term state, compaction, event/temporal structure, retrieval and explicit conflict handling rather than unbounded history.

Research references used for this decision:
- OpenAI Agents API (2026-09): automatic compaction for long sessions; external/stateful harnesses rather than assuming one finite context.
- Anthropic long-running agent harness guidance (2025-11, 2026-04): bridge sessions with durable artifacts/checkpoints and decouple state from ephemeral compute.
- Google ADK session contract: sessions/events/state deltas are separate storage concepts; in-memory continuity is not durable by itself.
- LangGraph production memory docs (2026): trim/summarize bounded short-term history; separate short-term thread state from long-term namespaced memory.
- TiMem (2026): temporal-hierarchical consolidation improves long-horizon recall while reducing recalled context.
- EMem/event-centric baseline (2025): source-attributed event-like memory can match/beat stronger baselines with shorter QA context.
- MemConflict (2026): semantically similar/stale/conflicting memories require query-conditioned validity/conflict handling, not similarity alone.

## Logical thread lifecycle

Physical VK chat is never exposed as a memory-management UI. Internally:

1. Resolver examines explicit artifact/topic/entity cues first.
2. Stable logical IDs: `general:main`, `story:<id>`, `research:<topic-hash>`, `nd:current`.
3. `web:transient` is a side-conversation and does **not** displace active literary/research work.
4. Explicit cues (`рассказ 16`, `вернёмся к...`) outrank current thread.
5. Short anaphoric follow-ups (`нет, предыдущий вариант...`) inherit active thread when confidence is high.
6. Ambiguous phrases (`сделай как в прошлый раз`) below confidence 0.72 produce one minimal clarification; irrelevant history is not guessed in.
7. Recently active stable threads are retained durably; inactive raw turns may expire after compaction, but working/artifact state and source-attributed episodes remain.

## ContextPacket v1

Hard default packet budget: **10,000 estimated tokens** excluding fixed system policy and the current user turn.
`/быстро`: **7,000**. `/глубоко`: **18,000**. Model context size never increases these budgets automatically.

Per-layer maxima:

| Layer | Max tokens | Rule |
|---|---:|---|
| recent_verbatim | 1,800 | selected logical thread only; max 12 turns / 18k chars |
| working_state | 1,800 | objective, unresolved decisions, constraints, source refs |
| artifact_state | 2,200 | exact active/accepted/previous/rejected version metadata and needed excerpts |
| episodic | 900 | source-attributed decisions/events, relevance+recency filtered |
| semantic | 500 | explicit stable user/work preferences only; no inferred transient claims |
| authority_evidence | 2,200 | fresh ND/Yandex/web/provider evidence as required |
| provenance_conflicts | 600 | conflicts, freshness, stale/repaired markers, source refs |

If the packet exceeds its mode budget, compress in this order: semantic → episodic → recent verbatim → working-state prose → conflict prose. Exact artifact/version state and fresh authority/evidence have highest preservation priority. If required authority evidence itself cannot fit safely, fail/clarify rather than silently discard it.

## State schema

Per user:
- schema/generation/updated_at;
- active stable thread + bounded thread stack;
- logical threads.

Per logical thread:
- stable `thread_id`, kind/label, last-active;
- bounded recent verbatim turns with VK event IDs;
- `working_state`: objective/status/unresolved/constraints/source_refs;
- derived summary with generation + source refs + validation timestamp;
- source-attributed episodic events;
- optional artifact state.

Artifact state (literary):
- artifact/source reference;
- immutable version records with parent pointer + hash;
- exact `current_version`, `accepted_version`, rejected version IDs;
- author intent, voice constraints, unresolved decisions;
- rollback via explicit parent/version, never fuzzy summary.

## Compaction and summary rules

- Raw selected-thread window: max 12 turns or 18,000 chars. Overflow becomes source-attributed episodic material; full history is never replayed.
- Summaries are generated only after threshold/closure and are `DERIVED/NON_AUTHORITATIVE`.
- Summary update must include source refs and monotonically increasing generation. A summary cannot change artifact versions or authority facts.
- Literary summaries are checked against exact current artifact/version metadata; text-critical accepted/rejected wording remains in artifact version state, not summary.
- Current ND/web/model/provider facts are VERIFY_AT_USE and refreshed when the request needs currentness.
- Raw VK messages may be retained only as long as needed for bounded continuity/debugging. Long-term retention should prefer compact source-attributed events/deltas for privacy and token/storage economy.

## Retrieval

Candidate state is ranked by:
1. explicit artifact/thread/entity cue;
2. currently active stable work;
3. source/artifact identity match;
4. recency;
5. lexical/semantic relevance;
6. completion/status applicability.

Similarity never overrides a more explicit thread/artifact cue. Retrieval returns a small set (normally <=3 logical threads) and packet assembly normally selects exactly one work thread plus necessary authority/evidence.

## Conflict / authority

Priority for consequential claims:
1. fresh canonical/authoritative source or exact artifact state;
2. verified current Father Workspace artifact/version state;
3. source-attributed working/episodic state;
4. derived summary;
5. old raw conversational inference.

Fresh authority conflict marks the older memory `STALE_REPAIRED`; it is not merely hidden. Missing providers create `PENDING_CURRENTNESS/UNKNOWN`, never inferred deletion. Newest timestamp, majority vote, and model confidence alone are not authority rules.

## Storage placement

- Canonical ND, Registry/StateHead, GitHub/Obsidian authority and Yandex canonical books remain read-only from VK.
- VK conversation memory is **non-canonical operational state**.
- Durable production placement should use the existing bounded Father Workspace / Shared Notes ledger via Safe Tool Broker, or another True-Memory-approved durable store with the same exact-ID/ancestry, provenance, idempotency, read-back and concurrency protections.
- Process RAM may cache packets but is disposable.
- No provider-specific memory API is authoritative; serialized state is plain JSON/provider-agnostic.
- Literary derived drafts remain in Book Drafts; research outputs remain in Research; handoffs remain Inbox; privileged ND→Outbox remains separate. Context state stores refs to those artifacts, not copies that can silently diverge.

## Failure behavior

- resolver confidence < 0.72 → minimal Russian clarification;
- missing/stale authority required for current claim → fetch or transparently report unavailable;
- stale summary vs fresh source → fresh source wins, stale state repaired;
- missing durable state after restart → reconstruct from durable refs; never pretend continuity from RAM;
- packet budget pressure → deterministic bounded compression; never append whole transcript;
- unknown version/undo target → refuse fuzzy mutation and request minimal disambiguation;
- storage/read-back failure → do not claim state was saved.

## Qualification gate A–I

Implemented deterministic regression coverage in `test_context_memory.py`:
A. 20+ Story 16 turns stay bounded while continuity state persists.
B. Story → transient web → Story return without contamination.
C. Interleaved stories/research resolve correct logical thread.
D. previous/accepted/rejected/undo semantics use explicit versions.
E. fresh authority supersedes stale memory and marks repair.
F. 500-turn synthetic history remains inside hard packet budget.
G. ambiguous anaphora yields minimal clarification instead of irrelevant-history guess.
H. JSON restart/provider switch recovers active work without process RAM/transcript dependency.
I. father-facing sample remains ordinary Russian without memory jargon.
Plus: summary provenance and monotonic-generation validation.

## Remaining production gate

The core is intentionally not yet wired into production V53. Before production adoption:
1. CI/regression PASS on this branch;
2. bind state persistence to the bounded Shared Notes ledger (or equivalent approved durable adapter) with idempotent read-back;
3. integrate resolver/ContextPacket assembly into gateway request path while preserving current routing and write boundaries;
4. server-side replay A–I against the integrated gateway;
5. True Version review because this changes production context/state architecture;
6. only then perform the next user VK retest.

This decision is resumable without this automation transcript.