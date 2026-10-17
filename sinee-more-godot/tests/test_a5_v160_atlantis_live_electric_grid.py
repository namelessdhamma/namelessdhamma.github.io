"""A5 v160: Atlantis' live continuous cyan grid, source-level only (not Godot parity)."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()


def body(name: str) -> str:
    start = re.search(rf'^func {re.escape(name)}\(', MAIN, re.M)
    assert start, name
    after = re.search(r'\nfunc ', MAIN[start.end():])
    return MAIN[start.start():start.end() + after.start() if after else len(MAIN)]


def test_atlantis_approved_source_is_exact_and_has_luminous_grid():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    item = next(i for i in manifest['images'] if i['world'] == 'atlantis')
    image_path = ROOT / 'assets/a5_atlantis_ranked/03_atlantis_canon_source.png'
    assert hashlib.sha256(image_path.read_bytes()).hexdigest() == item['sha256']
    with Image.open(image_path) as im:
        pixels = im.convert('RGB').crop((930, 370, 1010, 450))
        cyan = sum(1 for r, g, b in pixels.get_flattened_data() if b > 160 and g > 150 and b > 1.4 * r)
        assert cyan > 1000, 'Approved art has bright cyan grid at its real intersections'


def test_all_eight_continuous_seams_are_scene_nodes_above_tiles_below_pieces():
    create = body('_create_perspective_layer')
    assert 'for seam_index in range(8):' in create
    assert 'for junction_index in range(16):' in create
    assert 'seam_glow := Line2D.new()' in create
    assert 'seam_core := Line2D.new()' in create
    assert 'junction := Polygon2D.new()' in create
    assert 'seam_glow.z_index = 2' in create
    assert 'seam_core.z_index = 2' in create
    assert 'junction.z_index = 2' in create
    assert create.index('for i in range(9):') < create.index('for seam_index in range(8):')
    assert create.index('for seam_index in range(8):') < create.index('perspective_touch_preview_contact = Polygon2D.new()')
    assert 'seam_core.visible = false' in create
    assert 'junction.visible = false' in create
    assert 'Button.new()' not in create


def test_grid_follows_actual_live_board_and_world_switch_clears_geometry():
    update = body('_refresh_atlantis_live_seams')
    refresh = body('_refresh_perspective_layer')
    assert 'var show := current_world == 2 or current_world == 3' in update
    assert 'glow.visible = show' in update
    assert 'core.visible = show' in update
    assert 'junction.visible = show' in update
    assert 'glow.clear_points()' in update
    assert 'core.clear_points()' in update
    assert 'junction.polygon = PackedVector2Array()' in update
    assert '_refresh_atlantis_live_seams(base)' in refresh
    assert 'PerspectiveGeometry.board_quad(current_world, perspective_rect)' in refresh
    assert MAIN.count('_refresh_atlantis_live_seams(') == 2


def test_bilinear_grid_lines_have_shared_exact_intersections():
    # Independent geometry check for the approved Atlantis quadrilateral.
    quad = [(398, 278), (1288, 275), (1400, 739), (283, 744)]
    def lerp(a, b, t):
        return tuple(a[k] * (1-t) + b[k] * t for k in (0,1))
    for u_index in range(4):
        u = u_index / 3
        start, end = lerp(quad[0], quad[1], u), lerp(quad[3], quad[2], u)
        for v_index in range(4):
            v = v_index / 3
            crossing = lerp(start, end, v)
            hstart, hend = lerp(quad[0], quad[3], v), lerp(quad[1], quad[2], v)
            same = lerp(hstart, hend, u)
            assert math.dist(crossing, same) < 1e-10
    update = body('_refresh_atlantis_live_seams')
    assert 'quad[0].lerp(quad[1], t)' in update
    assert 'quad[3].lerp(quad[2], t)' in update
    assert 'quad[0].lerp(quad[3], t)' in update
    assert 'quad[1].lerp(quad[2], t)' in update
    assert 'var center := top.lerp(bottom, v)' in update


def test_mobile_seams_are_bounded_and_noninteractive():
    update = body('_refresh_atlantis_live_seams')
    assert 'clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)' in update
    assert 'maxf(2.2, 7.0 * scale)' in update
    assert 'maxf(1.0, 2.4 * scale)' in update
    assert 'radius := maxf(1.6, 4.3 * scale)' in update
    for logical_height in (280, 390, 720):
        scale = min(1, max(.35, logical_height/720))
        assert 2.2 <= max(2.2, 7*scale) <= 7
        assert 1.0 <= max(1, 2.4*scale) <= 2.4
    assert 'InputEvent' not in update and '_on_primary' not in update


def test_native_geometry_smoke_registered_but_not_misreported_as_executed():
    smoke = body('_run_headless_atlantis_live_seam_smoke')
    run = body('_run_headless_geometry_and_interaction_smoke')
    full = body('_run_headless_full_match_smoke')
    assert '_run_headless_atlantis_live_seam_smoke()' in run
    assert 'core.points[0].distance_to(expected_start) < 0.01' in smoke
    assert 'core.points[1].distance_to(expected_end) < 0.01' in smoke
    assert 'assert(not seam.visible and seam.points.size() == 0)' in smoke
    assert 'assert(junction.visible == (world == 2 or world == 3)' in full
    assert 'assert(seam.visible == (world == 2 or world == 3)' in full


def test_gameplay_ai_input_and_pirate_controller_do_not_reference_seam_logic():
    for name in ('_on_primary','_is_legal_move','_on_cell_pressed','_play_ai_turn',
                 '_reset_round','_set_world','_on_reserve_pressed','_on_secondary','_input','_save_match'):
        assert '_refresh_atlantis_live_seams' not in body(name)
    assert (ROOT / 'scripts/pirate_opening_campaign.gd').is_file()
    assert (ROOT / 'scripts/ai_opponent.gd').is_file()


def test_seven_world_canon_remains_single_shared_game():
    worlds = (ROOT / 'scripts/world_visuals.gd').read_text()
    assert worlds.count('"ND Premium Void"') == 1
    assert '"Pirate Sea", "Atlantis", "Gods of the Deep"' in worlds
    assert '"Sand Sea", "Night Sea", "Northern Sea"' in worlds
    assert 'var perspective_tiles: Array[Polygon2D]' in MAIN
    assert MAIN.count('func _on_primary(') == 1


def test_native_qualifier_covers_both_mobile_landscape_viewports():
    workflow = (ROOT.parent / '.github/workflows/a5-seven-worlds-native-qualification.yml').read_text()
    assert 'Capture 14 actual rendered frames at 746x280' in workflow
    assert 'Capture 14 actual rendered frames at 844x390' in workflow
    assert '--size 746x280 --timeout 240' in workflow
    assert '--size 844x390 --timeout 240' in workflow
    assert 'native_touch_simulation=NOT_REAL_PHONE_TOUCH' in workflow
    assert 'VISUAL_PARITY=REVIEW_REQUIRED_ALL_SEVEN' in workflow
