"""ND VK Father bounded conversation-context core.

Qualification candidate. Provider-agnostic. Canonical ND/artifact truth is never stored here;
source-aware derived state is assembled into bounded ContextPackets. Durable backing must be
outside process RAM (Father Workspace Shared Notes ledger or another True-Memory-approved store).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib, json, re, uuid
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "ND_VK_CONTEXT_V1"
DEFAULT_PACKET_BUDGET = 10000
DEEP_PACKET_BUDGET = 18000
FAST_PACKET_BUDGET = 7000
LAYER_LIMITS = {
    "recent_verbatim": 1800,
    "working_state": 1800,
    "artifact_state": 2200,
    "episodic": 900,
    "semantic": 500,
    "authority_evidence": 2200,
    "provenance_conflicts": 600,
}
RAW_TURN_MAX_PER_THREAD = 12
RAW_TURN_CHAR_MAX = 18000


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def est_tokens(value: Any) -> int:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return max(1, (len(s) + 3) // 4)


def clip(value: Any, max_tokens: int) -> Any:
    if est_tokens(value) <= max_tokens:
        return value
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return s[: max_tokens * 4] + "…[bounded]"


def _thread(kind: str, key: str, label: str) -> Dict[str, Any]:
    now = utcnow()
    return {
        "thread_id": f"{kind}:{key}", "kind": kind, "label": label,
        "created_at": now, "last_active_at": now, "recent_turns": [],
        "working_state": {"objective": "", "status": "ACTIVE", "unresolved": [], "constraints": [], "source_refs": []},
        "episodes": [], "artifact": None, "summary": None, "summary_generation": 0,
    }


def new_state(user_id: str) -> Dict[str, Any]:
    return {"schema": SCHEMA, "user_id": str(user_id), "generation": 0,
            "active_thread_id": "general:main", "thread_stack": ["general:main"],
            "threads": {"general:main": _thread("general", "main", "Общий разговор")},
            "semantic_memory": [], "updated_at": utcnow()}


STORY_RE = re.compile(r"(?:рассказ(?:у|а|ом|е)?|story)\s*[№#:]?\s*(\d+)", re.I)
RESEARCH_RE = re.compile(r"(?:исследуй|исследование|research)\s+(?:тему\s+)?(.{3,80})", re.I)


def resolve_thread(text: str, state: Dict[str, Any]) -> Tuple[str, float, str]:
    """Resolve a logical thread. Explicit artifact/topic cues outrank current activity.
    Confidence < .72 means the caller should clarify instead of guessing.
    """
    t = (text or "").strip()
    m = STORY_RE.search(t)
    if m:
        return f"story:{m.group(1)}", .99, "explicit_story"
    m = RESEARCH_RE.search(t)
    if m:
        topic = re.sub(r"\s+", " ", m.group(1).strip(" .?!,:;—-"))[:60]
        key = hashlib.sha256(topic.casefold().encode()).hexdigest()[:12]
        return f"research:{key}", .95, topic
    low = t.casefold()
    if any(x in low for x in ("что сейчас происходит в nd", "состояние nd", "текущий nd")):
        return "nd:current", .96, "nd_current"
    if any(x in low for x in ("погода", "новости", "сейчас в интернете", "свежие источники")):
        return "web:transient", .9, "transient_web"
    active = state.get("active_thread_id") or "general:main"
    # Explicit ambiguous anaphora must be handled before generic follow-up prefixes.
    # This prevents confident guessing from unrelated history.
    if low in {"сделай как в прошлый раз", "как в прошлый раз", "верни как было"}:
        return active, .66, "ambiguous_anaphora"
    if re.match(r"^(нет[, ]|да[, ]|верни|оставь|сделай|а теперь|ещ[её]|предыдущ)", low):
        return active, .88, "followup_active"
    return active, .78, "continuity_default"


def ensure_thread(state: Dict[str, Any], thread_id: str, reason: str = "") -> Dict[str, Any]:
    if thread_id in state["threads"]:
        return state["threads"][thread_id]
    kind, key = thread_id.split(":", 1)
    labels = {"story": f"Рассказ {key}", "research": reason or "Исследование", "nd": "Текущее ND", "web": "Временный веб-вопрос"}
    state["threads"][thread_id] = _thread(kind, key, labels.get(kind, thread_id))
    return state["threads"][thread_id]


def add_turn(state: Dict[str, Any], role: str, text: str, event_id: Optional[str] = None,
             thread_id: Optional[str] = None) -> Dict[str, Any]:
    if thread_id is None:
        thread_id, conf, reason = resolve_thread(text, state)
        if conf < .72:
            return {"state": state, "needs_clarification": True, "confidence": conf, "reason": reason}
    th = ensure_thread(state, thread_id)
    item = {"event_id": event_id or uuid.uuid4().hex, "role": role, "text": str(text), "at": utcnow()}
    th["recent_turns"].append(item)
    while len(th["recent_turns"]) > RAW_TURN_MAX_PER_THREAD or sum(len(x["text"]) for x in th["recent_turns"]) > RAW_TURN_CHAR_MAX:
        old = th["recent_turns"].pop(0)
        th["episodes"].append({"kind": "turn_compacted", "at": old["at"], "source_event_id": old["event_id"],
                               "gist": old["text"][:500], "derived": True})
    th["last_active_at"] = utcnow()
    if th["kind"] != "web":
        prev = state.get("active_thread_id")
        state["active_thread_id"] = thread_id
        if prev != thread_id:
            stack = [x for x in state.get("thread_stack", []) if x != thread_id]
            state["thread_stack"] = (stack + [thread_id])[-8:]
    state["generation"] += 1; state["updated_at"] = utcnow()
    return {"state": state, "needs_clarification": False, "thread_id": thread_id}


def set_working_state(state: Dict[str, Any], thread_id: str, *, objective: Optional[str] = None,
                      unresolved: Optional[List[str]] = None, constraints: Optional[List[str]] = None,
                      source_refs: Optional[List[str]] = None) -> None:
    w = ensure_thread(state, thread_id)["working_state"]
    if objective is not None: w["objective"] = objective
    if unresolved is not None: w["unresolved"] = unresolved[:30]
    if constraints is not None: w["constraints"] = constraints[:30]
    if source_refs is not None: w["source_refs"] = source_refs[:30]
    state["generation"] += 1; state["updated_at"] = utcnow()


def init_artifact(state: Dict[str, Any], thread_id: str, artifact_id: str, content: str,
                  source_ref: str, voice_constraints: Optional[List[str]] = None) -> str:
    th = ensure_thread(state, thread_id)
    vid = "v1"
    th["artifact"] = {"artifact_id": artifact_id, "source_ref": source_ref, "current_version": vid,
                      "accepted_version": vid, "versions": [{"version_id": vid, "parent": None, "status": "BASELINE",
                      "content": content, "hash": hashlib.sha256(content.encode()).hexdigest(), "at": utcnow()}],
                      "rejected": [], "voice_constraints": voice_constraints or [], "author_intent": [], "unresolved_decisions": []}
    return vid


def propose_version(state: Dict[str, Any], thread_id: str, content: str, status: str = "PROPOSED") -> str:
    a = ensure_thread(state, thread_id).get("artifact")
    if not a: raise ValueError("artifact state required")
    parent = a["current_version"]
    vid = f"v{len(a['versions'])+1}"
    a["versions"].append({"version_id": vid, "parent": parent, "status": status, "content": content,
                          "hash": hashlib.sha256(content.encode()).hexdigest(), "at": utcnow()})
    a["current_version"] = vid
    return vid


def accept_version(state: Dict[str, Any], thread_id: str, version_id: str) -> None:
    a = ensure_thread(state, thread_id)["artifact"]
    v = next(x for x in a["versions"] if x["version_id"] == version_id)
    v["status"] = "ACCEPTED"; a["accepted_version"] = version_id; a["current_version"] = version_id


def reject_version(state: Dict[str, Any], thread_id: str, version_id: str) -> None:
    a = ensure_thread(state, thread_id)["artifact"]
    v = next(x for x in a["versions"] if x["version_id"] == version_id)
    v["status"] = "REJECTED"; a["rejected"] = list(dict.fromkeys(a["rejected"] + [version_id]))
    if a["current_version"] == version_id:
        a["current_version"] = v["parent"] or a["accepted_version"]


def previous_version(state: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
    a = ensure_thread(state, thread_id)["artifact"]
    cur = next(x for x in a["versions"] if x["version_id"] == a["current_version"])
    pid = cur.get("parent")
    return next(x for x in a["versions"] if x["version_id"] == pid) if pid else cur


def validate_summary(state: Dict[str, Any], thread_id: str, summary: str, source_refs: List[str], generation: int) -> bool:
    th = ensure_thread(state, thread_id)
    # Summary is derived and cannot carry artifact-version authority. At least one source ref is required.
    if not source_refs or generation < th.get("summary_generation", 0): return False
    th["summary"] = {"text": summary[:8000], "source_refs": source_refs[:30], "derived": True, "validated_at": utcnow()}
    th["summary_generation"] = generation
    return True


def retrieve_threads(state: Dict[str, Any], query: str, limit: int = 3) -> List[Dict[str, Any]]:
    q = set(re.findall(r"[\wа-яё]+", query.casefold()))
    scored = []
    for th in state["threads"].values():
        hay = " ".join([th.get("label", ""), th.get("working_state", {}).get("objective", ""),
                        (th.get("summary") or {}).get("text", "")]).casefold()
        toks = set(re.findall(r"[\wа-яё]+", hay))
        score = len(q & toks) * 3 + (4 if th["thread_id"] == state.get("active_thread_id") else 0)
        if score: scored.append((score, th["last_active_at"], th))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in scored[:limit]]


def build_context_packet(state: Dict[str, Any], query: str, *, mode: str = "default",
                         authority_evidence: Optional[List[Dict[str, Any]]] = None,
                         semantic: Optional[List[Dict[str, Any]]] = None,
                         conflicts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    budget = {"fast": FAST_PACKET_BUDGET, "deep": DEEP_PACKET_BUDGET}.get(mode, DEFAULT_PACKET_BUDGET)
    tid, conf, reason = resolve_thread(query, state)
    if conf < .72:
        return {"schema": "ND_VK_CONTEXT_PACKET_V1", "needs_clarification": True, "reason": reason,
                "thread_id": state.get("active_thread_id"), "budget": budget, "layers": {}}
    th = ensure_thread(state, tid, reason)
    layers = {
        "recent_verbatim": th["recent_turns"],
        "working_state": th["working_state"],
        "artifact_state": th.get("artifact"),
        "episodic": th.get("episodes", [])[-12:],
        "semantic": semantic or state.get("semantic_memory", []),
        "authority_evidence": authority_evidence or [],
        "provenance_conflicts": conflicts or [],
    }
    bounded = {k: clip(v, LAYER_LIMITS[k]) for k, v in layers.items() if v not in (None, [], {}, "")}
    used = sum(est_tokens(v) for v in bounded.values())
    # Fail closed on budget drift. Lower-priority layers compress first; exact artifact/authority remain preferred.
    order = ["semantic", "episodic", "recent_verbatim", "working_state", "provenance_conflicts", "artifact_state", "authority_evidence"]
    i = 0
    while used > budget and i < len(order):
        k = order[i]; i += 1
        if k in bounded:
            bounded[k] = clip(bounded[k], max(80, est_tokens(bounded[k]) // 2))
            used = sum(est_tokens(v) for v in bounded.values())
    return {"schema": "ND_VK_CONTEXT_PACKET_V1", "thread_id": tid, "resolver_confidence": conf,
            "budget": budget, "estimated_tokens": used, "layers": bounded,
            "authority_rule": "fresh_authority_and_exact_artifact_state_override_derived_memory",
            "provider_agnostic": True, "generated_at": utcnow()}


def merge_fresh_authority(memory_value: Any, memory_source: str, fresh_value: Any, fresh_source: str) -> Dict[str, Any]:
    return {"value": fresh_value, "source_ref": fresh_source, "superseded_memory": {"value": memory_value,
            "source_ref": memory_source, "status": "STALE_REPAIRED"}, "rule": "FRESH_AUTHORITY_WINS"}
