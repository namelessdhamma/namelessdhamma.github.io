"""A5 v67: source-contract checks; native Godot smoke remains a separate gate."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def _body(name):
    pattern = rf'(?ms)^func {re.escape(name)}\([^\n]*\) -> void:\n(.*?)(?=^func |^static func |\Z)'
    match = re.search(pattern, MAIN)
    assert match, f'missing {name}'
    return match.group(1)


def test_invalid_reserve_handler_clears_selection_and_signals_error():
    body = _body('_reject_reserve_selection')
    assert '_on_secondary()' in body
    assert '_play_feedback("invalid")' in body
    assert '_update_status(reason)' in body


def test_guard_checks_bounds_before_array_index():
    body = _body('_on_reserve_pressed')
    bounds = body.index('if player < 1 or player > 2 or index < 0 or index >= 9:')
    indexed = body.index('reserve_available[player - 1][index]')
    assert bounds < indexed
    assert '_reject_reserve_selection("invalid reserve index")' in body


def test_all_rejected_gui_reserve_routes_clear_stale_selection():
    body = _body('_on_reserve_pressed')
    for message in ['invalid reserve index', 'AI reserve is not human-controllable',
                    'wrong player reserve', 'piece already played']:
        assert f'_reject_reserve_selection("{message}")' in body
    assert 'selected_reserve = index' in body


def test_actual_godot_smoke_is_wired_into_headless_suite():
    suite = _body('_run_headless_geometry_and_interaction_smoke')
    smoke = _body('_run_headless_reserve_invalid_guard_smoke')
    assert '_run_headless_reserve_invalid_guard_smoke()' in suite
    for route in ['_on_reserve_pressed(1, 0)', '_on_reserve_pressed(2, 1)',
                  '_on_reserve_pressed(1, 9)', '_on_reserve_pressed(0, 0)']:
        assert route in smoke
    assert 'no_ghost_move' in smoke


def test_shared_engine_and_canonical_bindings_remain_intact():
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
    assert 'const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")' in MAIN
    assert 'func _play_ai_turn()' in MAIN
    assert 'func _run_headless_full_match_smoke()' in MAIN
