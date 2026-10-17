"""A5 v96 lifecycle save: offline source checks + independent event-order model.

Not a Godot runtime test. Actual Android pause/focus events remain unqualified.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "main.gd").read_text(encoding="utf-8")


def body(name):
    match = re.search(rf"^func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)", SRC, re.M | re.S)
    assert match, name
    return match.group(1)


class ScrollPersistenceModel:
    """Single-writer persistence oracle, not a substitute for Godot."""
    def __init__(self):
        self.current = 0
        self.persisted = 0
        self.idle_timer = False
        self.ready = True
        self.active = True
        self.writes = 0

    def scroll(self, value):
        self.current = value
        self.idle_timer = True

    def flush(self, notification):
        if notification not in ("paused", "focus_out", "close", "android_back"):
            return
        if not self.ready:
            return
        self.idle_timer = False
        if self.active and self.current != self.persisted:
            self.persisted = self.current
            self.writes += 1

    def timer(self):
        if self.idle_timer:
            self.idle_timer = False
            if self.active and self.current != self.persisted:
                self.persisted = self.current
                self.writes += 1


class A5SuspendSave(unittest.TestCase):
    def test_01_saves_before_650ms_idle(self):
        m = ScrollPersistenceModel()
        m.scroll(264)
        m.flush("paused")
        self.assertEqual((m.persisted, m.writes, m.idle_timer), (264, 1, False))

    def test_02_repeated_focus_and_pause_idempotent(self):
        m = ScrollPersistenceModel()
        m.scroll(193)
        for event in ("focus_out", "paused", "paused", "close"):
            m.flush(event)
        m.timer()
        self.assertEqual((m.persisted, m.writes), (193, 1))

    def test_03_inactive_reserve_never_written(self):
        m = ScrollPersistenceModel()
        m.active = False
        m.scroll(212)
        m.flush("paused")
        self.assertEqual((m.persisted, m.writes), (0, 0))

    def test_04_initialization_notification_safe(self):
        m = ScrollPersistenceModel()
        m.ready = False
        m.scroll(103)
        m.flush("paused")
        self.assertEqual(m.writes, 0)

    def test_05_unrelated_notifications_no_io(self):
        m = ScrollPersistenceModel()
        m.scroll(177)
        m.flush("resumed")
        self.assertEqual((m.persisted, m.writes), (0, 0))

    def test_06_correct_godot_lifecycle_constants(self):
        b = body("_notification")
        for name in (
            "NOTIFICATION_APPLICATION_PAUSED",
            "NOTIFICATION_APPLICATION_FOCUS_OUT",
            "NOTIFICATION_WM_CLOSE_REQUEST",
            "NOTIFICATION_WM_GO_BACK_REQUEST",
        ):
            self.assertIn(name, b)

    def test_07_guard_before_child_access(self):
        b = body("_notification")
        self.assertLess(b.index("is_node_ready()"), b.index("reserve_scroll_save_timer.stop()"))
        self.assertIn("reserve_scroller == null", b)

    def test_08_existing_atomic_save_is_reused(self):
        b = body("_notification")
        self.assertIn("_persist_idle_reserve_scroll()", b)
        self.assertNotIn("_save_match()", b)
        p = body("_persist_idle_reserve_scroll")
        self.assertIn("offsets != _last_persisted_scroll_positions", p)
        self.assertIn("_save_match()", p)
        self.assertIn("_write_match_atomically(MATCH_STATE_PATH", body("_save_match"))

    def test_09_does_not_change_rules_turn_or_ai(self):
        b = body("_notification")
        for forbidden in ("board_stacks[", "_on_primary(", "turn =", "ai_enabled =", "_reset_round(", "_play_ai_turn("):
            self.assertNotIn(forbidden, b)

    def test_10_existing_idle_debounce_remains(self):
        self.assertIn("reserve_scroll_save_timer.wait_time = 0.65", body("_prepare_world_shell"))
        self.assertIn("reserve_scroll_save_timer.start()", body("_on_reserve_scroll_changed"))

    def test_11_headless_guard_and_valid_save_remain(self):
        self.assertIn('DisplayServer.get_name() == "headless"', body("_persist_idle_reserve_scroll"))
        self.assertIn("_match_snapshot_valid(state)", body("_write_match_atomically"))

    def test_12_all_worlds_still_share_one_gameplay(self):
        self.assertIn("func _set_world(", SRC)
        self.assertIn("const WorldVisuals = preload(", SRC)
        self.assertIn("const AIOpponent = preload(", SRC)
        self.assertEqual(SRC.count("func _notification("), 1)


if __name__ == "__main__":
    unittest.main()
