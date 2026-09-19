import hashlib
import json
import sys
from pathlib import Path
import unittest

TMP = Path(__file__).parent
sys.path.insert(0, str(TMP))

import nd_supervisor_resolver_v01 as r


ARTIFACT = b"canonical supervisor prompt"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT).hexdigest()

REGISTRY = {
    "registry_id": "ND_CAPABILITY_REGISTRY",
    "version": "9.9.9",
    "components": [{
        "component_key": "TRUE_RESEARCH",
        "semantic_id": "ND-SKILL-TR-1",
        "version": "1.3.0",
        "exact_status": "CANONICAL — ACTIVE",
        "canonical_artifact_id": "artifact-1",
        "canonical_artifact_name": "True Research.md",
        "canonical_hash": ARTIFACT_HASH,
        "interfaces": {"consumes": ["RESEARCH_REQUEST"], "produces": ["RESEARCH_PACKET"]},
        "owner": "research",
        "read_permissions": ["INPUT"],
        "write_permissions": ["TRANSIENT"],
    }]
}
REGISTRY_BYTES = json.dumps(REGISTRY, sort_keys=True).encode()
REGISTRY_HASH = hashlib.sha256(REGISTRY_BYTES).hexdigest()


class ResolverTests(unittest.TestCase):
    def test_happy_path_resolves_exact_artifact(self):
        identity, prompt = r.resolve_supervisor_identity(
            REGISTRY_BYTES,
            expected_registry_hash=REGISTRY_HASH,
            expected_registry_version="9.9.9",
            component_key="TRUE_RESEARCH",
            artifact_fetcher=lambda artifact_id: ARTIFACT,
        )
        self.assertEqual(identity.semantic_id, "ND-SKILL-TR-1")
        self.assertEqual(prompt, ARTIFACT.decode())

    def test_registry_hash_mismatch_fails_closed(self):
        with self.assertRaises(r.AuthorityMismatch):
            r.load_verified_registry(REGISTRY_BYTES, expected_registry_hash="0" * 64)

    def test_artifact_hash_mismatch_fails_closed(self):
        with self.assertRaises(r.AuthorityMismatch):
            r.resolve_supervisor_identity(
                REGISTRY_BYTES,
                expected_registry_hash=REGISTRY_HASH,
                component_key="TRUE_RESEARCH",
                artifact_fetcher=lambda artifact_id: b"tampered",
            )

    def test_noncanonical_component_fails_closed(self):
        bad = json.loads(REGISTRY_BYTES)
        bad["components"][0]["exact_status"] = "PROPOSED"
        raw = json.dumps(bad, sort_keys=True).encode()
        h = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(r.AuthorityMismatch):
            r.resolve_supervisor_identity(
                raw,
                expected_registry_hash=h,
                component_key="TRUE_RESEARCH",
                artifact_fetcher=lambda artifact_id: ARTIFACT,
            )

    def test_missing_component_fails_closed(self):
        registry = r.load_verified_registry(REGISTRY_BYTES, expected_registry_hash=REGISTRY_HASH)
        with self.assertRaises(r.ResolutionError):
            r.resolve_component(registry, component_key="TRUE_DOCTOR")

    def test_execution_policy_is_not_baked_into_identity(self):
        identity, prompt = r.resolve_supervisor_identity(
            REGISTRY_BYTES,
            expected_registry_hash=REGISTRY_HASH,
            component_key="TRUE_RESEARCH",
            artifact_fetcher=lambda artifact_id: ARTIFACT,
        )
        out = r.build_dispatch_resolution(
            identity,
            prompt,
            model="gpt-5.6-luna",
            tool_profile=[{"type": "web_search"}],
            reasoning_effort="high",
        )
        self.assertEqual(out["model"], "gpt-5.6-luna")
        self.assertEqual(out["tool_profile"], [{"type": "web_search"}])
        self.assertIn(ARTIFACT_HASH, out["prompt_source"])
        self.assertEqual(out["authority_evidence"]["registry_hash"], REGISTRY_HASH)


if __name__ == "__main__":
    unittest.main()
