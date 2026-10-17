#!/usr/bin/env python3
"""Fail-closed source/art admission check before A5 native Godot qualification.

This gate is NOT native gameplay evidence. It proves that the checked-out tree
contains the exact, complete, versioned source and layered art to be tested.
It deliberately rejects a branch containing only the older five-world shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def digest(data: bytes) -> dict[str, object]:
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
    }


def verify_local(root: Path, manifest: dict) -> list[dict]:
    defects = []
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries:
        return [{"reason": "EMPTY_OR_INVALID_MANIFEST"}]
    for name, expected in sorted(entries.items()):
        # No traversal, absolute path, symlink or other checkout escape.
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or not (
                rel.parts[0] in ("assets", "scripts", "tests", "tools")
                or name in ("project.godot", "main.tscn")):
            defects.append({"file": name, "reason": "INVALID_MANIFEST_PATH"})
            continue
        path = root / rel
        if not path.is_file() or path.is_symlink():
            defects.append({"file": name, "reason": "MISSING_OR_UNSAFE_FILE"})
            continue
        observed = digest(path.read_bytes())
        if observed != expected:
            defects.append({"file": name, "reason": "CONTENT_MISMATCH", "observed": observed})
    # Unknown executable or resource files are also a source drift, not an
    # innocuous addition. Ignore only transient Python test caches.
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "tools/a5_source_admission_manifest_v173.json" or (
                "__pycache__" in path.parts or ".pytest_cache" in path.parts):
            continue
        if (rel in ("project.godot", "main.tscn") or
                path.relative_to(root).parts[0] in ("assets", "scripts", "tests", "tools")) and rel not in entries:
            defects.append({"file": rel, "reason": "UNMANIFESTED_RUNTIME_SOURCE"})
    for key in ("project.godot", "main.tscn", "scripts/main.gd", "scripts/ai_opponent.gd", "scripts/world_visuals.gd"):
        if key not in entries:
            defects.append({"file": key, "reason": "MISSING_CRITICAL_BINDING"})
    if len([name for name in entries if name.startswith("assets/")]) < 280:
        defects.append({"reason": "INCOMPLETE_SEVEN_WORLD_ASSET_SET"})
    if len([name for name in entries if name.startswith("scripts/")]) != 7:
        defects.append({"reason": "INCOMPLETE_SHARED_SCRIPT_SET"})
    return defects


def verify_remote_tree(manifest: dict, tree: dict) -> list[dict]:
    """Compare against a GitHub Git Trees API recursive response (no network)."""
    remote = {item["path"]: item for item in tree.get("tree", []) if item.get("type") == "blob"}
    if tree.get("truncated") is not False:
        return [{"reason": "TRUNCATED_OR_UNKNOWN_REMOTE_TREE"}]
    defects = []
    for path, expected in sorted(manifest["files"].items()):
        item = remote.get("sinee-more-godot/" + path)
        if item is None:
            defects.append({"file": path, "reason": "MISSING_IN_REMOTE_BRANCH"})
        elif item.get("sha") != expected["git_blob_sha1"]:
            defects.append({"file": path, "reason": "REMOTE_CONTENT_MISMATCH"})
    return defects


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("a5_source_admission_manifest_v173.json"))
    parser.add_argument("--tree-json", type=Path, help="optional GitHub recursive tree response for branch admission")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if manifest.get("status") != "A5_STAGING_SOURCE_MANIFEST_NOT_NATIVE_PASS":
            raise ValueError("unexpected manifest status")
        defects = verify_local(args.root.resolve(), manifest)
        if args.tree_json:
            defects += verify_remote_tree(manifest, json.loads(args.tree_json.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("A5_SOURCE_ADMISSION_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    if defects:
        print(json.dumps({"status": "A5_SOURCE_ADMISSION_BLOCKED", "defect_count": len(defects), "defects": defects[:15]}, ensure_ascii=False))
        return 1
    print(f"A5_SOURCE_ADMISSION_LOCAL_PASS files={len(manifest['files'])} "
          f"assets={sum(k.startswith('assets/') for k in manifest['files'])} "
          "NATIVE_AND_REAL_TOUCH_STILL_UNVERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
