"""A5 v156: explicit human scroll intent outranks deferred reserve auto-scroll.

Offline source/event-model checks only. A registered Godot smoke fixture still
requires execution on the real 4.7.2 engine, and phone touch remains unverified.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()


def body(name):
    m = re.search(rf'^func {re.escape(name)}\(', SOURCE, re.M)
    assert m, name
    tail = SOURCE[m.end():]
    nxt = re.search(r'\n(?:func |static func )', tail)
    return SOURCE[m.start():m.end()+nxt.start() if nxt else len(SOURCE)]


class ScrollIntentModel:
    """Independent event-order model, not a Godot or physical touch simulator."""
    def __init__(self):
        self.epoch = 0
        self.turn = 1
        self.world = 1
        self.round = 1
        self.moves = 0
        self.rank = 8
        self.scroll = 0
        self.writes = 0

    def request(self):
        return (self.turn, self.world, self.round, self.moves, self.rank, self.epoch)

    def human_input(self, inside_reserve=True, pressed=True):
        if inside_reserve and pressed:
            self.epoch += 1

    def delayed_reveal(self, request, new_position):
        if request != self.request():
            return False
        self.scroll = new_position
        return True


class DeferredScrollIntent(unittest.TestCase):
    def test_01_original_race_reproduced_in_model(self):
        for world in range(7):
            model = ScrollIntentModel()
            model.world = world
            old = model.request()
            model.human_input()
            model.scroll = 140
            # Old v155 guards ignore user epoch: turn/world/moves/rank all match.
            self.assertEqual(old[:5], model.request()[:5])
            self.assertNotEqual(old, model.request())
            self.assertFalse(model.delayed_reveal(old, 380))
            self.assertEqual(model.scroll, 140)

    def test_02_newer_manual_input_wins_across_all_worlds(self):
        for world in range(7):
            model = ScrollIntentModel()
            model.world = world
            request = model.request()
            model.human_input()
            model.scroll = 240
            self.assertFalse(model.delayed_reveal(request, 400), world)
            self.assertEqual(model.scroll, 240)
            self.assertEqual(model.writes, 0)

    def test_03_programmatic_layout_change_does_not_cancel(self):
        model = ScrollIntentModel()
        request = model.request()
        model.scroll = 17  # scrollbar layout clamp, not a new human gesture
        self.assertTrue(model.delayed_reveal(request, 350))
        self.assertEqual(model.scroll, 350)

    def test_04_world_round_move_rank_and_turn_invalidate(self):
        for attr, new in [('turn', 2), ('world', 6), ('round', 2),
                          ('moves', 1), ('rank', 3)]:
            model = ScrollIntentModel()
            request = model.request()
            setattr(model, attr, new)
            self.assertFalse(model.delayed_reveal(request, 300), attr)

    def test_05_pointer_intent_tracking_non_consuming(self):
        source = body('_track_reserve_scroll_intent')
        for kind in ['InputEventScreenTouch', 'InputEventScreenDrag',
                     'InputEventPanGesture', 'InputEventMouseButton',
                     'InputEventMouseMotion']:
            self.assertIn(kind, source)
        self.assertIn('reserve_scroller.get_global_rect().has_point(position)', source)
        self.assertIn('_reserve_scroll_user_epoch += 1', source)
        self.assertNotIn('set_input_as_handled', source)
        self.assertNotIn('_save_match', source)
        self.assertIn('_track_reserve_scroll_intent(event)', body('_input'))

    def test_06_both_deferred_scrollers_use_same_live_guard(self):
        guard = body('_reserve_scroll_request_current')
        for value in ['turn == player', 'current_world == world',
                      'round_number == round_id', 'moves == move_count',
                      'selected_reserve == rank_index',
                      '_reserve_scroll_user_epoch == user_epoch']:
            self.assertIn(value, guard)
        tutorial = body('_ensure_tutorial_rank_visible')
        restore = body('_restore_active_reserve_scroll')
        self.assertIn('await get_tree().process_frame', tutorial)
        self.assertIn('await get_tree().process_frame', restore)
        self.assertIn('_reserve_scroll_request_current(', tutorial)
        self.assertIn('_reserve_scroll_request_current(', restore)
        self.assertIn('reserve_scroller.ensure_control_visible(button)', tutorial)
        self.assertIn('reserve_scroller.scroll_horizontal = clampi(', restore)

    def test_07_both_schedules_capture_request_epoch(self):
        self.assertIn('current_world, moves, round_number, _reserve_scroll_user_epoch)',
                      body('_on_mobile_menu_action'))
        self.assertIn('round_number, moves, selected_reserve, _reserve_scroll_user_epoch)',
                      body('_refresh_surface'))

    def test_08_native_fixture_registered_but_not_claimed(self):
        smoke = body('_run_headless_deferred_scroll_intent_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', smoke)
        self.assertIn('InputEventScreenTouch.new()', smoke)
        self.assertIn('not _reserve_scroll_request_current(', smoke)
        self.assertIn('BLUE_SEA_DEFERRED_SCROLL_INTENT_PASS', smoke)
        self.assertIn('_run_headless_deferred_scroll_intent_smoke()',
                      body('_run_headless_geometry_and_interaction_smoke'))

    def test_09_no_second_engine_or_art_replacement(self):
        self.assertIn('const WorldVisuals = preload(', SOURCE)
        self.assertIn('const AIOpponent = preload(', SOURCE)
        self.assertIn('PirateOpeningCampaign', (ROOT/'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
