"""Extract the seven approved menu glyph plates as live, hit-tested UI art.

The accepted PNGs remain immutable. Only derivative scenery-perimeter alpha is
cut under each extracted plate, preventing a doubled/distorted menu glyph.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CANON = [
    ("a5_void_ranked", "01_nd_premium_void_canon_source.png", (18, 18, 112, 88), 18),
    ("a5_pirate_ranked", "02_pirate_sea_canon_source.png", (27, 19, 96, 90), 14),
    ("a5_atlantis_ranked", "03_atlantis_canon_source.png", (21, 22, 108, 98), 17),
    ("a5_gods_ranked", "04_gods_of_the_deep_canon_source.png", (22, 19, 111, 97), 19),
    ("a5_sand_ranked", "05_sand_sea_canon_source.png", (24, 20, 107, 97), 17),
    ("a5_night_ranked", "06_night_sea_canon_source.png", (17, 19, 112, 99), 20),
    ("a5_northern_ranked", "07_northern_sea_canon_source.png", (20, 19, 111, 97), 19),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> list[dict]:
    expected = json.loads((ROOT / "tools" / "approved_seven_world_manifest.json").read_text())
    expected_images = expected.get("images", [])
    assert len(expected_images) == 7
    dest = ASSETS / "a5_menu_plates"
    dest.mkdir(exist_ok=True)
    records = []
    for i, (folder, name, bounds, radius) in enumerate(CANON):
        original = ASSETS / folder / name
        assert digest(original) == expected_images[i]["sha256"], f"Canonical PNG changed: {name}"
        source = Image.open(original).convert("RGBA")
        x0, y0, x1, y1 = bounds
        w, h = x1 - x0, y1 - y0
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        plate = source.crop(bounds)
        plate.putalpha(mask)
        if i == 0:
            # Void alone intentionally omits the busy cosmic screenshot ring.
            # Retain its approved three-bar glyph, but clean the surrounding
            # cosmic orange from the *derived UI plate*, never from canon.
            # Otherwise a conspicuous orange screenshot patch appears over
            # the accepted minimal warm/cool split field.
            for yy in range(h):
                for xx in range(w):
                    if mask.getpixel((xx, yy)) == 0:
                        continue
                    r, g, b, _ = plate.getpixel((xx, yy))
                    neutral_glyph = (13 <= xx <= 70 and 16 <= yy <= 54
                                     and min(r, g, b) >= 65
                                     and max(r, g, b) - min(r, g, b) < 34)
                    if not neutral_glyph:
                        plate.putpixel((xx, yy), (13, 14, 19, 255))
        target = dest / f"world_{i:02d}.png"
        plate.save(target, optimize=True)
        perimeter_path = ASSETS / "a5_scenery_perimeter" / f"world_{i:02d}.png"
        perimeter = Image.open(perimeter_path).convert("RGBA")
        # Remove only the exact plate footprint. The rest of the accepted
        # scenery remains a separate, transparent, noninteractive live layer.
        pixels = perimeter.load()
        for yy in range(h):
            for xx in range(w):
                if mask.getpixel((xx, yy)):
                    r, g, b, _ = pixels[x0 + xx, y0 + yy]
                    pixels[x0 + xx, y0 + yy] = (r, g, b, 0)
        # Void scenery is intentionally hidden in the game; do not touch its
        # historical derivative, since it is retained as provenance.
        if i != 0:
            perimeter.save(perimeter_path, optimize=True)
        records.append({
            "world": i, "source": name, "source_sha256": digest(original),
            "bounds": list(bounds), "radius": radius,
            "sprite": target.name, "sprite_sha256": digest(target),
            "scenery_cutout": i != 0,
        })
    (dest / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    return records


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
