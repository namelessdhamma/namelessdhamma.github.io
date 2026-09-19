import sys
from pathlib import Path
import json
import tempfile
import unittest

TMP = Path(__file__).parent
sys.path.insert(0, str(TMP))

import nd_supervisor_dispatch_v02 as nd


BASE_ASSIGNMENT = {
    "workitem_id": "WI-ASYNC",
    "assignment_id": "A-ASYNC",
    "issued_by": "ND Automation Agent",
    "assignee_peer": "True Research",
    "correlation_id": "corr-async",
    "assignment_state": "ACTIVE",
    "objective": "Execute bounded research.",
    "scope": "Research only",
    "authority_ceiling": "RESEARCH_ONLY",
    "constraints": "No production mutation",
    "done_when": "Evidence package returned",
    "issued_at": "2026-09-19T00:00:00Z",
}

SUPERVISOR = {
    "supervisor_id": "True Research",
    "canonical_version": "1.3.0",
    "prompt_source": "ND-SKILL-TR-1",
    "prompt_text": "Act as canonical True Research.",
    "model": "gpt-5.6-luna",
    "tool_profile": [{"type": "web_search"}],
    "reasoning_effort": "high",
    "max_output_tokens": 8000,
}


class FakeProvider:
    def __init__(self):
        self.submit_calls = 0
        self.retrieve_calls = 0
        self.cancel_calls = 0
        self.status = "queued"
        self.text = "research complete"
        self.fail_submit = False
        self.missing_id = False

    def submit(self, assignment, supervisor, dispatch_key):
        self.submit_calls += 1
        if self.fail_submit:
            raise RuntimeError("submit_network_unknown")
        result = {"status": self.status}
        if not self.missing_id:
            result["id"] = "resp_async_1"
        return result

    def retrieve(self, response_id):
        self.retrieve_calls += 1
        if self.status == "completed":
            return {
                "id": response_id,
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": self.text}],
                }],
            }
        if self.status == "failed":
            return {"id": response_id, "status": "failed", "error": {"message": "boom"}}
        return {"id": response_id, "status": self.status, "output": []}

    def cancel(self, response_id):
        self.cancel_calls += 1
        self.status = "cancelled"
        return {"id": response_id, "status": "cancelled"}


class AsyncDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.json"
        self.provider = FakeProvider()

    def tearDown(self):
        self.tmp.cleanup()

    def test_submit_persists_response_id_and_attempted_state(self):
        out = nd.submit_dispatch(
            BASE_ASSIGNMENT,
            SUPERVISOR,
            ledger_path=self.ledger,
            provider=self.provider,
        )
        self.assertEqual(out["state"], "ATTEMPTED")
        self.assertEqual(out["provider_response_id"], "resp_async_1")
        self.assertEqual(out["provider_status"], "queued")
        self.assertEqual(self.provider.submit_calls, 1)

    def test_replay_does_not_duplicate_provider_submission(self):
        first = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        second = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.assertEqual(first["provider_response_id"], second["provider_response_id"])
        self.assertTrue(second["replayed"])
        self.assertEqual(self.provider.submit_calls, 1)

    def test_refresh_active_stays_attempted(self):
        submitted = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.provider.status = "in_progress"
        out = nd.refresh_dispatch(
            submitted["dispatch_key"], ledger_path=self.ledger, provider=self.provider
        )
        self.assertEqual(out["state"], "ATTEMPTED")
        self.assertEqual(out["provider_status"], "in_progress")

    def test_refresh_completed_becomes_verified(self):
        submitted = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.provider.status = "completed"
        out = nd.refresh_dispatch(
            submitted["dispatch_key"], ledger_path=self.ledger, provider=self.provider
        )
        self.assertEqual(out["state"], "VERIFIED")
        self.assertEqual(out["output_text"], "research complete")
        self.assertTrue(out["verification"]["provider_response_id_bound"])

    def test_terminal_failure_is_observed_not_verified(self):
        submitted = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.provider.status = "failed"
        out = nd.refresh_dispatch(
            submitted["dispatch_key"], ledger_path=self.ledger, provider=self.provider
        )
        self.assertEqual(out["state"], "OBSERVED")
        self.assertTrue(out["terminal_failure"])
        self.assertEqual(out["provider_status"], "failed")

    def test_cancel_is_observed_and_idempotent_locally(self):
        submitted = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        first = nd.cancel_dispatch(
            submitted["dispatch_key"], ledger_path=self.ledger, provider=self.provider
        )
        second = nd.cancel_dispatch(
            submitted["dispatch_key"], ledger_path=self.ledger, provider=self.provider
        )
        self.assertEqual(first["provider_status"], "cancelled")
        self.assertEqual(first["state"], "OBSERVED")
        self.assertTrue(second["replayed"])
        self.assertEqual(self.provider.cancel_calls, 1)

    def test_ambiguous_submit_failure_does_not_blind_retry(self):
        self.provider.fail_submit = True
        with self.assertRaises(RuntimeError):
            nd.submit_dispatch(
                BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
            )
        self.provider.fail_submit = False
        out = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.assertTrue(out["recovery_required"])
        self.assertEqual(self.provider.submit_calls, 1)

    def test_missing_response_id_is_ambiguous_and_not_retried(self):
        self.provider.missing_id = True
        with self.assertRaises(nd.ProviderError):
            nd.submit_dispatch(
                BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
            )
        self.provider.missing_id = False
        out = nd.submit_dispatch(
            BASE_ASSIGNMENT, SUPERVISOR, ledger_path=self.ledger, provider=self.provider
        )
        self.assertTrue(out["recovery_required"])
        self.assertEqual(self.provider.submit_calls, 1)


    def test_terminal_sync_provider_preserves_pluggable_ledger(self):
        class MemoryLedger:
            def __init__(self):
                self.rows = {}
            def get(self, key):
                row = self.rows.get(key)
                return None if row is None else dict(row)
            def put(self, key, value):
                self.rows[key] = dict(value)

        class SyncProvider:
            def submit(self, assignment, supervisor, dispatch_key):
                return {
                    "id": "sync-1",
                    "status": "completed",
                    "provider": "groq",
                    "model": "openai/gpt-oss-120b",
                    "output": [{
                        "type": "message",
                        "content": [{"type": "output_text", "text": "sync complete"}],
                    }],
                }
            def retrieve(self, response_id):
                raise AssertionError("retrieve should not be called for terminal submit")
            def cancel(self, response_id):
                raise AssertionError("cancel not expected")

        ledger = MemoryLedger()
        out = nd.submit_dispatch(
            BASE_ASSIGNMENT,
            SUPERVISOR,
            ledger=ledger,
            provider=SyncProvider(),
            dispatch_key="sync-terminal",
        )
        self.assertEqual(out["state"], "VERIFIED")
        self.assertEqual(out["execution_provider"], "groq")
        self.assertEqual(out["execution_model"], "openai/gpt-oss-120b")
        self.assertEqual(out["output_text"], "sync complete")
        self.assertEqual(ledger.get("sync-terminal")["state"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
