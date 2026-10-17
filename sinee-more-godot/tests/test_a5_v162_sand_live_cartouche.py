"""A5 v162 Sand Sea live turquoise/gold cartouche: source/geometry checks.

These checks do not substitute for Godot 4.7.2 rendering or real phone touch.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name: str) -> str:
    m = re.search(rf'^func {re.escape(name)}\(', MAIN, re.M)
    assert m, name
    next_func = re.search(r'\nfunc ', MAIN[m.end():])
    return MAIN[m.start():m.end()+next_func.start() if next_func else len(MAIN)]


def test_accepted_sand_art_immutable_and_contains_lapis_border():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    entry = next(e for e in manifest['images'] if e['world'] == 'sand_sea')
    p = ROOT / 'assets/a5_sand_ranked/05_sand_sea_canon_source.png'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == entry['sha256']
    with Image.open(p) as im:
        assert im.size == tuple(entry['size'])
        crop = im.convert('RGB').crop((400, 300, 1400, 800))
        turquoise = sum(1 for r,g,b in crop.get_flattened_data()
                        if b > 100 and g > 80 and b > r * 1.25 and g > r * 1.15)
        assert turquoise > 2500


def test_one_noninteractive_live_layer_not_a_second_board():
    create = body('_create_perspective_layer')
    assert create.count('SandLapisCartoucheBand') == 1
    assert create.count('SandGoldCartoucheFillet') == 1
    assert create.count('for glyph_index in range(12):') == 1
    assert create.index('for i in range(9):') < create.index('SandLapisCartoucheBand')
    assert 'perspective_sand_inlay_band.z_index = 2' in create
    assert 'perspective_sand_inlay_gold.z_index = 2' in create
    assert 'glyph.z_index = 2' in create
    assert 'Button.new()' not in body('_refresh_sand_live_cartouche')
    assert MAIN.count('func _on_primary(') == 1


def test_cartouche_geometry_is_live_and_uses_real_board_quad():
    update = body('_refresh_sand_live_cartouche')
    refresh = body('_refresh_perspective_layer')
    assert 'var show := current_world == 4 and quad.size() == 4' in update
    assert 'perspective_sand_inlay_band.points = outer' in update
    assert 'perspective_sand_inlay_gold.points = quad' in update
    assert 'outer.append(corner + (corner - center).normalized() * 3.0 * scale)' in update
    assert 'var a: Vector2 = outer[edge_index]' in update
    assert 'var b: Vector2 = outer[(edge_index + 1) % 4]' in update
    assert 'var fraction := (float(glyph_index % 3) + 0.5) / 3.0' in update
    assert '_refresh_sand_live_cartouche(base)' in refresh
    assert refresh.index('_refresh_sand_live_cartouche(base)') < refresh.index('var has_support :=')


def test_non_sand_worlds_clear_all_geometry():
    update = body('_refresh_sand_live_cartouche')
    for phrase in ('perspective_sand_inlay_band.visible = show',
                   'perspective_sand_inlay_gold.visible = show',
                   'perspective_sand_inlay_band.clear_points()',
                   'perspective_sand_inlay_gold.clear_points()',
                   'glyph.visible = false', 'glyph.polygon = PackedVector2Array()'):
        assert phrase in update
    smoke = body('_run_headless_sand_live_cartouche_smoke')
    assert '_set_world(4)' in smoke
    assert 'for other_world in [0, 1, 2, 3, 5, 6]:' in smoke
    assert 'glyph.polygon.size() == 0' in smoke


def test_touch_hit_testing_and_actual_game_state_unchanged():
    for name in ('_on_primary', '_on_cell_pressed', '_input', '_is_legal_move',
                 '_play_ai_turn', '_set_world', '_save_match'):
        assert 'sand_inlay' not in body(name)
    assert 'perspective_sand_inlay_band' not in body('_touch_hit_test_cell') if 'func _touch_hit_test_cell(' in MAIN else True
    assert 'perspective_sand_inlay_band' not in body('_on_primary')


def test_mobile_geometry_nonzero_and_limited_outside_board():
    # A pure geometric sanity check, NOT a screenshot or actual Godot render.
    quad = [(0.2, 0.22), (0.8, 0.22), (0.88, 0.86), (0.12, 0.86)]
    for width, height in ((746,280),(844,390),(1280,720)):
        q = [(x*width,y*height) for x,y in quad]
        center = (sum(x for x,y in q)/4, sum(y for x,y in q)/4)
        scale = max(0.35,min(1.0,(0.64*height)/720.0))
        outer = []
        for x,y in q:
            dx,dy=x-center[0],y-center[1]
            norm=math.hypot(dx,dy)
            outer.append((x+dx/norm*3*scale,y+dy/norm*3*scale))
        for side in range(4):
            a,b=outer[side],outer[(side+1)%4]
            for slot in range(3):
                t=(slot+0.5)/3
                at=(a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t)
                assert 0 < at[0] < width and 0 < at[1] < height
                assert math.dist(at,a)>0 and math.dist(at,b)>0
        assert len(outer)==4


def test_native_smoke_and_21_match_invariants_registered():
    smoke = body('_run_headless_sand_live_cartouche_smoke')
    suite = body('_run_headless_geometry_and_interaction_smoke')
    full = body('_run_headless_full_match_smoke')
    assert '_run_headless_sand_live_cartouche_smoke()' in suite
    assert 'perspective_sand_inlay_gold.points[i].distance_to(quad[i]) < 0.01' in smoke
    assert 'perspective_sand_inlay_band.visible == (world == 4)' in full
    assert 'glyph.visible == (world == 4)' in full
    assert 'for mode in ["C", "D", "CD"]:' in full
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in full


def test_other_worlds_approved_art_remains_immutable():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    folders = ['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked',
               'a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
    for e,folder in zip(manifest['images'],folders):
        source=ROOT/'assets'/folder/(e['file'].removesuffix('.png')+'_canon_source.png')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==e['sha256']
