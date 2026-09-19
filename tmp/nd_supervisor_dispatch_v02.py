from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from nd_supervisor_dispatch_v01 import (
    AssignmentEnvelope,
    SupervisorResolution,
    AssignmentValidationError,
    DispatchError,
    JsonLedger,
    ProviderError,
    build_supervisor_input,
    extract_output_text,
    validate_dispatch,
)


TERMINAL_PROVIDER_STATUSES = {"completed", "failed", "cancelled", "incomplete"}
ACTIVE_PROVIDER_STATUSES = {"queued", "in_progress"}


def default_dispatch_key(a: AssignmentEnvelope, s: SupervisorResolution) -> str:
    return (
        a.assignment_id
        + "::"
        + a.correlation_id
        + "::"
        + s.supervisor_id
        + "::"
        + s.canonical_version
    )


class OpenAIBackgroundResponsesProvider:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 120):
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError("openai_api_key_missing")

    def _request(self, method: str, url: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "ND-Supervisor-Dispatch/0.2",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise ProviderError(f"openai_http_{exc.code}:{raw[:1200]}") from exc
        except Exception as exc:
            raise ProviderError("openai_request_failed:" + str(exc)) from exc

    def submit(
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
            "background": True,
            "store": True,
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
        return self._request("POST", self.endpoint, payload)

    def retrieve(self, response_id: str) -> Dict[str, Any]:
        if not response_id:
            raise ProviderError("provider_response_id_required")
        return self._request("GET", self.endpoint + "/" + urllib.parse.quote(response_id, safe=""))

    def cancel(self, response_id: str) -> Dict[str, Any]:
        if not response_id:
            raise ProviderError("provider_response_id_required")
        return self._request(
            "POST",
            self.endpoint + "/" + urllib.parse.quote(response_id, safe="") + "/cancel",
            {},
        )


def _base_record(a: AssignmentEnvelope, s: SupervisorResolution, key: str) -> Dict[str, Any]:
    return {
        "dispatch_key": key,
        "workitem_id": a.workitem_id,
        "assignment_id": a.assignment_id,
        "correlation_id": a.correlation_id,
        "supervisor_id": s.supervisor_id,
        "supervisor_version": s.canonical_version,
        "prompt_source": s.prompt_source,
        "model": s.model,
    }


def submit_dispatch(
    assignment_raw: Dict[str, Any],
    supervisor_raw: Dict[str, Any],
    *,
    ledger_path: str | Path,
    provider: Optional[Any] = None,
    dispatch_key: Optional[str] = None,
) -> Dict[str, Any]:
    assignment = AssignmentEnvelope.from_dict(assignment_raw)
    supervisor = SupervisorResolution.from_dict(supervisor_raw)
    validate_dispatch(assignment, supervisor)

    key = dispatch_key or default_dispatch_key(assignment, supervisor)
    ledger = JsonLedger(ledger_path)
    prior = ledger.get(key)

    # A persisted provider response id is the durable replay boundary.
    # Never create another provider response for the same dispatch key.
    if prior and prior.get("provider_response_id"):
        return {**prior, "replayed": True}

    # If the previous attempt died before returning a provider id, do not blindly
    # retry and risk duplicate side effects. Leave recovery to an explicit repair path.
    if prior and prior.get("state") == "ATTEMPTED":
        return {
            **prior,
            "replayed": True,
            "recovery_required": True,
            "recovery_reason": "attempt_exists_without_provider_response_id",
        }

    attempted = {
        **_base_record(assignment, supervisor, key),
        "state": "ATTEMPTED",
        "provider_status": None,
        "provider_response_id": None,
        "attempted_at": int(time.time()),
        "replayed": False,
    }
    ledger.put(key, attempted)

    runner = provider or OpenAIBackgroundResponsesProvider()
    try:
        response = runner.submit(assignment, supervisor, key)
    except Exception as exc:
        failed = {
            **attempted,
            "provider_error": str(exc),
            "failed_at": int(time.time()),
        }
        ledger.put(key, failed)
        raise

    response_id = str(response.get("id") or "").strip()
    if not response_id:
        ambiguous = {
            **attempted,
            "provider_error": "provider_submit_missing_response_id",
            "provider_submit_response": response,
            "recovery_required": True,
            "failed_at": int(time.time()),
        }
        ledger.put(key, ambiguous)
        raise ProviderError("provider_submit_missing_response_id")

    provider_status = str(response.get("status") or "queued")
    saved = {
        **attempted,
        "provider_response_id": response_id,
        "provider_status": provider_status,
        "submitted_at": int(time.time()),
    }
    ledger.put(key, saved)

    # Some provider calls may already complete before submit returns.
    if provider_status in TERMINAL_PROVIDER_STATUSES:
        return refresh_dispatch(key, ledger_path=ledger_path, provider=runner, provider_response=response)

    return saved


def refresh_dispatch(
    dispatch_key: str,
    *,
    ledger_path: str | Path,
    provider: Optional[Any] = None,
    provider_response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ledger = JsonLedger(ledger_path)
    prior = ledger.get(dispatch_key)
    if not prior:
        raise DispatchError("dispatch_not_found")
    response_id = str(prior.get("provider_response_id") or "").strip()
    if not response_id:
        raise DispatchError("dispatch_has_no_provider_response_id")

    runner = provider or OpenAIBackgroundResponsesProvider()
    response = provider_response or runner.retrieve(response_id)
    status = str(response.get("status") or "").strip() or "unknown"

    updated = {
        **prior,
        "provider_status": status,
        "last_observed_at": int(time.time()),
        "replayed": False,
    }

    if status in ACTIVE_PROVIDER_STATUSES:
        ledger.put(dispatch_key, updated)
        return updated

    # We have now observed a terminal provider state.
    updated["state"] = "OBSERVED"
    updated["provider_response"] = response

    if status == "completed":
        output_text = extract_output_text(response)
        updated["output_text"] = output_text
        if output_text:
            updated["state"] = "VERIFIED"
            updated["verification"] = {
                "correlation_bound": True,
                "assignment_bound": True,
                "provider_response_id_bound": True,
                "nonempty_output": True,
            }
        else:
            updated["verification"] = {
                "correlation_bound": True,
                "assignment_bound": True,
                "provider_response_id_bound": True,
                "nonempty_output": False,
            }
    elif status in {"failed", "cancelled", "incomplete"}:
        updated["terminal_failure"] = True
        updated["provider_error"] = response.get("error") or response.get("incomplete_details") or status

    ledger.put(dispatch_key, updated)
    return updated


def cancel_dispatch(
    dispatch_key: str,
    *,
    ledger_path: str | Path,
    provider: Optional[Any] = None,
) -> Dict[str, Any]:
    ledger = JsonLedger(ledger_path)
    prior = ledger.get(dispatch_key)
    if not prior:
        raise DispatchError("dispatch_not_found")
    response_id = str(prior.get("provider_response_id") or "").strip()
    if not response_id:
        raise DispatchError("dispatch_has_no_provider_response_id")

    if prior.get("provider_status") == "cancelled":
        return {**prior, "replayed": True}

    runner = provider or OpenAIBackgroundResponsesProvider()
    response = runner.cancel(response_id)
    updated = {
        **prior,
        "state": "OBSERVED",
        "provider_status": str(response.get("status") or "cancelled"),
        "provider_response": response,
        "cancelled_at": int(time.time()),
        "replayed": False,
    }
    ledger.put(dispatch_key, updated)
    return updated


__all__ = [
    "OpenAIBackgroundResponsesProvider",
    "submit_dispatch",
    "refresh_dispatch",
    "cancel_dispatch",
    "default_dispatch_key",
]
