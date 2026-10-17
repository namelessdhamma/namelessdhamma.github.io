"""A5 v163: live warm/cool floating Void halos. Source-level checks only.

These checks cannot establish native Godot compilation, phone touch, or
visual parity with the user-approved reference.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")
PROTECTED = {'_on_primary': '777708e5deabe19654034e02f3cb02eb4cf95072c3fb609f240fbeb75fcccf02', '_on_cell_pressed': '74631b002ebb3f3aed77414776a191f0170093ce0c90d5c68ca2bec9a09e3551', '_input': '20ad02201f715f950e2471526f2bda2b6dabf0e04f8b0826e4da2f73798f85dc', '_is_legal_move': 'ada41fede94de2598e349d5df08bc72688e8e6b956acb7a7bd7c2b78b406add2', '_play_ai_turn': 'a32c8066cdc045426fd27540e332c0cc5a2771c9bd0fddaac1d247604b45c3b4', '_set_world': '58626a9e95b4c55ac7e6290f00f122f838a5846b8783c12d1fa1add5db01c355', '_save_match': 'a2b1d2e1de43fb34a7b58f702716986b8916659537778e21aa6ff7876ab32e6e', '_load_match': '69f05ceabb024751f57c3c9bfb1eb1b02f51c8c38a53969f189b08bbf55695fb', '_reset_round': 'a7d66a984f4fc6399e8bc7968dd06c284959834865276decb8d8ee706280ef15', '_on_reserve_pressed': 'cfe577b295f1e94d506679926171663d9abd54c5717bd125b0bb011317a2b71f', '_match_snapshot': '813cad0fc420587b3b7265a62baee42d11db2eca26cf6eda06b5a2f34e74960b', '_undo_last_move': '1faaeecda72959751a814bf940e94ee4860bc9155cbe4cfb0701e54f407e8f4d'}


def body(name: str) -> str:
    m = re.search(r"^func " + re.escape(name) + r"\(", MAIN, re.M)
    assert m, name
    next_func = re.search(r"\nfunc ", MAIN[m.end():])
    return MAIN[m.start():m.end() + next_func.start() if next_func else len(MAIN)]


def test_canonical_seven_reference_images_unchanged():
    manifest = json.loads((ROOT / "tools/approved_seven_world_manifest.json").read_text())
    folders = ["a5_void_ranked", "a5_pirate_ranked", "a5_atlantis_ranked",
               "a5_gods_ranked", "a5_sand_ranked", "a5_night_ranked", "a5_northern_ranked"]
    assert len(manifest["images"]) == 7
    for entry, folder in zip(manifest["images"], folders):
        p = ROOT / "assets" / folder / (entry["file"].removesuffix(".png") + "_canon_source.png")
        assert hashlib.sha256(p.read_bytes()).hexdigest() == entry["sha256"]


def test_void_originals_are_warm_p1_and_cool_p2():
    def mean_rgb(player):
        with Image.open(ROOT / f"assets/a5_void_ranked/void_rank_09_p{player}.png") as im:
            rgba = im.convert("RGBA")
            pixels = [p for p in rgba.get_flattened_data() if p[3] > 180]
        return tuple(sum(p[i] for p in pixels) / len(pixels) for i in range(3))
    p1, p2 = mean_rgb(1), mean_rgb(2)
    assert p1[0] > p1[2] * 1.3
    assert p2[2] > p2[0] * 1.3
    helper = body("_update_void_dome_light")
    assert 'Color("#ff9d42") if player == 1 else Color("#49bfff")' in helper
    contact = body("_apply_piece_contact")
    assert 'Color(1.0, 0.74, 0.49, 0.23) if player == 1 else Color(0.57, 0.77, 1.0, 0.23)' in contact


def test_nine_live_void_halves_created_under_real_piece_icons():
    creation = body("_create_perspective_layer")
    assert creation.count('void_pool.name = "VoidDomePool%d" % i') == 1
    assert creation.count('void_bloom.name = "VoidDomeBloom%d" % i') == 1
    assert creation.count('void_rim.name = "VoidDomeRim%d" % i') == 1
    assert creation.index('void_pool.name') < creation.index('var icon := TextureRect.new()')
    assert 'perspective_void_dome_pools.append(void_pool)' in creation
    assert 'perspective_void_dome_blooms.append(void_bloom)' in creation
    assert 'perspective_void_dome_rims.append(void_rim)' in creation
    assert 'void_pool.texture = _night_beacon_pool_texture' in creation
    assert 'void_pool.z_index = 3' in creation
    assert 'Button.new()' not in body("_update_void_dome_light")


def test_rank_drives_strictly_increasing_radii_and_24_point_ellipse():
    helper = body("_update_void_dome_light")
    assert 'var radius_x := extent * (0.24 + 0.014 * rank)' in helper
    assert 'var radius_y := extent * (0.085 + 0.003 * rank)' in helper
    assert 'for i in range(24):' in helper
    assert 'bloom.points = points' in helper and 'rim.points = points' in helper
    assert 'pool.position = base' in helper
    for extent in (38, 54, 90):
        rx = [extent * (0.24 + 0.014 * rank) for rank in range(1, 10)]
        ry = [extent * (0.085 + 0.003 * rank) for rank in range(1, 10)]
        assert all(b > a for a,b in zip(rx, rx[1:]))
        assert all(b > a for a,b in zip(ry, ry[1:]))
        assert rx[-1] < extent * 0.5 and ry[-1] < extent * 0.2


def test_empty_and_other_worlds_hide_and_clear_geometry():
    helper = body("_update_void_dome_light")
    for fragment in ('world == 0 and rank >= 1 and rank <= 9 and player in [1, 2]',
                     'pool.visible = show', 'bloom.visible = show', 'rim.visible = show',
                     'bloom.clear_points()', 'rim.clear_points()'):
        assert fragment in helper
    refresh = body("_refresh_perspective_layer")
    assert '_update_void_dome_light(perspective_void_dome_pools[i],' in refresh
    assert 'int(top.rank) if not top.is_empty() else 0' in refresh
    assert 'int(top.player) if not top.is_empty() else 0' in refresh


def test_held_legal_preview_uses_identical_light_and_cancels():
    create = body("_create_perspective_layer")
    preview = body("_refresh_touch_preview")
    assert 'HeldVoidDomePool' in create
    assert 'HeldVoidDomeBloom' in create
    assert 'HeldVoidDomeRim' in create
    assert 'perspective_touch_preview_void_pool.self_modulate.a = 0.57' in create
    assert 'perspective_touch_preview_void_pool.visible = false' in preview
    assert 'perspective_touch_preview_void_bloom.clear_points()' in preview
    assert 'perspective_touch_preview_void_rim.clear_points()' in preview
    assert '_update_void_dome_light(perspective_touch_preview_void_pool,' in preview
    assert preview.index('if not _touch_board_pending') < preview.index('_update_void_dome_light(')
    assert '_is_legal_move(turn, rank, _touch_board_cell)' in preview


def test_void_still_floats_and_supported_worlds_have_ground():
    refresh = body("_refresh_perspective_layer")
    assert 'var has_support := current_world != 0' in refresh
    assert 'perspective_support_surface.visible = has_support' in refresh
    assert 'perspective_board_front_fascia.visible = has_support' in refresh
    assert 'perspective_board_right_fascia.visible = has_support' in refresh
    assert 'perspective_support_surface.texture = null' in refresh


def test_native_smoke_registered_and_match_occupancy_bound():
    smoke = body("_run_headless_void_dome_light_smoke")
    suite = body("_run_headless_geometry_and_interaction_smoke")
    match = body("_run_headless_full_match_smoke")
    assert '_run_headless_void_dome_light_smoke()' in suite
    assert 'Void rank 9 light must grow' in smoke
    assert 'Void P1 should be amber' in smoke
    assert 'Void P2 should be blue' in smoke
    assert 'board_stacks == old_board' in smoke
    assert 'var halo_expected := world == 0 and not _top_piece(halo_cell).is_empty()' in match
    assert 'var void_expected := world == 0 and occupied' in match
    assert 'perspective_void_dome_rims[light_cell].points.size() == 24' in match
    assert 'for mode in ["C", "D", "CD"]:' in match
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in match


def test_twelve_protected_gameplay_input_ai_save_functions_byte_identical():
    assert len(PROTECTED) == 12
    for name, original_sha in PROTECTED.items():
        assert hashlib.sha256(body(name).encode()).hexdigest() == original_sha, name


def test_shared_board_engine_and_pirate_controller_unchanged():
    assert MAIN.count('func _on_primary(') == 1
    assert MAIN.count('func _is_legal_move(') == 1
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")' in MAIN
    assert 'pirate' not in body("_update_void_dome_light").lower()
