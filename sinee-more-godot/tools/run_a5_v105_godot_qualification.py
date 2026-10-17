#!/usr/bin/env python3
"""Fail-closed native Godot 4.7.2 gate for A5 v105's integrated chart.

Native import, nine live Pirate chart cells, actual legal placement and 21
full matches are all required before gameplay claims. Visual/real-touch parity
requires separate physical-device and screenshot evidence.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", default=shutil.which("godot") or shutil.which("godot4") or "")
    ap.add_argument("--out", type=Path, default=ROOT / "a5_v105_native_qualification")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"version": "A5-v105", "godot": args.godot,
              "native_import": "NOT_RUN", "native_pirate_chart": "NOT_RUN",
              "native_21_matches": "NOT_RUN", "real_touch": "NOT_RUN",
              "visual_parity": "NOT_RUN", "production": "UNCHANGED"}
    if not args.godot or not Path(args.godot).is_file():
        report["blocker"] = "Qualified Godot 4.7.2 binary not available"
        (args.out / "report.json").write_text(json.dumps(report, indent=2))
        print("A5_V105_NATIVE_BLOCKED: " + report["blocker"])
        return 2
    try:
        version = subprocess.run([args.godot, "--version"], capture_output=True, text=True, timeout=20)
        if version.returncode or "4.7.2" not in version.stdout:
            raise RuntimeError("Godot 4.7.2 required: " + version.stdout.strip())
        checks = [
            ("import", [args.godot, "--headless", "--path", str(ROOT), "--editor", "--import", "--quit"], ""),
            ("pirate_chart", [args.godot, "--headless", "--path", str(ROOT), "--script", "res://tests/a5_v105_pirate_unique_chart_runtime_smoke.gd"], "A5_V105_PIRATE_CHART_PASS unique_live_tiles=9 placement=1"),
            ("matches", [args.godot, "--headless", "--path", str(ROOT), "--", "--nd-run-full-match", "--nd-test-size=746x280"], "BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21"),
        ]
        for label, command, marker in checks:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
            output = proc.stdout + "\n" + proc.stderr
            (args.out / f"{label}.log").write_text(output)
            if proc.returncode or any(token in output for token in ("SCRIPT ERROR", "Parse Error", "ASSERTION FAILED", "ERROR:")) or (marker and marker not in output):
                raise RuntimeError(f"Native {label} failed; inspect {label}.log")
            report[f"native_{label}"] = "PASS"
        from run_a5_v58_godot_qualification import assess_full_match_log
        match_log = (args.out / "matches.log").read_text()
        if not assess_full_match_log(match_log, 0)["pass"]:
            raise RuntimeError("Native 21-match matrix incomplete")
        report["native_21_matches"] = "PASS"
        report["engine_qualification"] = "PASS"
        result = 0
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        report["blocker"] = str(exc)
        report["engine_qualification"] = "NOT_PASS"
        result = 1
    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    print("A5_V105_NATIVE_QUALIFICATION_" + ("PASS" if result == 0 else "NOT_PASS"))
    return result

if __name__ == "__main__":
    raise SystemExit(main())
