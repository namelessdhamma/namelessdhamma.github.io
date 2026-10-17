"""A5 v94: phone tutorial is navigable and ends on the real live board.

These are structural and independent state-model tests, not a Godot runtime
or real-touch PASS. The production Godot smoke is separately wired.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text(encoding='utf8')


def body(name):
    pattern = rf'^func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)'
    m = re.search(pattern, SOURCE, re.M | re.S)
    assert m, f'missing production method {name}'
    return m.group(1)


class TutorialMenuModel:
    """Independent menu transition model, intentionally not a second game engine."""
    pages = {700: 'tutorial_1', 701: 'tutorial_2', 702: 'tutorial_3', 703: 'tutorial_4'}
    def __init__(self):
        self.page = 'main'
        self.open = True
        self.moves = 3
        self.board = (0, 1, 4)
        self.selected_rank = None

    def action(self, action_id, legal_ranks=(3, 5, 8)):
        if action_id == 3:
            self.page = 'tutorial_1'
        elif action_id in self.pages:
            self.page = self.pages[action_id]
        elif action_id == 704:
            self.open = False
            self.selected_rank = next(iter(legal_ranks), None)
        elif action_id == -2:
            self.open = False
        elif action_id == -1:
            self.page = 'main'


class LivePhoneTutorial(unittest.TestCase):
    def test_01_tutorial_is_part_of_real_phone_modal(self):
        self.assertIn('elif id == 3:', body('_on_mobile_menu_action'))
        self.assertIn('_render_mobile_menu_page("tutorial_1")', body('_on_mobile_menu_action'))
        self.assertIn('"MobileSettingsOverlay"', body('_create_mobile_menu_panel'))
        self.assertIn('ScrollContainer.new()', body('_create_mobile_menu_panel'))

    def test_02_all_four_pages_and_back_navigation(self):
        src = body('_render_mobile_menu_page')
        for page in range(1, 5):
            self.assertIn(f'page == "tutorial_{page}"', src)
        for action in [700, 701, 702, 703]:
            self.assertIn(f', {action})', src)
        self.assertIn('_mobile_menu_add("← Меню", -1)', src)

    def test_03_real_text_not_flattened_art(self):
        src = body('_mobile_menu_add_explanation')
        self.assertIn('Label.new()', src)
        self.assertIn('TextServer.AUTOWRAP_WORD_SMART', src)
        self.assertIn('mobile_menu_list.add_child(explanation)', src)
        self.assertIn('_native_touch_density() / _physical_pixel_scale()', src)
        self.assertNotIn('TextureRect', src)

    def test_04_no_second_board_or_game_engine(self):
        for name in ['_mobile_menu_add_explanation', '_render_mobile_menu_page', '_on_mobile_menu_action']:
            src = body(name)
            self.assertNotIn('board_stacks =', src)
            self.assertNotIn('reserve_available =', src)
            self.assertNotIn('moves +=', src)
            self.assertNotIn('_on_primary()', src)

    def test_05_practice_uses_real_legality_and_selection(self):
        src = body('_on_mobile_menu_action')
        self.assertIn('if _rank_has_legal_cell(turn, rank):', src)
        self.assertIn('_on_reserve_pressed(turn, practice_index)', src)
        self.assertIn('if selected_reserve == practice_index:', src)
        self.assertIn('mobile_menu_panel.hide()', src)
        self.assertNotIn('_on_cell_pressed(', src)

    def test_06_terminal_and_ai_turn_are_disabled(self):
        src = body('_render_mobile_menu_page')
        self.assertIn('game_over or (ai_enabled and turn == 2) or not _has_legal_move(turn)', src)
        src = body('_on_mobile_menu_action')
        self.assertIn('if not game_over and not (ai_enabled and turn == 2):', src)

    def test_07_no_unreadable_native_help_on_phone(self):
        src = body('_on_mobile_menu_action')
        self.assertIn('elif id == 3:', src)
        self.assertIn('_render_mobile_menu_page("tutorial_1")', src)
        self.assertNotIn('rules_dialog.popup_centered_ratio', src)
        self.assertIn('rules_dialog.popup_centered_ratio', body('_on_game_menu_item'))

    def test_08_tutorial_covers_actual_modes_and_resume(self):
        src = body('_render_mobile_menu_page')
        for concept in ['C:', 'D:', 'CD:', 'Партия сохраняется автоматически', 'Под доской', 'Сброс требует подтверждения']:
            self.assertIn(concept, src)

    def test_09_navigation_does_not_place_or_reset_piece(self):
        m = TutorialMenuModel()
        before = (m.moves, m.board)
        for action, page in [(3, 'tutorial_1'), (701, 'tutorial_2'), (702, 'tutorial_3'), (703, 'tutorial_4'), (702, 'tutorial_3'), (703, 'tutorial_4')]:
            m.action(action)
            self.assertEqual(m.page, page)
            self.assertEqual((m.moves, m.board), before)
        m.action(704)
        self.assertFalse(m.open)
        self.assertEqual(m.selected_rank, 3)
        self.assertEqual((m.moves, m.board), before)

    def test_10_production_headless_fixture_wired(self):
        suite = body('_run_headless_geometry_and_interaction_smoke')
        smoke = body('_run_headless_tutorial_live_practice_smoke')
        self.assertIn('_run_headless_tutorial_live_practice_smoke()', suite)
        self.assertIn('_on_mobile_menu_action(704)', smoke)
        self.assertIn('perspective_legal_outlines[cell].visible', smoke)
        self.assertIn('_match_snapshot() == practice_snapshot', smoke)
        self.assertIn('_match_snapshot() == preserved', smoke)


if __name__ == '__main__':
    unittest.main()
