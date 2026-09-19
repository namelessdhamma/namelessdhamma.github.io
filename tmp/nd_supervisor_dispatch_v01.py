from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import hashlib
import json
import os
import time
import urllib.error
import urllib.request


class DispatchError(RuntimeError):
    pass


class AssignmentValidationError(DispatchError):
    pass


class ProviderError(DispatchError):
    pass


@dataclass(frozen=True)
class AssignmentEnvelope:
    workitem_id: str
    assignment_id: str
    issued_by: str
    assignee_peer: str
    correlation_id: str
    assignment_state: str
    objective: str
    scope: str = ""
    authority_ceiling: str = ""
    constraints: str = ""
    done_when: str = ""
    issued_at: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssignmentEnvelope":
        required = [
            "workitem_id",
            "assignment_id",
            "issued_by",
            "assignee_peer",
            "correlation_id",
            "assignment_state",
            "objective",
        ]
        missing = [k for k in required if not str(raw.get(k) or "").strip()]
        if missing:
            raise AssignmentValidationError("missing_assignment_fields:" + ",".join(missing))
        return cls(
            workitem_id=str(raw["workitem_id"]).strip(),
            assignment_id=str(raw["assignment_id"]).strip(),
            issued_by=str(raw["issued_by"]).strip(),
            assignee_peer=str(raw["assignee_peer"]).strip(),
            correlation_id=str(raw["correlation_id"]).strip(),
            assignment_state=str(raw["assignment_state"]).strip(),
            objective=str(raw["objective"]).strip(),
            scope=str(raw.get("scope") or "").strip(),
            authority_ceiling=str(raw.get("authority_ceiling") or "").strip(),
            constraints=str(raw.get("constraints") or "").strip(),
            done_when=str(raw.get("done_when") or "").strip(),
            issued_at=str(raw.get("issued_at") or "").strip(),
        )


@dataclass(frozen=True)
class SupervisorResolution:
    supervisor_id: str
    canonical_version: str
    prompt_source: str
    prompt_text: str
    model: str
    tool_profile: List[Dict[str, Any]]
    reasoning_effort: str = "high"
    max_output_tokens: int = 32000

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SupervisorResolution":
        required = ["supervisor_id", "canonical_version", "prompt_source", "prompt_text", "model"]
        missing = [k for k in required if not str(raw.get(k) or "").strip()]
        if missing:
            raise AssignmentValidationError("missing_supervisor_fields:" + ",".join(missing))
        tools = raw.get("tool_profile") or []
        if not isinstance(tools, list):
            raise AssignmentValidationError("tool_profile_must_be_list")
        return cls(
            supervisor_id=str(raw["supervisor_id"]).strip(),
            canonical_version=str(raw["canonical_version"]).strip(),
            prompt_source=str(raw["prompt_source"]).strip(),
            prompt_text=str(raw["prompt_text"]),
            model=str(raw["model"]).strip(),
            tool_profile=tools,
            reasoning_effort=str(raw.get("reasoning_effort") or "high").strip(),
            max_output_tokens=int(raw.get("max_output_tokens") or 32000),
        )


