"""A5 v98: offline source + independent save-failure state model.

Not Godot compilation, real disk-failure injection or Android execution.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'^(?:static )?func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)', SRC, re.M | re.S)
    assert match, name
    return match.group(1)


class RetryModel:
    """Independent model: writes always serialize the CURRENT state."""
    def __init__(self, failures):
        self.failures = list(failures)
        self.state = 0
        self.disk = None
        self.dirty = False
        self.attempts = 0
        self.pending = None
        self.writes = 0

    def save(self):
        self.writes += 1
        fail = self.failures.pop(0) if self.failures else False
        if fail:
            self.dirty = True
            if self.attempts < 3 and self.pending is None:
                self.pending = min(8, 2 ** self.attempts)
        else:
            self.disk = self.state
            self.dirty = False
            self.attempts = 0
            self.pending = None

    def retry(self):
        if not self.dirty or self.attempts >= 3:
            return
        self.attempts += 1
        self.pending = None
        self.save()


class A5BoundedSaveRecovery(unittest.TestCase):
    def test_01_failure_does_not_claim_saved(self):
        m = RetryModel([True])
        m.state = 7
        m.save()
        self.assertEqual((m.disk, m.dirty, m.pending), (None, True, 1))

    def test_02_single_retry_recovers(self):
        m = RetryModel([True, False])
        m.state = 2
        m.save()
        m.retry()
        self.assertEqual((m.disk, m.dirty, m.attempts, m.pending), (2, False, 0, None))

    def test_03_retry_uses_latest_move_not_stale_snapshot(self):
        m = RetryModel([True, False])
        m.state = 1
        m.save()
        m.state = 3
        m.retry()
        self.assertEqual(m.disk, 3)
        self.assertIn('_save_match()', body('_retry_failed_match_save'))
        self.assertIn('_match_snapshot()', body('_save_match'))

    def test_04_exhausted_retries_bounded(self):
        m = RetryModel([True] * 20)
        m.state = 8
        m.save()
        for _ in range(50):
            m.retry()
        self.assertEqual((m.writes, m.attempts, m.dirty, m.pending), (4, 3, True, None))

    def test_05_backoff_sequence(self):
        m = RetryModel([True] * 5)
        m.save()
        delays = [m.pending]
        for _ in range(2):
            m.retry()
            delays.append(m.pending)
        self.assertEqual(delays, [1, 2, 4])
        self.assertIn('minf(8.0, pow(2.0, float(maxi(0, attempts))))', body('_match_save_retry_delay'))

    def test_06_success_cancels_old_retry(self):
        m = RetryModel([True, False])
        m.save()
        m.state = 9
        m.save()
        m.retry()
        self.assertEqual((m.writes, m.disk, m.dirty, m.pending), (2, 9, False, None))

    def test_07_repeated_user_move_can_recover_after_exhaustion(self):
        m = RetryModel([True, True, True, True, False])
        m.save()
        for _ in range(3):
            m.retry()
        m.state = 10
        m.save()
        self.assertEqual((m.disk, m.dirty, m.attempts), (10, False, 0))

    def test_08_actual_atomic_writer_is_retained(self):
        b = body('_save_match')
        self.assertIn('_write_match_atomically(MATCH_STATE_PATH, _match_snapshot())', b)
        self.assertIn('_last_persisted_scroll_positions = _snapshot_reserve_scroll()', b)
        self.assertNotIn('FileAccess.open(', b)

    def test_09_timer_is_one_shot_and_bound(self):
        b = body('_prepare_world_shell')
        self.assertIn('match_save_retry_timer.one_shot = true', b)
        self.assertIn('match_save_retry_timer.timeout.connect(_retry_failed_match_save)', b)
        self.assertIn('_match_save_retry_attempts < MATCH_SAVE_RETRY_MAX', body('_save_match'))
        self.assertIn('MATCH_SAVE_RETRY_MAX := 3', SRC)

    def test_10_storage_warning_visible_during_play(self):
        b = body('_refresh_match_hud')
        self.assertIn('state = "НЕ СОХР."', b)
        self.assertIn('score += " !"', b)
        self.assertIn('if not game_over:', b)

    def test_11_terminal_result_not_overwritten(self):
        b = body('_refresh_match_hud')
        self.assertLess(b.index('state = "НИЧЬЯ"'), b.index('if _match_save_dirty:'))
        self.assertIn('if not game_over:', b[b.index('if _match_save_dirty:'):])

    def test_12_suspend_flushes_failed_move_even_without_scroll(self):
        b = body('_notification')
        self.assertLess(b.index('_persist_idle_reserve_scroll()'), b.index('if _match_save_dirty'))
        self.assertIn('_retry_failed_match_save()', b)

    def test_13_startup_failure_can_schedule_after_shell(self):
        b = body('_prepare_world_shell')
        self.assertIn('if _match_save_dirty:', b)
        self.assertIn('match_save_retry_timer.start(', b)
        self.assertIn('if match_save_retry_timer != null', body('_save_match'))

    def test_14_headless_import_does_not_save(self):
        b = body('_save_match')
        self.assertLess(b.index('if DisplayServer.get_name() == "headless"'), b.index('_write_match_atomically('))

    def test_15_no_gameplay_state_changes_from_retry(self):
        for name in ('_retry_failed_match_save', '_match_save_retry_delay'):
            b = body(name)
            for token in ('board_stacks =', 'turn =', 'reserve_available =', 'moves +=', '_on_primary(', 'ai_engine.choose_move('):
                self.assertNotIn(token, b)

    def test_16_native_smoke_wired_not_claimed_executed(self):
        self.assertIn('_run_headless_match_save_retry_smoke()', body('_run_headless_geometry_and_interaction_smoke'))
        self.assertIn('BLUE_SEA_SAVE_RETRY_HUD_PASS', body('_run_headless_match_save_retry_smoke'))


if __name__ == '__main__':
    unittest.main()
