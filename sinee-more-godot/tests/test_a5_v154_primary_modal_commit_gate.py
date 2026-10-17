"""A5 v154: protect the final shared move-commit handler from modal/lifecycle races.

These checks are source preflight, not native Godot or physical touch evidence.
"""
from pathlib import Path
import hashlib
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text()


def body(name):
    m = re.search(rf'^func {re.escape(name)}\(', SOURCE, re.M)
    assert m, name
    end = re.search(r'\nfunc ', SOURCE[m.end():])
    return SOURCE[m.start():m.end()+end.start() if end else len(SOURCE)]


class PrimaryModalCommitGate(unittest.TestCase):
    def test_commit_checks_modal_before_any_state_mutation(self):
        s = body('_on_primary')
        self.assertRegex(s, r'func _on_primary\(\) -> void:\n(?:\t#.*\n)+\tif _modal_blocks_board_input\(\):\n\t\treturn')
        self.assertLess(s.index('if _modal_blocks_board_input():'), s.index('if selected_reserve < 0'))
        self.assertLess(s.index('if _modal_blocks_board_input():'), s.index('_undo_history.append('))
        self.assertLess(s.index('if _modal_blocks_board_input():'), s.index('board_stacks[selected_cell].append('))

    def test_original_gameplay_core_unchanged_since_v153(self):
        source = body('_on_primary')
        original_core = source[source.index('\tif selected_reserve < 0'):].rstrip() + '\n'
        self.assertEqual(hashlib.sha256(original_core.encode()).hexdigest(),
                         '107fa0f16abc702ddcfa023efab2a0fb5a6666fcf70a1375a50cf9ae0b7c4aa9')

    def test_existing_ai_route_remains_live_after_modal_closes(self):
        ai = body('_play_ai_turn')
        self.assertIn('if not ai_enabled or game_over or turn != 2 or _modal_blocks_board_input():', ai)
        self.assertIn('_on_primary()', ai)
        self.assertIn('_queue_ai_turn_if_ready()', body('_on_primary'))

    def test_modal_gate_covers_phone_menu_and_lifecycle(self):
        gate = body('_modal_blocks_board_input')
        self.assertIn('if _interaction_suspended():', gate)
        self.assertIn('mobile_menu_panel.visible', gate)
        self.assertIn('reset_dialog.visible', gate)
        self.assertIn('rules_dialog.visible', gate)
        self.assertIn('pirate_choice.visible', gate)

    def test_native_fixture_uses_actual_production_commit(self):
        fixture = body('_run_headless_primary_modal_commit_guard_smoke')
        self.assertGreaterEqual(fixture.count('_on_primary()'), 4)
        for token in ('mobile_menu_panel.show()', '_app_paused = true', '_app_unfocused = true',
                      'board_stacks[0].size() == 1', 'BLUE_SEA_PRIMARY_MODAL_COMMIT_GUARD_PASS',
                      '_apply_match_snapshot(original)', '_undo_history = original_history'):
            self.assertIn(token, fixture)
        self.assertIn('_run_headless_primary_modal_commit_guard_smoke()',
                      body('_run_headless_geometry_and_interaction_smoke'))

    def test_one_shared_engine_all_seven_worlds(self):
        self.assertIn('const WorldVisuals = preload("res://scripts/world_visuals.gd")', SOURCE)
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")', SOURCE)
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', SOURCE)


if __name__ == '__main__':
    unittest.main()
