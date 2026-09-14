"""Isolated qualification harness for ND VK Father V15 context.

This module does not send VK messages or mutate production. It composes two already-bounded
sources: per-user Father Workspace conversation history and governed V7 ND context.
"""
import json
from nd_vk_father_context_adapter_v15 import hydrate_user, read_nd_context

MAX_ENVELOPE_CHARS = 32000
MAX_CONVERSATION_CHARS = 20000
MAX_ND_CHARS = 10000


def _clip_messages(messages, max_chars=MAX_CONVERSATION_CHARS):
    out=[]
    used=0
    for m in reversed(list(messages or [])):
        if not isinstance(m, dict):
            continue
        role=str(m.get('role') or '')
        content=str(m.get('content') or '')
        if role not in ('user','assistant') or not content:
            continue
        room=max_chars-used
        if room<=0:
            break
        clipped=content[-room:]
        out.append({'role':role,'content':clipped})
        used += len(clipped)
    out.reverse()
    return out


def build_context_envelope(uid, *, nd_query='ND current architecture and relevant project context'):
    """Build a bounded, provenance-carrying context envelope for an isolated response harness."""
    history=_clip_messages(hydrate_user(uid, max_turns=10, max_chars=MAX_CONVERSATION_CHARS))
    nd=read_nd_context(query=nd_query, max_chars=MAX_ND_CHARS)
    nd_text=str(nd.get('text') or '')[:MAX_ND_CHARS]
    sources=[]
    for s in (nd.get('sources') or [])[:20]:
        if not isinstance(s,dict):
            continue
        authority=str(s.get('authority') or '').upper()
        if authority not in ('AUTHORITATIVE','CANONICAL'):
            continue
        sources.append({
            'source_ref':str(s.get('source_ref') or '')[:500],
            'title':str(s.get('title') or '')[:500],
            'authority':authority,
        })
    envelope={
        'schema':'nd.vk_father.context_envelope.v1',
        'uid':str(int(uid)),
        'conversation':history,
        'nd_context':{
            'text':nd_text,
            'sources':sources,
            'statehead_status':nd.get('statehead_status'),
            'registry_version':nd.get('registry_version'),
        },
        'policy':{
            'conversation_authority':'ND_FATHER_WORKSPACE',
            'nd_authority_allowlist':['AUTHORITATIVE','CANONICAL'],
            'non_auth_injection':False,
            'production_mutation':False,
        },
    }
    raw=json.dumps(envelope,ensure_ascii=False,separators=(',',':'))
    if len(raw)>MAX_ENVELOPE_CHARS:
        # ND project context is supporting context; preserve user conversation first.
        overflow=len(raw)-MAX_ENVELOPE_CHARS
        keep=max(0,len(nd_text)-overflow)
        envelope['nd_context']['text']=nd_text[:keep]
    return envelope


def qualification_summary(envelope):
    """Return safe metadata only; never echo conversation/project content."""
    conv=envelope.get('conversation') or []
    nd=envelope.get('nd_context') or {}
    return {
        'schema':envelope.get('schema'),
        'uid':envelope.get('uid'),
        'conversation_turns':len(conv),
        'conversation_chars':sum(len(str(x.get('content') or '')) for x in conv if isinstance(x,dict)),
        'nd_context_chars':len(str(nd.get('text') or '')),
        'nd_sources':len(nd.get('sources') or []),
        'nd_authorities':sorted(set(str(x.get('authority') or '') for x in (nd.get('sources') or []) if isinstance(x,dict))),
        'statehead_status':nd.get('statehead_status'),
        'registry_version':nd.get('registry_version'),
        'non_auth_injection':bool(envelope.get('policy',{}).get('non_auth_injection')),
    }
