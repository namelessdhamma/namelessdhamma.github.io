import base64
import json
import sys
from pathlib import Path
import unittest

TMP = Path(__file__).parent
sys.path.insert(0, str(TMP))

import nd_supervisor_dispatch_outer_v04 as outer


ASSIGNMENT = {
    "workitem_id": "WI-OUTER",
    "assignment_id": "A-OUTER",
    "issued_by": "ND Automation Agent",
    "assignee_peer": "True Research",
    "correlation_id": "corr-outer",
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
    "prompt_source": "ND_CAPABILITY_REGISTRY@1.12.0:TRUE_RESEARCH:artifact:hash",
    "prompt_text": "Act as canonical True Research.",
    "model": "gpt-5.6-luna",
    "tool_profile": [{"type": "web_search"}],
    "reasoning_effort": "high",
    "max_output_tokens": 8000,
    "authority_evidence": {
        "registry_hash": "r" * 64,
        "artifact_id": "artifact",
        "artifact_hash": "a" * 64,
        "exact_status": "CANONICAL — ACTIVE",
    },
}


class FakeProvider:
    def __init__(self):
        self.status = "queued"
        self.submit_calls = 0
        self.retrieve_calls = 0
        self.cancel_calls = 0

    def submit(self, assignment, supervisor, dispatch_key):
        self.submit_calls += 1
        return {"id": "resp_outer_1", "status": self.status}

    def retrieve(self, response_id):
        self.retrieve_calls += 1
        if self.status == "completed":
            return {
                "id": response_id,
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "outer result"}],
                }],
            }
        return {"id": response_id, "status": self.status, "output": []}

    def cancel(self, response_id):
        self.cancel_calls += 1
        self.status = "cancelled"
        return {"id": response_id, "status": "cancelled"}


class FakeGitHubTransport:
    def __init__(self):
        self.files = {}
        self.put_bodies = []

    def __call__(self, method, path, body=None):
        if method == "GET":
            row = self.files.get(path)
            if row is None:
                return 404, {"message": "Not Found"}
            return 200, row
        if method == "PUT":
            self.put_bodies.append(body)
            expected_sha = None
            if path in self.files:
                expected_sha = self.files[path]["sha"]
                if body.get("sha") != expected_sha:
                    return 409, {"message": "sha mismatch"}
            raw = base64.b64decode(body["content"]).decode("utf-8")
            new_sha = "sha-%d" % (len(self.put_bodies),)
            self.files[path] = {
                "sha": new_sha,
                "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            }
            return (200 if expected_sha else 201), {"content": {"sha": new_sha}}
        raise AssertionError("unexpected transport method")


class OuterAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The outer module intentionally bootstraps production dependencies only in main().
        # For unit tests, local prototype modules are already on sys.path.
        pass

    def setUp(self):
        self.ledger = outer.MemoryLedger()
        self.provider = FakeProvider()

    def test_exact_mcp_path_only(self):
        prior = outer.PATH_TOKEN
        try:
            outer.PATH_TOKEN = "secret-token"
            self.assertTrue(outer.is_supervisor_mcp("/nd/supervisor/mcp/secret-token"))
            self.assertTrue(outer.is_supervisor_mcp("/nd/supervisor/mcp/secret-token?x=1"))
            self.assertFalse(outer.is_supervisor_mcp("/nd/supervisor/mcp/wrong"))
            self.assertFalse(outer.is_supervisor_mcp("/remotion/health"))
        finally:
            outer.PATH_TOKEN = prior

    def test_submit_result_cancel_through_generic_tools(self):
        submitted = outer.supervisor_tool_call(
            "supervisor_submit",
            {"assignment": ASSIGNMENT, "supervisor": SUPERVISOR},
            ledger=self.ledger,
            provider=self.provider,
        )
        self.assertEqual(submitted["provider_response_id"], "resp_outer_1")
        key = submitted["dispatch_key"]

        self.provider.status = "completed"
        result = outer.supervisor_tool_call(
            "supervisor_result",
            {"dispatch_key": key},
            ledger=self.ledger,
            provider=self.provider,
        )
        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(result["output_text"], "outer result")

    def test_duplicate_submit_does_not_duplicate_provider_run(self):
        first = outer.supervisor_tool_call(
            "supervisor_submit",
            {"assignment": ASSIGNMENT, "supervisor": SUPERVISOR},
            ledger=self.ledger,
            provider=self.provider,
        )
        second = outer.supervisor_tool_call(
            "supervisor_submit",
            {"assignment": ASSIGNMENT, "supervisor": SUPERVISOR},
            ledger=self.ledger,
            provider=self.provider,
        )
        self.assertEqual(first["provider_response_id"], second["provider_response_id"])
        self.assertTrue(second["replayed"])
        self.assertEqual(self.provider.submit_calls, 1)

    def test_missing_authority_evidence_fails_closed(self):
        bad = dict(SUPERVISOR)
        bad.pop("authority_evidence")
        with self.assertRaises(RuntimeError):
            outer.supervisor_tool_call(
                "supervisor_submit",
                {"assignment": ASSIGNMENT, "supervisor": bad},
                ledger=self.ledger,
                provider=self.provider,
            )
        self.assertEqual(self.provider.submit_calls, 0)

    def test_partial_authority_evidence_fails_closed(self):
        bad = dict(SUPERVISOR)
        bad["authority_evidence"] = {"registry_hash": "x"}
        with self.assertRaises(RuntimeError):
            outer.supervisor_tool_call(
                "supervisor_submit",
                {"assignment": ASSIGNMENT, "supervisor": bad},
                ledger=self.ledger,
                provider=self.provider,
            )

    def test_github_receipt_ledger_create_read_update_with_cas(self):
        transport = FakeGitHubTransport()
        ledger = outer.GitHubReceiptLedger(
            "token",
            "owner/repo",
            "main",
            ".nd-runtime/test",
            transport=transport,
        )
        key = "assignment::correlation"
        ledger.put(key, {"dispatch_key": key, "state": "ATTEMPTED"})
        first = ledger.get(key)
        self.assertEqual(first["state"], "ATTEMPTED")
        self.assertTrue(first["_github_content_sha"].startswith("sha-"))

        ledger.put(key, {"dispatch_key": key, "state": "VERIFIED"})
        second = ledger.get(key)
        self.assertEqual(second["state"], "VERIFIED")
        self.assertIn("sha", transport.put_bodies[-1])

    def test_github_receipt_dispatch_key_mismatch_fails_closed(self):
        transport = FakeGitHubTransport()
        ledger = outer.GitHubReceiptLedger(
            "token",
            "owner/repo",
            "main",
            ".nd-runtime/test",
            transport=transport,
        )
        key = "expected"
        path = ledger.path_for(key)
        raw = json.dumps({"dispatch_key": "other", "state": "VERIFIED"}).encode()
        transport.files[path] = {
            "sha": "sha-x",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        with self.assertRaises(RuntimeError):
            ledger.get(key)

    def test_status_is_nonexecuting(self):
        status = outer.supervisor_tool_call(
            "supervisor_status",
            {},
            ledger=self.ledger,
            provider=self.provider,
        )
        self.assertTrue(status["ok"])
        self.assertFalse(status["production_adoption"])
        self.assertEqual(self.provider.submit_calls, 0)


if __name__ == "__main__":
    unittest.main()
