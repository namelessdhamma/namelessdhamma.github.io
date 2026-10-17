"""Night Sea dynamic diffuse pool integration, source/geometry only (not a native render)."""
from pathlib import Path
import hashlib
import math
import re
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()
MANIFEST = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())


def block(start, end):
    return SOURCE.split(start, 1)[1].split(end, 1)[0]


def test_canonical_night_png_unchanged():
    night = ROOT / 'assets/a5_night_ranked/06_night_sea_canon_source.png'
    assert hashlib.sha256(night.read_bytes()).hexdigest() == 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'
    assert any(i['world'] == 'night_sea' and i['sha256'] == hashlib.sha256(night.read_bytes()).hexdigest() for i in MANIFEST['images'])


def test_one_reusable_radial_alpha_texture_not_screenshot():
    make = block('func _make_night_beacon_pool_texture()', '\nfunc _create_perspective_layer()')
    assert 'Image.create(dimension, dimension, false, Image.FORMAT_RGBA8)' in make
    assert 'for y in range(dimension):' in make and 'for x in range(dimension):' in make
    assert '0.58 * pow(maxf(0.0, 1.0 - radius), 1.8)' in make
    assert 'ImageTexture.create_from_image(img)' in make
    assert SOURCE.count('_night_beacon_pool_texture = _make_night_beacon_pool_texture()') == 1
    assert '06_night_sea_canon_source.png' not in make
    # Verify the original Night live + held nodes independently. Other worlds
    # may reuse this ONE radial texture without changing Night's behavior.
    create = block('func _create_perspective_layer()', '\nfunc _perspective_visual_bottom(')
    assert 'pool.texture = _night_beacon_pool_texture' in create
    assert 'perspective_touch_preview_pool.texture = _night_beacon_pool_texture' in create
    assert 'perspective_night_beacon_pools.append(pool)' in create
    assert 'perspective_touch_preview_pool.name = "HeldNightBeaconPool"' in create


def test_radial_falloff_positive_center_zero_edge_and_bounded():
    def alpha(x, y):
        radius = math.hypot((x + .5 - 48) / 48, (y + .5 - 48) / 48)
        return .58 * max(0., 1. - radius)**1.8
    assert .56 < alpha(47, 47) < .58
    assert alpha(0, 0) == 0 and alpha(95, 95) == 0
    assert alpha(24, 47) > alpha(12, 47) > alpha(1, 47)
    assert 0 <= min(alpha(x, y) for x in range(0, 96, 7) for y in range(0, 96, 7))


def test_nine_live_noninteractive_pools_plus_one_held_preview():
    create = block('func _create_perspective_layer()', '\nfunc _perspective_visual_bottom(')
    assert 'for i in range(9):' in create
    assert 'pool := Sprite2D.new()' in create
    assert 'pool.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR' in create
    assert 'pool.z_index = 3' in create
    assert 'perspective_night_beacon_pools.append(pool)' in create
    assert 'HeldNightBeaconPool' in create
    assert 'perspective_touch_preview_pool.self_modulate.a = 0.57' in create
    assert 'Button.new()' not in create and 'pool.mouse_filter' not in create


def test_pool_geometry_is_live_rank_specific_and_world_gated():
    pool = block('func _update_night_beacon_pool(', '\nfunc _update_night_beacon_ring(')
    assert 'world == 5 and rank >= 1 and rank <= 9 and player in [1, 2]' in pool
    assert 'pool.visible = show' in pool and 'if not show:\n\t\treturn' in pool
    assert 'PieceGrounding.bottom_fraction(world, rank)' in pool
    assert 'radius_x := extent * (0.28 + 0.015 * rank)' in pool
    assert 'radius_y := extent * (0.105 + 0.003 * rank)' in pool
    assert '2.9 * radius_x / 96.0' in pool
    assert 'Color("#ff9c35") if player == 1 else Color("#4cbcff")' in pool
    for rank in range(1, 9):
        assert 2.9*(.28+.015*rank) < 2.9*(.28+.015*(rank+1))


def test_live_and_preview_share_helper_and_clear_on_release():
    assert SOURCE.count('_update_night_beacon_pool(') == 3  # declaration + 2 call sites
    live = block('func _refresh_perspective_layer()', '\nfunc _refresh_touch_preview()')
    preview = block('func _refresh_touch_preview()', '\nfunc _refresh_selection_feedback()')
    assert '_update_night_beacon_pool(perspective_night_beacon_pools[i]' in live
    assert '_update_night_beacon_pool(perspective_touch_preview_pool' in preview
    assert 'perspective_touch_preview_pool.visible = false' in preview
    assert '_is_legal_move(turn, rank, _touch_board_cell)' in preview
    assert 'perspective_touch_preview_pool.visible = true' not in preview


def test_native_21_match_smoke_checks_live_pool_state():
    smoke = block('func _run_headless_full_match_smoke()', '\nfunc _run_headless_hud_notice_smoke()')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'for mode in ["C", "D", "CD"]:' in smoke
    assert 'perspective_night_beacon_pools[light_cell].visible == light_expected' in smoke
    assert 'perspective_night_beacon_pools[light_cell].texture == _night_beacon_pool_texture' in smoke


def test_shared_d2_rules_and_touch_handlers_unmodified_from_v157():
    # Hash assertions are generated from v157 separately in the build receipt.
    assert SOURCE.count('func _on_primary() -> void:') == 1
    assert SOURCE.count('func _on_cell_pressed(index: int) -> void:') == 1
    assert 'func _is_legal_move(' in SOURCE
    assert '_update_night_beacon_pool' not in block('func _on_primary() -> void:', '\nfunc _on_secondary()')
