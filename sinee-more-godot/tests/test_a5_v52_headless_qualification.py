"""A5 v52 static + independent model checks; not Godot execution."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()
AI_SOURCE = (ROOT / 'scripts/ai_opponent.gd').read_text()
WORLD_SOURCE = (ROOT / 'scripts/world_visuals.gd').read_text()
CANON_SHA = {
    '01_nd_premium_void_canon_source.png': '00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
    '02_pirate_sea_canon_source.png': '0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
    '03_atlantis_canon_source.png': '2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
    '04_gods_of_the_deep_canon_source.png': '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
    '05_sand_sea_canon_source.png': '01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
    '06_night_sea_canon_source.png': 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
    '07_northern_sea_canon_source.png': '3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775',
}


def function(name):
    pattern = rf'(?ms)^func {re.escape(name)}\([^\n]*\n(?:^(?!func ).*\n)*'
    m = re.search(pattern, SOURCE)
    assert m, f'Function missing: {name}'
    return m.group(0)


class V52HeadlessQualification(unittest.TestCase):
    def test_01_headless_mode_is_explicit(self):
        s = function('_headless_run_mode')
        self.assertIn('"--nd-run-smoke" in args', s)
        self.assertIn('"--nd-run-full-match" in args', s)
        self.assertIn('return ""', s)

    def test_02_normal_headless_does_not_launch_mutating_smoke(self):
        s = function('_ready')
        self.assertIn('match _headless_run_mode():', s)
        self.assertIn('"smoke":', s)
        self.assertIn('"full_match":', s)
        self.assertIn('BLUE_SEA_HEADLESS_RENDER_READY_NO_TEST_MUTATION', s)
        self.assertNotIn('if DisplayServer.get_name() == "headless":\n\t\tcall_deferred', s)

    def test_03_headless_import_does_not_load_prior_test_preferences(self):
        s = function('_load_preferences')
        self.assertLess(s.index('if DisplayServer.get_name() == "headless":'), s.index('settings.load'))

    def test_04_headless_import_does_not_write_test_preferences(self):
        s = function('_save_preferences')
        self.assertLess(s.index('_headless_run_mode() == ""'), s.index('settings.save'))

    def test_05_real_user_preferences_still_persist(self):
        self.assertIn('return "user://blue_sea_freeplay_v1_test.cfg" if DisplayServer.get_name() == "headless" else PREFERENCES_PATH', SOURCE)
        self.assertIn('settings.load(_preferences_path())', SOURCE)
        self.assertIn('settings.save(_preferences_path())', SOURCE)

    def test_06_full_match_is_opt_in_and_bounded(self):
        s = function('_run_headless_full_match_smoke')
        self.assertIn('assert(_headless_run_mode() == "full_match"', s)
        self.assertIn('rounds_completed < 12', s)
        self.assertIn('moves < 18', s)

    def test_07_full_match_covers_all_worlds_and_modes(self):
        s = function('_run_headless_full_match_smoke')
        self.assertIn('range(WorldVisuals.WORLDS.size())', s)
        self.assertIn('["C", "D", "CD"]', s)
        self.assertIn('BLUE_SEA_FULL_MATCH_CASE_PASS', s)
        self.assertIn('BLUE_SEA_FULL_MATCH_SUITE_PASS', s)

    def test_08_full_match_uses_real_commit_handlers(self):
        s = function('_run_headless_full_match_smoke')
        # v58: the fixture must exercise the actual deferred AI controller;
        # manually calling _on_primary() for player 2 hid scheduler defects.
        for x in ['ai_enabled = true', 'ai_engine.choose_move(', '_on_reserve_pressed(',
                  '_on_cell_pressed(', 'await get_tree().process_frame',
                  'Deferred production AI did not move']:
            self.assertIn(x, s)
        self.assertNotIn('selected_reserve = int(move["rank"]) - 1', s)

    def test_09_full_match_asserts_terminal_and_reserve_invariants(self):
        s = function('_run_headless_full_match_smoke')
        for x in ['assert(game_over', 'assert(next_round_button.visible', 'assert(not _reserve_node(1).visible', 'match_score[1] == MATCH_TARGET']:
            self.assertIn(x, s)

    def test_10_full_match_tests_midgame_world_switch(self):
        s = function('_run_headless_full_match_smoke')
        self.assertIn('board_stacks.duplicate(true)', s)
        self.assertIn('_set_world((world + 1) % WorldVisuals.WORLDS.size())', s)
        self.assertIn('board_stacks == old_board', s)

    def test_11_existing_ai_and_visual_bindings_remain(self):
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")', SOURCE)
        self.assertIn('const WorldVisuals = preload("res://scripts/world_visuals.gd")', SOURCE)
        self.assertIn('func choose_move(', AI_SOURCE)
        self.assertIn('func apply_world(', WORLD_SOURCE)

    def test_12_canonical_seven_pngs_unchanged(self):
        for name, expected in CANON_SHA.items():
            found = list((ROOT / 'assets').rglob(name))
            self.assertEqual(len(found), 1, name)
            self.assertEqual(hashlib.sha256(found[0].read_bytes()).hexdigest(), expected, name)

    def test_13_no_synthetic_success_in_nonqualifying_headless(self):
        s = function('_ready')
        default = s.split('"full_match":', 1)[1].split('func _prepare_world_shell', 1)[0]
        self.assertIn('BLUE_SEA_HEADLESS_RENDER_READY_NO_TEST_MUTATION', default)
        self.assertNotIn('BLUE_SEA_FULL_MATCH_SUITE_PASS', default)

    def test_14_existing_headless_smoke_kept(self):
        s = function('_run_headless_geometry_and_interaction_smoke')
        self.assertIn('_run_headless_even_round_ai_smoke()', s)
        self.assertIn('_run_headless_mobile_world_selector_smoke()', s)

    def test_15_gameplay_was_not_rewritten(self):
        for name in ['_is_legal_move', '_winning_line', '_has_legal_move', '_on_primary', '_reset_round', '_on_menu']:
            self.assertIn('func ' + name + '(', SOURCE)


if __name__ == '__main__':
    unittest.main()
