"""Portable source + asset acceptance; native Godot smoke is still required."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/world_visuals.gd").read_text(encoding="utf-8")
ASSETS = ROOT / "assets"
WORLD_DIRS = ["a5_void_ranked", "a5_pirate_ranked", "a5_atlantis_ranked",
              "a5_gods_ranked", "a5_sand_ranked", "a5_night_ranked", "a5_northern_ranked"]
CANON_HASHES = [
    "00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8",
    "0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1",
    "2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f",
    "10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d",
    "01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3",
    "ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da",
    "3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775",
]


def decoded_bytes(files):
    total = 0
    for path in files:
        with Image.open(path) as image:
            total += image.width * image.height * 4
    return total


def test_native_shared_scene_enforces_bounded_cache_on_each_world_entry():
    assert "const RESIDENT_WORLD_LIMIT := 2" in SCRIPT
    assert "var resident_worlds: Array[int] = []" in SCRIPT
    cache = SCRIPT.split("func _touch_world_cache(world: int) -> void:", 1)[1].split("\nfunc ", 1)[0]
    assert "resident_worlds.erase(world)" in cache
    assert "resident_worlds.append(world)" in cache
    assert "while resident_worlds.size() > RESIDENT_WORLD_LIMIT:" in cache
    for cache_name in ("backdrop_cache", "scenery_cache", "piece_cache", "canonical_cell_cache"):
        assert f"{cache_name}.erase(key)" in cache
    entry = SCRIPT.split("func apply_world(root: Control, world: int) -> void:", 1)[1].split("\nfunc ", 1)[0]
    assert entry.index("_touch_world_cache(world)") < entry.index('var background :=')
    assert 'assert(_cache_within_budget(), "World texture cache exceeded two-world budget")' in entry


def test_direct_sprite_probe_is_bounded_without_scene_switch():
    # Native headless art QA probes world-specific ranks directly; it must
    # not reintroduce an all-seven cache via piece_texture().
    section = SCRIPT.split("func piece_texture(world: int, player: int, rank: int) -> Texture2D:", 1)[1].split("\nfunc ", 1)[0]
    assert section.index("_touch_world_cache(world)") < section.index("if piece_cache.has(key):")
    assert "piece_cache[key] = " in section



def test_large_source_derived_textures_bypass_global_resource_cache():
    assert 'ResourceLoader.load(path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE)' in SCRIPT
    # Seven world-specific ranked families and six supported-world empty cells
    # use the bounded loader; no accidental default-cache fallback.
    for name in ("void_texture", "pirate_texture", "atlantis_texture",
                 "gods_texture", "sand_texture", "night_texture", "runed_texture"):
        assert f"var {name} := _load_bounded_texture(" in SCRIPT
    assert 'var texture := _load_bounded_texture(path) as Texture2D' in SCRIPT


def test_void_never_decodes_invisible_reference_perimeter():
    section = SCRIPT.split("# The approved Void perimeter is NEVER displayed", 1)[1].split("# Void alone is an empty", 1)[0]
    assert re.search(r"if world == 0:\s+scenery.texture = null\s+else:", section)
    assert 'scenery_cache[world] = texture' in section
    assert 'scenery.texture = scenery_cache[world]' in section
    assert "scenery.visible = world != 0" in SCRIPT


def test_offline_cache_oracle_all_seven_worlds_and_return_visits():
    resident = []
    caches = {name: {} for name in ("backdrop", "scenery", "piece", "cell")}
    for world in list(range(7)) + [0, 6, 2, 1, 2, 5, 0, 5]:
        if world in resident:
            resident.remove(world)
        resident.append(world)
        while len(resident) > 2:
            resident.pop(0)
        for cache in caches.values():
            for key in list(cache):
                if key not in resident:
                    del cache[key]
        for name, cache in caches.items():
            if world != 0 or name != "scenery":
                cache[world] = f"world-{world}-{name}"
            assert all(key in resident for key in cache)
            assert len(cache) <= 2
        assert resident[-1] == world


def test_approved_pngs_are_unchanged_and_separate_from_live_textures():
    for world, dirname in enumerate(WORLD_DIRS):
        sources = list((ASSETS / dirname).glob("*canon_source.png"))
        assert len(sources) == 1
        assert hashlib.sha256(sources[0].read_bytes()).hexdigest() == CANON_HASHES[world]
        # One image per rank/side; no static board occupancy in those sprites.
        assert len(list((ASSETS / dirname).glob("*rank_*_p?.png"))) == 18
    assert 'CANONICAL_CELL_ART_ROOT' in SCRIPT
    assert 'root.get_node("SafeArea/Landscape/Center/BoardAspect/Board")' in SCRIPT


def test_bounded_explicit_perimeter_retention_reduces_decoded_bytes():
    perimeters = [ASSETS / "a5_scenery_perimeter" / f"world_{i:02d}.png" for i in range(7)]
    old_bytes = decoded_bytes(perimeters)
    # A two-world LRU may retain at most two visible perimeters; world 0
    # is invisible and must never be decoded for the live scene.
    new_max = max(decoded_bytes([perimeters[i], perimeters[j]])
                  for i in range(1, 7) for j in range(i + 1, 7))
    assert old_bytes > 40 * 1024**2
    assert new_max < 13 * 1024**2
    assert old_bytes - new_max > 29 * 1024**2


def test_no_gameplay_or_pirate_controller_fork():
    assert (ROOT / "scripts/main.gd").exists()
    assert (ROOT / "scripts/ai_opponent.gd").exists()
    assert (ROOT / "scripts/pirate_opening_campaign.gd").exists()
    assert SCRIPT.count("func apply_world(") == 1
    assert SCRIPT.count("func piece_texture(") == 1
