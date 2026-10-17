"""A5 v99: offline verification of bounded, user-requested save recovery.

This checks integrated Godot source and an independent state-transition model.
It does NOT claim native Godot execution or actual storage-fault injection.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'^(?:static )?func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)', SOURCE, re.M | re.S)
    assert match, name
    return match.group(1)


class RecoveryModel:
    def __init__(self, results):
        self.results = list(results)
        self.dirty = False
        self.attempts = 0
        self.timer = None
        self.disk = None
        self.current = 'round-1'
        self.writes = 0

    def save(self):
        self.writes += 1
        success = self.results.pop(0) if self.results else False
        if success:
            self.disk = self.current
            self.dirty = False
            self.attempts = 0
            self.timer = None
        else:
            self.dirty = True
            if self.attempts < 3 and self.timer is None:
                self.timer = 2 ** self.attempts

    def auto_retry(self):
        if not self.dirty or self.attempts >= 3:
            return
        self.attempts += 1
        self.timer = None
        self.save()

    def manual_retry(self):
        if not self.dirty:
            return
        self.timer = None
        self.attempts = 0
        self.save()


class TestManualRecovery(unittest.TestCase):
    def test_01_real_menu_button_only_when_unsaved(self):
        self.assertIn('if _match_save_dirty:\n\t\t\t_mobile_menu_add("Повторить сохранение", 107)', body('_render_mobile_menu_page'))

    def test_02_desktop_menu_button_only_when_unsaved(self):
        self.assertIn('if _match_save_dirty:\n\t\tpopup.add_item("Повторить сохранение", 107)', body('_populate_game_menu'))

    def test_03_both_surfaces_share_one_handler(self):
        self.assertIn('_on_game_menu_item(id)', body('_on_mobile_menu_action'))
        self.assertIn('_retry_unsaved_match_on_request()', body('_on_game_menu_item'))
        self.assertIn('if id == 107:', body('_on_game_menu_item'))

    def test_04_one_manual_request_resets_bounded_retry_budget(self):
        handler = body('_retry_unsaved_match_on_request')
        self.assertLess(handler.index('if not _match_save_dirty:'), handler.index('_save_match()'))
        self.assertLess(handler.index('match_save_retry_timer.stop()'), handler.index('_match_save_retry_attempts = 0'))
        self.assertLess(handler.index('_match_save_retry_attempts = 0'), handler.index('_save_match()'))
        self.assertNotIn('while ', handler)
        self.assertNotIn('call_deferred(', handler)

    def test_05_save_uses_latest_full_snapshot(self):
        self.assertIn('_write_match_atomically(MATCH_STATE_PATH, _match_snapshot())', body('_save_match'))
        self.assertNotIn('_apply_match_snapshot(', body('_retry_unsaved_match_on_request'))

    def test_06_exhaustion_does_not_retry_indefinitely(self):
        m = RecoveryModel([False] * 8)
        m.save()
        for _ in range(3):
            m.auto_retry()
        for _ in range(100):
            m.auto_retry()
        self.assertEqual((m.writes, m.attempts, m.timer, m.dirty), (4, 3, None, True))

    def test_07_manual_action_recovers_after_storage_fixed(self):
        m = RecoveryModel([False] * 4 + [True])
        m.save()
        for _ in range(3):
            m.auto_retry()
        m.current = 'round-2-after-storage-repair'
        m.manual_retry()
        self.assertEqual((m.writes, m.disk, m.dirty, m.attempts, m.timer), (5, m.current, False, 0, None))

    def test_08_manual_failure_still_bounded(self):
        m = RecoveryModel([False] * 20)
        m.save()
        for _ in range(3):
            m.auto_retry()
        m.manual_retry()
        self.assertEqual((m.writes, m.attempts, m.timer, m.dirty), (5, 0, 1, True))
        for _ in range(3):
            m.auto_retry()
        self.assertEqual((m.writes, m.attempts, m.timer), (8, 3, None))

    def test_09_no_write_when_healthy(self):
        m = RecoveryModel([True, True])
        m.save()
        m.manual_retry()
        self.assertEqual(m.writes, 1)
        self.assertEqual(m.disk, 'round-1')

    def test_10_manual_retry_does_not_touch_gameplay_state(self):
        b = body('_retry_unsaved_match_on_request')
        for token in ('board_stacks =', 'reserve_available =', 'turn =', 'moves +=', 'round_number =', '_on_primary(', '_reset_round('):
            self.assertNotIn(token, b)

    def test_11_user_feedback_reports_success_or_failure(self):
        b = body('_retry_unsaved_match_on_request')
        self.assertIn('"save recovered" if not _match_save_dirty else "save retry failed"', b)
        notices = body('_hud_notice_for_event')
        self.assertIn('return "СОХРАНЕНО"', notices)
        self.assertIn('return "НЕ СОХР."', notices)

    def test_12_native_smoke_checks_both_real_menu_nodes(self):
        b = body('_run_headless_match_save_retry_smoke')
        self.assertIn('mobile_menu_list.get_node_or_null("MobileChoice_107")', b)
        self.assertIn('top_menu.get_popup().get_item_index(107)', b)
        self.assertIn('BLUE_SEA_SAVE_RETRY_HUD_PASS', b)
        self.assertIn('_run_headless_match_save_retry_smoke()', body('_run_headless_geometry_and_interaction_smoke'))


if __name__ == '__main__':
    unittest.main()
