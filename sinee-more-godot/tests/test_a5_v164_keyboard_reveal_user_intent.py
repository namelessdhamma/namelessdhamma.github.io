"""v164: keyboard auto-reveal must not override newer human reserve scrolling.

Source and independent event-order model only. Native Godot smoke is registered,
not executed; physical touch and visual parity remain unverified.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")


def body(name):
    m = re.search(rf"^func {re.escape(name)}\(", SRC, re.M)
    assert m, name
    tail = SRC[m.start():]
    nxt = re.search(r"\n(?:func |static func )", tail)
    return tail[:nxt.start()] if nxt else tail


class KeyboardRevealModel:
    def __init__(self, world):
        self.turn, self.world, self.round, self.moves, self.rank, self.epoch = 1, world, 1, 0, 8, 0
        self.scroll = 0
        self.writes = 0

    def context(self):
        return (self.turn, self.rank, self.world, self.round, self.moves, self.epoch)

    def keyboard_reveal(self, context, new_scroll):
        if context != self.context():
            return False
        self.scroll = new_scroll
        return True


class KeyboardScrollIntent(unittest.TestCase):
    def test_01_stale_reveal_race_reproduced_and_blocked_seven_worlds(self):
        for world in range(7):
            model = KeyboardRevealModel(world)
            scheduled = model.context()
            model.epoch += 1  # human finger-down/swipe in live reserve
            model.scroll = 125
            self.assertEqual(scheduled[:5], model.context()[:5])
            self.assertFalse(model.keyboard_reveal(scheduled, 410), world)
            self.assertEqual(model.scroll, 125)
            self.assertEqual(model.writes, 0)

    def test_02_newest_keyboard_reveal_still_works(self):
        for world in range(7):
            model = KeyboardRevealModel(world)
            scheduled = model.context()
            self.assertTrue(model.keyboard_reveal(scheduled, 410))
            self.assertEqual(model.scroll, 410)

    def test_03_reselect_same_rank_after_manual_scroll(self):
        model = KeyboardRevealModel(5)
        stale = model.context()
        model.epoch += 1
        fresh = model.context()
        self.assertFalse(model.keyboard_reveal(stale, 400))
        self.assertTrue(model.keyboard_reveal(fresh, 420))

    def test_04_turn_world_round_move_rank_each_invalidate(self):
        for name, value in [('turn', 2), ('world', 3), ('round', 2),
                            ('moves', 1), ('rank', 2)]:
            model = KeyboardRevealModel(0)
            scheduled = model.context()
            setattr(model, name, value)
            self.assertFalse(model.keyboard_reveal(scheduled, 300), name)

    def test_05_keyboard_scheduler_captures_all_six_context_fields(self):
        selector = body('_select_keyboard_rank')
        self.assertIn('call_deferred("_reveal_keyboard_rank", turn, index, current_world,', selector)
        self.assertIn('round_number, moves, _reserve_scroll_user_epoch)', selector)
        self.assertLess(selector.index('_on_reserve_pressed(turn, index)'), selector.index('call_deferred('))

    def test_06_keyboard_reveal_uses_shared_epoch_and_modal_gate(self):
        reveal = body('_reveal_keyboard_rank')
        self.assertIn('if reserve_scroller == null or game_over or _modal_blocks_board_input():', reveal)
        self.assertIn('_reserve_scroll_request_current(player, world, round_id, move_count,', reveal)
        self.assertIn('index, user_epoch)', reveal)
        self.assertIn('reserve_scroller.ensure_control_visible(button)', reveal)
        self.assertNotIn('_save_match(', reveal)
        self.assertNotIn('_on_primary(', reveal)

    def test_07_shared_predicate_covers_all_mutable_dimensions(self):
        guard = body('_reserve_scroll_request_current')
        for part in ['turn == player', 'current_world == world', 'round_number == round_id',
                     'moves == move_count', 'selected_reserve == rank_index',
                     '_reserve_scroll_user_epoch == user_epoch']:
            self.assertIn(part, guard)

    def test_08_touch_and_wheel_intent_seen_without_consuming_input(self):
        track = body('_track_reserve_scroll_intent')
        for term in ['InputEventScreenTouch', 'InputEventScreenDrag', 'InputEventMouseButton',
                     'MOUSE_BUTTON_WHEEL_UP', 'MOUSE_BUTTON_WHEEL_DOWN']:
            self.assertIn(term, track)
        self.assertIn('_reserve_scroll_user_epoch += 1', track)
        self.assertNotIn('set_input_as_handled', track)

    def test_09_native_fixture_seven_worlds_registered_not_claimed(self):
        fixture = body('_run_headless_keyboard_rank_guard_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', fixture)
        self.assertIn('not _reserve_scroll_request_current(1, world, round_number, moves,', fixture)
        self.assertIn('_reveal_keyboard_rank(1, 8, world, round_number, moves, epoch_at_request)', fixture)
        self.assertIn('_run_headless_keyboard_rank_guard_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_10_seven_worlds_share_one_gameplay_and_pirate_controller(self):
        self.assertEqual(SRC.count('func _on_primary()'), 1)
        self.assertIn('const AIOpponent = preload(', SRC)
        self.assertIn('const WorldVisuals = preload(', SRC)
        self.assertIn('PirateOpeningCampaign', (ROOT / 'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
