"""A5 v97: source and independent UI-state model checks.

NOT a native Godot run, Android screenshot, or verified visual parity.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'^(?:static )?func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)', SOURCE, re.M | re.S)
    assert match, name
    return match.group(1)


class PhoneHudModel:
    def __init__(self):
        self.score = '1:0'
        self.turn = 'ХОД P1'
        self.notice = ''
        self.deadline = 0
        self.terminal = False
        self.mobile = True

    def notify(self, text, now):
        self.notice = text
        self.deadline = now + 1700

    def draw(self, now):
        state = self.notice if self.mobile and not self.terminal and self.notice and self.deadline > now else self.turn
        return self.score + '\n' + state


class A5VisibleMobileFeedback(unittest.TestCase):
    def test_01_previous_phone_status_was_tooltip_only(self):
        self.assertIn('status.tooltip_text = event', body('_update_status'))
        self.assertIn('center.get_node("Status").visible = not _use_mobile_menu()', SOURCE)

    def test_02_feedback_uses_existing_live_hud_no_new_modal(self):
        self.assertIn('_refresh_match_hud()', body('_update_status'))
        self.assertIn('match_hud_label.text = score + "\\n" + state', body('_refresh_match_hud'))
        self.assertNotIn('Popup', body('_update_status'))
        self.assertNotIn('add_child(', body('_update_status'))

    def test_03_only_mobile_and_nonterminal_notice(self):
        self.assertIn('not game_over and _use_mobile_menu()', body('_update_status'))
        self.assertIn('mobile and not terminal', body('_hud_secondary_line'))

    def test_04_score_remains_visible_during_error(self):
        m = PhoneHudModel()
        m.notify('НЕЛЬЗЯ', 1000)
        self.assertEqual(m.draw(1010), '1:0\nНЕЛЬЗЯ')
        self.assertIn('score + "\\n" + state', body('_refresh_match_hud'))

    def test_05_transient_notice_expires_to_turn(self):
        m = PhoneHudModel()
        m.notify('НЕЛЬЗЯ', 1000)
        self.assertEqual(m.draw(2699), '1:0\nНЕЛЬЗЯ')
        self.assertEqual(m.draw(2700), '1:0\nХОД P1')
        self.assertIn('Time.get_ticks_msec() >= _hud_notice_deadline_msec', body('_process'))

    def test_06_terminal_result_dominates_notice(self):
        m = PhoneHudModel()
        m.notify('НЕЛЬЗЯ', 1000)
        m.turn = 'РАУНД P1'
        m.terminal = True
        self.assertEqual(m.draw(1010), '1:0\nРАУНД P1')
        self.assertIn('_use_mobile_menu(), game_over', body('_refresh_match_hud'))

    def test_07_desktop_retains_original_turn(self):
        m = PhoneHudModel()
        m.notify('НЕЛЬЗЯ', 1000)
        m.mobile = False
        self.assertEqual(m.draw(1010), '1:0\nХОД P1')

    def test_08_rank_notice_is_one_based(self):
        b = body('_hud_notice_for_event')
        self.assertIn('"РАНГ %d" % (int(rank_index) + 1)', b)
        self.assertIn('int(rank_index) < 9', b)
        self.assertIn('"reserve 8"', body('_run_headless_hud_notice_smoke'))

    def test_09_cell_notice_is_one_based(self):
        b = body('_hud_notice_for_event')
        self.assertIn('"КЛЕТКА %d" % (int(cell_index) + 1)', b)
        self.assertIn('"keyboard cell "', b)

    def test_10_invalid_move_is_visible_not_silent(self):
        self.assertIn('"illegal move"', body('_hud_notice_for_event'))
        self.assertIn('_update_status("illegal move")', body('_on_primary'))
        self.assertIn('"piece already played"', body('_hud_notice_for_event'))

    def test_11_reset_discards_old_notice(self):
        b = body('_reset_round')
        self.assertIn('_hud_notice_text = ""', b)
        self.assertIn('_hud_notice_deadline_msec = 0', b)

    def test_12_no_gameplay_or_disk_mutation_from_feedback(self):
        for fn in ('_hud_notice_for_event', '_hud_secondary_line', '_refresh_match_hud'):
            b = body(fn)
            for token in ('board_stacks.append', '_on_primary(', '_save_match(', '_write_match_atomically(', 'reserve_available[', 'turn = 2'):
                self.assertNotIn(token, b, (fn, token))

    def test_13_native_smoke_wired_but_not_claimed_executed(self):
        self.assertIn('_run_headless_hud_notice_smoke()', body('_run_headless_geometry_and_interaction_smoke'))
        self.assertIn('BLUE_SEA_MOBILE_VISIBLE_FEEDBACK_PASS', body('_run_headless_hud_notice_smoke'))

    def test_14_bounded_compact_notice_labels(self):
        b = body('_hud_notice_for_event')
        notices = re.findall(r'\t\t\treturn "([^\"]+)"', b)
        self.assertGreaterEqual(len(notices), 8)
        for notice in notices:
            self.assertLessEqual(len(notice), 11, notice)


if __name__ == '__main__':
    unittest.main()
