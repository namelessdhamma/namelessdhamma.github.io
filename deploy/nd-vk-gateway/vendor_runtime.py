#!/usr/bin/env python3
"""Vendor the exact pinned V53 dependency graph at image-build time.

Every pinned raw-GitHub URL is rewritten to ndvendor:// so the running service
cannot accidentally execute code fetched from GitHub. Normal provider/API HTTP
traffic is untouched.

The one qualified semantic successor patch currently folded into the immutable
artifact is the readonly-vault orientation path correction. It is applied only
to the exact pinned V13 source and fails closed on marker drift. This avoids
adding a V54 runtime wrapper/monkey-patch layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import urllib.request

REPO = "namelessdhamma/namelessdhamma.github.io"
RAW_PREFIX = f"https://raw.githubusercontent.com/{REPO}/"
VENDOR_PREFIX = "ndvendor://namelessdhamma.github.io/"
PIN_RE = re.compile(r"^(?P<path>.+)@(?P<commit>[0-9a-f]{40})$")

VAULT_PATH_PATCH_PIN = (
    "tmp/nd_vk_gateway_v13_nd_readonly.py@"
    "9ebbfe3c8dbeb9a57f23e63c34527d5e3afd46fc"
)
VAULT_PATHS_OLD = "paths=['00 СЕЙЧАС.md','01 ТЕМЫ.md','02 РЕШЕНИЯ.md','03 ИЗМЕНЕНИЯ.md']"
VAULT_PATHS_NEW = "paths=['00 ตอนนี้ — Now.md','01 แผนที่ — Maps.md','02 หัวข้อ — Topics.md','03 การเปลี่ยนแปลง — Changes.md']"


def parse_pin(pin: str) -> tuple[str, str]:
    match = PIN_RE.fullmatch(pin)
    if not match:
        raise ValueError(f"invalid pinned source: {pin!r}")
    return match.group("path"), match.group("commit")


def collect_pins(lock: dict) -> list[str]:
    pins: set[str] = set()
    for edge in lock.get("observed_dependency_edges", []):
        pins.add(edge["to"])
    for pin in lock.get("terminal_sources_observed_without_further_raw_bootstrap", []):
        pins.add(pin)
    return sorted(pins)


def rewrite_runtime_bootstrap(text: str) -> str:
    return text.replace(RAW_PREFIX, VENDOR_PREFIX)


def apply_qualified_successor_patches(pin: str, text: str) -> tuple[str, list[str]]:
    patches: list[str] = []
    if pin == VAULT_PATH_PATCH_PIN:
        count = text.count(VAULT_PATHS_OLD)
        if count != 1:
            raise RuntimeError(
                f"readonly vault path marker drift for {pin}: expected exactly 1, got {count}"
            )
        if VAULT_PATHS_NEW in text:
            raise RuntimeError(f"readonly vault path successor already present unexpectedly in {pin}")
        text = text.replace(VAULT_PATHS_OLD, VAULT_PATHS_NEW, 1)
        if VAULT_PATHS_OLD in text or VAULT_PATHS_NEW not in text:
            raise RuntimeError(f"readonly vault path successor invariant failed for {pin}")
        patches.append("readonly_vault_orientation_paths_v54")
    return text, patches


def vendor(lock_path: pathlib.Path, out_root: pathlib.Path) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("graph_status") != "OBSERVED_RUNTIME_BOOTSTRAP_GRAPH_CLOSED_FOR_CURRENT_V53_CHAIN":
        raise RuntimeError("dependency graph is not closed; refusing to package")

    entries = []
    for pin in collect_pins(lock):
        rel_path, commit = parse_pin(pin)
        url = f"{RAW_PREFIX}{commit}/{rel_path}"
        with urllib.request.urlopen(url, timeout=45) as response:
            raw = response.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"non-UTF8 executable dependency: {pin}") from exc

        text, patches = apply_qualified_successor_patches(pin, text)
        transformed = rewrite_runtime_bootstrap(text).encode("utf-8")
        if RAW_PREFIX.encode() in transformed:
            raise RuntimeError(f"unrewritten raw GitHub bootstrap URL remains in {pin}")
        target = out_root / commit / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(transformed)
        entries.append(
            {
                "pin": pin,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "packaged_sha256": hashlib.sha256(transformed).hexdigest(),
                "bytes": len(transformed),
                "qualified_successor_patches": patches,
            }
        )

    manifest = {
        "schema_version": 1,
        "dependency_lock_name": lock_path.name,
        "entries": entries,
        "runtime_raw_github_fetches_expected": 0,
        "qualified_successor_patches_expected": ["readonly_vault_orientation_paths_v54"],
    }
    applied = {
        patch
        for entry in entries
        for patch in entry.get("qualified_successor_patches", [])
    }
    if applied != set(manifest["qualified_successor_patches_expected"]):
        raise RuntimeError(
            "qualified successor patch set mismatch: "
            f"expected={manifest['qualified_successor_patches_expected']} applied={sorted(applied)}"
        )
    (out_root / "vendor-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = vendor(pathlib.Path(args.lock), pathlib.Path(args.out))
    print(f"ND_VK_VENDOR_COMPLETE entries={len(manifest['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
