"""v118: offline source/transition checks; not native Godot or physical touch QA."""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)', SOURCE, re.M | re.S)
    assert match, name
    return match.group(1)


def token(*, world=0, rule='CD', turn=1, moves=0, round=1, rank=0, cell=-1, ai=False, blocked=0, score=(0,0)):
    return (world, rule, turn, moves, round, rank, cell, ai, blocked, tuple(score))


def would_commit(start, end, *, same_cell=True, unbroken=True):
    return unbroken and same_cell and start == end


@pytest.mark.parametrize('changed', ['world', 'rule', 'turn', 'moves', 'round', 'rank', 'cell', 'ai', 'blocked', 'score'])
def test_changed_live_context_cancels_in_all_seven_worlds(changed):
    alternatives = dict(world=3, rule='D', turn=2, moves=1, round=2, rank=8,
                        cell=4, ai=True, blocked=2, score=(1,0))
    for world in range(7):
        base = dict(world=world)
        after = dict(base)
        after[changed] = alternatives[changed] if changed != 'world' else (world+1)%7
        assert not would_commit(token(**base), token(**after))


def test_unchanged_state_still_allows_same_cell_release_all_worlds():
    for world in range(7):
        for rank in range(9):
            state = token(world=world, rank=rank)
            assert would_commit(state, state)
            assert not would_commit(state, state, same_cell=False)
            assert not would_commit(state, state, unbroken=False)


def test_production_token_contains_full_live_context():
    code = body('_touch_board_state_token')
    for name in ['current_world', 'current_rule', 'turn', 'moves', 'round_number',
                 'selected_reserve', 'selected_cell', 'ai_enabled', 'blocked_player',
                 'match_score.duplicate()']:
        assert name in code


def test_release_uses_press_token_before_commit_and_clears_it():
    code = body('_input')
    release = code.split('if not touch.pressed:',1)[1].split('# Track ALL primary touches',1)[0]
    assert release.index('var initial_state := _touch_board_state_at_press.duplicate(true)') < release.index('_touch_board_state_at_press.clear()')
    assert release.index('initial_state != _touch_board_state_token()') < release.index('_on_cell_pressed(initial_cell)')
    assert 'if not should_commit:' in release and 'if initial_state.is_empty()' in release
    assert release.count('_on_cell_pressed(initial_cell)') == 1


def test_board_press_arms_token_only_after_cell_hit():
    code = body('_input')
    press = code.split('# Track ALL primary touches',1)[1].split('if event is InputEventScreenDrag:',1)[0]
    assert press.index('if touch_index < 0:') < press.index('_touch_board_state_at_press = _touch_board_state_token()')
    assert press.index('_touch_board_state_at_press.clear()') < press.index('if perspective_tiles.size() != 9')


def test_multitouch_and_drag_cancel_transaction():
    code = body('_input')
    assert '_cancel_pending_board_touch()' in code.split('if touch.index != 0:',1)[1].split('if not touch.pressed:',1)[0]
    drag = code.split('if event is InputEventScreenDrag:',1)[1].split('if not (event is InputEventMouseButton):',1)[0]
    assert 'if drifted or traversed_cell != _touch_board_cell:' in drag
    assert '_cancel_pending_board_touch()' in drag
    cancel = body('_cancel_pending_board_touch')
    assert '_touch_board_pending = false' in cancel and '_touch_board_state_at_press.clear()' in cancel


def test_rotation_and_suspend_cancel_without_altering_match():
    for name in ['_sync_orientation_gate', '_notification']:
        assert '_cancel_pending_board_touch()' in body(name)
    assert '_touch_primary_active = false' in body('_notification')
    assert '_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS' in body('_notification')
    assert '_match_snapshot()' not in body('_cancel_pending_board_touch')


def test_canceled_release_still_guards_synthetic_mouse_echo():
    release = body('_input').split('if not touch.pressed:',1)[1].split('var was_board',1)[0]
    assert release.index('_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS') < release.index('return')


def test_native_smoke_is_opt_in_and_seven_world_shared_input():
    smoke = body('_run_headless_touch_state_binding_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert '_input(touch)' in smoke and '_on_reserve_pressed(1, 1)' in smoke
    assert '_set_world((world + 1) % WorldVisuals.WORLDS.size())' in smoke
    assert 'BLUE_SEA_TOUCH_STATE_BINDING_PASS' in smoke
    assert '_run_headless_touch_state_binding_smoke()' in body('_run_headless_geometry_and_interaction_smoke')
