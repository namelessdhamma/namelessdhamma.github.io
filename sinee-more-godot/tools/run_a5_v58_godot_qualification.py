#!/usr/bin/env python3
"""Run real Godot 4.7.2 import, smoke, and 21-match qualification.

This script cannot certify real phone touch or visual parity. It fails closed if
Godot is missing, any process fails, or a required case marker is absent.
"""
import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLDS = range(7)
MODES = ("C", "D", "CD")
CASE = re.compile(r"BLUE_SEA_FULL_MATCH_CASE_PASS world=(\d+) rule=(C|D|CD)\b")


def assess_full_match_log(text: str, returncode: int) -> dict:
    matches = CASE.findall(text)
    expected = {(str(w), mode) for w in WORLDS for mode in MODES}
    observed = set(matches)
    forbidden = any(token in text for token in ("SCRIPT ERROR", "Parse Error", "ERROR:", "ASSERTION FAILED"))
    summary = "BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21" in text
    return {
        "pass": returncode == 0 and not forbidden and summary and len(matches) == 21 and observed == expected,
        "cases_observed": len(matches),
        "unique_cases": len(observed),
        "missing_cases": [f"{w}:{m}" for w, m in sorted(expected - observed)],
        "unexpected_cases": [f"{w}:{m}" for w, m in sorted(observed - expected)],
        "duplicate_cases": len(matches) != len(observed),
        "summary_present": summary,
        "engine_errors_present": forbidden,
        "returncode": returncode,
    }


def run(label: str, command: list[str], timeout: int, output_dir: Path) -> dict:
    result = {"command": command, "pass": False, "returncode": None, "timeout": False}
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                              timeout=timeout, errors="replace")
        log = proc.stdout + "\n" + proc.stderr
        result["returncode"] = proc.returncode
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        log += "\nTIMEOUT: bounded external Godot process exceeded deadline"
        result["timeout"] = True
    log_path = output_dir / f"{label}.log"
    log_path.write_text(log)
    result["log"] = str(log_path)
    result["pass"] = result["returncode"] == 0 and not result["timeout"] and not any(
        s in log for s in ("SCRIPT ERROR", "Parse Error", "ERROR:", "ASSERTION FAILED"))
    if label == "smoke":
        result["pass"] &= "BLUE_SEA_HEADLESS_SMOKE_SUITE_PASS" in log
    if label == "full_match":
        result["qualification"] = assess_full_match_log(log, result["returncode"] if result["returncode"] is not None else -1)
        result["pass"] &= result["qualification"]["pass"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", default=shutil.which("godot") or shutil.which("godot4") or "")
    parser.add_argument("--out", type=Path, default=ROOT / "a5_v58_godot_qualification")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"version": "A5-v58", "time_utc": datetime.now(timezone.utc).isoformat(),
              "godot": args.godot, "project": str(ROOT), "runs": {},
              "playable": "UNVERIFIED", "visual_parity": "UNVERIFIED",
              "real_phone_touch": "NOT_TESTED", "production": "UNCHANGED"}
    if not args.godot or not Path(args.godot).is_file():
        report["blocker"] = "Godot executable not found; no engine checks executed"
        (args.out / "report.json").write_text(json.dumps(report, indent=2))
        print(report["blocker"])
        return 2
    base = [args.godot, "--headless", "--path", str(ROOT)]
    steps = [
        ("version", [args.godot, "--version"]),
        ("import", base + ["--editor", "--import", "--quit"]),
        ("smoke", base + ["--", "--nd-run-smoke", "--nd-test-size=746x280"]),
        ("full_match", base + ["--", "--nd-run-full-match", "--nd-test-size=746x280"]),
    ]
    for label, command in steps:
        result = run(label, command, args.timeout, args.out)
        report["runs"][label] = result
        if label == "version":
            version = Path(result["log"]).read_text().strip()
            result["pass"] &= "4.7.2" in version
        if not result["pass"]:
            report["blocker"] = f"Godot {label} did not pass; inspect exact log"
            break
    report["engine_qualification"] = (len(report["runs"]) == 4 and all(x["pass"] for x in report["runs"].values()))
    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    print("ENGINE_QUALIFICATION_PASS" if report["engine_qualification"] else "ENGINE_QUALIFICATION_NOT_PASS")
    return 0 if report["engine_qualification"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
