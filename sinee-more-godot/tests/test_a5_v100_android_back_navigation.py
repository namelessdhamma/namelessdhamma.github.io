"""A5 v100 Android Back navigation, source wiring and independent event model.

These tests are OFFLINE. They do not certify native Android/Godot behavior.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text(encoding='utf-8')


def body(name):
    m = re.search(rf'^func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)', SRC, re.M | re.S)
    assert m, name
    return m.group(1)


class BackModel:
    def __init__(self):
        self.page = None
        self.frame = 0
        self.last_frame = -100
        self.match = (7, 2, 'CD', (1, 0))
        self.reset_count = 0
        self.ai_moves = 0
        self.pirate_modal = False
        self.orientation_modal = False

    def back(self):
        if self.frame - self.last_frame <= 2:
            return
        if self.pirate_modal or self.orientation_modal:
            return
        self.last_frame = self.frame
        if self.page == 'main':
            self.page = None
        elif self.page and self.page.startswith('tutorial_') and self.page != 'tutorial_1':
            self.page = 'tutorial_' + str(int(self.page[-1]) - 1)
        elif self.page:
            self.page = 'main'
        else:
            self.page = 'main'

    def tick(self, n=3):
        self.frame += n


class AndroidBackNavigation(unittest.TestCase):
    def test_01_android_only_intercepts_system_quit(self):
        ready = body('_ready')
        self.assertIn('if DisplayServer.get_name() == "Android":\n\t\tget_tree().auto_accept_quit = false', ready)
        self.assertLess(ready.index('auto_accept_quit = false'), ready.index('_prepare_world_shell()'))

    def test_02_android_escape_uses_same_handler(self):
        key = body('_unhandled_key_input')
        self.assertIn('if DisplayServer.get_name() == "Android" and event.keycode in [KEY_ESCAPE, KEY_BACKSPACE]:', key)
        self.assertLess(key.index('_handle_mobile_back()'), key.index('if _modal_blocks_board_input():'))
        self.assertIn('get_viewport().set_input_as_handled()', key)

    def test_03_browser_desktop_keyboard_semantics_unchanged(self):
        key = body('_unhandled_key_input')
        self.assertIn('KEY_ESCAPE, KEY_BACKSPACE:\n\t\t\t_on_secondary()', key)
        self.assertNotIn('if _use_mobile_menu() and event.keycode', key)

    def test_04_wm_back_flows_after_lifecycle_save(self):
        notification = body('_notification')
        self.assertIn('NOTIFICATION_WM_GO_BACK_REQUEST', notification)
        self.assertLess(notification.index('_persist_idle_reserve_scroll()'), notification.index('_handle_mobile_back()'))
        self.assertLess(notification.index('_retry_failed_match_save()'), notification.index('_handle_mobile_back()'))

    def test_05_back_deduplicates_key_and_notification(self):
        back = body('_handle_mobile_back')
        self.assertIn('frame - _last_mobile_back_frame <= 2', back)
        self.assertIn('_last_mobile_back_frame = frame', back)
        m = BackModel()
        m.back()
        self.assertEqual(m.page, 'main')
        m.back()
        self.assertEqual(m.page, 'main')
        m.tick()
        m.back()
        self.assertIsNone(m.page)

    def test_06_reset_confirmation_is_cancelled_not_accepted(self):
        back = body('_handle_mobile_back')
        self.assertIn('_render_mobile_menu_page("main")', back)
        self.assertNotIn('_confirm_reset_match(', back)
        m = BackModel()
        m.page = 'confirm_reset'
        m.back()
        self.assertEqual(m.page, 'main')
        self.assertEqual(m.reset_count, 0)

    def test_07_tutorial_back_goes_to_previous_page(self):
        back = body('_handle_mobile_back')
        self.assertIn('page_number - 1', back)
        m = BackModel()
        m.page = 'tutorial_4'
        m.back()
        self.assertEqual(m.page, 'tutorial_3')

    def test_08_modal_and_orientation_block_back(self):
        back = body('_handle_mobile_back')
        self.assertIn('orientation_overlay.visible', back)
        self.assertIn('pirate_choice.visible', back)
        m = BackModel()
        m.pirate_modal = True
        m.back()
        self.assertIsNone(m.page)
        m.pirate_modal = False
        m.orientation_modal = True
        m.back()
        self.assertIsNone(m.page)

    def test_09_back_never_commits_a_game_move(self):
        back = body('_handle_mobile_back')
        for forbidden in ('_on_primary(', '_reset_round(', '_on_menu(', 'board_stacks[', 'reserve_available[', 'moves +=', 'turn =', '_play_ai_turn('):
            self.assertNotIn(forbidden, back)
        m = BackModel()
        original = m.match
        for _ in range(5):
            m.back()
            m.tick()
        self.assertEqual(m.match, original)
        self.assertEqual(m.ai_moves, 0)

    def test_10_back_closes_visible_phone_modal(self):
        back = body('_handle_mobile_back')
        self.assertIn('mobile_menu_panel.hide()', back)
        self.assertIn('_open_mobile_menu()', back)

    def test_11_closing_menu_preserves_ai_resume_signal(self):
        self.assertIn('mobile_menu_panel.visibility_changed.connect(_resume_ai_after_modal_close)', body('_create_mobile_menu_panel'))
        self.assertIn('_queue_ai_turn_if_ready', body('_resume_ai_after_modal_close'))

    def test_12_native_smoke_wired_with_reset_cancel_and_snapshot(self):
        smoke = body('_run_headless_mobile_back_navigation_smoke')
        self.assertIn('confirm_reset', smoke)
        self.assertIn('Back must CANCEL reset', smoke)
        self.assertIn('_match_snapshot() == before', smoke)
        self.assertIn('BLUE_SEA_MOBILE_BACK_NAVIGATION_PASS', smoke)
        self.assertIn('await _run_headless_mobile_back_navigation_smoke()', body('_run_headless_geometry_and_interaction_smoke'))


if __name__ == '__main__':
    unittest.main()
