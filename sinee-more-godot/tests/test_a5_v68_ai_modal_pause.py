"""Offline regression for the shared AI modal-pause scheduling contract.

Static/model checks are NOT substitutes for executing the Godot fixture.
"""
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd'
SOURCE = MAIN.read_text()


def function(name):
    start = SOURCE.index(f'func {name}(')
    end = SOURCE.find('\nfunc ', start + 1)
    if end < 0:
        end = len(SOURCE)
    return SOURCE[start:end]


def test_only_one_deferred_ai_call_site():
    assert SOURCE.count('call_deferred("_play_ai_turn")') == 1
    assert 'var _ai_turn_queued := false' in SOURCE
    assert 'if _ai_turn_queued or not ai_enabled or game_over or turn != 2 or _modal_blocks_board_input():' in function('_queue_ai_turn_if_ready')


def test_ai_checks_modal_again_at_execution():
    f = function('_play_ai_turn')
    assert '_ai_turn_queued = false' in f
    assert 'turn != 2 or _modal_blocks_board_input()' in f
    assert 'ai_engine.choose_move' in f
    assert '_on_primary()' in f


def test_auto_resume_in_existing_process_loop():
    f = function('_process')
    assert f.index('_sync_orientation_gate()') < f.index('_queue_ai_turn_if_ready()')
    assert '_queue_ai_turn_if_ready()' in function('_toggle_ai')
    assert '_queue_ai_turn_if_ready()' in function('_on_primary')
    assert '_queue_ai_turn_if_ready()' in function('_reset_round')


def test_engine_fixture_is_opt_in_and_checks_real_ai_entrypoint():
    smoke = function('_run_headless_geometry_and_interaction_smoke')
    assert '_run_headless_ai_modal_guard_smoke()' in smoke
    f = function('_run_headless_ai_modal_guard_smoke')
    assert 'mobile_menu_panel.show()' in f
    assert 'assert(moves == 0 and turn == 2' in f
    assert 'mobile_menu_panel.hide()' in f
    assert 'assert(moves == 1 and turn == 1' in f


def test_no_duplicate_queue_or_hidden_move_in_small_model():
    # An independent state-transition model, not a Godot execution.
    for blocked_at_queue, blocked_at_execution in [(False, False), (False, True), (True, False), (True, True)]:
        queued = False
        moves = 0
        def queue(blocked):
            nonlocal queued
            if not queued and not blocked and moves == 0:
                queued = True
        queue(blocked_at_queue)
        queue(blocked_at_queue)
        assert queued == (not blocked_at_queue)
        if queued:
            queued = False
            if not blocked_at_execution:
                moves += 1
        assert moves == int(not blocked_at_queue and not blocked_at_execution)
        queue(False)
        if queued:
            queued = False
            moves += 1
        assert moves == 1
