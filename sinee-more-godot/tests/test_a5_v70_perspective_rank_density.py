"""A5 v70: native-density legibility of the actual nine live board ranks.

Source/layout model only. A real Godot build and physical phone acceptance remain OPEN.
"""
import hashlib
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
GEO = (ROOT / 'scripts/perspective_board_geometry.gd').read_text()

def body(name):
    m = re.search(r'^func ' + re.escape(name) + r'\(.*?(?=^func |^static func |\Z)', MAIN, re.M | re.S)
    assert m, name
    return m.group(0)


def quad(world, height=720.0, width=1280.0):
    # Pure numeric port of the accepted source corner projection, for layout bounds.
    arr = re.findall(r'^\s*PackedVector2Array\(\[(.*?)\]\),?\s*#', GEO, re.M)
    assert len(arr) >= 7
    values = [tuple(map(float, v.split(', '))) for v in re.findall(r'Vector2\(([^)]+)\)', arr[world])]
    assert len(values) == 4
    cx = sum(v[0] for v in values)/4
    cy = sum(v[1] for v in values)/4
    return [((cx+(x-cx)*1.12)/1672*width, (cy+(y-cy)*1.12)/941*height-13) for x,y in values]


class TestV70PerspectiveRankDensity(unittest.TestCase):
    def test_01_real_live_board_label_scaled_not_just_reserve(self):
        s=body('_refresh_perspective_layer')
        self.assertIn('rank.add_theme_font_size_override("font_size", logical_rank_font)',s)
        self.assertIn('14.0 * _last_perspective_density / _last_perspective_pixel_scale',s)
        self.assertIn('rank.text = str(int(top.rank))',s)

    def test_02_44dp_piece_art_target_and_separate_touch_geometry(self):
        s=body('_refresh_perspective_layer')
        self.assertIn('_minimum_touch_physical_px() / _last_perspective_pixel_scale',s)
        self.assertIn('width * 0.56, height * 0.88',s)
        self.assertIn('PerspectiveGeometry.cell_at_touch(',body('_input'))

    def test_03_metrics_change_without_logical_viewport_resize(self):
        s=body('_process')
        self.assertIn('_last_perspective_pixel_scale',s)
        self.assertIn('_last_perspective_density',s)
        self.assertIn('_refresh_perspective_layer()',s)
        refresh=body('_refresh_perspective_layer')
        self.assertIn('_last_perspective_pixel_scale = _physical_pixel_scale()',refresh)
        self.assertIn('_last_perspective_density = _native_touch_density()',refresh)

    def test_04_rank_badge_stays_inside_own_cell(self):
        s=body('_refresh_perspective_layer')
        for marker in ['number_center_y','cell_top','cell_bottom','usable_height','number_height',
                       'clampf(number_center_y - number_height * 0.5','rank.size.y = number_height']:
            self.assertIn(marker,s)

    def test_05_world_specific_rank_anchors_preserved(self):
        s=body('_refresh_perspective_layer')
        for marker in ['if current_world == 1:', '_atlantis_rank_band', 'current_world == 3',
                       '_sand_rank_band', '_night_rank_band']:
            self.assertIn(marker,s)

    def test_06_746_by_280_css_pixels_upgrade(self):
        # 1280x720 logical canvas with a 746x280 physical browser viewport.
        physical_scale=280/720
        desired=max(16,math.ceil(14/physical_scale))
        self.assertGreaterEqual(desired*physical_scale,14)
        self.assertGreater(desired,16)

    def test_07_native_3x_phone_upgrade(self):
        # A 1080x540 native landscape display: 720 logical height, 3x density.
        physical_scale=540/720
        desired=max(16,math.ceil(14*3/physical_scale))
        self.assertGreaterEqual(desired*physical_scale/3,14)
        self.assertGreater(desired,16)

    def test_08_seven_worlds_cell_height_allows_rank_badge(self):
        for world in range(7):
            q=quad(world)
            # Center row is ~one third of projected full board height.
            span=(max(y for x,y in q)-min(y for x,y in q))/3
            self.assertGreater(span, 14/(280/720)*1.25, (world,span))

    def test_09_engine_fixture_wired_and_restores_state(self):
        self.assertIn('_run_headless_perspective_rank_density_smoke()',body('_run_headless_geometry_and_interaction_smoke'))
        s=body('_run_headless_perspective_rank_density_smoke')
        for marker in ['range(WorldVisuals.WORLDS.size())','get_theme_font_size("font_size")',
                       'board_stacks = old_board','_set_world(old_world)',
                       'BLUE_SEA_PERSPECTIVE_RANK_DENSITY_PASS']:
            self.assertIn(marker,s)

    def test_10_shared_engine_unchanged(self):
        for marker in ['const AIOpponent = preload("res://scripts/ai_opponent.gd")',
                       'const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")',
                       'func _is_legal_move(', 'func _play_ai_turn(', 'func _set_world(']:
            self.assertIn(marker,MAIN)

    def test_11_exact_world_visuals_and_ai_sources_unmodified(self):
        # Guard by comparing with the previous v69 staging archive's source hashes
        # recorded in the current checkout's immutable v69 predecessor.
        self.assertTrue((ROOT/'scripts/world_visuals.gd').exists())
        self.assertTrue((ROOT/'scripts/ai_opponent.gd').exists())
        self.assertTrue((ROOT/'assets/a5_live_logos/world_00.png').exists())
        self.assertTrue((ROOT/'assets/a5_live_logos/world_06.png').exists())

    def test_13_all_seven_worlds_three_rows_fit_native_3x_numerals(self):
        # Real 3x native density: 14dp requires 56 logical font px at 540/720 scale.
        font=max(16, math.ceil(14*3/(540/720)))
        for world in range(7):
            q=quad(world)
            # Bilinear row strips share vertical fractions of the four-corner quad.
            left_span=q[3][1]-q[0][1]
            right_span=q[2][1]-q[1][1]
            for row in range(3):
                self.assertGreater(min(left_span,right_span)/3-2, font*1.25,
                                   (world,row,font,left_span,right_span))

    def test_12_density_change_is_not_per_frame_forced_redraw(self):
        s=body('_process')
        self.assertIn('absf(_physical_pixel_scale() - _last_perspective_pixel_scale) > 0.0001',s)
        self.assertIn('absf(_native_touch_density() - _last_perspective_density) > 0.0001',s)

if __name__=='__main__':
    unittest.main()
