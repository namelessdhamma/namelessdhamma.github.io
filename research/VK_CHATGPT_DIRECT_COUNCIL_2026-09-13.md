# VK ↔ ChatGPT Direct Council — 2026-09-13

Status: RESEARCH HANDOFF / IMPLEMENTATION DIRECTION / NOT PRODUCTION AUTHORITY
Branch: qualify/vk-transport-council

## Objective
Determine whether father can communicate from VK with the same OpenAI intelligence/tool fabric represented by the user's current ChatGPT environment, minimizing bespoke model routers and treating VK as the only hard interface constraint.

## Council verdict

### Core distinction
1. **Literal current ChatGPT UI thread**: no public OpenAI interface was found that allows an arbitrary external VK event or MCP server to inject a user message into this exact existing ChatGPT conversation and trigger a model turn. ChatGPT MCP/apps are ChatGPT-as-client integrations: ChatGPT calls tools/resources exposed by remote MCP servers. They do not, by themselves, make an existing ChatGPT thread an externally invokable webhook target.
2. **Same OpenAI model/intelligence family + same tool fabric**: viable today. OpenAI Responses API supports GPT-5.6 Sol, built-in web search, file search, MCP tools, custom functions/tools, persistent Conversations, context management/compaction, background responses, and other agentic capabilities. This is the closest robust engineering equivalent to "this ChatGPT in VK".
3. **Same ND context/plugins**: not automatic. ChatGPT product memory, thread state, and account-side plugins are product-layer state. For VK runtime they must be represented through explicit durable context + the same underlying MCP/API backends. True Memory is therefore an optional synchronization layer, not a prerequisite for the first useful father assistant.

## Evidence-based findings

### OpenAI Apps / MCP
- ChatGPT Apps SDK is built on MCP and lets ChatGPT connect to external tools/data and backend logic.
- Full MCP support allows ChatGPT to take actions in tools, but the documented interaction direction is ChatGPT invoking connected apps/tools.
- Remote MCP is therefore suitable for VK send/read/control tools, but does not itself prove inbound external-event initiation of an existing ChatGPT UI conversation.

### Responses + Conversations
- `POST /responses` accepts a `conversation` id; conversation items are prepended and new input/output items are automatically added back to the same conversation.
- Responses supports built-in web search and MCP tools in the same turn.
- Persistent `Conversation` objects are provider-side state and are suitable for one long-lived father dialogue without requiring him to create or manage chats.
- Context management/compaction is supported, avoiding unbounded transcript replay.

### Model choice
- `gpt-5.6-sol` is the flagship GPT-5.6 model; it supports web search, file search, MCP, code interpreter, computer use, tool search, skills, and other tools through Responses.
- `chat-latest` points to the latest Instant model used in ChatGPT, but OpenAI explicitly recommends production API usage on production model families rather than relying on this rolling alias.
- `gpt-6-astra` is currently OpenAI's most capable API model, but is more expensive than GPT-5.6 Sol and is not required for the initial father assistant.

### Billing
- ChatGPT subscription billing and API billing are separate. A Plus/Pro seat cannot be assumed to provide API quota. API use needs Platform billing/credits separately.

## Recommended architecture

### Stage 1 — Minimum useful father assistant (highest priority)

VK event
→ minimal reliable transport (Callback API or Long Poll; runtime optional)
→ one durable OpenAI `Conversation` per father VK identity
→ `gpt-5.6-sol` via Responses API
→ built-in `web_search` available by default for current-information requests
→ concise Russian response
→ VK send

No ND dependency. No custom multi-model router required. No Railway requirement.

Required behavior:
- Current-info requests use live web search and cite/source URLs or fail transparently.
- General questions answer directly.
- Conversation state survives process restart through OpenAI Conversation id + small local mapping `{vk_user_id -> conversation_id}`.
- If the current transport fails, transport can be replaced without changing intelligence state.

### Stage 2 — Reliability and bounded continuity
- Idempotency on VK event/message id.
- Retry/circuit breaker for VK send and OpenAI response calls.
- Conversation compaction/context management.
- Minimal user profile/instructions for Russian nontechnical style.
- Optional model fallback only for availability/cost, not as the semantic core.

### Stage 3 — ND equivalence expansion
Attach the same underlying ND capabilities through MCP/API:
- True Memory context endpoint / semantic recovery
- Drive / GitHub / Yandex read paths
- bounded Father Workspace writes
- NotebookLM where server-side bridge is qualified
- other ND tools/plugins as explicit MCP/function backends

This stage makes the VK assistant progressively resemble the user's known ND ChatGPT environment, but it is intentionally not a blocker for Stage 1.

## Alternatives

### A. Literal browser automation of ChatGPT UI
REJECT as primary.
Reason: possible in principle through browser/computer automation, but fragile, session-sensitive, UI-change-sensitive, hard to secure, hard to guarantee message routing to the correct thread, and unnecessary because the same production model/tool stack is available through API.

### B. Custom free multi-model router as primary
REVISE / fallback only.
Useful for zero-cost fallback and experimentation, but not preferred if the goal is "the ND/ChatGPT I know" and paid OpenAI API is acceptable.

### C. Railway as mandatory runtime
REJECT.
Transport/runtime is replaceable. Use only if live evidence shows it is the simplest reliable host.

### D. MCP-only transport assumption
REJECT as unproven.
MCP is excellent for exposing VK operations and ND tools, but inbound father message initiation still needs an event source (Callback/Long Poll/custom MCP polling bridge) unless a concrete MCP server proves server-initiated delivery semantics.

## Implementation frontier
1. Build a minimal VK↔OpenAI E2E prototype independent of the old V53 semantics.
2. Use one persistent OpenAI Conversation for the user-side test identity first.
3. Enable built-in web search; test: "Исследуй, что нового произошло в OpenAI за последние 7 дней, покажи источники".
4. Require source-backed fresh answer, no ND/GRC scope contamination, clean Russian plain text.
5. Test restart recovery and follow-up continuity.
6. Only after PASS, repeat with father ID 452972559.
7. After father can already use it, progressively attach ND memory/tools.

## Human gate
Only API billing/key authorization or VK-side callback confirmation should require user involvement. Do not ask father to configure anything.

## Final research position
The best currently supported interpretation of "connect this ChatGPT to VK" is not to tunnel into the literal existing ChatGPT UI thread, but to instantiate the same/stronger OpenAI production intelligence through Responses + Conversations and reconnect the same tool/data fabric through MCP/API. This preserves model quality, web access, long-lived dialogue, provider-managed conversation state, and incremental ND integration while removing Railway and bespoke router architecture from the critical path.
