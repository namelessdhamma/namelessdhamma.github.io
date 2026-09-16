"""Portable MCP JSON-RPC protocol core for ND Social Direct MCP Stage 2.

This is transport-neutral. Vercel/HTTP wiring is deliberately separate so the
protocol can be tested without network access or credentials.
"""
from __future__ import annotations
from typing import Any, Dict, Mapping
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
ADAPTER_PATH=HERE/"nd_social_direct_adapters_v01.py"
_spec=importlib.util.spec_from_file_location("nd_social_direct_adapters_v01",ADAPTER_PATH)
adapters=importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(adapters)

PROTOCOL_VERSION="2025-06-18"
SERVER_INFO={"name":"nd-social-direct-mcp","version":"0.1.0-stage2"}

def _result(rid: Any, result: Any) -> Dict[str,Any]:
    return {"jsonrpc":"2.0","id":rid,"result":result}

def _error(rid: Any, code: int, message: str, data: Any=None) -> Dict[str,Any]:
    out={"jsonrpc":"2.0","id":rid,"error":{"code":code,"message":message}}
    if data is not None:
        out["error"]["data"]=data
    return out

def _tool_content(obj: Mapping[str,Any]) -> Dict[str,Any]:
    import json
    return {
        "content":[{"type":"text","text":json.dumps(dict(obj),ensure_ascii=False,sort_keys=True)}],
        "structuredContent":dict(obj),
        "isError":not bool(obj.get("ok",True)),
    }

def handle_jsonrpc(payload: Any, environ: Mapping[str,str] | None=None) -> Dict[str,Any] | None:
    if not isinstance(payload,Mapping):
        return _error(None,-32600,"Invalid Request")
    method=str(payload.get("method") or "")
    rid=payload.get("id")
    params=payload.get("params") or {}
    if method=="initialize":
        return _result(rid,{
            "protocolVersion":PROTOCOL_VERSION,
            "capabilities":{"tools":{"listChanged":False}},
            "serverInfo":SERVER_INFO,
            "instructions":"ND Social Direct MCP Stage 2. Provider writes fail closed until authorization and qualification are complete."
        })
    if method=="notifications/initialized":
        return None
    if method=="ping":
        return _result(rid,{})
    if method=="tools/list":
        return _result(rid,{"tools":list(adapters.mcp_tools())})
    if method=="tools/call":
        if not isinstance(params,Mapping):
            return _error(rid,-32602,"Invalid params")
        name=str(params.get("name") or "")
        arguments=params.get("arguments") or {}
        try:
            out=adapters.handle_stage2_tool(name,arguments,environ)
            return _result(rid,_tool_content(out))
        except Exception as e:
            return _result(rid,_tool_content({"ok":False,"error":str(e)[:800]}))
    return _error(rid,-32601,"Method not found")

def structural_selftest() -> Dict[str,Any]:
    failures=[]
    init=handle_jsonrpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
    if (init or {}).get("result",{}).get("protocolVersion")!=PROTOCOL_VERSION:
        failures.append("initialize")
    tools=handle_jsonrpc({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
    names=[x.get("name") for x in ((tools or {}).get("result",{}).get("tools") or [])]
    expected=["social_direct_status","social_direct_auth_requirements","social_direct_invoke"]
    if names!=expected:
        failures.append("tools_list")
    status=handle_jsonrpc({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"social_direct_status","arguments":{"provider":"youtube"}}},{})
    if not status or "result" not in status:
        failures.append("tools_call_status")
    write=handle_jsonrpc({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"social_direct_invoke","arguments":{"provider":"youtube","operation":"publish"}}},{})
    sc=((write or {}).get("result") or {}).get("structuredContent") or {}
    if sc.get("ok") is not False or sc.get("error")!="provider_write_not_enabled_before_qualification":
        failures.append("write_fail_closed")
    return {"ok":not failures,"protocol":PROTOCOL_VERSION,"server":SERVER_INFO["name"],"failures":failures}
