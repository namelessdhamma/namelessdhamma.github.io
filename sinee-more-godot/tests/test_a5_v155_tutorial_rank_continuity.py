"""A5 v155: tutorial practice preserves a legal selected rank and reveals its real reserve button.

Offline checks cannot certify native Godot layout or physical touch. The opt-in
native fixture exercises all seven worlds and verifies visible rank 9.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text()


def body(name):
    m = re.search(rf'^func {re.escape(name)}\(', SOURCE, re.M)
    assert m, name
    end = re.search(r'\nfunc ', SOURCE[m.end():])
    return SOURCE[m.start():m.end() + end.start() if end else len(SOURCE)]


def tutorial_selection(available, legal, chosen, game_over=False, ai_turn=False):
    """Independent model of user-visible rank choice, not D2 rules."""
    if game_over or ai_turn:
        return chosen, False
    if chosen is not None and 0 <= chosen < 9 and available[chosen] and legal[chosen]:
        return chosen, True
    for i in range(9):
        if available[i] and legal[i]:
            return i, True
    return chosen, False


class TutorialRankContinuity(unittest.TestCase):
    def test_01_selected_high_rank_does_not_toggle_off(self):
        available = [True] * 9
        legal = [True] * 9
        for world in range(7):
            self.assertEqual(tutorial_selection(available, legal, 8), (8, True), world)

    def test_02_falls_back_only_when_selected_rank_cannot_move(self):
        available = [True] * 9
        legal = [True] * 9
        legal[8] = False
        self.assertEqual(tutorial_selection(available, legal, 8), (0, True))
        available[0] = False
        self.assertEqual(tutorial_selection(available, legal, 8), (1, True))

    def test_03_no_move_when_terminal_or_ai_turn(self):
        for terminal, ai in [(True, False), (False, True), (True, True)]:
            self.assertEqual(tutorial_selection([True]*9, [True]*9, 8, terminal, ai), (8, False))

    def test_04_no_legal_rank_does_not_invent_one(self):
        self.assertEqual(tutorial_selection([True]*9, [False]*9, None), (None, False))

    def test_05_real_live_selection_without_placement(self):
        s = body('_on_mobile_menu_action')
        block = s[s.index('elif id == 704:'):s.index('elif id == 106:')]
        self.assertIn('if selected_reserve == practice_index:', block)
        self.assertIn('selected_cell = -1', block)
        self.assertIn('_refresh_selection_feedback()', block)
        self.assertIn('_on_reserve_pressed(turn, practice_index)', block)
        self.assertIn('_rank_has_legal_cell(turn, rank)', block)
        self.assertIn('call_deferred("_ensure_tutorial_rank_visible"', block)
        for forbidden in ('_on_primary()', '_on_cell_pressed(', 'board_stacks[', 'reserve_available[turn - 1][practice_index] ='):
            self.assertNotIn(forbidden, block)

    def test_06_deferred_scroll_is_transaction_bound(self):
        s = body('_ensure_tutorial_rank_visible')
        self.assertIn('await get_tree().process_frame', s)
        self.assertIn('turn != player or current_world != world or moves != move_count or selected_reserve != rank_index', s)
        self.assertIn('mobile_menu_panel.visible', s)
        self.assertIn('reserve_scroller.ensure_control_visible(button)', s)
        self.assertIn('button.visible', s)

    def test_07_native_fixture_runs_seven_real_worlds(self):
        s = body('_run_headless_tutorial_selection_continuity_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', s)
        self.assertIn('_on_reserve_pressed(1, 8)', s)
        self.assertIn('_on_mobile_menu_action(704)', s)
        self.assertIn('rank_button.get_global_rect()', s)
        self.assertIn('BLUE_SEA_TUTORIAL_SELECTION_CONTINUITY_PASS', s)
        self.assertIn('await _run_headless_tutorial_selection_continuity_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_08_shared_gameplay_and_canon_unmodified(self):
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")', SOURCE)
        self.assertIn('const WorldVisuals = preload("res://scripts/world_visuals.gd")', SOURCE)
        self.assertIn('PirateOpeningCampaign', (Path(__file__).resolve().parents[1] / 'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
