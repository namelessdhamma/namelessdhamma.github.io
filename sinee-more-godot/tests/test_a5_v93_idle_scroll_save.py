"""A5 v93: scroll-only phone navigation persists without per-frame writes.

Static contract and independent event-model checks; native Godot execution is a
separate mandatory acceptance gate, not implied by this test module.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts" / "main.gd").read_text()


def gd_func(name):
    match = re.search(r"^func " + re.escape(name) + r"\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)", SOURCE, re.M | re.S)
    assert match, f"missing Godot function: {name}"
    return match.group(1)


class ScrollPersistenceModel:
    """Small independent event model, not an executable Godot substitute."""
    def __init__(self):
        self.active = 1
        self.last_player = 1
        self.visible = True
        self.ai = False
        self.over = False
        self.headless = False
        self.timer_pending = False
        self.offsets = [0, 0]
        self.saved = [0, 0]
        self.writes = 0

    def changed(self, value):
        self.offsets[self.active - 1] = value
        if not (self.headless or self.over or not self.visible or self.last_player != self.active or (self.ai and self.active == 2)):
            self.timer_pending = True

    def idle(self):
        if not self.timer_pending:
            return
        self.timer_pending = False
        if self.headless or self.over or not self.visible or self.last_player != self.active or (self.ai and self.active == 2):
            return
        if self.offsets != self.saved:
            self.saved = self.offsets.copy()
            self.writes += 1


class IdleReserveScroll(unittest.TestCase):
    def test_01_real_scrollbar_signal_to_one_shot_timer(self):
        setup = gd_func("_prepare_world_shell")
        self.assertIn('reserve_scroll_save_timer = Timer.new()', setup)
        self.assertIn('reserve_scroll_save_timer.one_shot = true', setup)
        self.assertIn('reserve_scroll_save_timer.wait_time = 0.65', setup)
        self.assertIn('reserve_scroll_save_timer.timeout.connect(_persist_idle_reserve_scroll)', setup)
        self.assertIn('reserve_scroller.get_h_scroll_bar().value_changed.connect(_on_reserve_scroll_changed)', setup)

    def test_02_scroll_tick_only_resets_timer_never_writes(self):
        changed = gd_func("_on_reserve_scroll_changed")
        self.assertIn('reserve_scroll_save_timer.start()', changed)
        self.assertNotIn('_save_match()', changed)
        self.assertIn('DisplayServer.get_name() == "headless"', changed)
        self.assertIn('_last_reserve_scroll_player != turn', changed)

    def test_03_idle_persists_only_when_changed(self):
        idle = gd_func("_persist_idle_reserve_scroll")
        self.assertIn('offsets != _last_persisted_scroll_positions', idle)
        self.assertIn('_save_match()', idle)
        self.assertIn('game_over', idle)
        self.assertIn('reserve_scroller.visible', idle)
        self.assertIn('ai_enabled and turn == 2', idle)

    def test_04_successful_atomic_write_updates_saved_offsets(self):
        save = gd_func("_save_match")
        self.assertIn('_write_match_atomically(MATCH_STATE_PATH, _match_snapshot())', save)
        self.assertIn('if _write_match_atomically(', save)
        self.assertIn('_last_persisted_scroll_positions = _snapshot_reserve_scroll()', save)
        self.assertNotIn('= _snapshot_reserve_scroll()', gd_func("_on_reserve_scroll_changed"))

    def test_05_restored_two_player_offsets_are_initial_checkpoint(self):
        restore = gd_func("_apply_match_snapshot")
        self.assertIn('_last_persisted_scroll_positions = _reserve_scroll_by_player.duplicate()', restore)
        self.assertIn('_reserve_scroll_by_player = [int(state["reserve_scroll"][0])', restore)
        self.assertIn('"reserve_scroll": _snapshot_reserve_scroll()', gd_func("_match_snapshot"))

    def test_06_many_scroll_ticks_one_write(self):
        model = ScrollPersistenceModel()
        for value in [18, 37, 94, 155, 211, 289]:
            model.changed(value)
        self.assertEqual(model.writes, 0)
        model.idle()
        self.assertEqual((model.writes, model.saved), (1, [289, 0]))
        model.changed(289)
        model.idle()
        self.assertEqual(model.writes, 1)

    def test_07_hidden_or_ai_or_headless_never_write(self):
        for attr, value in [("visible", False), ("headless", True), ("over", True), ("last_player", 2)]:
            model = ScrollPersistenceModel()
            setattr(model, attr, value)
            model.changed(133)
            model.idle()
            self.assertEqual(model.writes, 0, attr)
        model = ScrollPersistenceModel()
        model.active = model.last_player = 2
        model.ai = True
        model.changed(133)
        model.idle()
        self.assertEqual(model.writes, 0)

    def test_08_player_isolation_and_turn_transition(self):
        model = ScrollPersistenceModel()
        model.changed(500)
        model.idle()
        model.active = model.last_player = 2
        model.changed(120)
        model.idle()
        self.assertEqual(model.saved, [500, 120])
        self.assertEqual(model.writes, 2)
        model.active = model.last_player = 1
        model.changed(500)
        model.idle()
        self.assertEqual(model.writes, 2)

    def test_09_future_native_smoke_wired_without_headless_io(self):
        suite = gd_func("_run_headless_geometry_and_interaction_smoke")
        smoke = gd_func("_run_headless_scroll_idle_persistence_smoke")
        self.assertIn('_run_headless_scroll_idle_persistence_smoke()', suite)
        self.assertIn('_on_reserve_scroll_changed(150.0)', smoke)
        self.assertIn('reserve_scroll_save_timer.is_stopped()', smoke)
        self.assertIn('if DisplayServer.get_name() == "headless":', gd_func("_save_match"))


if __name__ == "__main__":
    unittest.main()
