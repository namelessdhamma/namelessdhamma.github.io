from __future__ import annotations

from typing import Any, Dict, Optional
import json
import os
import re
import html as html_lib
import time
import urllib.error
import urllib.parse
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


class LocalBrokerToolLoopProvider:
    """
    Bounded OpenAI-compatible tool loop that exposes only existing ND read-only
    broker tools to the supervisor model. No side-effect tools are admitted.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        endpoint: str,
        model: str,
        broker_token: str,
        broker_url: str = "http://127.0.0.1:3302/invoke",
        max_tool_rounds: int = 8,
        timeout: int = 180,
    ):
        self.provider_name = provider_name
        self.api_key = (api_key or "").strip()
        self.endpoint = endpoint
        self.model = model.strip()
        self.broker_token = (broker_token or "").strip()
        self.broker_url = broker_url
        self.max_tool_rounds = max(1, min(int(max_tool_rounds), 12))
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError(provider_name + "_api_key_missing")
        if not self.broker_token:
            raise ProviderError("nd_readonly_broker_token_missing")

    @staticmethod
    def tool_schema() -> list[Dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "web_current",
                "description": (
                    "Search/retrieve current public web evidence using the existing "
                    "ND read-only broker. Use concise targeted queries and preserve "
                    "source provenance returned by the broker."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 9000}
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }]

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        *,
        secrets: list[str],
    ) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                return json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise ProviderError(
                f"http_{exc.code}:" + _clean_error(raw, secrets)
            ) from exc
        except Exception as exc:
            raise ProviderError(
                "tool_loop_request_failed:" + _clean_error(exc, secrets)
            ) from exc

    @staticmethod
    def _safe_public_http_url(url: str) -> bool:
        try:
            p = urllib.parse.urlparse(url)
        except Exception:
            return False
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
        host = (p.hostname or "").lower()
        if (
            host in {"localhost", "127.0.0.1", "::1"}
            or host.startswith("10.")
            or host.startswith("192.168.")
            or host.startswith("169.254.")
            or host.endswith(".local")
        ):
            return False
        if host.startswith("172."):
            try:
                second = int(host.split(".")[1])
                if 16 <= second <= 31:
                    return False
            except Exception:
                pass
        return True

    def _fetch_page_excerpt(self, url: str) -> str:
        if not self._safe_public_http_url(url):
            return ""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ND-Research/1.0)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read(140000).decode("utf-8", "replace")
        except Exception:
            return ""
        raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", raw)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:7000]

    def _bing_html_fallback(self, query: str) -> Dict[str, Any]:
        search_url = (
            "https://www.bing.com/search?q="
            + urllib.parse.quote(query)
            + "&count=10&setlang=en-US"
        )
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ND-Research/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read(900000).decode("utf-8", "replace")
        except Exception as exc:
            raise ProviderError("bing_html_search_failed:" + str(exc)) from exc

        results = []
        blocks = re.findall(
            r'(?is)<li[^>]+class=["\'][^"\']*b_algo[^"\']*["\'][^>]*>(.*?)</li>',
            body,
        )
        for block in blocks:
            m = re.search(
                r'(?is)<h2[^>]*>\s*<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>',
                block,
            )
            if not m:
                continue
            url = html_lib.unescape(m.group(1))
            if not self._safe_public_http_url(url):
                continue
            title = re.sub(r"(?s)<[^>]+>", " ", m.group(2))
            title = re.sub(r"\s+", " ", html_lib.unescape(title)).strip()
            sm = re.search(
                r'(?is)<(?:p|div)[^>]+class=["\'][^"\']*(?:b_lineclamp\d*|b_caption)[^"\']*["\'][^>]*>(.*?)</(?:p|div)>',
                block,
            )
            snippet = ""
            if sm:
                snippet = re.sub(r"(?s)<[^>]+>", " ", sm.group(1))
                snippet = re.sub(r"\s+", " ", html_lib.unescape(snippet)).strip()
            if not any(r.get("url") == url for r in results):
                results.append({"title": title[:500], "url": url, "snippet": snippet[:1800]})
            if len(results) >= 8:
                break

        if not results:
            raise ProviderError("bing_html_search_returned_no_results")

        # Fetch a few public result pages to strengthen evidence beyond snippets.
        for row in results[:3]:
            excerpt = self._fetch_page_excerpt(row["url"])
            if excerpt:
                row["page_excerpt"] = excerpt

        return {
            "brief": "Direct Bing HTML fallback used because the primary ND web broker was unavailable.",
            "source_urls": [r["url"] for r in results],
            "results": results,
            "verified_search": True,
            "backend": "bing_html",
            "query": query,
            "mutations": False,
        }

    def _broker_call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name != "web_current":
            raise ProviderError("broker_tool_denied:" + name)
        query = str(args.get("query") or "").strip()
        if not query:
            raise ProviderError("web_current_query_required")
        try:
            obj = self._post_json(
                self.broker_url,
                {"tool": "web_current", "query": query},
                {
                    "Authorization": "Bearer " + self.broker_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "ND-Supervisor-Dispatch-ToolLoop/0.2",
                },
                secrets=[self.broker_token],
            )
            if not isinstance(obj, dict) or "result" not in obj:
                raise ProviderError("invalid_nd_broker_response")
            result = obj.get("result")
            if not isinstance(result, dict):
                raise ProviderError("invalid_nd_broker_result")
            return {
                "ok": True,
                "tool": name,
                "result": result,
                "route": "nd_broker",
                "mutations": False,
            }
        except Exception as primary_exc:
            fallback = self._bing_html_fallback(query)
            fallback["primary_route_error"] = _clean_error(
                primary_exc, [self.broker_token]
            )
            return {
                "ok": True,
                "tool": name,
                "result": fallback,
                "route": "bing_html_fallback",
                "mutations": False,
            }

    def submit(
        self,
        assignment: AssignmentEnvelope,
        supervisor: SupervisorResolution,
        dispatch_key: str,
    ) -> Dict[str, Any]:
        messages: list[Dict[str, Any]] = [
            {"role": "system", "content": supervisor.prompt_text},
            {"role": "user", "content": build_supervisor_input(assignment, supervisor)},
        ]
        tools = self.tool_schema()
        total_usage: Dict[str, int] = {}
        tool_events: list[Dict[str, Any]] = []
        last_data: Dict[str, Any] = {}
        started = time.time()

        for round_index in range(self.max_tool_rounds + 1):
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": min(supervisor.max_output_tokens, 16000),
            }
            data = self._post_json(
                self.endpoint,
                payload,
                {
                    "Authorization": "Bearer " + self.api_key,
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://namelessdhamma.org",
                    "X-Title": "ND True Research",
                    "User-Agent": "ND-Supervisor-Dispatch-ToolLoop/0.1",
                },
                secrets=[self.api_key],
            )
            last_data = data
            usage = data.get("usage") or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(usage.get(key), int):
                    total_usage[key] = total_usage.get(key, 0) + usage[key]

            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = message.get("content")
                if isinstance(content, list):
                    content = "\n".join(
                        str(item.get("text") or "")
                        for item in content
                        if isinstance(item, dict)
                    )
                text = str(content or "").strip()
                response_id = str(data.get("id") or "").strip() or (
                    self.provider_name + "_" + assignment.assignment_id
                )
                return {
                    "id": response_id,
                    "status": "completed" if text else "incomplete",
                    "model": data.get("model") or self.model,
                    "output": [{
                        "type": "message",
                        "content": [{"type": "output_text", "text": text}],
                    }] if text else [],
                    "provider": self.provider_name,
                    "provider_latency_ms": int((time.time() - started) * 1000),
                    "provider_usage": total_usage or data.get("usage"),
                    "provider_finish_reason": choice.get("finish_reason"),
                    "provider_raw_id": data.get("id"),
                    "tool_events": tool_events,
                    "tool_rounds": round_index,
                    "metadata": {
                        "nd_dispatch_key": dispatch_key,
                        "nd_assignment_id": assignment.assignment_id,
                        "nd_correlation_id": assignment.correlation_id,
                        "nd_supervisor_id": supervisor.supervisor_id,
                        "nd_supervisor_version": supervisor.canonical_version,
                    },
                }

            if round_index >= self.max_tool_rounds:
                raise ProviderError("tool_round_limit_exceeded")

            assistant_message = {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for tc in tool_calls:
                tc_id = str(tc.get("id") or "")
                fn = tc.get("function") or {}
                name = str(fn.get("name") or "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except Exception as exc:
                    raise ProviderError("tool_arguments_invalid_json:" + str(exc)) from exc
                result = self._broker_call(name, args)
                tool_events.append({
                    "tool_call_id": tc_id,
                    "name": name,
                    "query": str(args.get("query") or "")[:9000],
                    "mutations": False,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        raise ProviderError("tool_loop_exhausted")


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
    if (os.environ.get("MISTRAL_API_KEY") or "").strip():
        names.append("mistral")
        names.append("openrouter_research_free")
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

    if provider_name == "openrouter_research_free":
        key = (
            os.environ.get("OpenRouter")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        ).strip()
        broker_token = (os.environ.get("QSTASH_TOKEN") or "").strip()
        return LocalBrokerToolLoopProvider(
            provider_name="openrouter_research_free",
            api_key=key,
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            model="nvidia/nemotron-3-ultra-550b-a55b-20260604:free",
            broker_token=broker_token,
        )

    if provider_name == "mistral":
        key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
        model = (os.environ.get("MISTRAL_MODEL") or "mistral-large-latest").strip()
        return OpenAICompatibleSyncProvider(
            provider_name="mistral",
            api_key=key,
            endpoint="https://api.mistral.ai/v1/chat/completions",
            model=model,
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
        for name in ("openrouter_research_free", "groq_web", "groq", "openrouter"):
            if name in configured:
                order.append(name)
    else:
        for name in ("groq", "mistral", "openrouter"):
            if name in configured:
                order.append(name)
    return order


__all__ = [
    "OpenAICompatibleSyncProvider",
    "LocalBrokerToolLoopProvider",
    "configured_provider_names",
    "make_sync_provider",
    "auto_provider_order",
]