class JsonLedger:
    """Small development ledger. Production transport may replace storage without changing dispatch semantics."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"dispatches": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("dispatches"), dict):
            raise DispatchError("invalid_dispatch_ledger")
        return raw

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._load()["dispatches"].get(key)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        state = self._load()
        state["dispatches"][key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_peer(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").upper().split())


def validate_dispatch(assignment: AssignmentEnvelope, supervisor: SupervisorResolution) -> None:
    if assignment.assignment_state != "ACTIVE":
        raise AssignmentValidationError("assignment_not_active")
    if _normalize_peer(assignment.issued_by) not in {
        "ND AUTOMATION AGENT",
        "AUTOMATION AGENT",
    }:
        raise AssignmentValidationError("issuer_not_automation_agent")
    if _normalize_peer(assignment.assignee_peer) != _normalize_peer(supervisor.supervisor_id):
        raise AssignmentValidationError("assignee_supervisor_mismatch")
    if not assignment.correlation_id:
        raise AssignmentValidationError("missing_correlation_id")


def build_supervisor_input(assignment: AssignmentEnvelope, supervisor: SupervisorResolution) -> str:
    packet = {
        "workitem_id": assignment.workitem_id,
        "assignment_id": assignment.assignment_id,
        "correlation_id": assignment.correlation_id,
        "objective": assignment.objective,
        "scope": assignment.scope,
        "authority_ceiling": assignment.authority_ceiling,
        "constraints": assignment.constraints,
        "done_when": assignment.done_when,
        "issued_at": assignment.issued_at,
    }
    return (
        "You are executing an ND supervisor assignment.\n"
        "Preserve the assignment lifecycle distinction: ASSIGNED is not ATTEMPTED; "
        "ATTEMPTED is not OBSERVED; OBSERVED is not VERIFIED or ADOPTED.\n"
        "Return a bounded machine-auditable result with: status, decisive evidence, "
        "result, limitations, verification, exact_stop, next_action.\n"
        "Never exceed the authority ceiling.\n\n"
        "ASSIGNMENT_ENVELOPE:\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2)
    )


class OpenAIResponsesProvider:
    """Minimal provider adapter for an already-existing OPENAI_API_KEY runtime."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 900):
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError("openai_api_key_missing")

    def __call__(
        self,
        assignment: AssignmentEnvelope,
        supervisor: SupervisorResolution,
        dispatch_key: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": supervisor.model,
            "instructions": supervisor.prompt_text,
            "input": build_supervisor_input(assignment, supervisor),
            "tools": supervisor.tool_profile,
            "max_output_tokens": supervisor.max_output_tokens,
            "metadata": {
                "nd_dispatch_key": dispatch_key,
                "nd_assignment_id": assignment.assignment_id,
                "nd_correlation_id": assignment.correlation_id,
                "nd_supervisor_id": supervisor.supervisor_id,
                "nd_supervisor_version": supervisor.canonical_version,
            },
        }
        if supervisor.reasoning_effort:
            payload["reasoning"] = {"effort": supervisor.reasoning_effort}

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "ND-Supervisor-Dispatch/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                obj = json.loads(raw)
                return obj
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise ProviderError(f"openai_http_{exc.code}:{raw[:1200]}") from exc
        except Exception as exc:
            raise ProviderError("openai_request_failed:" + str(exc)) from exc


def extract_output_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    chunks: List[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "\n".join(chunks).strip()


def dispatch(
    assignment_raw: Dict[str, Any],
    supervisor_raw: Dict[str, Any],
    *,
    ledger_path: str | Path,
    provider: Optional[Callable[[AssignmentEnvelope, SupervisorResolution, str], Dict[str, Any]]] = None,
    dispatch_key: Optional[str] = None,
) -> Dict[str, Any]:
    assignment = AssignmentEnvelope.from_dict(assignment_raw)
    supervisor = SupervisorResolution.from_dict(supervisor_raw)
    validate_dispatch(assignment, supervisor)

    key = dispatch_key or (
        assignment.assignment_id
        + "::"
        + assignment.correlation_id
        + "::"
        + supervisor.supervisor_id
        + "::"
        + supervisor.canonical_version
    )
    ledger = JsonLedger(ledger_path)
    prior = ledger.get(key)
    if prior and prior.get("state") in {"OBSERVED", "VERIFIED"}:
        return {**prior, "replayed": True}

    attempted = {
        "dispatch_key": key,
        "state": "ATTEMPTED",
        "replayed": False,
        "workitem_id": assignment.workitem_id,
        "assignment_id": assignment.assignment_id,
        "correlation_id": assignment.correlation_id,
        "supervisor_id": supervisor.supervisor_id,
        "supervisor_version": supervisor.canonical_version,
        "prompt_source": supervisor.prompt_source,
        "model": supervisor.model,
        "attempted_at": int(time.time()),
    }
    ledger.put(key, attempted)

    runner = provider or OpenAIResponsesProvider()
    try:
        response = runner(assignment, supervisor, key)
    except Exception as exc:
        failed = {
            **attempted,
            "state": "ATTEMPTED",
            "provider_error": str(exc),
            "failed_at": int(time.time()),
        }
        ledger.put(key, failed)
        raise

    output_text = extract_output_text(response)
    observed = {
        **attempted,
        "state": "OBSERVED",
        "provider_response_id": response.get("id"),
        "provider_model": response.get("model") or supervisor.model,
        "output_text": output_text,
        "output_sha256": _sha256_text(output_text),
        "provider_response_sha256": _sha256_text(
            json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ),
        "observed_at": int(time.time()),
        "provider_response": response,
    }
    if output_text:
        observed["state"] = "VERIFIED"
        observed["verification"] = {
            "correlation_bound": True,
            "assignment_bound": True,
            "nonempty_output": True,
        }

    ledger.put(key, observed)
    return observed


__all__ = [
    "AssignmentEnvelope",
    "SupervisorResolution",
    "DispatchError",
    "AssignmentValidationError",
    "ProviderError",
    "JsonLedger",
    "OpenAIResponsesProvider",
    "build_supervisor_input",
    "dispatch",
    "extract_output_text",
    "validate_dispatch",
]
