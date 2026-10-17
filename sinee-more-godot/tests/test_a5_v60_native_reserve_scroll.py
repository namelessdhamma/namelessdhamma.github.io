"""A5 v60 native-density reserve overflow: static/model evidence, not a Godot runtime PASS."""
import hashlib
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
SCENE = (ROOT / 'main.tscn').read_text()


def body(name):
    m = re.search(r'^func '+re.escape(name)+r'\([^\n]*\).*?(?=^func |^static func |\Z)', MAIN, re.M | re.S)
    assert m, name
    return m.group()


def reserve_layout(physical_width, density, scale=1.0, usable_fraction=0.97):
    """Model target widths and scroll extent, not an engine screenshot."""
    touch = math.ceil(44.0 * density / scale)
    visible = math.floor(physical_width * usable_fraction / scale)
    content = 9 * touch + 8  # eight 1px logical separations
    return {'touch':touch, 'viewport':visible, 'content':content,
            'overflow':max(0,content-visible)}


class TestA5V60(unittest.TestCase):
    def test_01_reproduced_native_high_density_overflow(self):
        for width, density in [(1080,3),(1170,3),(720,2),(1440,4)]:
            x=reserve_layout(width,density)
            self.assertGreater(x['overflow'],0,(width,density,x))
            self.assertGreaterEqual(x['touch'],44*density)

    def test_02_browser_746_stays_unclipped(self):
        x=reserve_layout(746,1)
        self.assertEqual(x['overflow'],0)
        self.assertGreaterEqual(x['viewport'],x['content'])

    def test_03_scroller_is_shared_and_scrollable_only_horizontally(self):
        f=body('_prepare_world_shell')
        for phrase in ['reserve_scroller = ScrollContainer.new()',
                       'reserve_scroller.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO',
                       'reserve_scroller.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED',
                       'reserve_scroller.follow_focus = true',
                       'reserve_scroller.scroll_deadzone = 8',
                       'reserve.reparent(reserve_row, false)',
                       'reserve.columns = 9']:
            self.assertIn(phrase,f)
        self.assertEqual(f.count('reserve_scroller = ScrollContainer.new()'),1)
        self.assertEqual(f.count('reserve.reparent(reserve_row, false)'),1)

    def test_04_reserve_lookup_and_geometry_follow_reparent(self):
        f=body('_reserve_node')
        self.assertIn('ReserveDock/ReserveScroll/ReserveRow/ReserveOne',f)
        self.assertIn('ReserveDock/ReserveScroll/ReserveRow/ReserveTwo',f)
        for s in ['"reserve1": "SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveOne"',
                  '"reserve2": "SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveTwo"']:
            self.assertIn(s,body('_geometry_snapshot'))
        self.assertIn('ReserveOne',SCENE)
        self.assertIn('ReserveTwo',SCENE)

    def test_05_native_density_reflows_scroller_height_with_buttons(self):
        f=body('_ensure_physical_touch_targets')
        self.assertIn('ceilf(_minimum_touch_physical_px() / scale)',f)
        self.assertIn('reserve_scroller.custom_minimum_size.y = logical_touch',f)
        self.assertIn('dock.custom_minimum_size = Vector2(0, logical_touch)',f)

    def test_06_active_only_and_next_outside_scroller(self):
        f=body('_refresh_surface')
        self.assertIn('reserve.visible = player == turn and not game_over and (not ai_enabled or player == 1)',f)
        self.assertIn('reserve_scroller.visible = not game_over and (not ai_enabled or turn == 1)',f)
        self.assertIn('reserve_scroller.scroll_horizontal = 0',f)
        shell=body('_prepare_world_shell')
        self.assertLess(shell.index('dock.add_child(reserve_scroller)'),shell.index('dock.add_child(next_round_button)'))
        self.assertIn('next_round_button.visible = false',shell)

    def test_07_input_does_not_commit_scroll_swipe_as_board_move(self):
        f=body('_input')
        self.assertIn('dock.get_global_rect().has_point(position)',f)
        self.assertIn('if perspective_tiles.size() != 9 or game_over or _modal_blocks_board_input()',f)
        self.assertIn('get_viewport().set_input_as_handled()',f)

    def test_08_engine_asserts_scroll_reachability_but_is_not_executed(self):
        f=body('_assert_landscape_geometry')
        self.assertIn('reserve_scroller.size.x <= dock.size.x + 0.5',f)
        self.assertIn('last_piece.position.x + last_piece.size.x',f)
        self.assertIn('assert(reserve_scroller.scroll_horizontal > 0',f)
        self.assertIn('await get_tree().process_frame',f)

    def test_09_gameplay_and_ai_remain_shared(self):
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")',MAIN)
        self.assertIn('const WorldVisuals = preload("res://scripts/world_visuals.gd")',MAIN)
        self.assertIn('ai_engine.choose_move(',body('_play_ai_turn'))
        self.assertIn('board_stacks[selected_cell].append(',body('_on_primary'))
        self.assertIn('var pirate_choice := get_node_or_null(',body('_modal_blocks_board_input'))

    def test_10_canonical_pngs_byte_identical(self):
        m=(ROOT/'tools/approved_seven_world_manifest.json').read_text()
        import json
        obj=json.loads(m)
        for entry in obj['images']:
            name=entry['file']
            candidates=list((ROOT/'assets').rglob(name.replace('.png','_canon_source.png')))
            self.assertEqual(len(candidates),1,name)
            self.assertEqual(hashlib.sha256(candidates[0].read_bytes()).hexdigest(),entry['sha256'])

if __name__=='__main__':
    unittest.main()
