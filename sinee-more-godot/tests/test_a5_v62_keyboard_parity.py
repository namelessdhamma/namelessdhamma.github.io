"""Offline structural and independent model checks; never label these Godot runtime PASS."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    m = re.search(rf'^func {re.escape(name)}\([^\n]*\) -> void:\n(.*?)(?=^func |^static func |\Z)', MAIN, re.M | re.S)
    assert m, name
    return m.group(1)


def test_keyboard_maps_both_digit_rows_and_all_arrows():
    s = body('_unhandled_key_input')
    assert 'event.keycode >= KEY_1 and event.keycode <= KEY_9' in s
    assert 'event.keycode >= KEY_KP_1 and event.keycode <= KEY_KP_9' in s
    for direction in ['LEFT', 'RIGHT', 'UP', 'DOWN']:
        assert f'KEY_{direction}:' in s
    for token in ['KEY_ENTER', 'KEY_KP_ENTER', 'KEY_SPACE', 'KEY_ESCAPE', 'KEY_M']:
        assert token in s


def test_keyboard_reuses_real_gameplay_handlers():
    assert '_on_reserve_pressed(turn, index)' in body('_select_keyboard_rank')
    assert '_on_primary()' in body('_unhandled_key_input')
    assert '_refresh_selection_feedback()' in body('_move_keyboard_cell')
    assert 'const AIOpponent = preload(' in MAIN
    assert 'func _run_headless_full_match_smoke() -> void:' in MAIN


def test_keyboard_does_not_steal_modal_or_ai_turn():
    assert '_modal_blocks_board_input()' in body('_unhandled_key_input')
    for helper in ['_select_keyboard_rank', '_move_keyboard_cell']:
        assert 'ai_enabled and turn == 2' in body(helper)
        assert 'game_over' in body(helper)
    assert 'if not game_over and not (ai_enabled and turn == 2):' in body('_unhandled_key_input')


def test_keyboard_grid_bounds_and_center():
    s = body('_move_keyboard_cell')
    assert 'selected_cell = 4' in s
    assert 'clampi(row + dy, 0, 2) * 3 + clampi(col + dx, 0, 2)' in s
    def step(cell, dx, dy):
        if cell < 0: return 4
        return max(0, min(2, cell // 3 + dy)) * 3 + max(0, min(2, cell % 3 + dx))
    for initial in range(-1, 9):
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            final = step(initial, dx, dy)
            assert 0 <= final < 9
            if initial >= 0:
                assert abs(final // 3 - initial // 3) <= 1
                assert abs(final % 3 - initial % 3) <= 1
    assert step(-1, 0, -1) == 4
    assert step(step(step(-1, 0, -1), -1, 0), 0, -1) == 0
    assert step(0, -1, 0) == 0


def test_selected_target_highlight_and_illegal_warning():
    s = body('_refresh_selection_feedback')
    assert 'var chosen_cell := can_select and selected_cell == i' in s
    assert 'perspective_legal_outlines[i].visible = legal or chosen_cell' in s
    assert 'Color("#ff716b") if has_piece and not legal else Color("#6be7e6")' in s


def test_keyboard_smoke_integrated_for_seven_worlds_three_modes():
    smoke = body('_run_headless_keyboard_navigation_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size())' in smoke
    assert 'for mode in ["C", "D", "CD"]' in smoke
    assert 'board_stacks[0][-1].rank' in smoke
    assert 'ai_enabled = true' in smoke
    assert 'BLUE_SEA_KEYBOARD_PARITY_PASS' in smoke
    assert '_run_headless_keyboard_navigation_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_no_new_engine_or_worlds():
    assert 'const CELL_NAMES: Array[String] = ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]' in MAIN
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'func _set_world(world: int) -> void:' in MAIN
    assert 'reserve_scroller = ScrollContainer.new()' in MAIN
