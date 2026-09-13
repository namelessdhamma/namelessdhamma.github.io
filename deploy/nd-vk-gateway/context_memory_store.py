"""Durable state adapter for ND VK Father context memory.

The adapter deliberately depends only on the existing Safe Tool Broker contract and a caller-supplied
`broker_call(tool, payload)` function. It does not know provider/model details and cannot write
outside Father Workspace. Production binding must use the already-qualified broker identity,
ancestry/idempotency/read-back guards.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Optional

STATE_TITLE = "VK Conversation Context State"
STATE_KIND = "VK_CONTEXT_STATE"
STATE_SCHEMA = "ND_VK_CONTEXT_V1"
SHARED_NOTES_FOLDER_ID = "1cF1qB25BZPKmtvgoXXkSMrEh_LnYJiRD"


def _canonical_json(state: Dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def state_hash(state: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(state).encode("utf-8")).hexdigest()


class MemoryStoreError(RuntimeError):
    pass


class FatherWorkspaceMemoryStore:
    """Append/version state through existing bounded sandbox tools.

    Expected broker contract:
      sandbox_shared_note({title, body, idempotency_key, metadata?}) -> created artifact
      sandbox_update({artifact_id, body, idempotency_key, expected_hash?, metadata?}) -> new version
      sandbox_read({artifact_id}) -> body/hash/read-back metadata

    No direct Drive IDs supplied by the caller can override the fixed Shared Notes boundary.
    """

    def __init__(self, broker_call: Callable[[str, Dict[str, Any]], Dict[str, Any]], user_id: str,
                 artifact_id: Optional[str] = None):
        self.broker_call = broker_call
        self.user_id = str(user_id)
        self.artifact_id = artifact_id

    def _body(self, state: Dict[str, Any]) -> str:
        if state.get("schema") != STATE_SCHEMA:
            raise MemoryStoreError("state schema mismatch")
        if str(state.get("user_id")) != self.user_id:
            raise MemoryStoreError("state user mismatch")
        digest = state_hash(state)
        envelope = {
            "kind": STATE_KIND,
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_MEMORY",
            "user_id": self.user_id,
            "schema": STATE_SCHEMA,
            "generation": int(state.get("generation", 0)),
            "sha256": digest,
            "state": state,
        }
        return json.dumps(envelope, ensure_ascii=False, sort_keys=True)

    def _parse(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        body = raw.get("body") or raw.get("content") or raw.get("text")
        if not isinstance(body, str):
            raise MemoryStoreError("read-back missing body")
        try:
            env = json.loads(body)
        except Exception as exc:
            raise MemoryStoreError("invalid memory envelope") from exc
        if env.get("kind") != STATE_KIND or env.get("authority") != "NON_AUTHORITATIVE_OPERATIONAL_MEMORY":
            raise MemoryStoreError("memory envelope classification mismatch")
        if str(env.get("user_id")) != self.user_id or env.get("schema") != STATE_SCHEMA:
            raise MemoryStoreError("memory envelope identity mismatch")
        state = env.get("state")
        if not isinstance(state, dict) or state_hash(state) != env.get("sha256"):
            raise MemoryStoreError("memory envelope digest mismatch")
        return state

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.artifact_id:
            return None
        raw = self.broker_call("sandbox_read", {"artifact_id": self.artifact_id})
        return self._parse(raw)

    def save(self, state: Dict[str, Any], previous_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = self._body(state)
        digest = state_hash(state)
        generation = int(state.get("generation", 0))
        key = f"vk-context:{self.user_id}:g{generation}:{digest[:20]}"
        metadata = {
            "kind": STATE_KIND,
            "schema": STATE_SCHEMA,
            "user_id": self.user_id,
            "generation": generation,
            "sha256": digest,
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_MEMORY",
            "fixed_folder_id": SHARED_NOTES_FOLDER_ID,
        }
        if self.artifact_id is None:
            result = self.broker_call("sandbox_shared_note", {
                "title": STATE_TITLE, "body": body, "idempotency_key": key, "metadata": metadata,
            })
            aid = result.get("artifact_id") or result.get("id")
            if not aid:
                raise MemoryStoreError("create did not return artifact_id")
            self.artifact_id = str(aid)
        else:
            expected_hash = state_hash(previous_state) if previous_state else None
            payload = {"artifact_id": self.artifact_id, "body": body, "idempotency_key": key, "metadata": metadata}
            if expected_hash: payload["expected_hash"] = expected_hash
            result = self.broker_call("sandbox_update", payload)

        # Mandatory exact read-back. Save is not acknowledged before digest equality.
        readback_raw = self.broker_call("sandbox_read", {"artifact_id": self.artifact_id})
        readback = self._parse(readback_raw)
        if state_hash(readback) != digest or int(readback.get("generation", -1)) != generation:
            raise MemoryStoreError("read-back mismatch")
        return {"artifact_id": self.artifact_id, "generation": generation, "sha256": digest, "verified": True}
