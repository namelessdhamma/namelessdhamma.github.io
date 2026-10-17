#!/usr/bin/env python3
"""Extract only the approved world mastheads; never flatten gameplay into art.

The seven exact source PNGs and their manifest remain byte-identical.  The
soft alpha crop is an independently positioned, non-interactive visual layer.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools" / "approved_seven_world_manifest.json"
OUT = ROOT / "assets" / "a5_live_logos"
CROP = (565, 0, 1107, 150)
SOURCE_DIRS = [
    "a5_void_ranked", "a5_pirate_ranked", "a5_atlantis_ranked",
    "a5_gods_ranked", "a5_sand_ranked", "a5_night_ranked", "a5_northern_ranked",
]
# Last opaque rows precede the first accepted reference's option buttons.
BUTTON_CUTOFF = [122, 130, 130, 132, 149, 123, 124]


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _mask(width: int, height: int, cutoff: int) -> Image.Image:
    alpha = Image.new("L", (width, height), 0)
    px = alpha.load()
    for y in range(height):
        top = _smoothstep(y / 8.0)
        bottom = 1.0 - _smoothstep((y - (cutoff - 16)) / 16.0)
        for x in range(width):
            left = _smoothstep(x / 28.0)
            right = _smoothstep((width - 1 - x) / 28.0)
            px[x, y] = round(255 * min(left, right) * min(top, bottom))
    return alpha


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(data["images"]) == len(SOURCE_DIRS) == 7
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for i, entry in enumerate(data["images"]):
        files = list((ROOT / "assets" / SOURCE_DIRS[i]).glob("*canon_source.png"))
        assert len(files) == 1, (entry["world"], files)
        src = files[0]
        raw = src.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], src
        original = Image.open(src).convert("RGBA")
        assert original.size == tuple(entry["size"]) == (1672, 941)
        logo = original.crop(CROP)
        logo.putalpha(_mask(logo.width, logo.height, BUTTON_CUTOFF[i]))
        out = OUT / f"world_{i:02d}.png"
        logo.save(out, optimize=True)
        results.append({
            "world": entry["world"],
            "source_sha256": entry["sha256"],
            "asset": out.name,
            "asset_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "crop": list(CROP),
            "button_cutoff": BUTTON_CUTOFF[i],
        })
    (OUT / "logo_manifest.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("A5_CANONICAL_LIVE_LOGOS_7_OF_7_PASS")


if __name__ == "__main__":
    main()
