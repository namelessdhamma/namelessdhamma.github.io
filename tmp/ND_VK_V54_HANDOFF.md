# ND VK V54 handoff

Status: PREDEVELOPMENT CANDIDATE. ND Automation Agent owns orchestration.

Prepared implementation:
- `tmp/nd_v54_clean_context_loader.py`
- commit `1100daf8b570322ccaebf391e11002ff4388e854`
- branch `qualify/vk-v54-clean-context`
- Dockerfile commit `6fab340a3e106da26b8e42baeddc72a161aa3f5a`

Current production at handoff:
- Railway service `nd-qstash-control-v2` (`7c280018-9102-4357-9965-4a4f88eee93e`)
- deployment `b40a76dc-8fbb-4f6e-ae72-04064157dbd4`
- still V53, not V54.

Verified root cause: legacy V36 converts external research to deep; legacy V13 then injects ND context into unrelated general research. On web failure the legacy path injects `verified=false` text into the prompt. Old global read-only prompt also conflicts with bounded Father Workspace writes.

Next Agent WorkItem: deploy and qualify V54 using the safest current native route. Do not rediscover/rewrite V54 unless fresh evidence finds a defect. Verify startup/health/VK_READY, no ND-context leakage in general research, current-date web evidence/fallback, Research save read-back, literary/ND context isolation, and canonical-write DENY before asking for another user VK test.

Fresh runtime/True Memory/Agent evidence supersedes this pointer; mark it SUPERSEDED rather than restarting old work.