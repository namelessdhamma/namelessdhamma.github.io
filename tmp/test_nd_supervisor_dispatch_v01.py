import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("nd_supervisor_dispatch_v01.py")
spec = importlib.util.spec_from_file_location("nd_dispatch", MODULE_PATH)
nd = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = nd
spec.loader.exec_module(nd)


BASE_ASSIGNMENT = {
    "workitem_id": "WI-1",
    "assignment_id": "A-1",
    "issued_by": "ND Automation Agent",
    "assignee_peer": "True Research",
    "correlation_id": "corr-1",
    "assignment_state": "ACTIVE",
    "objective": "Research the agent systems landscape.",
    "scope": "Research only",
    "authority_ceiling": "RESEARCH_ONLY",
    "constraints": "No production mutation",
    "done_when": "Evidence-backed package returned",
    "issued_at": "2026-09-19T00:00:00Z",
}

TRUE_RESEARCH = {
    "supervisor_id": "True Research",
    "canonical_version": "1.3.0",
    "prompt_source": "ND-SKILL-TR-1",
    "prompt_text": "Act as canonical True Research.",
    "model": "gpt-5.6-luna",
    "tool_profile": [{"type": "web_search"}],
    "reasoning_effort": "high",
    "max_output_tokens": 8000,
}

TRUE_DOCTOR = {
    "supervisor_id": "True Doctor",
    "canonical_version": "0.3",
    "prompt_source": "ND-TRUE-DOCTOR",
    "prompt_text": "Act as canonical True Doctor.",
    "model": "gpt-5.6-luna",
    "tool_profile": [],
    "reasoning_effort": "medium",
    "max_output_tokens": 4000,
}


def provider(text="ok", response_id="resp_1"):
    def run(assignment, supervisor, dispatch_key):
        return {
            "id": response_id,
            "model": supervisor.model,
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }],
        }
    return run


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_happy_path_is_verified(self):
        out = nd.dispatch(
            BASE_ASSIGNMENT,
            TRUE_RESEARCH,
            ledger_path=self.ledger,
            provider=provider("research result"),
        )
        self.assertEqual(out["state"], "VERIFIED")
        self.assertTrue(out["verification"]["correlation_bound"])
        self.assertEqual(out["assignment_id"], "A-1")
        self.assertEqual(out["supervisor_id"], "True Research")

    def test_replay_is_idempotent(self):
        calls = {"n": 0}
        def counted(assignment, supervisor, dispatch_key):
            calls["n"] += 1
            return provider("once")(assignment, supervisor, dispatch_key)

        first = nd.dispatch(
            BASE_ASSIGNMENT,
            TRUE_RESEARCH,
            ledger_path=self.ledger,
            provider=counted,
            dispatch_key="same-key",
        )
        second = nd.dispatch(
            BASE_ASSIGNMENT,
            TRUE_RESEARCH,
            ledger_path=self.ledger,
            provider=counted,
            dispatch_key="same-key",
        )
        self.assertEqual(calls["n"], 1)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])

    def test_inactive_assignment_fails_closed(self):
        bad = dict(BASE_ASSIGNMENT)
        bad["assignment_state"] = "REVOKED"
        with self.assertRaises(nd.AssignmentValidationError):
            nd.dispatch(bad, TRUE_RESEARCH, ledger_path=self.ledger, provider=provider())
        self.assertFalse(self.ledger.exists())

    def test_assignee_mismatch_fails_closed(self):
        bad = dict(BASE_ASSIGNMENT)
        bad["assignee_peer"] = "True Developer"
        with self.assertRaises(nd.AssignmentValidationError):
            nd.dispatch(bad, TRUE_RESEARCH, ledger_path=self.ledger, provider=provider())
        self.assertFalse(self.ledger.exists())

    def test_non_agent_issuer_fails_closed(self):
        bad = dict(BASE_ASSIGNMENT)
        bad["issued_by"] = "Unknown"
        with self.assertRaises(nd.AssignmentValidationError):
            nd.dispatch(bad, TRUE_RESEARCH, ledger_path=self.ledger, provider=provider())
        self.assertFalse(self.ledger.exists())

    def test_provider_failure_remains_attempted_not_observed(self):
        def broken(*args):
            raise nd.ProviderError("provider_down")
        with self.assertRaises(nd.ProviderError):
            nd.dispatch(BASE_ASSIGNMENT, TRUE_RESEARCH, ledger_path=self.ledger, provider=broken)
        saved = json.loads(self.ledger.read_text())
        row = next(iter(saved["dispatches"].values()))
        self.assertEqual(row["state"], "ATTEMPTED")
        self.assertIn("provider_down", row["provider_error"])

    def test_generic_second_supervisor_uses_same_dispatch(self):
        assignment = dict(BASE_ASSIGNMENT)
        assignment.update({
            "workitem_id": "WI-DOCTOR",
            "assignment_id": "A-DOCTOR",
            "assignee_peer": "True Doctor",
            "correlation_id": "corr-doctor",
            "objective": "Diagnose a bounded incident.",
        })
        out = nd.dispatch(
            assignment,
            TRUE_DOCTOR,
            ledger_path=self.ledger,
            provider=provider("incident diagnosis", "resp_doctor"),
        )
        self.assertEqual(out["state"], "VERIFIED")
        self.assertEqual(out["supervisor_id"], "True Doctor")

    def test_output_hash_is_stable(self):
        a = nd.dispatch(
            BASE_ASSIGNMENT,
            TRUE_RESEARCH,
            ledger_path=self.ledger,
            provider=provider("same output"),
            dispatch_key="hash-a",
        )
        b_assignment = dict(BASE_ASSIGNMENT)
        b_assignment["assignment_id"] = "A-2"
        b_assignment["correlation_id"] = "corr-2"
        b = nd.dispatch(
            b_assignment,
            TRUE_RESEARCH,
            ledger_path=self.ledger,
            provider=provider("same output", "resp_2"),
            dispatch_key="hash-b",
        )
        self.assertEqual(a["output_sha256"], b["output_sha256"])


if __name__ == "__main__":
    unittest.main()
