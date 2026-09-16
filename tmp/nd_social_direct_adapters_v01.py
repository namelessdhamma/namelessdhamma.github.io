"""Stage 2 direct-provider auth/catalog layer for ND Social Gateway.

No provider write is performed here. This module declares auth requirements,
checks credential presence by environment-variable *name*, and generates the
Developer Mode MCP tool surface that will be hosted on the existing Vercel MCP
project in a later deployment step.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

CATALOG_PATH=Path(__file__).with_name("nd_social_direct_catalog_v01.json")
DIRECT_VERSION="0.1.0-stage2"
PROVIDERS=("youtube","telegram","instagram","facebook","tiktok","vk","line","dzen")

class DirectAdapterError(ValueError):
    pass

def load_catalog() -> Dict[str, Any]:
    obj=json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(obj,dict) or not isinstance(obj.get("providers"),dict):
        raise DirectAdapterError("invalid_catalog")
    return obj

def provider_spec(provider: Any) -> Dict[str, Any]:
    p=str(provider or "").strip().lower()
    if p not in PROVIDERS:
        raise DirectAdapterError("unsupported_provider")
    return dict(load_catalog()["providers"][p])

def auth_readiness(provider: Any, environ: Mapping[str,str] | None=None) -> Dict[str, Any]:
    p=str(provider or "").strip().lower()
    spec=provider_spec(p)
    env=dict(os.environ if environ is None else environ)
    secret_names=list(spec.get("required_secrets") or [])
    id_names=list(spec.get("required_ids") or [])
    missing_secrets=[n for n in secret_names if not str(env.get(n) or "").strip()]
    missing_ids=[n for n in id_names if not str(env.get(n) or "").strip()]
    return {
        "ok": not missing_secrets and not missing_ids,
        "provider":p,
        "catalog_state":spec.get("state"),
        "official_api":bool(spec.get("official_api")),
        "auth_mode":spec.get("auth_mode"),
        "missing_secret_names":missing_secrets,
        "missing_id_names":missing_ids,
        "manual_action":spec.get("manual_action"),
        "callback_url":spec.get("callback_url"),
    }

def all_auth_readiness(environ: Mapping[str,str] | None=None) -> Dict[str,Any]:
    rows={p:auth_readiness(p,environ) for p in PROVIDERS}
    return {
        "ok":all(v["ok"] for v in rows.values()),
        "version":DIRECT_VERSION,
        "providers":rows,
    }

MCP_TOOLS=(
    {
        "name":"social_direct_status",
        "description":"Return direct-route authorization/configuration status for an ND social provider without exposing secrets.",
        "inputSchema":{"type":"object","properties":{"provider":{"type":"string","enum":list(PROVIDERS)}},"required":["provider"],"additionalProperties":False},
    },
    {
        "name":"social_direct_auth_requirements",
        "description":"Return the bounded authorization requirements, callback URL and scopes for an ND social provider.",
        "inputSchema":{"type":"object","properties":{"provider":{"type":"string","enum":list(PROVIDERS)}},"required":["provider"],"additionalProperties":False},
    },
    {
        "name":"social_direct_invoke",
        "description":"Invoke a qualified direct social-provider adapter. Stage 2 fails closed until provider credentials and write qualification are complete.",
        "inputSchema":{
            "type":"object",
            "properties":{
                "provider":{"type":"string","enum":list(PROVIDERS)},
                "operation":{"type":"string","enum":["status","account","publish","schedule","edit","delete","metrics","comments"]},
                "args":{"type":"object"},
                "confirm_write":{"type":"boolean"}
            },
            "required":["provider","operation"],
            "additionalProperties":False
        },
    },
)

def mcp_tools() -> Tuple[Dict[str,Any],...]:
    return tuple(dict(x) for x in MCP_TOOLS)

def handle_stage2_tool(name: str, arguments: Mapping[str,Any] | None=None, environ: Mapping[str,str] | None=None) -> Dict[str,Any]:
    args=dict(arguments or {})
    if name=="social_direct_status":
        return auth_readiness(args.get("provider"),environ)
    if name=="social_direct_auth_requirements":
        p=str(args.get("provider") or "").strip().lower()
        spec=provider_spec(p)
        return {
            "ok":True,
            "provider":p,
            "state":spec.get("state"),
            "official_api":bool(spec.get("official_api")),
            "auth_mode":spec.get("auth_mode"),
            "callback_url":spec.get("callback_url"),
            "authorize_url":spec.get("authorize_url"),
            "token_url":spec.get("token_url"),
            "scopes":list(spec.get("scopes") or []),
            "required_secret_names":list(spec.get("required_secrets") or []),
            "required_id_names":list(spec.get("required_ids") or []),
            "manual_action":spec.get("manual_action"),
            "notes":list(spec.get("notes") or []),
        }
    if name=="social_direct_invoke":
        p=str(args.get("provider") or "").strip().lower()
        readiness=auth_readiness(p,environ)
        return {
            "ok":False,
            "provider":p,
            "operation":str(args.get("operation") or ""),
            "stage":"STAGE_2_AUTH_PREP_ONLY",
            "auth_ready":readiness["ok"],
            "error":"provider_write_not_enabled_before_qualification",
        }
    raise DirectAdapterError("unsupported_tool")

def structural_selftest() -> Dict[str,Any]:
    cat=load_catalog()
    failures=[]
    if cat.get("identity",{}).get("email")!="namelessdhamma@gmail.com":
        failures.append("identity_email")
    if cat.get("identity",{}).get("handle")!="@namelessdhamma":
        failures.append("identity_handle")
    if tuple(cat.get("providers",{}).keys())!=PROVIDERS:
        failures.append("provider_order_or_set")
    host=cat.get("direct_host") or {}
    if host.get("project_name")!="nd-notebooklm-remote-mcp":
        failures.append("direct_host_reuse")
    if host.get("mcp_url")!="https://nd-notebooklm-remote-mcp.vercel.app/api/social-mcp":
        failures.append("mcp_url")
    for p in PROVIDERS:
        spec=cat["providers"][p]
        if not spec.get("state"):
            failures.append(p+":state")
        if not spec.get("auth_mode"):
            failures.append(p+":auth_mode")
        # Never put actual credential values into the repository catalog.
        for k in ("required_secrets","required_ids"):
            vals=spec.get(k) or []
            if not all(isinstance(x,str) and x.startswith(("ND_","VK_")) for x in vals):
                failures.append(p+":"+k)
    blank=all_auth_readiness({})
    if blank.get("ok"):
        failures.append("blank_environment_must_not_be_ready")
    if handle_stage2_tool("social_direct_invoke",{"provider":"youtube","operation":"publish"},{}).get("ok") is not False:
        failures.append("writes_must_fail_closed")
    return {"ok":not failures,"version":DIRECT_VERSION,"providers":len(PROVIDERS),"failures":failures}
