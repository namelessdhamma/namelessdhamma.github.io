"""v123 negative-oracle tests. Synthetic PNGs are NOT Godot evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capture_v123", ROOT / "tools/a5_native_seven_world_capture.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
MAIN = (ROOT / "scripts/main.gd").read_text()
WORLD_NAMES = ["ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep",
               "Sand Sea", "Night Sea", "Northern Sea"]


def synthetic_manifest():
    entries = []
    for world, slug in enumerate(MOD.WORLDS):
        for phase, moves in (("empty", 0), ("played", 6)):
            entries.append({"file": f"{slug}_{phase}.png", "world": WORLD_NAMES[world],
                            "world_index": world, "live_world": world, "live_cell_count": 9,
                            "physical_support_visible": world != 0,
                            "phase": phase, "moves": moves, "width": 320, "height": 200,
                            "sha256": "not-yet-written"})
    return {"status": "NATIVE_CAPTURED_NOT_VISUAL_PARITY_ACCEPTED",
            "world_count": 7, "capture_count": 14, "real_gameplay_handlers": True,
            "rule": "CD", "source": "Godot live scene", "captures": entries}


def test_live_scene_captures_world_and_physical_support_identity():
    assert '"live_world": current_world' in MAIN
    assert '"live_cell_count": perspective_tiles.size()' in MAIN
    assert '"physical_support_visible":' in MAIN
    assert 'current_world != world or perspective_tiles.size() != 9' in MAIN
    assert 'canonical_live_logo.texture == null' in MAIN


@pytest.mark.parametrize("field,value", [
    ("world_index", 4), ("live_world", 4), ("world", "Pirate Sea"),
    ("live_cell_count", 0), ("physical_support_visible", True),
    ("width", 746), ("height", 280), ("phase", "played")
])
def test_forged_world_metadata_fails_before_any_png_is_read(tmp_path, field, value):
    manifest = synthetic_manifest()
    manifest["captures"][0][field] = value
    (tmp_path / "capture_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="Live world/board/support identity mismatch"):
        MOD.inspect_captures(tmp_path, ROOT, (320, 200))


def test_duplicated_world_pixels_fail_even_with_distinct_names(tmp_path):
    manifest = synthetic_manifest()
    # Tiny deterministic synthetic gradient; this fixture tests the verifier,
    # never claims to be a renderer frame.
    base = Image.new("RGB", (320, 200))
    pixels = base.load()
    for y in range(200):
        for x in range(320):
            pixels[x, y] = ((x * 7 + y * 3) % 256, (x * 2 + y * 11) % 256, (x * 5 + y * 13) % 256)
    for i, entry in enumerate(manifest["captures"]):
        frame = base.copy()
        if i not in (0, 2):
            frame.putpixel((0, 0), (i * 13 % 256, i * 17 % 256, i * 19 % 256))
        frame.save(tmp_path / entry["file"])
        entry["sha256"] = hashlib.sha256((tmp_path / entry["file"]).read_bytes()).hexdigest()
    (tmp_path / "capture_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="Repeated rendered world frame in empty phase"):
        MOD.inspect_captures(tmp_path, ROOT, (320, 200))


def test_review_preserves_ultrawide_aspect_without_stretch():
    source = Image.new("RGB", (746, 280), "#cc2222")
    fitted = ImageOps.contain(source, (480, 270), Image.Resampling.LANCZOS)
    assert fitted.size == (480, 180)
    assert "ImageOps.contain(source, (tile_w, tile_h)" in (ROOT / "tools/a5_native_seven_world_capture.py").read_text()


def test_verifier_does_not_promote_worlds_or_touch_to_pass():
    code = (ROOT / "tools/a5_native_seven_world_capture.py").read_text()
    assert '"PLAYABLE": "UNVERIFIED", "VISUAL_PARITY": "UNVERIFIED"' in code
    assert '"real_touch": "NOT_TESTED", "21_ai_matches": "NOT_TESTED"' in code
