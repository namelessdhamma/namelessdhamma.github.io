"""Durable state adapter for ND VK Father context memory.

This adapter is pinned to the existing Father Comment Sandbox contract:
  sandbox_shared_note(args.content, args.idempotency_key, ...)
  sandbox_update(args.artifact_id, args.content, args.idempotency_key, ...)
  sandbox_read(args.artifact_id) -> result.content

The broker, not the caller, fixes sandbox_shared_note to Father Workspace / Shared Notes.
No folder/parent override is sent. Memory remains NON_AUTHORITATIVE operational state.
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
    """Version context state through the existing bounded Shared Notes ledger.

    The current broker does not expose an atomic compare-and-swap argument. For an update this
    adapter therefore performs an explicit latest-state read and rejects a stale previous_state
    before writing, then requires exact read-back. The gateway integration must additionally keep
    one in-flight state mutation per VK user; overlapping deployments remain a promotion-time
    exclusion rather than something this adapter pretends to solve atomically.
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
        body = raw.get("content") or raw.get("body") or raw.get("text")
        if not isinstance(body, str):
            raise MemoryStoreError("read-back missing content")
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
        if int(env.get("generation", -1)) != int(state.get("generation", -2)):
            raise MemoryStoreError("memory envelope generation mismatch")
        return state

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.artifact_id:
            return None
        raw = self.broker_call("sandbox_read", {"artifact_id": self.artifact_id})
        return self._parse(raw)

    def _common_args(self, body: str, key: str) -> Dict[str, Any]:
        return {
            "content": body,
            "idempotency_key": key,
            "actor": "vk_ai_assistant",
            "sender_vk_id": self.user_id,
            "gateway_version": "vk-context-memory-v1",
            "source_ref": f"vk-context-state:{self.user_id}",
            "source_refs": [],
        }

    def save(self, state: Dict[str, Any], previous_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = self._body(state)
        digest = state_hash(state)
        generation = int(state.get("generation", 0))
        key = f"vk-context:{self.user_id}:g{generation}:{digest[:20]}"

        if self.artifact_id is None:
            payload = self._common_args(body, key)
            payload["title"] = STATE_TITLE
            result = self.broker_call("sandbox_shared_note", payload)
            aid = result.get("artifact_id") or result.get("id")
            if not aid:
                raise MemoryStoreError("create did not return artifact_id")
            if result.get("read_back_verified") is not True:
                raise MemoryStoreError("broker did not verify create read-back")
            self.artifact_id = str(aid)
        else:
            if previous_state is None:
                raise MemoryStoreError("previous_state required for guarded update")
            if str(previous_state.get("user_id")) != self.user_id:
                raise MemoryStoreError("previous state user mismatch")
            if generation <= int(previous_state.get("generation", -1)):
                raise MemoryStoreError("non-monotonic state generation")

            # Fail closed on stale local state. This is a precondition check, not an atomic CAS;
            # gateway integration serializes mutations per user and deployment promotion forbids
            # overlapping writers.
            latest = self.load()
            if latest is None or state_hash(latest) != state_hash(previous_state):
                raise MemoryStoreError("stale previous state")

            payload = self._common_args(body, key)
            payload["artifact_id"] = self.artifact_id
            result = self.broker_call("sandbox_update", payload)
            if str(result.get("artifact_id") or "") != self.artifact_id:
                raise MemoryStoreError("update artifact identity mismatch")
            if result.get("read_back_verified") is not True:
                raise MemoryStoreError("broker did not verify update read-back")

        # Mandatory adapter-level exact read-back. Save is not acknowledged before digest equality.
        readback_raw = self.broker_call("sandbox_read", {"artifact_id": self.artifact_id})
        readback = self._parse(readback_raw)
        if state_hash(readback) != digest or int(readback.get("generation", -1)) != generation:
            raise MemoryStoreError("read-back mismatch")
        return {
            "artifact_id": self.artifact_id,
            "generation": generation,
            "sha256": digest,
            "verified": True,
            "atomic_cas": False,
            "boundary": "FATHER_WORKSPACE_SHARED_NOTES_SERVER_FIXED",
        }
