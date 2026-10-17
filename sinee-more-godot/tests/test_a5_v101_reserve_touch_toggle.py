"""v101: touch cancellation is integrated in the one live seven-world Godot UI.

These are offline source/contract checks, not a native Godot or phone PASS.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()


def function(name):
    start = MAIN.index('func ' + name + '(')
    tail = MAIN[start:]
    match = re.search(r'\n(?:func |static func |var |const )', tail[5:])
    return tail[:match.start()+5] if match else tail


class ReserveTouchToggle(unittest.TestCase):
    def test_01_uses_live_handler_not_secondary_engine(self):
        handler = function('_on_reserve_pressed')
        self.assertIn('if selected_reserve == index:', handler)
        self.assertIn('_on_secondary()', handler)
        self.assertLess(handler.index('if selected_reserve == index:'), handler.index('selected_reserve = index'))
        self.assertEqual(MAIN.count('func _on_reserve_pressed('), 1)

    def test_02_toggle_after_all_guards_before_mutation(self):
        handler = function('_on_reserve_pressed')
        for guard in ['if game_over or _modal_blocks_board_input():',
                      'if player < 1 or player > 2 or index < 0 or index >= 9:',
                      'if ai_enabled and player == 2:',
                      'if player != turn:',
                      'if not reserve_available[player - 1][index]:']:
            self.assertLess(handler.index(guard), handler.index('if selected_reserve == index:'))
        self.assertIn('if selected_reserve == index:\n\t\t_on_secondary()\n\t\treturn', handler)

    def test_03_cancel_resets_selection_and_visual_feedback(self):
        secondary = function('_on_secondary')
        for clause in ('selected_reserve = -1', 'selected_cell = -1',
                       '_refresh_selection_feedback()', '_update_status("selection cleared")'):
            self.assertIn(clause, secondary)
        visuals = function('_refresh_selection_feedback')
        self.assertIn('has_piece and player == turn and i == selected_reserve', visuals)
        self.assertIn('legal or chosen_cell', visuals)

    def test_04_actual_board_move_path_preserved(self):
        handler = function('_on_cell_pressed')
        self.assertIn('_on_primary()', handler)
        primary = function('_on_primary')
        for clause in ('_is_legal_move(turn, rank, selected_cell)',
                       'board_stacks[selected_cell].append',
                       'reserve_available[moving_player - 1][selected_reserve] = false',
                       '_save_match()'):
            self.assertIn(clause, primary)

    def test_05_native_fixture_covers_all_seven_two_players_two_extreme_ranks(self):
        smoke = function('_run_headless_reserve_touch_toggle_smoke')
        for clause in ('range(WorldVisuals.WORLDS.size())',
                       'for player in [1, 2]:', 'for index in [0, 8]:',
                       '_on_reserve_pressed(player, index)',
                       'selected_reserve == -1 and selected_cell == -1 and moves == 0',
                       'assert(not outline.visible',
                       'BLUE_SEA_RESERVE_TOUCH_TOGGLE_PASS'):
            self.assertIn(clause, smoke)
        self.assertIn('_run_headless_reserve_touch_toggle_smoke()', function('_run_headless_geometry_and_interaction_smoke'))

    def test_06_world_canon_and_shared_ai_unchanged(self):
        worlds = (ROOT / 'scripts/world_visuals.gd').read_text()
        self.assertEqual(worlds.count('"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep"'), 1)
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")', MAIN)
        self.assertIn('PirateOpeningCampaign=', (ROOT / 'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
