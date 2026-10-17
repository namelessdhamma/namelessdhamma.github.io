"""Seven-world rank-size evidence at small PHONE render scales (not Godot parity).

These are the actual 126 source sprite paths selected by world_visuals.gd.
The approved references are immutable. This is a pixel-coverage invariant,
not proof of native Godot composition, touch target size or visual parity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "assets"
WORLDS = (
    ("void", "a5_void_ranked", "void_rank"),
    ("pirate", "a5_pirate_ranked", "pirate_rank"),
    ("atlantis", "a5_atlantis_ranked", "atlantis_rank"),
    ("gods", "a5_gods_ranked", "gods_rank"),
    ("sand", "a5_sand_ranked", "sand_rank"),
    ("night", "a5_night_ranked", "night_rank"),
    ("north", "a5_northern_runed", "north_runed_rank"),
)


def _source_sprite(world: str, folder: str, stem: str, player: int, rank: int) -> Path:
    return ART / folder / f"{stem}_{rank:02d}_p{player}.png"


def _visible_pixels_at(path: Path, size: int) -> int:
    with Image.open(path) as image:
        assert image.size == (128, 128), f"Unexpected native source dimensions: {path}"
        scaled = image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        return sum(value > 100 for value in scaled.getchannel("A").get_flattened_data())


def test_approved_seven_pngs_are_exact_unmodified_sources():
    manifest = json.loads((ROOT / "tools/approved_seven_world_manifest.json").read_text())
    assert len(manifest["images"]) == 7
    for entry in manifest["images"]:
        matches = list(ART.rglob(entry["file"].replace(".png", "_canon_source.png")))
        assert len(matches) == 1, entry["file"]
        assert hashlib.sha256(matches[0].read_bytes()).hexdigest() == entry["sha256"]
        with Image.open(matches[0]) as image:
            assert image.size == (1672, 941)


def test_all_126_live_selected_rank_sources_have_strict_phone_size_ladder():
    code = (ROOT / "scripts/world_visuals.gd").read_text()
    # Prevent passing against unused sprite variants: every path must be the
    # actual live texture path selected by the shared seven-world renderer.
    for world, folder, stem in WORLDS:
        assert f"res://assets/{folder}/{stem}_%02d_p%d.png" in code, world
        for player in (1, 2):
            files = [_source_sprite(world, folder, stem, player, rank) for rank in range(1, 10)]
            assert all(path.is_file() for path in files), (world, player)
            for size in (14, 22):
                coverage = [_visible_pixels_at(path, size) for path in files]
                assert all(a < b for a, b in zip(coverage, coverage[1:])), (
                    world, player, size, coverage
                )
                assert coverage[0] > 0, (world, player, size)


def test_two_players_have_distinct_live_materials_in_every_world_and_rank():
    for world, folder, stem in WORLDS:
        for rank in range(1, 10):
            first = _source_sprite(world, folder, stem, 1, rank).read_bytes()
            second = _source_sprite(world, folder, stem, 2, rank).read_bytes()
            assert first != second, (world, rank)
