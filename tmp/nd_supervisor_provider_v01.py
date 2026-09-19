from __future__ import annotations

from typing import Any, Dict, Optional
import json
import os
import time
import urllib.error
import urllib.request

from nd_supervisor_dispatch_v01 import (
    AssignmentEnvelope,
    SupervisorResolution,
    ProviderError,
    build_supervisor_input,
)


def _clean_error(value: Any, secrets: list[str]) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:2000]


class OpenAICompatibleSyncProvider:
    """
    Generic synchronous chat/completions provider.

    submit() returns a Responses-like terminal object so the existing durable
    dispatch lifecycle can classify and persist it without provider-specific
    lifecycle branches.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        endpoint: str,
        model: str,
        headers: Optional[Dict[str, str]] = None,
        built_in_tools: Optional[list[Dict[str, Any]]] = None,
        timeout: int = 180,
    ):
        self.provider_name = provider_name
        self.api_key = (api_key or "").strip()
        self.endpoint = endpoint
        self.model = model.strip()
        self.timeout = timeout
        self.extra_headers = dict(headers or {})
        self.built_in_tools = list(built_in_tools or [])
        if not self.api_key:
            raise ProviderError(provider_name + "_api_key_missing")
        if not self.model:
            raise ProviderError(provider_name + "_model_missing")

    def submit(
        self,
        assignment: AssignmentEnvelope,
        supervisor: SupervisorResolution,
        dispatch_key: str,
    ) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": supervisor.prompt_text},
            {"role": "user", "content": build_supervisor_input(assignment, supervisor)},
        ]
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": min(supervisor.max_output_tokens, 16000),
        }
        if self.built_in_tools:
            payload["tools"] = self.built_in_tools
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "ND-Supervisor-Dispatch/0.5",
            **self.extra_headers,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise ProviderError(
                f"{self.provider_name}_http_{exc.code}:"
                + _clean_error(raw, [self.api_key])
            ) from exc
        except Exception as exc:
            raise ProviderError(
                self.provider_name + "_request_failed:" + _clean_error(exc, [self.api_key])
            ) from exc

        message = (((data.get("choices") or [{}])[0].get("message") or {}))
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            content = "\n".join(parts)
        text = str(content or "").strip()

        response_id = str(data.get("id") or "").strip()
        if not response_id:
            response_id = (
                self.provider_name
                + "_"
                + assignment.assignment_id
                + "_"
                + str(int(started * 1000))
            )

        return {
            "id": response_id,
            "status": "completed" if text else "incomplete",
            "model": data.get("model") or self.model,
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                }
            ] if text else [],
            "provider": self.provider_name,
            "provider_latency_ms": int((time.time() - started) * 1000),
            "provider_usage": data.get("usage"),
            "provider_finish_reason": ((data.get("choices") or [{}])[0].get("finish_reason")),
            "provider_raw_id": data.get("id"),
            "metadata": {
                "nd_dispatch_key": dispatch_key,
                "nd_assignment_id": assignment.assignment_id,
                "nd_correlation_id": assignment.correlation_id,
                "nd_supervisor_id": supervisor.supervisor_id,
                "nd_supervisor_version": supervisor.canonical_version,
            },
        }

    def retrieve(self, response_id: str) -> Dict[str, Any]:
        raise ProviderError(self.provider_name + "_sync_provider_has_no_retrieve")

    def cancel(self, response_id: str) -> Dict[str, Any]:
        raise ProviderError(self.provider_name + "_sync_provider_has_no_cancel")


def configured_provider_names() -> list[str]:
    names = []
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        names.append("openai")
    if (os.environ.get("GROQ_API_KEY") or "").strip():
        names.append("groq")
    if (os.environ.get("GROQ_API_KEY") or "").strip():
        names.append("groq_web")
    if (
        (os.environ.get("OpenRouter") or "").strip()
        or (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    ):
        names.append("openrouter")
    return names


def make_sync_provider(
    provider_name: str,
    *,
    purpose: str = "general",
) -> OpenAICompatibleSyncProvider:
    provider_name = provider_name.strip().lower()
    purpose = purpose.strip().lower()

    if provider_name == "groq":
        key = (os.environ.get("GROQ_API_KEY") or "").strip()
        if purpose == "research":
            model = (
                os.environ.get("GROQ_RESEARCH_MODEL")
                or os.environ.get("GROQ_MODEL")
                or "groq/compound"
            ).strip()
        else:
            model = (
                os.environ.get("GROQ_MODEL")
                or "openai/gpt-oss-120b"
            ).strip()
        return OpenAICompatibleSyncProvider(
            provider_name="groq",
            api_key=key,
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            model=model,
        )

    if provider_name == "groq_web":
        key = (os.environ.get("GROQ_API_KEY") or "").strip()
        model = (os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b").strip()
        return OpenAICompatibleSyncProvider(
            provider_name="groq_web",
            api_key=key,
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            model=model,
            built_in_tools=[{"type": "browser_search"}],
        )

    if provider_name == "openrouter":
        key = (
            os.environ.get("OpenRouter")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        ).strip()
        model = (os.environ.get("OPENROUTER_MODEL") or "openrouter/free").strip()
        return OpenAICompatibleSyncProvider(
            provider_name="openrouter",
            api_key=key,
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            model=model,
            headers={
                "HTTP-Referer": "https://namelessdhamma.org",
                "X-Title": "ND Supervisor Dispatch",
            },
        )

    raise ProviderError("unsupported_sync_provider:" + provider_name)


def auto_provider_order(*, purpose: str = "general") -> list[str]:
    """
    Current fallback policy is availability-first and intentionally does not
    claim quality equivalence between providers.
    """
    configured = set(configured_provider_names())
    order = []
    if purpose.strip().lower() == "research":
        for name in ("groq_web", "groq", "openrouter"):
            if name in configured:
                order.append(name)
    else:
        for name in ("groq", "openrouter"):
            if name in configured:
                order.append(name)
    return order


__all__ = [
    "OpenAICompatibleSyncProvider",
    "configured_provider_names",
    "make_sync_provider",
    "auto_provider_order",
]
