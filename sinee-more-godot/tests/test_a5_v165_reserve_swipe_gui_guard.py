"""A5 v165: reserve drag must not trigger a GUI rank click.

Source integration + independent event-order model only. The in-project
seven-world native smoke is registered but NOT executed in this environment.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'^func {re.escape(name)}\(', SRC, re.M)
    assert match, name
    tail = SRC[match.start():]
    nxt = re.search(r'\n(?:func |static func )', tail)
    return tail[:nxt.start()] if nxt else tail


class ReserveGesture:
    def __init__(self):
        self.active = False
        self.swiped = False
        self.block_until = 0
        self.origin = 0
        self.selected = -1
        self.moves = 0

    def press(self, x, now, inside=True, secondary_held=False):
        self.active = inside
        self.origin = x
        self.swiped = inside and secondary_held
        if inside:
            self.block_until = 0

    def drag(self, x, density=1, scale=1):
        if self.active and abs(x-self.origin) > max(8, 12*density/scale):
            self.swiped = True

    def second_finger(self, now, inside=True):
        if self.active:
            self.swiped = True
        if self.active or inside:
            self.block_until = now+350

    def release(self, now):
        if self.active and self.swiped:
            self.block_until = now+350
        self.active = False
        self.swiped = False

    def gui_press(self, rank, now):
        if self.swiped or (self.block_until > 0 and now <= self.block_until):
            return False
        self.selected = rank
        return True


class ReserveSwipeGuardTests(unittest.TestCase):
    def test_01_swipe_cannot_select_rank_9_across_seven_worlds(self):
        for world in range(7):
            m = ReserveGesture()
            m.press(100, 1000)
            m.drag(150)
            m.release(1010)
            self.assertFalse(m.gui_press(8, 1010), world)
            self.assertEqual((m.selected, m.moves), (-1, 0))

    def test_02_fresh_tap_immediately_after_swipe_works(self):
        m = ReserveGesture()
        m.press(100, 1000); m.drag(160); m.release(1010)
        self.assertFalse(m.gui_press(8, 1010))
        m.press(100, 1020); m.release(1030)
        self.assertTrue(m.gui_press(8, 1030))
        self.assertEqual(m.selected, 8)

    def test_03_small_stationary_motion_remains_tap(self):
        for density, scale in [(1, 1), (2, 1), (3, 2), (4, 4)]:
            m = ReserveGesture(); m.press(100, 1000)
            m.drag(103, density, scale); m.release(1020)
            self.assertTrue(m.gui_press(0, 1020))

    def test_04_multitouch_blocks_ghost_rank(self):
        m = ReserveGesture(); m.press(100, 1000)
        m.second_finger(1010); m.release(1020)
        self.assertFalse(m.gui_press(0, 1020))
        self.assertEqual(m.selected, -1)

    def test_05_secondary_first_expires_and_does_not_permanently_block_mouse(self):
        m = ReserveGesture(); m.second_finger(1000)
        self.assertFalse(m.gui_press(0, 1001))
        self.assertTrue(m.gui_press(0, 1351))

    def test_06_gui_callback_is_guarded_keyboard_remains_direct(self):
        self.assertIn('.pressed.connect(_on_reserve_gui_pressed.bind(player, i))', SRC)
        wrapper = body('_on_reserve_gui_pressed')
        self.assertIn('_reserve_touch_swiped', wrapper)
        self.assertIn('_reserve_touch_block_until_msec', wrapper)
        self.assertIn('_on_reserve_pressed(player, index)', wrapper)
        self.assertNotIn('_on_primary(', wrapper)
        self.assertIn('_on_reserve_pressed(turn, index)', body('_select_keyboard_rank'))

    def test_07_complete_gesture_tracks_press_drag_release_secondary(self):
        tracker = body('_track_reserve_touch_gesture')
        for required in ['InputEventScreenTouch', 'touch.index != 0',
                         'InputEventScreenDrag', 'drag.index == 0',
                         'touch.pressed', 'RESERVE_SWIPE_CANCEL_DP',
                         '_reserve_touch_origin', '_reserve_touch_active = false',
                         'TOUCH_MOUSE_ECHO_MS', '_touch_secondary_indices.is_empty()']:
            self.assertIn(required, tracker)
        self.assertNotIn('_on_primary(', tracker)
        self.assertNotIn('_save_match(', tracker)
        self.assertNotIn('set_input_as_handled', tracker)

    def test_08_existing_scroll_epoch_and_board_input_still_used(self):
        track = body('_track_reserve_scroll_intent')
        self.assertIn('_track_reserve_touch_gesture(event)', track)
        self.assertIn('_reserve_scroll_user_epoch += 1', track)
        self.assertIn('_track_reserve_scroll_intent(event)', body('_input'))
        self.assertIn('_on_cell_pressed(initial_cell)', body('_input'))

    def test_09_seven_world_native_smoke_registered(self):
        native = body('_run_headless_reserve_swipe_click_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', native)
        self.assertIn('_on_reserve_gui_pressed(1, 8)', native)
        self.assertIn('_on_reserve_gui_pressed(1, 0)', native)
        self.assertIn('BLUE_SEA_RESERVE_SWIPE_CLICK_SAFETY_PASS', native)
        self.assertIn('_run_headless_reserve_swipe_click_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_10_focus_loss_cancels_reserve_touch_without_committing(self):
        notification = body('_notification')
        self.assertIn('if _reserve_touch_active:', notification)
        self.assertIn('_reserve_touch_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS', notification)
        self.assertIn('_reserve_touch_active = false', notification)
        self.assertIn('_reserve_touch_swiped = false', notification)

    def test_11_shared_rules_ai_and_pirate_unchanged_architecture(self):
        self.assertEqual(SRC.count('func _on_primary()'), 1)
        self.assertEqual(SRC.count('func _on_reserve_pressed('), 1)
        self.assertIn('const AIOpponent = preload(', SRC)
        self.assertIn('const WorldVisuals = preload(', SRC)
        self.assertIn('PirateOpeningCampaign', (ROOT/'project.godot').read_text())

if __name__ == '__main__':
    unittest.main()
