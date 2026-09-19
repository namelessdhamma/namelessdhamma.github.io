import json
import os
import sys
from pathlib import Path
import unittest
from unittest import mock

TMP = Path(__file__).parent
sys.path.insert(0, str(TMP))

import nd_supervisor_provider_v01 as p
import nd_supervisor_dispatch_v01 as d1


ASSIGNMENT = d1.AssignmentEnvelope.from_dict({
    "workitem_id": "WI-PROVIDER",
    "assignment_id": "A-PROVIDER",
    "issued_by": "ND Automation Agent",
    "assignee_peer": "True Writer",
    "correlation_id": "corr-provider",
    "assignment_state": "ACTIVE",
    "objective": "Return qualification result.",
})

SUPERVISOR = d1.SupervisorResolution.from_dict({
    "supervisor_id": "True Writer",
    "canonical_version": "0.5",
    "prompt_source": "canonical",
    "prompt_text": "Canonical supervisor prompt.",
    "model": "logical-policy-model",
    "tool_profile": [],
    "reasoning_effort": "low",
    "max_output_tokens": 4000,
})


class FakeHTTPResponse:
    def __init__(self, obj, status=200):
        self.obj = obj
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.obj).encode("utf-8")


class ProviderTests(unittest.TestCase):
    def test_sync_provider_transforms_chat_completion_to_terminal_response(self):
        provider = p.OpenAICompatibleSyncProvider(
            provider_name="groq",
            api_key="secret",
            endpoint="https://example.invalid/chat/completions",
            model="openai/gpt-oss-120b",
        )
        payload = {
            "id": "chatcmpl-1",
            "model": "openai/gpt-oss-120b",
            "choices": [{
                "message": {"content": "qualified"},
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 42},
        }
        with mock.patch("urllib.request.urlopen", return_value=FakeHTTPResponse(payload)):
            out = provider.submit(ASSIGNMENT, SUPERVISOR, "dispatch-1")
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["provider"], "groq")
        self.assertEqual(out["model"], "openai/gpt-oss-120b")
        self.assertEqual(out["output"][0]["content"][0]["text"], "qualified")
        self.assertEqual(out["metadata"]["nd_correlation_id"], "corr-provider")

    def test_research_groq_prefers_research_model(self):
        env = {
            "GROQ_API_KEY": "g",
            "GROQ_MODEL": "openai/gpt-oss-120b",
            "GROQ_RESEARCH_MODEL": "groq/compound",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            provider = p.make_sync_provider("groq", purpose="research")
        self.assertEqual(provider.model, "groq/compound")

    def test_general_groq_uses_general_model(self):
        env = {
            "GROQ_API_KEY": "g",
            "GROQ_MODEL": "openai/gpt-oss-120b",
            "GROQ_RESEARCH_MODEL": "groq/compound",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            provider = p.make_sync_provider("groq", purpose="general")
        self.assertEqual(provider.model, "openai/gpt-oss-120b")


    def test_groq_web_uses_general_model_with_browser_search(self):
        env = {
            "GROQ_API_KEY": "g",
            "GROQ_MODEL": "openai/gpt-oss-120b",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            provider = p.make_sync_provider("groq_web", purpose="research")
        self.assertEqual(provider.model, "openai/gpt-oss-120b")
        self.assertEqual(provider.provider_name, "groq_web")
        self.assertEqual(provider.built_in_tools, [{"type": "browser_search"}])

    def test_groq_web_sends_browser_search_tool(self):
        provider = p.OpenAICompatibleSyncProvider(
            provider_name="groq_web",
            api_key="secret",
            endpoint="https://example.invalid/chat/completions",
            model="openai/gpt-oss-120b",
            built_in_tools=[{"type": "browser_search"}],
        )
        captured = {}
        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return FakeHTTPResponse({
                "id": "chatcmpl-web",
                "model": "openai/gpt-oss-120b",
                "choices": [{
                    "message": {"content": "researched"},
                    "finish_reason": "stop",
                }],
            })
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            out = provider.submit(ASSIGNMENT, SUPERVISOR, "dispatch-web")
        self.assertEqual(captured["payload"]["tools"], [{"type": "browser_search"}])
        self.assertEqual(out["provider"], "groq_web")
        self.assertEqual(out["status"], "completed")

    def test_openrouter_uses_existing_environment_key(self):
        env = {
            "OpenRouter": "or-secret",
            "OPENROUTER_MODEL": "openrouter/free",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            provider = p.make_sync_provider("openrouter", purpose="general")
        self.assertEqual(provider.model, "openrouter/free")
        self.assertEqual(provider.provider_name, "openrouter")

    def test_auto_order_prefers_groq_before_openrouter(self):
        env = {
            "GROQ_API_KEY": "g",
            "OpenRouter": "o",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                p.auto_provider_order(purpose="research"),
                ["openrouter_research_free", "groq_web", "groq", "openrouter"],
            )

    def test_sync_provider_has_no_fake_resume_or_cancel(self):
        provider = p.OpenAICompatibleSyncProvider(
            provider_name="groq",
            api_key="secret",
            endpoint="https://example.invalid",
            model="m",
        )
        with self.assertRaises(d1.ProviderError):
            provider.retrieve("id")
        with self.assertRaises(d1.ProviderError):
            provider.cancel("id")


    def test_openrouter_research_free_uses_explicit_free_model_and_broker(self):
        env = {
            "OpenRouter": "or-secret",
            "QSTASH_TOKEN": "broker-secret",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            provider = p.make_sync_provider("openrouter_research_free", purpose="research")
        self.assertEqual(provider.provider_name, "openrouter_research_free")
        self.assertEqual(provider.model, "nvidia/nemotron-3-ultra-550b-a55b-20260604:free")
        self.assertEqual(provider.broker_token, "broker-secret")

    def test_local_broker_tool_loop_executes_readonly_web_and_finishes(self):
        provider = p.LocalBrokerToolLoopProvider(
            provider_name="openrouter_research_free",
            api_key="or-secret",
            endpoint="https://openrouter.invalid/chat/completions",
            model="nvidia/nemotron-3-ultra-550b-a55b-20260604:free",
            broker_token="broker-secret",
            max_tool_rounds=3,
        )
        calls = {"model": 0, "broker": 0, "payloads": []}

        def fake_post(url, payload, headers, secrets):
            if "openrouter.invalid" in url:
                calls["model"] += 1
                calls["payloads"].append(payload)
                if calls["model"] == 1:
                    return {
                        "id": "gen-1",
                        "model": "nvidia/nemotron-3-ultra-550b-a55b-20260604:free",
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": "tc-1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_current",
                                        "arguments": json.dumps({"query": "current agent systems"}),
                                    },
                                }],
                            },
                            "finish_reason": "tool_calls",
                        }],
                        "usage": {"total_tokens": 10},
                    }
                return {
                    "id": "gen-2",
                    "model": "nvidia/nemotron-3-ultra-550b-a55b-20260604:free",
                    "choices": [{
                        "message": {"role": "assistant", "content": "Evidence-backed result."},
                        "finish_reason": "stop",
                    }],
                    "usage": {"total_tokens": 20},
                }
            self.assertEqual(url, "http://127.0.0.1:3302/invoke")
            calls["broker"] += 1
            self.assertEqual(payload["tool"], "web_current")
            return {
                "result": {
                    "verified_search": True,
                    "results": [{"title": "Example", "url": "https://example.com"}],
                }
            }

        provider._post_json = fake_post
        out = provider.submit(ASSIGNMENT, SUPERVISOR, "dispatch-tool-loop")
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["provider"], "openrouter_research_free")
        self.assertEqual(out["output"][0]["content"][0]["text"], "Evidence-backed result.")
        self.assertEqual(calls["model"], 2)
        self.assertEqual(calls["broker"], 1)
        self.assertEqual(out["tool_rounds"], 1)
        self.assertEqual(out["tool_events"][0]["name"], "web_current")
        second_messages = calls["payloads"][1]["messages"]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertIn("verified_search", second_messages[-1]["content"])

    def test_local_broker_tool_loop_denies_unknown_tool(self):
        provider = p.LocalBrokerToolLoopProvider(
            provider_name="openrouter_research_free",
            api_key="or-secret",
            endpoint="https://openrouter.invalid",
            model="nvidia/nemotron-3-ultra-550b-a55b-20260604:free",
            broker_token="broker-secret",
        )
        with self.assertRaises(d1.ProviderError):
            provider._broker_call("dangerous_write", {"query": "x"})


if __name__ == "__main__":
    unittest.main()
