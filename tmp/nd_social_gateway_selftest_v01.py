#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
core_path=ROOT/"nd_social_gateway_core_v01.py"
manifest_path=ROOT/"nd_social_gateway_manifest_v01.json"

spec=importlib.util.spec_from_file_location("nd_social_gateway_core_v01",core_path)
core=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(core)

manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
errors=[]

result=core.structural_selftest()
if not result.get("ok"):
    errors.append("core_structural_selftest:"+repr(result.get("failures")))

if manifest.get("gateway_id") != core.GATEWAY_ID:
    errors.append("gateway_id_mismatch")
if manifest.get("gateway_version") != core.GATEWAY_VERSION:
    errors.append("gateway_version_mismatch")

policy=manifest.get("execution_policy") or {}
if tuple(policy.get("route_order") or ()) != core.ROUTE_ORDER:
    errors.append("manifest_route_order")
if policy.get("new_railway_service_allowed") is not False:
    errors.append("new_railway_service_must_be_false")
if policy.get("failed_route_is_not_failed_capability") is not True:
    errors.append("failed_route_invariant_missing")
if policy.get("browserless_enabled") is not False:
    errors.append("browserless_must_be_disabled")
if policy.get("tinyfish_enabled") is not False:
    errors.append("tinyfish_must_be_disabled")

providers=manifest.get("providers") or {}
if set(providers) != set(core.PROVIDERS):
    errors.append("provider_set_mismatch")

for provider in core.PROVIDERS:
    entry=providers.get(provider) or {}
    routes=entry.get("routes") or {}
    if tuple(routes.keys()) != core.ROUTE_ORDER:
        errors.append(provider+":route_order_or_set")
    ops=entry.get("operations") or []
    unknown=[op for op in ops if op not in core.OPERATIONS]
    if unknown:
        errors.append(provider+":unknown_operations:"+",".join(unknown))
    for route in core.ROUTE_ORDER:
        state=str((routes.get(route) or {}).get("state") or "").upper()
        if state not in core.ROUTE_STATE_VALUES:
            errors.append(provider+":"+route+":bad_state")

# Explicit failover invariant: Direct failure must select GitHub before Railway/Kernel.
synthetic={
    "vk":{
        "direct_mcp":{"state":"FAIL","healthy":False,"qualified":True},
        "github":{"state":"PASS","healthy":True,"qualified":True},
        "railway":{"state":"PASS","healthy":True,"qualified":True},
        "kernel":{"state":"PASS","healthy":True,"qualified":True},
    }
}
selected=core.resolve_route("vk","status",synthetic)
if selected.get("selected_route")!="github":
    errors.append("failover_precedence")

summary={
    "ok":not errors,
    "gateway":core.GATEWAY_ID,
    "version":core.GATEWAY_VERSION,
    "providers":len(core.PROVIDERS),
    "routes_per_provider":len(core.ROUTE_ORDER),
    "operations":len(core.OPERATIONS),
    "errors":errors,
}
print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
raise SystemExit(0 if not errors else 1)
