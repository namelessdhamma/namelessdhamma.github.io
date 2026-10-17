"""A5 v168: a world skin change must close the old touch transaction.

Source wiring and a separate portable state-machine oracle only. Actual
Godot fixture is registered but requires native Godot execution.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    m = re.search(rf'^func {re.escape(name)}\(', SRC, re.M)
    assert m, name
    tail = SRC[m.start():]
    next_fn = re.search(r'\n(?:func |static func )', tail)
    return tail[:next_fn.start()] if next_fn else tail


class WorldInputModel:
    def __init__(self):
        self.world = 0
        self.board = [[] for _ in range(9)]
        self.reserves = [[True]*9 for _ in range(2)]
        self.score = [0, 0]
        self.turn = 1
        self.moves = 0
        self.ai = True
        self.selected_rank = 8
        self.selected_cell = -1
        self.held_board = False
        self.held_reserve = False
        self.block_until = 0
        self.scroll_epoch = 5

    def switch(self, new_world, now=1000):
        if not 0 <= new_world < 7:
            return
        if new_world != self.world:
            self.held_board = False
            if self.held_reserve:
                self.block_until = now + 350
            self.held_reserve = False
            self.scroll_epoch += 1
            self.selected_rank = -1
            self.selected_cell = -1
        self.world = new_world

    def late_release(self, now=1001):
        if self.held_board and self.selected_rank >= 0:
            self.moves += 1
            self.reserves[self.turn - 1][self.selected_rank] = False
        self.held_board = False

    def late_gui(self, now=1001):
        if now <= self.block_until:
            return
        self.selected_rank = 8

    def fresh_tap(self):
        self.block_until = 0
        self.selected_rank = 8


class WorldSwitchTransactionTests(unittest.TestCase):
    def test_board_held_release_never_spends_piece_in_any_world(self):
        for world in range(7):
            m = WorldInputModel(); m.world = world; m.held_board = True
            old = (m.board[:], [x[:] for x in m.reserves], m.score[:], m.turn, m.moves, m.ai)
            m.switch((world+1) % 7)
            m.late_release()
            self.assertEqual((m.board, m.reserves, m.score, m.turn, m.moves, m.ai), old)
            self.assertEqual((m.selected_rank, m.selected_cell), (-1, -1))

    def test_delayed_old_reserve_click_is_rejected_and_new_tap_works(self):
        for world in range(7):
            m = WorldInputModel(); m.world = world; m.held_reserve = True
            m.switch((world+1) % 7)
            m.late_gui()
            self.assertEqual(m.selected_rank, -1)
            m.fresh_tap()
            self.assertEqual(m.selected_rank, 8)

    def test_invalid_and_same_world_selection_are_not_mutations(self):
        m = WorldInputModel(); m.held_board = True
        for new_world in (-1, 7, 0):
            m.switch(new_world)
            self.assertTrue(m.held_board)
            self.assertEqual(m.selected_rank, 8)
            self.assertEqual(m.scroll_epoch, 5)

    def test_world_change_invalidates_deferred_scroll(self):
        for world in range(7):
            m = WorldInputModel(); m.world = world
            epoch = m.scroll_epoch
            m.switch((world+1) % 7)
            self.assertGreater(m.scroll_epoch, epoch)

    def test_actual_set_world_cancels_before_mutating_world(self):
        b = body('_prepare_world_switch_input')
        self.assertIn('world == current_world', b)
        for token in ('_cancel_pending_board_touch()', '_reserve_touch_block_until_msec',
                      '_reserve_pointer_block_until_msec', '_reserve_touch_active = false',
                      '_reserve_pointer_active = false', '_reserve_scroll_user_epoch += 1',
                      'selected_reserve = -1', 'selected_cell = -1'):
            self.assertIn(token, b)
        self.assertNotIn('board_stacks =', b)
        self.assertNotIn('reserve_available =', b)
        self.assertNotIn('match_score =', b)
        self.assertNotIn('_reset_round(', b)
        self.assertNotIn('_on_primary(', b)

    def test_actual_world_switch_retains_live_shared_skin_update(self):
        b = body('_set_world')
        for token in ('world_visuals.apply_world(self, current_world)',
                      '_refresh_surface()', '_refresh_perspective_layer()',
                      '_save_preferences()'):
            self.assertIn(token, b)
        self.assertEqual(SRC.count('func _set_world('), 1)
        self.assertIn('popup.id_pressed.connect(_prepare_world_switch_input)', body('_prepare_world_shell'))
        self.assertIn('popup.id_pressed.connect(_set_world)', body('_prepare_world_shell'))
        self.assertIn('_prepare_world_switch_input(id - 500)', body('_on_mobile_menu_action'))
        self.assertIn('_set_world(id - 500)', body('_on_mobile_menu_action'))
        self.assertEqual(SRC.count('func _on_primary('), 1)

    def test_native_fixture_is_registered_for_all_seven_worlds(self):
        b = body('_run_headless_world_switch_input_transaction_smoke')
        for token in ('for world in range(WorldVisuals.WORLDS.size()):',
                      'InputEventScreenTouch.new()', '_input(touch)',
                      '_prepare_world_switch_input(next_world)', '_set_world(next_world)', '_on_reserve_gui_pressed(turn, 8)',
                      'board_stacks == board_before', 'reserve_available == reserves_before',
                      'BLUE_SEA_WORLD_SWITCH_INPUT_TRANSACTION_PASS'):
            self.assertIn(token, b)
        self.assertIn('_run_headless_world_switch_input_transaction_smoke()',
                      body('_run_headless_geometry_and_interaction_smoke'))

    def test_protected_d2_and_pirate_engine_still_shared(self):
        self.assertIn('const AIOpponent = preload(', SRC)
        self.assertIn('const WorldVisuals = preload(', SRC)
        self.assertIn('func _is_legal_move(', SRC)
        self.assertIn('func _winning_line(', SRC)
        self.assertIn('func _play_ai_turn(', SRC)
        self.assertIn('PirateOpeningCampaign', (Path(__file__).resolve().parents[1] / 'project.godot').read_text())


if __name__ == '__main__':
    unittest.main()
