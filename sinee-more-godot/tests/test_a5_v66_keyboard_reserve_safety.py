"""A5 v66 source/geometry checks; not Godot compilation or phone evidence."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')

def fn(name):
    m = re.search(rf'^func {re.escape(name)}\(.*?(?=^func |\Z)', SRC, re.M | re.S)
    if not m:
        raise AssertionError(f'Missing GDScript function: {name}')
    return m.group(0)

class KeyboardReserveSafety(unittest.TestCase):
    def test_used_rank_clears_previous_selection(self):
        s=fn('_select_keyboard_rank')
        self.assertIn('if not reserve_available[turn - 1][index]:', s)
        self.assertLess(s.index('_on_secondary()'), s.index('_on_reserve_pressed(turn, index)'))
        self.assertIn('return\n\t_on_reserve_pressed(turn, index)',s)

    def test_invalid_selection_has_explicit_feedback(self):
        s=fn('_select_keyboard_rank')
        self.assertIn('_play_feedback("invalid")',s)
        self.assertIn('piece already played',s)

    def test_selection_cannot_bypass_modal(self):
        self.assertIn('_modal_blocks_board_input()',fn('_select_keyboard_rank'))

    def test_keyboard_rank_is_not_an_independent_engine(self):
        self.assertIn('_on_reserve_pressed(turn, index)',fn('_select_keyboard_rank'))
        self.assertEqual(SRC.count('func _on_primary()'),1)
        self.assertEqual(SRC.count('func _winning_line('),1)

    def test_deferred_reveal_follows_valid_selection(self):
        s=fn('_select_keyboard_rank')
        self.assertIn('call_deferred("_reveal_keyboard_rank", turn, index, current_world,',s)
        self.assertGreater(s.index('call_deferred('),s.index('_on_reserve_pressed(turn, index)'))

    def test_deferred_reveal_does_not_cross_turn_or_selection(self):
        s=fn('_reveal_keyboard_rank')
        self.assertIn('_reserve_scroll_request_current(player, world, round_id, move_count,',s)
        self.assertIn('game_over or _modal_blocks_board_input()',s)
        self.assertIn('if not reserve.visible or reserve.get_child_count() <= index:',s)

    def test_uses_native_scrollcontainer_method(self):
        self.assertIn('reserve_scroller.ensure_control_visible(button)',fn('_reveal_keyboard_rank'))
        self.assertIn('reserve_scroller = ScrollContainer.new()',fn('_prepare_world_shell'))
        self.assertIn('reserve_scroller.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO',SRC)

    def test_nine_safe_targets_overflow_360dp_and_need_scroll(self):
        for density in (1,2,3,4):
            self.assertGreater(9*44*density,360*density)
        self.assertIn('logical_touch := ceilf(_minimum_touch_physical_px() / scale)',fn('_ensure_physical_touch_targets'))

    def test_qualification_is_wired_to_headless_suite(self):
        self.assertIn('_run_headless_keyboard_rank_guard_smoke()',fn('_run_headless_geometry_and_interaction_smoke'))
        s=fn('_run_headless_keyboard_rank_guard_smoke')
        self.assertIn('selected_reserve == -1 and selected_cell == -1',s)
        self.assertIn('_select_keyboard_rank(8)',s)
        self.assertIn('BLUE_SEA_KEYBOARD_RANK_GUARD_PASS',s)

    def test_existing_21_case_ai_and_world_switches_retained(self):
        s=fn('_run_headless_full_match_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):',s)
        self.assertIn('for mode in ["C", "D", "CD"]:',s)
        self.assertIn('await get_tree().process_frame',s)
        # The shared modal-safe scheduler owns the sole deferred call site.
        self.assertIn('_queue_ai_turn_if_ready()',fn('_on_primary'))
        self.assertIn('call_deferred("_play_ai_turn")',fn('_queue_ai_turn_if_ready'))

if __name__ == '__main__':
    unittest.main()
