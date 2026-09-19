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
                ["groq_web", "groq", "openrouter"],
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


if __name__ == "__main__":
    unittest.main()
