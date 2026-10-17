#!/usr/bin/env python3
"""A5 v122: run the actual Godot 4.7.2 scene and collect 14 live frames.

This is an evidence collector, NOT a visual-parity judge. No fake Godot
captures, offline composites, or reference PNGs count as runtime evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

WORLDS = [
    "01_nd_premium_void", "02_pirate_sea", "03_atlantis",
    "04_gods_of_the_deep", "05_sand_sea", "06_night_sea", "07_northern_sea",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon_paths(root: Path) -> dict[str, Path]:
    manifest = json.loads((root / "tools/approved_seven_world_manifest.json").read_text())
    assert len(manifest["images"]) == 7
    result = {}
    for item in manifest["images"]:
        expected = item["file"].replace(".png", "_canon_source.png")
        paths = list((root / "assets").rglob(expected))
        if len(paths) != 1 or sha(paths[0]) != item["sha256"]:
            raise RuntimeError(f"Approved reference mismatch: {item['file']}")
        result[item["file"].removesuffix(".png")] = paths[0]
    if set(result) != set(WORLDS):
        raise RuntimeError("Approved reference names do not match seven live worlds")
    return result


def inspect_captures(output: Path, root: Path, expected_size: tuple[int, int]) -> dict:
    """Fail closed unless all 14 frames are native, distinct and self-consistent."""
    references = canon_paths(root)
    manifest_path = output / "capture_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("No Godot native capture manifest; no visual evidence")
    evidence = json.loads(manifest_path.read_text())
    if (evidence.get("status") != "NATIVE_CAPTURED_NOT_VISUAL_PARITY_ACCEPTED"
            or evidence.get("world_count") != 7 or evidence.get("capture_count") != 14
            or evidence.get("real_gameplay_handlers") is not True):
        raise RuntimeError("Incomplete or non-native capture manifest")
    entries = evidence.get("captures", [])
    expected_names = [f"{world}_{phase}.png" for world in WORLDS for phase in ("empty", "played")]
    if [item.get("file") for item in entries] != expected_names:
        raise RuntimeError("Missing, reordered or duplicate seven-world captures")
    if evidence.get("rule") != "CD" or evidence.get("source") != "Godot live scene":
        raise RuntimeError("Capture manifest does not describe the expected live rules/scene")
    expected_world_names = ["ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep",
                            "Sand Sea", "Night Sea", "Northern Sea"]
    for position, item in enumerate(entries):
        world_index = position // 2
        phase = ("empty", "played")[position % 2]
        if (item.get("world_index") != world_index
                or item.get("live_world") != world_index
                or item.get("world") != expected_world_names[world_index]
                or item.get("phase") != phase
                or item.get("live_cell_count") != 9
                or item.get("physical_support_visible") is not (world_index != 0)
                or item.get("width") != expected_size[0]
                or item.get("height") != expected_size[1]):
            raise RuntimeError(f"Live world/board/support identity mismatch in {item.get('file')}")
        path = output / item["file"]
        if not path.is_file() or sha(path) != item.get("sha256"):
            raise RuntimeError(f"Missing or modified native frame: {path}")
        with Image.open(path) as image:
            if image.size != expected_size:
                raise RuntimeError(f"Unexpected physical viewport {image.size}: {path}")
            # A dummy black headless frame is never a pass.
            colors = len(image.convert("RGB").resize((80, 45)).getcolors(3600) or [])
            if colors < 32:
                raise RuntimeError(f"Flat/dummy renderer frame: {path}")
        if item["phase"] == "empty" and item.get("moves") != 0:
            raise RuntimeError("Empty capture contains game moves")
        if item["phase"] == "played" and item.get("moves") != 6:
            raise RuntimeError("Played capture was not generated from six legal moves")
    # A played board must visibly differ from its empty counterpart. This is
    # necessary, but NOT sufficient, for a canonical visual parity verdict.
    for world in WORLDS:
        if sha(output / f"{world}_empty.png") == sha(output / f"{world}_played.png"):
            raise RuntimeError(f"World has no live occupancy visual delta: {world}")
    # Seven renamed copies of one rendered world must never count as seven
    # worlds, even if the capture manifest's indices look superficially valid.
    for phase in ("empty", "played"):
        phase_hashes = [sha(output / f"{world}_{phase}.png") for world in WORLDS]
        if len(set(phase_hashes)) != 7:
            raise RuntimeError(f"Repeated rendered world frame in {phase} phase")

    # Contact sheet compares actual rendered gameplay with the exact approved
    # art; no generated reference, no fake runtime and no automatic PASS.
    tile_w, tile_h = 480, 270
    sheet = Image.new("RGB", (tile_w * 3, tile_h * 7 + 26), "#10131a")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 7), "APPROVED REFERENCE    |    LIVE EMPTY    |    LIVE PLAYED    —    REVIEW REQUIRED", fill="white")
    diagnostics = []
    for i, world in enumerate(WORLDS):
        with Image.open(references[world]) as approved, Image.open(output / f"{world}_empty.png") as empty, Image.open(output / f"{world}_played.png") as played:
            frames = [approved.convert("RGB"), empty.convert("RGB"), played.convert("RGB")]
            # A 746x280 landscape is 2.66:1, not 16:9. Stretching it into a
            # 16:9 review tile would disguise genuine viewport distortion.
            # Contain + letterbox preserves each source's native proportions.
            review_frames = []
            for source in frames:
                fitted = ImageOps.contain(source, (tile_w, tile_h), Image.Resampling.LANCZOS)
                frame = Image.new("RGB", (tile_w, tile_h), "#10131a")
                frame.paste(fitted, ((tile_w - fitted.width) // 2, (tile_h - fitted.height) // 2))
                review_frames.append(frame)
            frames = review_frames
            for j, frame in enumerate(frames):
                sheet.paste(frame, (tile_w * j, 26 + tile_h * i))
            # Raw MAE includes legitimate reference screenshot occupancy
            # differences; report it only as a triage metric, never acceptance.
            raw_mae = sum(ImageStat.Stat(ImageChops.difference(frames[0], frames[2])).mean) / 3
            diagnostics.append({"world": world, "reference_sha256": sha(references[world]),
                                "empty_sha256": sha(output / f"{world}_empty.png"),
                                "played_sha256": sha(output / f"{world}_played.png"),
                                "raw_rgb_mae_diagnostic_not_parity": round(raw_mae, 3),
                                "PLAYABLE": "UNVERIFIED", "VISUAL_PARITY": "UNVERIFIED"})
    sheet.save(output / "native_visual_comparison_REVIEW_REQUIRED.jpg", quality=90)
    report = {"status": "NATIVE_RENDER_CAPTURED_REVIEW_REQUIRED", "native_capture_count": 14,
              "canonical_reference_count": 7, "physical_viewport": list(expected_size),
              "real_touch": "NOT_TESTED", "21_ai_matches": "NOT_TESTED",
              "LEGACY_PRODUCT_PARITY_PASS": "OPEN", "worlds": diagnostics}
    (output / "native_capture_review.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True, help="Official Godot 4.7.2 executable")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    width, height = map(int, args.size.lower().split("x"))
    if width < 300 or height < 200:
        parser.error("capture viewport must be at least 300x200")
    root = args.project.resolve()
    output = args.output.resolve()
    canon_paths(root)  # verify immutable canon before touching output
    version = subprocess.run([str(args.godot), "--version"], text=True, capture_output=True, timeout=15, check=True)
    if "4.7.2" not in version.stdout:
        raise RuntimeError(f"Expected Godot 4.7.2, got {version.stdout.strip()!r}")
    output.mkdir(parents=True, exist_ok=True)
    # CI/Xvfb has no sound device. The previous windowed capture inherited the
    # default audio backend and could fail with ERR_CANT_OPEN despite a valid
    # graphical renderer. Godot documents Dummy as an independent audio driver;
    # this does NOT switch to headless rendering or alter player audio settings.
    command = [str(args.godot), "--audio-driver", "Dummy", "--path", str(root), "--windowed", "--resolution", args.size,
               "--", "--nd-capture-seven", f"--nd-capture-dir={output}", f"--nd-test-size={args.size}"]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout)
    (output / "native_godot_stdout.log").write_text(completed.stdout)
    (output / "native_godot_stderr.log").write_text(completed.stderr)
    if completed.returncode or "BLUE_SEA_NATIVE_SEVEN_WORLD_CAPTURE_PASS" not in completed.stdout:
        raise RuntimeError(f"Godot native capture did not pass (exit={completed.returncode}); see logs")
    report = inspect_captures(output, root, (width, height))
    print(json.dumps({"status": report["status"], "captures": 14, "output": str(output)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"A5_NATIVE_CAPTURE_BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
