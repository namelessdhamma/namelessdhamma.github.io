#!/usr/bin/env python3
"""Native A5 v104 cache stress + shared 21-match gate; fail closed without Godot."""
import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "A5_V104_WORLD_CACHE_RUNTIME_PASS switches=14 worlds=7 placements=1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", default=shutil.which("godot") or shutil.which("godot4") or "")
    ap.add_argument("--out", type=Path, default=ROOT / "a5_v104_native_qualification")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"version": "A5-v104", "utc": datetime.now(timezone.utc).isoformat(),
              "godot": args.godot, "native_cache": "NOT_RUN", "native_21_matches": "NOT_RUN",
              "real_phone_touch": "NOT_RUN", "visual_parity": "NOT_RUN", "production": "UNCHANGED"}
    if not args.godot or not Path(args.godot).is_file():
        report["blocker"] = "Godot executable unavailable: native qualification not executed"
        (args.out / "report.json").write_text(json.dumps(report, indent=2))
        print(report["blocker"])
        return 2
    try:
        version = subprocess.run([args.godot, "--version"], capture_output=True, text=True, timeout=15)
        report["engine_version"] = version.stdout.strip()
        if version.returncode or "4.7.2" not in version.stdout:
            raise RuntimeError("Expected qualified Godot 4.7.2")
        for label, command, marker in [
            ("import", [args.godot, "--headless", "--path", str(ROOT), "--editor", "--import", "--quit"], None),
            ("cache", [args.godot, "--headless", "--path", str(ROOT), "--script", "res://tests/a5_v104_world_cache_runtime_smoke.gd"], MARKER),
            ("matches", [args.godot, "--headless", "--path", str(ROOT), "--", "--nd-run-full-match", "--nd-test-size=746x280"], "BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21"),
        ]:
            result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
            output = result.stdout + "\n" + result.stderr
            (args.out / f"{label}.log").write_text(output)
            if result.returncode or any(token in output for token in ("SCRIPT ERROR", "Parse Error", "ERROR:", "ASSERTION FAILED")) or (marker and marker not in output):
                raise RuntimeError(f"Native {label} failed; inspect {label}.log")
            report[f"native_{label}"] = "PASS"
        # A passing native 21-match log must still contain 21 distinct cases.
        from run_a5_v58_godot_qualification import assess_full_match_log
        match_log = (args.out / "matches.log").read_text()
        if not assess_full_match_log(match_log, 0)["pass"]:
            raise RuntimeError("Native 21-match matrix incomplete")
        report["native_cache"] = "PASS"
        report["native_21_matches"] = "PASS"
        report["engine_qualification"] = "PASS"
        returncode = 0
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        report["blocker"] = str(exc)
        report["engine_qualification"] = "NOT_PASS"
        returncode = 1
    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    print("A5_V104_NATIVE_QUALIFICATION_" + ("PASS" if returncode == 0 else "NOT_PASS"))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
