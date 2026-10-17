#!/usr/bin/env python3
"""A5 native CI preflight: run every current numbered source regression.

The old shell glob ``test_a5_v1[2-3][0-9]*.py`` silently excluded v140+.
Discover by numeric version instead, so new current tests cannot fall out of
the native acceptance path as A5 advances beyond a decade boundary.
This is a SOURCE regression, not Godot execution or real-phone evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

_TEST_PATTERN = re.compile(r"^test_a5_v(\d+)(?:_[a-zA-Z0-9_]+)?\.py$")


def discover_tests(test_dir: Path, min_version: int = 120) -> list[Path]:
    selected: list[tuple[int, str, Path]] = []
    for candidate in test_dir.glob("test_a5_v*.py"):
        match = _TEST_PATTERN.fullmatch(candidate.name)
        if match and int(match.group(1)) >= min_version:
            selected.append((int(match.group(1)), candidate.name, candidate))
    selected.sort()
    return [entry[2] for entry in selected]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-version", type=int, default=120)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--exclude-version", type=int, action="append", default=[],
                        help="Explicitly quarantine a historical numbered version; always reported")
    args = parser.parse_args(argv)
    if args.min_version < 1:
        parser.error("--min-version must be positive")

    project_root = Path(__file__).resolve().parents[1]
    all_files = discover_tests(project_root / "tests", args.min_version)
    excluded = sorted(set(args.exclude_version))
    available_versions = {int(_TEST_PATTERN.fullmatch(p.name).group(1)) for p in all_files}
    if any(v not in available_versions for v in excluded):
        print("A5_NATIVE_CI_QUARANTINE_ERROR unknown version requested", file=sys.stderr)
        return 2
    files = [p for p in all_files
             if int(_TEST_PATTERN.fullmatch(p.name).group(1)) not in excluded]
    if excluded:
        print(f"A5_HISTORICAL_QUARANTINE_NOT_GREEN versions={','.join(map(str, excluded))}",
              flush=True)
    if not files:
        print("A5_NATIVE_CI_FRONTIER_ERROR no current tests found", file=sys.stderr)
        return 2
    versions = sorted({int(_TEST_PATTERN.fullmatch(p.name).group(1)) for p in files})
    print(
        f"A5_NATIVE_CI_FRONTIER selected={len(files)} "
        f"min={versions[0]} max={versions[-1]}",
        flush=True,
    )
    for file in files:
        print(file.relative_to(project_root), flush=True)
    if args.list_only:
        return 0
    command = [
        sys.executable, "-m", "pytest", "-q",
        *(str(p.relative_to(project_root)) for p in files),
        "--tb=short",
    ]
    return subprocess.call(command, cwd=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
