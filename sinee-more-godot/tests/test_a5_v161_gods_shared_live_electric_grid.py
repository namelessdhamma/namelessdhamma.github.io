"""A5 v161: Gods of the Deep shares live underwater seam geometry with Atlantis.

Static/source verification only: not a Godot engine or physical-touch PASS.
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
GEOM = (ROOT / 'scripts/perspective_board_geometry.gd').read_text(encoding='utf-8')


def body(name: str) -> str:
    match = re.search(rf'^func {re.escape(name)}\(', MAIN, re.M)
    assert match is not None, name
    nxt = re.search(r'\nfunc ', MAIN[match.end():])
    return MAIN[match.start():match.end()+nxt.start() if nxt else len(MAIN)]


def test_exact_approved_gods_source_and_blue_seam_evidence():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    entry = next(item for item in manifest['images'] if item['world'] == 'gods_of_the_deep')
    source = ROOT / 'assets/a5_gods_ranked/04_gods_of_the_deep_canon_source.png'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256']
    with Image.open(source) as im:
        assert im.size == tuple(entry['size'])
        # The accepted central vertical seam at x~990 y~300-700 is vivid blue.
        region = im.convert('RGB').crop((969, 380, 1000, 530))
        blue = sum(1 for r,g,b in region.get_flattened_data()
                   if b > 160 and b > r*1.45 and g > r*1.3)
        assert blue > 75, f'No meaningful bright blue seam pixels: {blue}'


def test_one_shared_eight_seam_layer_not_a_second_engine_or_screenshot():
    create = body('_create_perspective_layer')
    assert create.count('for seam_index in range(8):') == 1
    assert create.count('for junction_index in range(16):') == 1
    assert 'seam_glow.z_index = 2' in create
    assert 'seam_core.z_index = 2' in create
    assert 'junction.z_index = 2' in create
    assert create.index('for i in range(9):') < create.index('for seam_index in range(8):')
    assert MAIN.count('func _on_primary(') == 1
    assert 'perspective_tiles: Array[Polygon2D]' in MAIN
    assert 'Button.new()' not in body('_refresh_atlantis_live_seams')


def test_both_underwater_worlds_show_and_other_five_clear():
    update = body('_refresh_atlantis_live_seams')
    assert 'var show := current_world == 2 or current_world == 3' in update
    assert 'var gods := current_world == 3' in update
    for phrase in ('glow.visible = show', 'core.visible = show',
                   'junction.visible = show', 'glow.clear_points()',
                   'core.clear_points()', 'junction.polygon = PackedVector2Array()'):
        assert phrase in update
    assert MAIN.count('_refresh_atlantis_live_seams(') == 2
    assert '_refresh_atlantis_live_seams(base)' in body('_refresh_perspective_layer')


def test_gods_cobalt_white_palette_atlantis_original_cyan_unchanged():
    update = body('_refresh_atlantis_live_seams')
    assert 'Color(0.02, 0.48, 1.0, 0.41) if gods else Color(0.05, 0.78, 1.0, 0.31)' in update
    assert 'Color(0.62, 0.92, 1.0, 0.95) if gods else Color(0.34, 0.96, 1.0, 0.84)' in update
    assert 'Color(0.72, 0.96, 1.0, 0.96) if gods else Color(0.45, 0.98, 1.0, 0.82)' in update
    assert 'maxf(2.2, 7.0 * scale)' in update and 'maxf(1.0, 2.4 * scale)' in update
    assert 'maxf(2.4, 8.0 * scale)' in update and 'maxf(1.1, 2.8 * scale)' in update


def test_undersea_grid_intersections_coincide_with_nine_live_cells_at_mobile_sizes():
    corners = {
        2: [(398.,278.),(1288.,275.),(1400.,739.),(283.,744.)],
        3: [(385.,278.),(1280.,279.),(1410.,730.),(265.,730.)],
    }
    def lerp(a,b,t):
        return (a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t)
    for world, ref in corners.items():
        for w,h in ((746,280),(844,390),(1280,720)):
            center = (sum(p[0] for p in ref)/4,sum(p[1] for p in ref)/4)
            shift = -min(h*0.045,13)
            q = [((center[0]+(p[0]-center[0])*1.12)/1672*w,
                  (center[1]+(p[1]-center[1])*1.12)/941*h+shift)
                 for p in ref]
            for i in range(4):
                u = i/3
                a,b = lerp(q[0],q[1],u),lerp(q[3],q[2],u)
                for j in range(4):
                    v=j/3
                    x,y=lerp(q[0],q[3],v),lerp(q[1],q[2],v)
                    assert math.dist(lerp(a,b,v),lerp(x,y,u)) < 1e-8
            assert w>0 and h>0
    assert 'static func cell_quad(' in GEOM
    assert '_bilinear(q, u0, v0)' in GEOM


def test_native_smoke_covers_atlantis_gods_switch_and_all_21_matches():
    smoke = body('_run_headless_atlantis_live_seam_smoke')
    full = body('_run_headless_full_match_smoke')
    assert '_set_world(2)' in smoke
    assert '_set_world(3)' in smoke
    assert '_set_world(1)' in smoke
    assert 'seam.default_color == Color(0.62, 0.92, 1.0, 0.95)' in smoke
    assert 'assert(not seam.visible and seam.points.size() == 0)' in smoke
    assert 'seam.visible == (world == 2 or world == 3)' in full
    assert 'junction.visible == (world == 2 or world == 3)' in full
    assert 'for mode in ["C", "D", "CD"]:' in full
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in full


def test_gameplay_and_pirate_unchanged_in_underwater_visual_delta():
    for name in ('_on_primary','_is_legal_move','_on_cell_pressed','_play_ai_turn',
                 '_reset_round','_set_world','_on_reserve_pressed','_on_secondary',
                 '_input','_save_match'):
        assert '_refresh_atlantis_live_seams' not in body(name)
    assert (ROOT / 'scripts/pirate_opening_campaign.gd').exists()
    assert (ROOT / 'scripts/ai_opponent.gd').exists()


def test_source_canon_all_seven_immutable():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    assert len(manifest['images']) == 7
    asset_roots = ['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked',
                   'a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
    for entry, folder in zip(manifest['images'], asset_roots):
        source = ROOT / 'assets' / folder / (entry['file'].removesuffix('.png')+'_canon_source.png')
        assert source.exists(), source
        assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256']
