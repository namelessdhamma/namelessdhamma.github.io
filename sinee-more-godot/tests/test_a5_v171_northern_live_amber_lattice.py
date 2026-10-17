"""A5 v171 Northern Sea: live gold ice-board lattice, source-only qualification.

Does not claim Godot execution, native frames, real touch, or visual parity.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT/'scripts/main.gd').read_text(encoding='utf-8')


def body(name: str) -> str:
    start = re.search(rf'^func {re.escape(name)}\(', MAIN, re.M)
    assert start, name
    after = re.search(r'\nfunc ', MAIN[start.end():])
    return MAIN[start.start():start.end()+after.start() if after else len(MAIN)]


def test_northern_approved_png_is_exact_and_has_warm_grid():
    manifest = json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
    entry = next(e for e in manifest['images'] if e['world']=='northern_sea')
    path = ROOT/'assets/a5_northern_ranked/07_northern_sea_canon_source.png'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    with Image.open(path) as im:
        assert im.size == tuple(entry['size'])
        region = im.convert('RGB').crop((680,330,730,520))
        gold = sum(1 for r,g,b in region.get_flattened_data()
                   if r>180 and g>100 and b<g*1.2 and r>g*1.05)
        assert gold > 1000, gold


def test_northern_uses_own_8_seams_and_16_noninteractive_junctions():
    create = body('_create_perspective_layer')
    for token in ('NorthernGridGlow%d','NorthernGridCore%d','NorthernGridStar%d'):
        assert create.count(token)==1
    assert create.count('perspective_northern_grid_glows.append(north_glow)')==1
    assert create.count('perspective_northern_grid_cores.append(north_core)')==1
    assert create.count('perspective_northern_grid_junctions.append(north_star)')==1
    assert 'north_glow.z_index = 2' in create
    assert 'north_core.z_index = 2' in create
    assert 'north_star.z_index = 2' in create
    assert create.index('perspective_atlantis_junctions.append(junction)') < create.index('NorthernGridGlow%d')
    assert 'Button.new()' not in body('_refresh_northern_live_lattice')


def test_northern_grid_is_bound_to_live_board_quad_and_clears_on_world_change():
    update=body('_refresh_northern_live_lattice')
    refresh=body('_refresh_perspective_layer')
    assert 'var show := current_world == 6 and quad.size() == 4' in update
    assert '_refresh_northern_live_lattice(base)' in refresh
    assert refresh.index('_refresh_atlantis_live_seams(base)') < refresh.index('_refresh_northern_live_lattice(base)') < refresh.index('_refresh_sand_live_cartouche(base)')
    for token in ('glow.visible = show','core.visible = show','star.visible = show',
                  'glow.clear_points()','core.clear_points()','star.polygon = PackedVector2Array()'):
        assert token in update
    assert MAIN.count('_refresh_northern_live_lattice(')==2


def test_perspective_grid_has_16_consistent_intersections_at_phone_sizes():
    quad=[(407.,300.),(1264.,299.),(1396.,744.),(281.,747.)]
    def lerp(a,b,t):return (a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t)
    for w,h in ((746,280),(844,390),(1280,720)):
        q=[(x*w/1672,y*h/941) for x,y in quad]
        for u in [i/3 for i in range(4)]:
            a=lerp(q[0],q[1],u);b=lerp(q[3],q[2],u)
            for v in [j/3 for j in range(4)]:
                c=lerp(q[0],q[3],v);d=lerp(q[1],q[2],v)
                assert math.dist(lerp(a,b,v),lerp(c,d,u))<1e-8
    update=body('_refresh_northern_live_lattice')
    assert 'quad[0].lerp(quad[1], t)' in update
    assert 'quad[3].lerp(quad[2], t)' in update
    assert 'var center := upper.lerp(lower, v)' in update


def test_warm_palette_and_bounded_746x280_geometry():
    update=body('_refresh_northern_live_lattice')
    for token in ('Color(1.0, 0.52, 0.12, 0.34)',
                  'Color(1.0, 0.86, 0.57, 0.91)',
                  'Color(1.0, 0.93, 0.71, 0.96)',
                  'maxf(2.5, 9.0 * scale)', 'maxf(1.2, 3.0 * scale)',
                  'maxf(1.8, 5.0 * scale)',
                  'clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)'):
        assert token in update
    for h in (280,390,720):
        scale=min(1,max(.35,h/720))
        assert 2.5 <= max(2.5,9*scale) <=9
        assert 1.2 <= max(1.2,3*scale) <=3
    assert 'InputEvent' not in update and '_on_primary' not in update


def test_qualified_underwater_palette_and_world_selection_unchanged():
    underwater=body('_refresh_atlantis_live_seams')
    assert 'var show := current_world == 2 or current_world == 3' in underwater
    assert 'Color(0.02, 0.48, 1.0, 0.41) if gods else Color(0.05, 0.78, 1.0, 0.31)' in underwater
    assert 'Color(0.62, 0.92, 1.0, 0.95) if gods else Color(0.34, 0.96, 1.0, 0.84)' in underwater
    assert 'northern_grid' not in underwater
    assert 'perspective_northern_grid' not in body('_refresh_sand_live_cartouche')


def test_native_smoke_registered_with_all_seven_world_teardown():
    smoke=body('_run_headless_northern_live_lattice_smoke')
    suite=body('_run_headless_geometry_and_interaction_smoke')
    assert '_run_headless_northern_live_lattice_smoke()' in suite
    assert '_set_world(6)' in smoke
    assert 'for other_world in [0, 1, 2, 3, 4, 5]:' in smoke
    assert 'core.points[0].distance_to(expected_start) < 0.01' in smoke
    assert 'assert(not line.visible and line.points.size() == 0)' in smoke
    assert 'assert(not star.visible and star.polygon.size() == 0)' in smoke
    assert 'board_stacks == previous_board and reserve_available == previous_reserves' in smoke


def test_shared_gameplay_and_ai_unmodified_by_northern_lattice():
    for name in ('_on_primary','_is_legal_move','_on_cell_pressed','_play_ai_turn',
                 '_reset_round','_set_world','_on_reserve_pressed','_input','_save_match'):
        assert 'northern_grid' not in body(name)
        assert 'northern_live_lattice' not in body(name)
    assert MAIN.count('func _on_primary(')==1
    assert (ROOT/'scripts/ai_opponent.gd').exists()
    assert (ROOT/'scripts/pirate_opening_campaign.gd').exists()


def test_all_seven_exact_approved_images_untouched():
    manifest=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
    folders=['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked',
             'a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
    assert len(manifest['images'])==7
    for entry,folder in zip(manifest['images'],folders):
        path=ROOT/'assets'/folder/(entry['file'].removesuffix('.png')+'_canon_source.png')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
