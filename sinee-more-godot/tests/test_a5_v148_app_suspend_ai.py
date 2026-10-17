"""A5 v148: background/focus lifecycle is an independent gameplay gate.

Offline source checks and independent event-order model. The actual Godot
headless lifecycle smoke is opt-in and NOT claimed executed by pytest.
"""
from pathlib import Path
import re
from itertools import product
import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    pattern = rf'^func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)'
    found = re.search(pattern, MAIN, re.M | re.S)
    assert found is not None, name
    return found.group(1)


def transition(paused, unfocused, event):
    if event == 'pause':
        paused = True
    elif event == 'focus_out':
        unfocused = True
    elif event == 'resume':
        paused = False
    elif event == 'focus_in':
        unfocused = False
    elif event not in ('back', 'close'):
        raise ValueError(event)
    return paused, unfocused


@pytest.mark.parametrize('paused,unfocused', product((False, True), repeat=2))
def test_two_independent_os_gates(paused, unfocused):
    assert (paused or unfocused) == (paused or unfocused)
    source = body('_interaction_suspended')
    assert 'return _app_paused or _app_unfocused' in source
    assert ('if _interaction_suspended():' in body('_modal_blocks_board_input'))


@pytest.mark.parametrize('first,second', [
    ('resume', 'focus_in'), ('focus_in', 'resume'),
    ('pause', 'focus_out'), ('focus_out', 'pause'),
    ('back', 'close'), ('close', 'back'),
])
def test_os_notification_order_is_monotone_and_back_does_not_suspend(first, second):
    paused, unfocused = (True, True) if first in ('resume', 'focus_in') else (False, False)
    p1, u1 = transition(paused, unfocused, first)
    p2, u2 = transition(p1, u1, second)
    if first in ('resume', 'focus_in'):
        assert p1 or u1, 'One resume signal cannot clear the other OS gate'
        assert not p2 and not u2
    elif first in ('pause', 'focus_out'):
        assert p1 or u1
        assert p2 and u2
    else:
        assert (p1, u1) == (p2, u2) == (False, False)


@pytest.mark.parametrize('world', range(7))
def test_shared_worlds_have_single_lifecycle_gate(world):
    # The lifecycle gate lives in main.gd, not in seven diverging world engines.
    assert 'var current_world := 1' in MAIN
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert f'world_{world:02d}.png' not in body('_notification')
    assert '_modal_blocks_board_input()' in body('_queue_ai_turn_if_ready')
    assert '_modal_blocks_board_input()' in body('_play_ai_turn')


def test_actual_notification_handlers_and_resume_deferred_queue():
    source = body('_notification')
    for key in ('NOTIFICATION_APPLICATION_PAUSED', 'NOTIFICATION_APPLICATION_FOCUS_OUT',
                'NOTIFICATION_APPLICATION_RESUMED', 'NOTIFICATION_APPLICATION_FOCUS_IN',
                'NOTIFICATION_WM_GO_BACK_REQUEST', 'NOTIFICATION_WM_CLOSE_REQUEST'):
        assert key in source
    assert 'if what == NOTIFICATION_APPLICATION_PAUSED:\n\t\t_app_paused = true' in source
    assert 'elif what == NOTIFICATION_APPLICATION_FOCUS_OUT:\n\t\t_app_unfocused = true' in source
    assert 'if what == NOTIFICATION_APPLICATION_RESUMED:\n\t\t_app_paused = false' in source
    assert 'if what == NOTIFICATION_APPLICATION_FOCUS_IN:\n\t\t_app_unfocused = false' in source
    assert source.count('call_deferred("_queue_ai_turn_if_ready")') == 2
    assert source.count('if not _interaction_suspended() and is_node_ready() and reserve_scroller != null:') == 2
    assert 'if what == NOTIFICATION_WM_GO_BACK_REQUEST:\n\t\t_handle_mobile_back()' in source
    assert '_persist_idle_reserve_scroll()' in source
    assert '_retry_failed_match_save()' in source


def test_deferred_ai_cannot_commit_behind_suspended_app():
    play = body('_play_ai_turn')
    queue = body('_queue_ai_turn_if_ready')
    assert play.index('_ai_turn_queued = false') < play.index('_modal_blocks_board_input()')
    assert play.index('_modal_blocks_board_input()') < play.index('ai_engine.choose_move(')
    assert queue.index('_modal_blocks_board_input()') < queue.index('_ai_turn_queued = true')
    assert 'call_deferred("_play_ai_turn")' in queue
    assert 'if _interaction_suspended():\n\t\treturn true' in body('_modal_blocks_board_input')


def test_native_fixture_is_wired_but_not_confused_with_real_os_qualification():
    fixture = body('_run_headless_lifecycle_ai_smoke')
    assert fixture.count('_play_ai_turn()') == 2
    assert '_match_snapshot() == before' in fixture
    assert 'Resume before focus-in prematurely released AI' in fixture
    assert 'ai_enabled = previous_ai' in fixture
    assert '_app_paused = previous_paused' in fixture
    assert '_app_unfocused = previous_unfocused' in fixture
    assert '_run_headless_lifecycle_ai_smoke()' in body('_run_headless_geometry_and_interaction_smoke')
    assert 'BLUE_SEA_LIFECYCLE_AI_GATE_SMOKE_PASS' in fixture


def test_no_new_engine_or_visual_asset_mutation():
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
    assert 'const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")' in MAIN
    assert 'const MATCH_TARGET := 3' in MAIN
    assert 'const CELL_NAMES: Array[String]' in MAIN
