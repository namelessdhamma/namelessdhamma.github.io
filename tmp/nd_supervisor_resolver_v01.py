from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import hashlib
import json


class ResolutionError(RuntimeError):
    pass


class AuthorityMismatch(ResolutionError):
    pass


@dataclass(frozen=True)
class CanonicalSupervisorIdentity:
    component_key: str
    semantic_id: str
    version: str
    exact_status: str
    canonical_artifact_id: str
    canonical_artifact_name: str
    canonical_hash: str
    owner: str
    interfaces: Dict[str, Any]
    read_permissions: list[str]
    write_permissions: list[str]
    registry_id: str
    registry_version: str
    registry_hash: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_verified_registry(
    registry_bytes: bytes,
    *,
    expected_registry_hash: str,
    expected_registry_id: str = "ND_CAPABILITY_REGISTRY",
    expected_registry_version: Optional[str] = None,
) -> Dict[str, Any]:
    actual = sha256_bytes(registry_bytes)
    if actual != expected_registry_hash:
        raise AuthorityMismatch(
            f"registry_hash_mismatch:expected={expected_registry_hash}:actual={actual}"
        )
    try:
        registry = json.loads(registry_bytes.decode("utf-8-sig"))
    except Exception as exc:
        raise ResolutionError("registry_parse_failed:" + str(exc)) from exc

    if registry.get("registry_id") != expected_registry_id:
        raise AuthorityMismatch("registry_id_mismatch")
    if expected_registry_version and registry.get("version") != expected_registry_version:
        raise AuthorityMismatch("registry_version_mismatch")
    if not isinstance(registry.get("components"), list):
        raise ResolutionError("registry_components_missing")
    return registry


def resolve_component(
    registry: Dict[str, Any],
    *,
    component_key: Optional[str] = None,
    semantic_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not component_key and not semantic_id:
        raise ResolutionError("component_key_or_semantic_id_required")

    matches = []
    for component in registry["components"]:
        if component_key and component.get("component_key") != component_key:
            continue
        if semantic_id and component.get("semantic_id") != semantic_id:
            continue
        matches.append(component)

    if len(matches) != 1:
        raise ResolutionError(f"component_resolution_count:{len(matches)}")

    component = matches[0]
    required = [
        "component_key",
        "semantic_id",
        "version",
        "exact_status",
        "canonical_artifact_id",
        "canonical_hash",
        "interfaces",
        "owner",
        "read_permissions",
        "write_permissions",
    ]
    missing = [k for k in required if k not in component]
    if missing:
        raise ResolutionError("component_binding_incomplete:" + ",".join(missing))

    status = str(component.get("exact_status") or "").upper()
    if "ACTIVE" not in status or "CANONICAL" not in status:
        raise AuthorityMismatch("component_not_canonical_active")

    return component


def verify_canonical_artifact(
    component: Dict[str, Any],
    artifact_bytes: bytes,
) -> str:
    expected = str(component["canonical_hash"])
    actual = sha256_bytes(artifact_bytes)
    if actual != expected:
        raise AuthorityMismatch(
            f"canonical_artifact_hash_mismatch:expected={expected}:actual={actual}"
        )
    return actual


def resolve_supervisor_identity(
    registry_bytes: bytes,
    *,
    expected_registry_hash: str,
    artifact_fetcher: Callable[[str], bytes],
    component_key: Optional[str] = None,
    semantic_id: Optional[str] = None,
    expected_registry_version: Optional[str] = None,
) -> tuple[CanonicalSupervisorIdentity, str]:
    registry = load_verified_registry(
        registry_bytes,
        expected_registry_hash=expected_registry_hash,
        expected_registry_version=expected_registry_version,
    )
    component = resolve_component(
        registry,
        component_key=component_key,
        semantic_id=semantic_id,
    )
    artifact_id = str(component["canonical_artifact_id"])
    artifact_bytes = artifact_fetcher(artifact_id)
    verify_canonical_artifact(component, artifact_bytes)

    try:
        prompt = artifact_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ResolutionError("canonical_artifact_not_utf8") from exc

    identity = CanonicalSupervisorIdentity(
        component_key=str(component["component_key"]),
        semantic_id=str(component["semantic_id"]),
        version=str(component["version"]),
        exact_status=str(component["exact_status"]),
        canonical_artifact_id=artifact_id,
        canonical_artifact_name=str(component.get("canonical_artifact_name") or ""),
        canonical_hash=str(component["canonical_hash"]),
        owner=str(component["owner"]),
        interfaces=dict(component["interfaces"]),
        read_permissions=list(component["read_permissions"]),
        write_permissions=list(component["write_permissions"]),
        registry_id=str(registry["registry_id"]),
        registry_version=str(registry["version"]),
        registry_hash=expected_registry_hash,
    )
    return identity, prompt


def build_dispatch_resolution(
    identity: CanonicalSupervisorIdentity,
    prompt: str,
    *,
    model: str,
    tool_profile: list[Dict[str, Any]],
    reasoning_effort: str = "high",
    max_output_tokens: int = 32000,
) -> Dict[str, Any]:
    """
    Execution policy (model/tools/effort) is intentionally supplied by the Agent
    at dispatch time. Canonical supervisor identity/prompt comes from authority.
    This prevents the resolver from becoming a duplicate permanent routing catalog.
    """
    return {
        "supervisor_id": identity.component_key.replace("_", " ").title(),
        "canonical_version": identity.version,
        "prompt_source": (
            f"{identity.registry_id}@{identity.registry_version}:"
            f"{identity.component_key}:{identity.canonical_artifact_id}:"
            f"{identity.canonical_hash}"
        ),
        "prompt_text": prompt,
        "model": model,
        "tool_profile": tool_profile,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "authority_evidence": {
            "semantic_id": identity.semantic_id,
            "exact_status": identity.exact_status,
            "registry_hash": identity.registry_hash,
            "artifact_id": identity.canonical_artifact_id,
            "artifact_hash": identity.canonical_hash,
        },
    }


__all__ = [
    "CanonicalSupervisorIdentity",
    "ResolutionError",
    "AuthorityMismatch",
    "sha256_bytes",
    "load_verified_registry",
    "resolve_component",
    "verify_canonical_artifact",
    "resolve_supervisor_identity",
    "build_dispatch_resolution",
]
