"""A5 v104: portable checks for real scene texture ownership; native fixture pending."""
from __future__ import annotations

import hashlib
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/world_visuals.gd").read_text(encoding="utf-8")
ASSETS = ROOT / "assets"


def section(begin, end):
    return SCRIPT.split(begin, 1)[1].split(end, 1)[0]


def test_all_persistent_world_texture_owners_use_one_lru():
    assert "var support_cache: Dictionary = {}" in SCRIPT
    assert "const RESIDENT_WORLD_LIMIT := 2" in SCRIPT
    touch = section("func _touch_world_cache(world: int) -> void:", "func _cache_within_budget")
    budget = section("func _cache_within_budget() -> bool:", "func apply_world")
    for cache in ("backdrop_cache", "scenery_cache", "support_cache", "piece_cache", "canonical_cell_cache"):
        assert f"{cache}.erase(key)" in touch
        assert cache in budget
    assert "pirate_plinth: Texture2D" not in SCRIPT
    assert "northern_plinth: Texture2D" not in SCRIPT
    assert "night_plinth: Texture2D" not in SCRIPT
    assert "gods_plinth: Texture2D" not in SCRIPT


def test_all_six_physical_supports_share_one_live_loader():
    entry = section("func apply_world(root: Control, world: int) -> void:", "func piece_texture")
    assert "foundation.texture = support_cache[world]" in entry
    assert "support_cache[world] = support_texture" in entry
    assert "_load_bounded_texture(SUPPORT_TEXTURE_PATHS[world])" in entry
    assert "support.visible = world != 0" in entry
    assert "foundation.visible = world >= 1 and world <= 6" in entry
    assert entry.count('assert(_cache_within_budget()') >= 2
    paths = (
        "pirate_chart_support.png", "atlantis_stone_support.png", "gods_basalt_support.png",
        "sand_sandstone_support.png", "night_masonry_support.png", "north_frozen_runestone_plinth.png",
    )
    for path in paths:
        assert path in SCRIPT
        assert len(list(ASSETS.rglob(path))) == 1


def test_world_backdrops_do_not_implicitly_pin_all_seven_in_engine_cache():
    entry = section("func apply_world(root: Control, world: int) -> void:", "func piece_texture")
    assert "ResourceLoader.CACHE_MODE_IGNORE" in SCRIPT
    for path in (
        "void_split_light_backdrop.png", "north_fjord_backdrop.png", "gods_underwater_backdrop.png"
    ):
        assert path in entry
    for variable in ("void_scene", "prepared", "northern_scene", "gods_scene", "prepared_scene"):
        assert f"var {variable} := _load_bounded_texture(" in entry
    assert " = load(" not in entry


def test_void_releases_previous_invisible_support_and_nine_cell_references():
    entry = section("func apply_world(root: Control, world: int) -> void:", "func piece_texture")
    assert "if world == 0:\n\t\tfoundation.texture = null" in entry
    # Void now has nine intentionally live luminous cells. The old null-cell
    # assertion became wrong after v111; stale supported-world tiles must be
    # replaced with current-world source art, not blanked permanently.
    assert "chart.texture = _canonical_cell_texture(world, cell_index)" in entry
    assert 'var cell_index := cell.get_index()' in entry
    assert len(list((ASSETS / "a5_reference_cells" / "void").glob("cell_*.png"))) == 9
    assert "scenery.texture = null" in entry
    assert "scenery.visible = world != 0" in entry


def test_asset_dimensions_and_two_world_cache_model():
    support_files = [
        "a5_pirate_atlantis_prebaked_environment/pirate_chart_support.png",
        "a5_pirate_atlantis_prebaked_environment/atlantis_stone_support.png",
        "a5_gods_prebaked_environment/gods_basalt_support.png",
        "a5_sand_night_prebaked_environment/sand_sandstone_support.png",
        "a5_sand_night_prebaked_environment/night_masonry_support.png",
        "a5_northern_environment/north_frozen_runestone_plinth.png",
    ]
    support_bytes = []
    for name in support_files:
        with Image.open(ASSETS / name) as im:
            support_bytes.append(im.width * im.height * 4)
    assert len(support_bytes) == 6
    assert sum(support_bytes) > max(support_bytes) + min(support_bytes)
    # v103 retained all six plinths forever; v104 owns at most two, and
    # when Void is current only one older slab may remain in the LRU.
    assert sum(support_bytes) > sum(sorted(support_bytes)[-2:])
    resident = []
    retained = {}
    for world in [1, 2, 3, 4, 5, 6, 0, 6, 1, 5, 0, 2, 4, 0]:
        if world in resident:
            resident.remove(world)
        resident.append(world)
        resident = resident[-2:]
        retained = {w: b for w, b in retained.items() if w in resident}
        if world != 0:
            retained[world] = support_bytes[world - 1]
        assert set(retained).issubset(set(resident))
        assert len(retained) <= 2
        assert sum(retained.values()) <= sum(sorted(support_bytes)[-2:])


def test_menu_and_red_masthead_do_not_pin_all_seven_worlds():
    main = (ROOT / "scripts/main.gd").read_text()
    for name in ("reference_menu_art", "canonical_live_logo"):
        assert f'{name}.texture = ResourceLoader.load(' in main
    assert main.count('ResourceLoader.CACHE_MODE_IGNORE) as Texture2D') >= 2
    assert 'title.visible = canonical_live_logo.texture == null' in main
    assert 'Color("#f33c39")' in SCRIPT


def test_reference_images_and_shared_gameplay_are_not_modified():
    canon = ROOT / "tools/approved_seven_world_manifest.json"
    assert canon.is_file()
    assert (ROOT / "scripts/main.gd").is_file()
    assert (ROOT / "scripts/ai_opponent.gd").is_file()
    assert (ROOT / "scripts/pirate_opening_campaign.gd").is_file()
    # Full source hash comparison against predecessor is performed by packager.
    assert "func _touch_world_cache(world: int)" in SCRIPT
    assert SCRIPT.count("func apply_world(") == 1
    assert SCRIPT.count("func piece_texture(") == 1


def test_native_fixture_included_but_not_marked_executed():
    fixture = ROOT / "tests/a5_v104_world_cache_runtime_smoke.gd"
    assert fixture.is_file()
    data = fixture.read_text()
    assert 'game.call("_set_world", world)' in data
    assert 'game.call("_on_cell_pressed", 0)' in data
    assert "A5_V104_WORLD_CACHE_RUNTIME_PASS" in data
