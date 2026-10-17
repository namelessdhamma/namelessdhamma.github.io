"""A5 v58: static contract and independent model, NOT a Godot runtime PASS."""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text()
AI = (ROOT / 'scripts/ai_opponent.gd').read_bytes()
CANON = {
    '01_nd_premium_void_canon_source.png': '00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
    '02_pirate_sea_canon_source.png': '0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
    '03_atlantis_canon_source.png': '2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
    '04_gods_of_the_deep_canon_source.png': '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
    '05_sand_sea_canon_source.png': '01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
    '06_night_sea_canon_source.png': 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
    '07_northern_sea_canon_source.png': '3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775',
}


def func(name):
    marker = 'func ' + name + '('
    start = SRC.index(marker)
    next_func = SRC.find('\nfunc ', start + len(marker))
    return SRC[start:next_func if next_func != -1 else None]


class TestProductionAIQualification(unittest.TestCase):
    def test_01_ai_remains_enabled_in_21_cases(self):
        f = func('_run_headless_full_match_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size())', f)
        self.assertIn('for mode in ["C", "D", "CD"]', f)
        self.assertIn('ai_enabled = true', f)
        self.assertIn('ai_difficulty = 3', f)
        self.assertIn('ai_persona = 0', f)
        self.assertNotIn('ai_enabled = false', f)

    def test_02_real_deferred_ai_not_manual_ai_commit(self):
        f = func('_run_headless_full_match_smoke')
        self.assertIn('await get_tree().process_frame', f)
        self.assertIn('Deferred production AI did not move within three frames', f)
        self.assertIn('AI failed to consume chosen rank', f)
        self.assertIn('AI did not commit chosen cell', f)
        self.assertNotIn('selected_reserve = int(move["rank"])', f)
        self.assertNotIn('\n\t\t\t\t\t\t_on_primary()', f)
        self.assertIn('assert(ai_enabled and not _reserve_node(2).visible', f)

    def test_03_human_uses_real_live_input_handlers(self):
        f = func('_run_headless_full_match_smoke')
        self.assertIn('_on_reserve_pressed(1,', f)
        self.assertIn('_on_cell_pressed(int(move["cell"]))', f)
        self.assertIn('Human input did not commit exactly once', f)

    def test_04_live_world_swap_preserves_state(self):
        f = func('_run_headless_full_match_smoke')
        self.assertIn('_set_world((world + 1) % WorldVisuals.WORLDS.size())', f)
        self.assertIn('board_stacks == old_board and match_score == old_score and turn == old_turn', f)

    def test_05_terminal_reserve_next_match(self):
        f = func('_run_headless_full_match_smoke')
        for token in ['assert(game_over', 'assert(next_round_button.visible',
                      'assert(not _reserve_node(1).visible and not _reserve_node(2).visible)',
                      'assert(moves <= 18', 'match_score[1] == MATCH_TARGET']:
            self.assertIn(token, f)

    def test_06_headless_test_modes_exit_after_success(self):
        self.assertIn('get_tree().quit(0)', func('_run_headless_full_match_smoke'))
        self.assertIn('get_tree().quit(0)', func('_run_headless_geometry_and_interaction_smoke'))
        self.assertEqual(SRC.count('get_tree().quit(0)'), 2)

    def test_07_regular_headless_is_nonmutating(self):
        f = func('_ready')
        self.assertIn('BLUE_SEA_HEADLESS_RENDER_READY_NO_TEST_MUTATION', f)
        self.assertNotIn('get_tree().quit', f)

    def test_08_gameplay_and_ai_production_paths_preserved(self):
        for name in ['_is_legal_move', '_winning_line', '_has_legal_move', '_on_primary',
                     '_reset_round', '_on_menu', '_play_ai_turn']:
            self.assertIn('func ' + name + '(', SRC)
        self.assertIn('func choose_move(', AI.decode())

    def test_09_exact_approved_reference_hashes_unchanged(self):
        for name, expected in CANON.items():
            paths = list((ROOT / 'assets').rglob(name))
            self.assertEqual(len(paths), 1, name)
            self.assertEqual(hashlib.sha256(paths[0].read_bytes()).hexdigest(), expected)

    def test_10_finite_wait_and_finite_match_bounds(self):
        f = func('_run_headless_full_match_smoke')
        for token in ['range(3)', 'rounds_completed < 12', 'moves < 18',
                      'verified_ai_turns > 0', 'BLUE_SEA_FULL_MATCH_SUITE_PASS']:
            self.assertIn(token, f)

if __name__ == '__main__':
    unittest.main()
