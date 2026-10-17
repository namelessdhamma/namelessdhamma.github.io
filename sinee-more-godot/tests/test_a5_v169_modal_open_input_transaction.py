"""A5 v169: opening a modal invalidates a held board/reserve transaction.

Static integration assertions and a separate model oracle. Real Godot smoke
is registered but is NOT counted as executed without the native engine.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    m = re.search(rf'^func {re.escape(name)}\(', SRC, re.M)
    assert m, name
    tail = SRC[m.start():]
    next_fn = re.search(r'\n(?:func |static func )', tail)
    return tail[:next_fn.start()] if next_fn else tail


class ModalInputModel:
    def __init__(self):
        self.board = [[] for _ in range(9)]
        self.reserves = [[True] * 9 for _ in range(2)]
        self.turn, self.moves, self.score = 1, 0, [0, 0]
        self.rank, self.cell, self.held_board, self.held_reserve = 8, -1, True, False
        self.block_until, self.scroll_epoch, self.modal = 0, 5, False

    def open_modal(self, now=1000):
        self.held_board = False
        if self.held_reserve:
            self.block_until = now + 350
        self.held_reserve = False
        self.scroll_epoch += 1
        self.modal = True

    def close_modal(self):
        self.modal = False

    def late_board_release(self):
        if self.held_board and not self.modal and self.rank >= 0:
            self.moves += 1
            self.reserves[self.turn - 1][self.rank] = False
        self.held_board = False

    def late_gui_click(self, now=1001):
        if not self.modal and now > self.block_until:
            self.rank = 8

    def fresh_rank_press(self):
        self.block_until = 0
        self.rank = 8


class ModalOpenTransactionTests(unittest.TestCase):
    def test_old_board_touch_cannot_commit_after_modal_close(self):
        for world in range(7):
            m = ModalInputModel()
            before = (m.board[:], [r[:] for r in m.reserves], m.score[:], m.turn, m.moves)
            m.open_modal(); m.close_modal(); m.late_board_release()
            self.assertEqual((m.board, m.reserves, m.score, m.turn, m.moves), before, world)
            self.assertEqual(m.rank, 8, world)

    def test_late_reserve_gui_rejected_and_new_tap_works(self):
        for world in range(7):
            m = ModalInputModel()
            m.rank = -1
            m.held_reserve = True
            m.open_modal(); m.close_modal(); m.late_gui_click()
            self.assertEqual(m.rank, -1, world)
            m.fresh_rank_press()
            self.assertEqual(m.rank, 8, world)

    def test_modal_invalidates_scroll_but_never_mutates_game(self):
        m = ModalInputModel()
        m.open_modal()
        self.assertEqual(m.scroll_epoch, 6)
        self.assertEqual((m.moves, m.score, m.reserves[0][8]), (0, [0, 0], True))

    def test_live_helper_invalidates_only_transient_state(self):
        b = body('_invalidate_input_on_modal_open')
        for token in ('_cancel_pending_board_touch()', '_reserve_touch_active',
                      '_reserve_pointer_active', '_reserve_touch_block_until_msec',
                      '_reserve_pointer_block_until_msec', '_reserve_scroll_user_epoch += 1'):
            self.assertIn(token, b)
        for forbidden in ('selected_reserve =', 'selected_cell =', 'board_stacks =',
                          'reserve_available =', 'match_score =', '_reset_round(',
                          '_on_primary(', '_set_world('):
            self.assertNotIn(forbidden, b)

    def test_mobile_menu_and_world_picker_invoke_helper_before_show(self):
        for fn in ('_open_mobile_menu', '_open_mobile_worlds'):
            b = body(fn)
            self.assertLess(b.index('_invalidate_input_on_modal_open()'),
                            b.index('mobile_menu_panel.show()'))

    def test_desktop_popups_and_dialogs_use_same_boundary(self):
        shell = body('_prepare_world_shell')
        for token in ('popup.about_to_popup.connect(_invalidate_input_on_modal_open)',
                      'game_popup.about_to_popup.connect(_invalidate_input_on_modal_open)',
                      'submenu.about_to_popup.connect(_invalidate_input_on_modal_open)'):
            self.assertIn(token, shell)
        menu = body('_on_game_menu_item')
        for token in ('reset_dialog.popup_centered()', 'rules_dialog.popup_centered_ratio(0.90)',
                      'show_opening_choice'):
            self.assertIn(token, menu)
        self.assertEqual(menu.count('_invalidate_input_on_modal_open()'), 3)

    def test_native_fixture_is_wired_for_seven_worlds_and_both_inputs(self):
        b = body('_run_headless_modal_open_input_transaction_smoke')
        for token in ('for world in range(WorldVisuals.WORLDS.size()):',
                      '_open_mobile_menu()', '_open_mobile_worlds()',
                      '_input(held)', '_on_reserve_gui_pressed(turn, 8)',
                      'board_stacks == before_board', 'reserve_available == before_reserves',
                      'BLUE_SEA_MODAL_OPEN_INPUT_TRANSACTION_PASS'):
            self.assertIn(token, b)
        self.assertIn('_run_headless_modal_open_input_transaction_smoke()',
                      body('_run_headless_geometry_and_interaction_smoke'))

    def test_shared_engine_and_pirate_controller_preserved(self):
        self.assertEqual(SRC.count('func _is_legal_move('), 1)
        self.assertEqual(SRC.count('func _winning_line('), 1)
        self.assertEqual(SRC.count('func _set_world('), 1)
        self.assertIn('PirateOpeningCampaign', (ROOT / 'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
