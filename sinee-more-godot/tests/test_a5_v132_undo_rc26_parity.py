"""Offline source contracts for the RC2.6 Undo port.

These are NOT a Godot execution, device-touch test, or visual-parity pass.
The native handler test is BLUE_SEA_UNDO_RC26_PARITY_PASS in main.gd.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts' / 'main.gd').read_text(encoding='utf-8')
SCENE = (ROOT / 'main.tscn').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'(?m)^func {re.escape(name)}\([^\n]*', MAIN)
    assert match, name
    following = re.search(r'(?m)^func |^static func ', MAIN[match.end():])
    return MAIN[match.start():match.end() + (following.start() if following else len(MAIN))]


def test_accepted_web_feature_has_shared_implementation():
    assert 'var _undo_history: Array[Dictionary] = []' in MAIN
    assert 'func _undo_last_move() -> void:' in MAIN
    assert 'func _undo_steps() -> int:' in MAIN
    assert 'var moving_player := turn' in body('_on_primary')
    assert '"before": _match_snapshot()' in body('_on_primary')
    assert '"was_ai": ai_enabled and moving_player == 2' in body('_on_primary')


def test_undo_does_not_use_shadow_rules_or_direct_piece_pops():
    undo = body('_undo_last_move')
    assert '_apply_match_snapshot(previous, true)' in undo
    assert '_match_snapshot_valid(previous)' in undo
    assert 'board_stacks.pop' not in undo
    assert 'reserve_available.pop' not in undo
    assert '_save_match()' in undo


def test_ai_pair_only_when_recorded_ai_and_previous_human():
    steps = body('_undo_steps')
    assert 'bool(last["was_ai"])' in steps
    assert 'for index in range(_undo_history.size() - 1, -1, -1):' in steps
    assert 'int(entry["player"]) != 1' in steps
    assert 'return ai_tail + 1' in steps and 'return 1' in steps


def test_no_cross_round_or_restore_undo():
    assert '_undo_history.clear()' in body('_reset_round')
    assert 'if not preserve_undo:' in body('_apply_match_snapshot')
    assert '_undo_history.clear()' in body('_apply_match_snapshot')


def test_no_undo_entry_for_illegal_move():
    move = body('_on_primary')
    assert move.index('if not _is_legal_move(') < move.index('_undo_history.append(') < move.index('board_stacks[selected_cell].append(')


def test_desktop_and_mobile_menu_action_reuse_same_handler():
    assert '_mobile_menu_add("Отменить ход", 108, _undo_steps() == 0)' in body('_render_mobile_menu_page')
    popup = body('_populate_game_menu')
    assert 'popup.add_item("Отменить ход", 108)' in popup
    assert 'popup.set_item_disabled(popup.item_count - 1, _undo_steps() == 0)' in popup
    assert '_undo_last_move()' in body('_on_game_menu_item')
    assert '_on_game_menu_item(id)' in body('_on_mobile_menu_action')


def test_undo_never_creates_control_below_active_reserve():
    assert '"Отменить ход"' not in SCENE
    assert '"Отменить ход"' not in body('_prepare_world_shell')
    assert '"Отменить ход"' not in body('_refresh_surface')


def test_in_session_undo_does_not_change_snapshot_schema():
    assert '"undo_history"' not in body('_match_snapshot')
    assert '"undo_history"' not in body('_match_snapshot_valid')
    assert 'schema' in body('_match_snapshot_valid')


def test_native_smoke_is_opt_in_and_covers_all_worlds_and_rules():
    smoke = body('_run_headless_undo_parity_smoke')
    assert 'range(WorldVisuals.WORLDS.size())' in smoke
    assert 'for mode in ["C", "D", "CD"]' in smoke
    assert 'assert(game_over and winner == 1 and match_score[0] == 1)' in smoke
    assert 'assert(moves == 2 and _undo_steps() == 2)' in smoke
    assert 'BLUE_SEA_UNDO_RC26_PARITY_PASS' in smoke
    assert '_run_headless_undo_parity_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_canonical_assets_and_shared_ai_untouched_by_undo():
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
    assert 'PirateOpeningChoiceSurface' in MAIN
