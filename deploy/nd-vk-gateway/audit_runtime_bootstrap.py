#!/usr/bin/env python3
"""Fail-closed audit for ND VK packaged runtime.

The production-ready packaged tree must not acquire executable source or OS
packages during process startup. External application APIs (VK, Google, Groq,
OpenRouter, Yandex, GitHub data reads) are not prohibited by this audit; only
bootstrap/code acquisition and runtime package installation are.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

TEXT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".sh", ".toml", ".yaml", ".yml"}

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("RAW_GITHUB_EXECUTABLE_FETCH", re.compile(r"raw\.githubusercontent\.com", re.I)),
    ("RUNTIME_APK_INSTALL", re.compile(r"(?:^|[;&|\s])apk\s+add\b", re.I)),
    ("RUNTIME_APT_INSTALL", re.compile(r"(?:^|[;&|\s])apt(?:-get)?\s+install\b", re.I)),
    ("RUNTIME_PIP_INSTALL", re.compile(r"(?:^|[;&|\s])pip(?:3)?\s+install\b", re.I)),
    ("RUNTIME_NPM_INSTALL", re.compile(r"(?:^|[;&|\s])npm\s+(?:i|install)\b", re.I)),
)

# Build recipes are allowed to install packages at image-build time. They are
# excluded only by exact filename, not by arbitrary path, so embedded startup
# scripts still fail the audit.
BUILD_RECIPE_NAMES = {"Dockerfile", "Containerfile"}


def iter_text_files(root: pathlib.Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in BUILD_RECIPE_NAMES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def audit(root: pathlib.Path) -> list[tuple[str, pathlib.Path, int, str]]:
    violations: list[tuple[str, pathlib.Path, int, str]] = []
    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for rule_name, pattern in RULES:
                if pattern.search(line):
                    violations.append((rule_name, path, line_no, line.strip()[:300]))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", help="packaged runtime tree")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"AUDIT_ERROR root_not_directory: {root}", file=sys.stderr)
        return 2

    violations = audit(root)
    if violations:
        print(f"ND_VK_RUNTIME_BOOTSTRAP_AUDIT FAIL violations={len(violations)}")
        for rule, path, line_no, excerpt in violations:
            rel = path.relative_to(root)
            print(f"{rule} {rel}:{line_no}: {excerpt}")
        return 1

    print("ND_VK_RUNTIME_BOOTSTRAP_AUDIT PASS runtime_code_fetches=0 runtime_package_installs=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
