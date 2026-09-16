"""ND Social Gateway v0.1 qualification core.

Pure routing/capability layer. It intentionally contains no credentials and performs
no social-network writes. Provider adapters are attached in later stages.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

GATEWAY_ID = "nd-social-gateway"
GATEWAY_VERSION = "0.1.0-qualification"
ROUTE_ORDER: Tuple[str, ...] = ("direct_mcp", "github", "railway", "kernel")
PROVIDERS: Tuple[str, ...] = (
    "youtube", "telegram", "instagram", "facebook",
    "tiktok", "vk", "line", "dzen",
)
OPERATIONS: Tuple[str, ...] = (
    "status", "account", "publish", "schedule",
    "edit", "delete", "metrics", "comments",
)

ROUTE_STATE_VALUES = {
    "PASS", "READY", "AWAITING_AUTH", "PLANNED",
    "REPAIR_REQUIRED", "EXISTS_UNQUALIFIED_FOR_SMM",
    "UNRESOLVED", "FAIL", "DISABLED",
}

DEFAULT_ROUTE_STATE: Dict[str, Dict[str, Any]] = {
    provider: {
        route: {
            "state": "PLANNED",
            "healthy": False,
            "qualified": False,
            "last_error": None,
        }
        for route in ROUTE_ORDER
    }
    for provider in PROVIDERS
}


class SocialGatewayError(ValueError):
    pass


def normalize_provider(provider: Any) -> str:
    value = str(provider or "").strip().lower()
    if value not in PROVIDERS:
        raise SocialGatewayError("unsupported_provider")
    return value


def normalize_operation(operation: Any) -> str:
    value = str(operation or "").strip().lower()
    if value not in OPERATIONS:
        raise SocialGatewayError("unsupported_operation")
    return value


def validate_route_state(route_health: Optional[Mapping[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    state = deepcopy(DEFAULT_ROUTE_STATE)
    if route_health is None:
        return state
    if not isinstance(route_health, Mapping):
        raise SocialGatewayError("route_health_must_be_object")
    for provider, routes in route_health.items():
        p = normalize_provider(provider)
        if not isinstance(routes, Mapping):
            raise SocialGatewayError("provider_routes_must_be_object")
        for route, entry in routes.items():
            r = str(route or "").strip()
            if r not in ROUTE_ORDER:
                raise SocialGatewayError("unsupported_route")
            if not isinstance(entry, Mapping):
                raise SocialGatewayError("route_entry_must_be_object")
            new_entry = dict(state[p][r])
            if "state" in entry:
                s = str(entry["state"] or "").strip().upper()
                if s not in ROUTE_STATE_VALUES:
                    raise SocialGatewayError("unsupported_route_state")
                new_entry["state"] = s
            if "healthy" in entry:
                new_entry["healthy"] = bool(entry["healthy"])
            if "qualified" in entry:
                new_entry["qualified"] = bool(entry["qualified"])
            if "last_error" in entry:
                new_entry["last_error"] = None if entry["last_error"] is None else str(entry["last_error"])[:1000]
            state[p][r] = new_entry
    return state


def resolve_route(
    provider: Any,
    operation: Any,
    route_health: Optional[Mapping[str, Any]] = None,
    *,
    require_qualified: bool = True,
) -> Dict[str, Any]:
    p = normalize_provider(provider)
    op = normalize_operation(operation)
    health = validate_route_state(route_health)
    checked: List[Dict[str, Any]] = []
    for route in ROUTE_ORDER:
        entry = dict(health[p][route])
        eligible = bool(entry.get("healthy"))
        if require_qualified:
            eligible = eligible and bool(entry.get("qualified"))
        checked.append({"route": route, **entry, "eligible": eligible})
        if eligible:
            return {
                "ok": True,
                "gateway": GATEWAY_ID,
                "version": GATEWAY_VERSION,
                "provider": p,
                "operation": op,
                "selected_route": route,
                "checked": checked,
            }
    return {
        "ok": False,
        "gateway": GATEWAY_ID,
        "version": GATEWAY_VERSION,
        "provider": p,
        "operation": op,
        "selected_route": None,
        "checked": checked,
        "error": "no_qualified_healthy_route",
    }


def validate_request(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SocialGatewayError("request_must_be_object")
    provider = normalize_provider(payload.get("provider"))
    operation = normalize_operation(payload.get("operation"))
    args = payload.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, Mapping):
        raise SocialGatewayError("args_must_be_object")
    request_id = str(payload.get("request_id") or "").strip()[:200]
    return {
        "provider": provider,
        "operation": operation,
        "args": dict(args),
        "request_id": request_id,
    }


def capability_contract() -> Dict[str, Any]:
    return {
        "gateway": GATEWAY_ID,
        "version": GATEWAY_VERSION,
        "providers": list(PROVIDERS),
        "operations": list(OPERATIONS),
        "route_order": list(ROUTE_ORDER),
        "invariants": {
            "host_reuse_first": True,
            "new_railway_service_allowed": False,
            "failed_route_is_not_failed_capability": True,
            "browserless_enabled": False,
            "tinyfish_enabled": False,
        },
    }


def structural_selftest() -> Dict[str, Any]:
    failures: List[str] = []
    if len(PROVIDERS) != 8:
        failures.append("provider_count")
    if ROUTE_ORDER != ("direct_mcp", "github", "railway", "kernel"):
        failures.append("route_order")
    if len(set(PROVIDERS)) != len(PROVIDERS):
        failures.append("duplicate_provider")
    if len(set(OPERATIONS)) != len(OPERATIONS):
        failures.append("duplicate_operation")

    synthetic = {
        "youtube": {
            "direct_mcp": {"state": "FAIL", "healthy": False, "qualified": True},
            "github": {"state": "PASS", "healthy": True, "qualified": True},
            "railway": {"state": "PASS", "healthy": True, "qualified": True},
            "kernel": {"state": "PASS", "healthy": True, "qualified": True},
        }
    }
    result = resolve_route("youtube", "status", synthetic)
    if result.get("selected_route") != "github":
        failures.append("failover_order")

    no_route = resolve_route("telegram", "publish", {})
    if no_route.get("ok") is not False:
        failures.append("default_must_not_claim_ready")

    return {
        "ok": not failures,
        "gateway": GATEWAY_ID,
        "version": GATEWAY_VERSION,
        "failures": failures,
        "provider_count": len(PROVIDERS),
        "route_count_per_provider": len(ROUTE_ORDER),
        "operation_count": len(OPERATIONS),
    }
