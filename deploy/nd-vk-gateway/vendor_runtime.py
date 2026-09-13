#!/usr/bin/env python3
"""Vendor the exact pinned V53 dependency graph at image-build time."""
from __future__ import annotations

import argparse, hashlib, json, pathlib, re, urllib.request

REPO = "namelessdhamma/namelessdhamma.github.io"
RAW_PREFIX = f"https://raw.githubusercontent.com/{REPO}/"
VENDOR_PREFIX = "ndvendor://namelessdhamma.github.io/"
PIN_RE = re.compile(r"^(?P<path>.+)@(?P<commit>[0-9a-f]{40})$")

VAULT_PATH_PATCH_PIN = "tmp/nd_vk_gateway_v13_nd_readonly.py@9ebbfe3c8dbeb9a57f23e63c34527d5e3afd46fc"
VAULT_PATHS_OLD = "paths=['00 СЕЙЧАС.md','01 ТЕМЫ.md','02 РЕШЕНИЯ.md','03 ИЗМЕНЕНИЯ.md']"
VAULT_PATHS_NEW = "paths=['00 ตอนนี้ — Now.md','01 แผนที่ — Maps.md','02 หัวข้อ — Topics.md','03 การเปลี่ยนแปลง — Changes.md']"

V36_CONTEXT_PATCH_PIN = "tmp/nd_vk_gateway_v36_father_ux_research.py@835a07aa1af8a66ee4b9643a266e012b329b6190"
V36_BROKER_OLD = """def broker_invoke(tool,q):
    base=os.environ.get('ND_GOOGLE_GATEWAY_URL','').rstrip('/')
    key=os.environ.get('QSTASH_TOKEN','')
    if not base or not key:raise RuntimeError('safe tool broker unavailable')
    payload=json.dumps({'tool':tool,'query':(q or '')[:9000]},ensure_ascii=False).encode()
"""
V36_BROKER_NEW = """def broker_invoke(tool,q='',args=None):
    base=os.environ.get('ND_GOOGLE_GATEWAY_URL','').rstrip('/')
    key=os.environ.get('QSTASH_TOKEN','')
    if not base or not key:raise RuntimeError('safe tool broker unavailable')
    request_obj={'tool':tool,'query':(q or '')[:9000]}
    if args is not None:request_obj['args']=args
    payload=json.dumps(request_obj,ensure_ascii=False).encode()
"""

V9_CONTEXT_PATCH_PIN = "tmp/nd_vk_gateway_v9_free_router.py@c617c9b200cb1637fca544985d35ab2a1b8d9e08"
V9_IMPORT_ANCHOR = "from urllib.error import HTTPError\n"
V9_IMPORT_NEW = V9_IMPORT_ANCHOR + "from context_gateway import dispatch as nd_context_dispatch\n"
V9_DISPATCH_OLD = "last_call[uid]=time.time();send(peer,routed_response(uid,text or 'Продолжи.'))"
V9_DISPATCH_NEW = """last_call[uid]=time.time()
                def _nd_responder(_uid,_text,_history):return routed_response(_uid,_text)
                send(peer,nd_context_dispatch(uid,text or 'Продолжи.',eid,_nd_responder,history_by_uid,broker_invoke,mode_by_uid))"""


def parse_pin(pin: str) -> tuple[str, str]:
    m=PIN_RE.fullmatch(pin)
    if not m: raise ValueError(f"invalid pinned source: {pin!r}")
    return m.group('path'),m.group('commit')

def collect_pins(lock: dict) -> list[str]:
    pins=set()
    for edge in lock.get('observed_dependency_edges',[]):pins.add(edge['to'])
    for pin in lock.get('terminal_sources_observed_without_further_raw_bootstrap',[]):pins.add(pin)
    return sorted(pins)

def rewrite_runtime_bootstrap(text: str) -> str:return text.replace(RAW_PREFIX,VENDOR_PREFIX)

def _replace_exact(text:str, old:str, new:str, label:str)->str:
    count=text.count(old)
    if count!=1:raise RuntimeError(f"{label} marker drift: expected exactly 1, got {count}")
    if new in text:raise RuntimeError(f"{label} successor already present unexpectedly")
    out=text.replace(old,new,1)
    if old in out or new not in out:raise RuntimeError(f"{label} successor invariant failed")
    return out

def apply_qualified_successor_patches(pin: str, text: str) -> tuple[str,list[str]]:
    patches=[]
    if pin==VAULT_PATH_PATCH_PIN:
        text=_replace_exact(text,VAULT_PATHS_OLD,VAULT_PATHS_NEW,'readonly vault path')
        patches.append('readonly_vault_orientation_paths_v54')
    elif pin==V36_CONTEXT_PATCH_PIN:
        text=_replace_exact(text,V36_BROKER_OLD,V36_BROKER_NEW,'V36 broker args')
        patches.append('context_broker_args_v1')
    elif pin==V9_CONTEXT_PATCH_PIN:
        text=_replace_exact(text,V9_IMPORT_ANCHOR,V9_IMPORT_NEW,'V9 context import')
        text=_replace_exact(text,V9_DISPATCH_OLD,V9_DISPATCH_NEW,'V9 context dispatch')
        patches.append('context_dispatch_hook_v1')
    return text,patches

def vendor(lock_path:pathlib.Path,out_root:pathlib.Path)->dict:
    lock=json.loads(lock_path.read_text(encoding='utf-8'))
    if lock.get('graph_status')!='OBSERVED_RUNTIME_BOOTSTRAP_GRAPH_CLOSED_FOR_CURRENT_V53_CHAIN':
        raise RuntimeError('dependency graph is not closed; refusing to package')
    entries=[]
    for pin in collect_pins(lock):
        rel_path,commit=parse_pin(pin);url=f"{RAW_PREFIX}{commit}/{rel_path}"
        with urllib.request.urlopen(url,timeout=45) as response:raw=response.read()
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError as exc:raise RuntimeError(f"non-UTF8 executable dependency: {pin}") from exc
        text,patches=apply_qualified_successor_patches(pin,text)
        transformed=rewrite_runtime_bootstrap(text).encode('utf-8')
        if RAW_PREFIX.encode() in transformed:raise RuntimeError(f"unrewritten raw GitHub bootstrap URL remains in {pin}")
        target=out_root/commit/rel_path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(transformed)
        entries.append({'pin':pin,'source_sha256':hashlib.sha256(raw).hexdigest(),'packaged_sha256':hashlib.sha256(transformed).hexdigest(),'bytes':len(transformed),'qualified_successor_patches':patches})
    manifest={'schema_version':1,'dependency_lock_name':lock_path.name,'entries':entries,'runtime_raw_github_fetches_expected':0,
              'qualified_successor_patches_expected':['readonly_vault_orientation_paths_v54','context_broker_args_v1','context_dispatch_hook_v1']}
    applied={p for e in entries for p in e.get('qualified_successor_patches',[])}
    if applied!=set(manifest['qualified_successor_patches_expected']):
        raise RuntimeError(f"qualified successor patch set mismatch: expected={manifest['qualified_successor_patches_expected']} applied={sorted(applied)}")
    (out_root/'vendor-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--lock',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    manifest=vendor(pathlib.Path(a.lock),pathlib.Path(a.out));print(f"ND_VK_VENDOR_COMPLETE entries={len(manifest['entries'])}");return 0
if __name__=='__main__':raise SystemExit(main())
