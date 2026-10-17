"""A5 v55: mobile reset confirmation safety (static + behavioral model).

Does not assert Godot runtime or real-device touch acceptance.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'scripts/main.gd').read_text()


def body(name):
    m = re.search(r'^func '+re.escape(name)+r'\([^\n]*\)(?: -> [^:]+)?:\n', SCRIPT, re.M)
    assert m, name
    n = re.search(r'^func |^var perspective_|^# Explicit, bounded whole-match', SCRIPT[m.end():], re.M)
    return SCRIPT[m.end():m.end()+n.start()] if n else SCRIPT[m.end():]


class ResetModel:
    def __init__(self):
        self.board = [[(1,1)]] + [[] for _ in range(8)]
        self.reserves = [[False] + [True]*8, [True]*9]
        self.score = [1,2]
        self.moves = 1
        self.round = 4
        self.visible = False
        self.page = 'main'

    def open_menu(self):
        self.visible = True
        self.page = 'main'

    def action(self, key):
        if key == -2:
            self.visible = False
        elif key == 1:
            self.visible = True
            self.page = 'confirm_reset'
        elif key == 600 and self.visible and self.page == 'confirm_reset':
            self.visible = False
            self.board = [[] for _ in range(9)]
            self.reserves = [[True]*9 for _ in range(2)]
            self.score = [0,0]
            self.moves = 0
            self.round = 1


class TestMobileResetConfirmation(unittest.TestCase):
    def test_page_has_two_touch_safe_actions(self):
        b = body('_render_mobile_menu_page')
        self.assertIn('elif page == "confirm_reset":', b)
        self.assertIn('_mobile_menu_add("Отмена · продолжить игру", -2)', b)
        self.assertIn('_mobile_menu_add("Да · сбросить матч и счёт", 600)', b)
        self.assertIn('mobile_menu_heading.text = "СБРОСИТЬ ТЕКУЩИЙ МАТЧ?"', b)

    def test_all_mobile_choices_share_physical_touch_factory(self):
        b = body('_mobile_menu_add')
        self.assertIn('ceilf(44.0 / _physical_pixel_scale())', b)
        self.assertIn('ceili(14.0 / _physical_pixel_scale())', b)

    def test_native_dialog_only_on_desktop(self):
        b = body('_on_game_menu_item')
        self.assertRegex(b, r'if id == 1:\n\t\tif _use_mobile_menu\(\):\n\t\t\t_render_mobile_menu_page\("confirm_reset"\)\n\t\t\tmobile_menu_panel.show\(\)\n\t\telse:\n\t\t\treset_dialog.popup_centered\(\)')

    def test_confirm_requires_visible_correct_page(self):
        b = body('_on_mobile_menu_action')
        self.assertRegex(b, r'elif id == 600:\n(?:[^\n]*\n)*?\t\tif mobile_menu_panel.visible and _mobile_menu_page == "confirm_reset":')
        self.assertIn('\t\t\t_confirm_reset_match()', b)

    def test_no_direct_reset_on_menu_selection(self):
        b = body('_on_game_menu_item')
        section = b.split('elif id == 3:')[0]
        self.assertNotIn('_confirm_reset_match()', section)

    def test_cancel_preserves_board_reserves_score(self):
        g = ResetModel(); old = (str(g.board),str(g.reserves),str(g.score),g.moves,g.round)
        g.open_menu(); g.action(1); g.action(-2)
        self.assertEqual((str(g.board),str(g.reserves),str(g.score),g.moves,g.round), old)
        self.assertFalse(g.visible)

    def test_hidden_confirm_is_ignored(self):
        g = ResetModel(); g.action(600)
        self.assertEqual(g.score,[1,2]);self.assertEqual(g.moves,1)

    def test_wrong_page_confirm_is_ignored(self):
        g = ResetModel();g.open_menu();g.action(600)
        self.assertEqual(g.score,[1,2]);self.assertEqual(g.moves,1)

    def test_confirm_resets_game(self):
        g=ResetModel();g.open_menu();g.action(1);g.action(600)
        self.assertEqual(g.score,[0,0]);self.assertEqual(g.moves,0)
        self.assertEqual(g.round,1);self.assertEqual(g.board,[[] for _ in range(9)])
        self.assertTrue(all(all(p) for p in g.reserves))

    def test_headless_fixture_is_opt_in_and_restores(self):
        b=body('_run_headless_mobile_reset_confirmation_smoke')
        self.assertIn('if not _use_mobile_menu():',b)
        self.assertIn('old_board := board_stacks.duplicate(true)',b)
        self.assertIn('board_stacks = old_board',b)
        self.assertIn('BLUE_SEA_MOBILE_RESET_CONFIRM_PASS',b)
        self.assertIn('_run_headless_mobile_reset_confirmation_smoke()',body('_run_headless_geometry_and_interaction_smoke'))

if __name__=='__main__':unittest.main()
