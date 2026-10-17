"""A5 v167: prevent reserve ghost selections from pan and mouse-drag input.

Portable event-order oracle + exact source bindings. Native Godot fixture is
registered in main.gd but is NOT executed by these Python tests.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text()


def body(name):
    match = re.search(rf'^func {re.escape(name)}\(', SRC, re.M)
    assert match, name
    tail = SRC[match.start():]
    next_fn = re.search(r'\n(?:func |static func )', tail)
    return tail[:next_fn.start()] if next_fn else tail


class ReserveInputOracle:
    def __init__(self):
        self.touch = False
        self.touch_swiped = False
        self.touch_block = 0
        self.pointer = False
        self.pointer_dragged = False
        self.pointer_block = 0
        self.origin = 0
        self.selected = None

    def touch_down(self, inside=True):
        self.touch = inside
        self.touch_swiped = False
        if inside:
            self.touch_block = 0
            self.pointer_block = 0

    def touch_pan(self):
        if self.touch:
            self.touch_swiped = True
        if self.pointer:
            self.pointer_dragged = True

    def touch_up(self, now):
        if self.touch and self.touch_swiped:
            self.touch_block = now + 350
        self.touch = False
        self.touch_swiped = False

    def mouse_down(self, x, inside=True):
        self.pointer = inside
        self.origin = x
        self.pointer_dragged = False
        if inside:
            self.pointer_block = 0

    def mouse_move(self, x, left=True, density=1, scale=1):
        if self.pointer and left and abs(x - self.origin) > max(8, 12 * density / scale):
            self.pointer_dragged = True

    def mouse_up(self, now):
        if self.pointer and self.pointer_dragged:
            self.pointer_block = now + 350
        self.pointer = False
        self.pointer_dragged = False

    def gui_pressed(self, rank, now):
        if (self.touch_swiped or self.pointer_dragged or
                self.touch_block > 0 and now <= self.touch_block or
                self.pointer_block > 0 and now <= self.pointer_block):
            return False
        self.selected = rank
        return True


class ReservePointerPanGuard(unittest.TestCase):
    def test_pan_during_live_touch_blocks_late_rank9(self):
        for world in range(7):
            m = ReserveInputOracle(); m.touch_down(); m.touch_pan(); m.touch_up(1000)
            self.assertFalse(m.gui_pressed(9, 1001), world)
            self.assertIsNone(m.selected)

    def test_pan_without_active_contact_does_not_block_click(self):
        m = ReserveInputOracle(); m.touch_pan()
        m.mouse_down(100); m.mouse_up(1010)
        self.assertTrue(m.gui_pressed(8, 1010))

    def test_mouse_drag_blocks_late_rank_selection(self):
        for world in range(7):
            m = ReserveInputOracle(); m.mouse_down(100); m.mouse_move(160); m.mouse_up(1010)
            self.assertFalse(m.gui_pressed(8, 1011), world)

    def test_fresh_mouse_click_immediately_after_drag(self):
        m = ReserveInputOracle(); m.mouse_down(100); m.mouse_move(160); m.mouse_up(1010)
        self.assertFalse(m.gui_pressed(8, 1010))
        m.mouse_down(100); m.mouse_up(1015)
        self.assertTrue(m.gui_pressed(8, 1015))

    def test_fresh_touch_after_mouse_drag_works_immediately(self):
        m = ReserveInputOracle(); m.mouse_down(100); m.mouse_move(160); m.mouse_up(1010)
        self.assertFalse(m.gui_pressed(8, 1010))
        m.touch_down(); m.touch_up(1015)
        self.assertTrue(m.gui_pressed(8, 1015))

    def test_small_motion_and_nonleft_motion_remain_clicks(self):
        for density, scale in [(1, 1), (2, 1), (3, 2), (4, 4)]:
            m = ReserveInputOracle(); m.mouse_down(100)
            m.mouse_move(103, density=density, scale=scale); m.mouse_up(1020)
            self.assertTrue(m.gui_pressed(1, 1020))
            m = ReserveInputOracle(); m.mouse_down(100)
            m.mouse_move(200, left=False); m.mouse_up(1020)
            self.assertTrue(m.gui_pressed(1, 1020))

    def test_pointer_drag_outside_reserve_does_not_block_click(self):
        m = ReserveInputOracle(); m.mouse_down(100, inside=False)
        m.mouse_move(200); m.mouse_up(1010)
        self.assertTrue(m.gui_pressed(1, 1010))

    def test_guard_wiring_uses_same_seven_world_engine(self):
        tracker = body('_track_reserve_touch_gesture')
        for token in ['InputEventPanGesture', 'InputEventMouseButton', 'InputEventMouseMotion',
                      '_reserve_pointer_active', '_reserve_pointer_origin', '_reserve_pointer_dragged',
                      '_reserve_pointer_block_until_msec', 'MOUSE_BUTTON_MASK_LEFT',
                      'RESERVE_SWIPE_CANCEL_DP', '_reserve_touch_swiped = true']:
            self.assertIn(token, tracker)
        self.assertNotIn('_on_primary(', tracker)
        self.assertNotIn('_save_match(', tracker)
        self.assertNotIn('set_input_as_handled', tracker)
        self.assertIn('_track_reserve_touch_gesture(event)', body('_track_reserve_scroll_intent'))
        gui = body('_on_reserve_gui_pressed')
        self.assertIn('_reserve_pointer_dragged', gui)
        self.assertIn('_reserve_pointer_block_until_msec', gui)
        self.assertIn('_on_reserve_pressed(player, index)', gui)
        self.assertEqual(SRC.count('func _on_primary()'), 1)

    def test_lifecycle_and_native_seven_world_smoke(self):
        notification = body('_notification')
        self.assertIn('_reserve_pointer_active = false', notification)
        self.assertIn('_reserve_pointer_block_until_msec', notification)
        native = body('_run_headless_reserve_swipe_click_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', native)
        self.assertIn('InputEventPanGesture.new()', native)
        self.assertIn('InputEventMouseButton.new()', native)
        self.assertIn('InputEventMouseMotion.new()', native)
        self.assertIn('"Fresh pointer click must work immediately after drag"', native)
        self.assertIn('_run_headless_reserve_swipe_click_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

if __name__ == '__main__':
    unittest.main()
