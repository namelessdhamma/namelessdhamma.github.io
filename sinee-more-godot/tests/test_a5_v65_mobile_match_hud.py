"""A5 v65 source/model checks. NOT Godot execution or visual parity."""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")
WORLD = (ROOT / "scripts/world_visuals.gd").read_text(encoding="utf-8")


def body(name):
    match = re.search(rf"^func {name}\(.*?(?=^func |\Z)", SOURCE, re.M | re.S)
    if not match:
        raise AssertionError(f"missing function {name}")
    return match.group(0)


def hud_model(score, turn, ai, winner=0, match_winner=0, game_over=False, draw=False):
    state = "ХОД ИИ" if ai and turn == 2 else f"ХОД P{turn}"
    if match_winner:
        state = f"МАТЧ P{match_winner}"
    elif game_over and draw:
        state = "НИЧЬЯ"
    elif game_over and winner:
        state = f"РАУНД P{winner}"
    return f"{score[0]}:{score[1]}\n{state}"


class TestV65MatchHUD(unittest.TestCase):
    def test_01_real_topbar_widget_not_reference_screenshot(self):
        self.assertIn('match_hud = PanelContainer.new()', SOURCE)
        self.assertIn('match_hud_label = Label.new()', SOURCE)
        self.assertIn('topbar.add_child(match_hud)', body('_prepare_world_shell'))
        self.assertIn('match_hud_label.name = "LiveMatchState"', SOURCE)

    def test_02_hud_is_noninteractive(self):
        self.assertIn('match_hud.mouse_filter = Control.MOUSE_FILTER_IGNORE', SOURCE)
        self.assertIn('match_hud_label.mouse_filter = Control.MOUSE_FILTER_IGNORE', SOURCE)

    def test_03_physical_font_and_width_for_phone(self):
        f = body('_ensure_physical_touch_targets')
        self.assertIn('100.0 * density / scale', f)
        self.assertIn('13.0 * density / scale', f)
        for scale, density in [(1.0, 1.0), (280/720, 1.0), (1.0, 3.0), (0.75, 2.0)]:
            from math import ceil
            physical_width = ceil(100 * density / scale) * scale
            physical_font = max(16, ceil(13 * density / scale)) * scale
            self.assertGreaterEqual(physical_width + 1e-7, 100 * density)
            self.assertGreaterEqual(physical_font + 1e-7, 13 * density)

    def test_04_live_score_always_refreshes_on_game_state(self):
        self.assertIn('_refresh_match_hud()', body('_refresh_surface'))
        for name in ['_on_primary', '_reset_round', '_set_world', '_toggle_ai', '_confirm_reset_match']:
            f = body(name)
            self.assertTrue('_refresh_surface()' in f or '_reset_round()' in f, name)

    def test_05_hud_semantic_priority(self):
        f = body('_refresh_match_hud')
        self.assertLess(f.index('if match_winner != 0:'), f.index('elif game_over and round_draw:'))
        self.assertLess(f.index('elif game_over and round_draw:'), f.index('elif game_over and winner != 0:'))
        self.assertEqual(hud_model([0, 0], 1, False), '0:0\nХОД P1')
        self.assertEqual(hud_model([1, 0], 2, True), '1:0\nХОД ИИ')
        self.assertEqual(hud_model([1, 1], 2, True, winner=2, game_over=True), '1:1\nРАУНД P2')
        self.assertEqual(hud_model([1, 1], 2, True, game_over=True, draw=True), '1:1\nНИЧЬЯ')
        self.assertEqual(hud_model([1, 3], 2, True, winner=2, match_winner=2, game_over=True), '1:3\nМАТЧ P2')

    def test_06_terminal_next_replaces_reserve_only_after_game_over(self):
        f = body('_refresh_surface')
        self.assertIn('next_round_button.visible = game_over', f)
        self.assertIn('reserve_scroller.visible = not game_over', f)
        self.assertIn('next_round_button.text = "P%d ВЫИГРАЛ МАТЧ · НОВЫЙ"', f)
        self.assertIn('next_round_button.text = "НИЧЬЯ · ДАЛЬШЕ"', f)
        self.assertIn('next_round_button.text = "P%d ПОБЕДИЛ · ДАЛЬШЕ"', f)

    def test_07_headless_smoke_checks_terminal_and_restores(self):
        f = body('_run_headless_match_hud_smoke')
        for marker in ['ХОД ИИ', 'РАУНД P2', 'НИЧЬЯ', 'МАТЧ P2',
                       'board_stacks = saved_board', 'reserve_available = saved_reserves',
                       'match_score = saved_score', 'game_over = saved_over',
                       'BLUE_SEA_LIVE_MATCH_HUD_PASS']:
            self.assertIn(marker, f)
        self.assertIn('_run_headless_match_hud_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_08_no_second_game_engine(self):
        self.assertEqual(SOURCE.count('func _on_primary()'), 1)
        self.assertEqual(SOURCE.count('func _winning_line('), 1)
        self.assertIn('const WorldVisuals = preload', SOURCE)
        self.assertIn('const AIOpponent = preload', SOURCE)

    def test_09_all_seven_worlds_still_live(self):
        for name in ['ND Premium Void', 'Pirate Sea', 'Atlantis', 'Gods of the Deep',
                     'Sand Sea', 'Night Sea', 'Northern Sea']:
            self.assertIn(name, WORLD)
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', body('_run_headless_full_match_smoke'))

    def test_10_pirate_opening_and_rule_modes_preserved(self):
        self.assertIn('PirateOpeningChoiceSurface', SOURCE)
        self.assertIn('for mode in ["C", "D", "CD"]:', body('_run_headless_full_match_smoke'))
        self.assertIn('current_rule = ["C", "D", "CD"][id - 300]', body('_on_game_menu_item'))


if __name__ == '__main__':
    unittest.main()
