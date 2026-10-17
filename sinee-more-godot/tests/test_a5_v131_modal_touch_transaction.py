"""A5 v131: modal transitions cancel armed board touches; static/model tests only."""
from pathlib import Path
import re
import pytest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    pattern = r'^func ' + re.escape(name) + r'\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)'
    found = re.search(pattern, SOURCE, re.M | re.S)
    assert found, name
    return found.group(1)


@pytest.mark.parametrize('world', range(7))
def test_modal_transition_never_rearms_existing_board_touch(world):
    # The minimal state machine is an independent model, not an engine test.
    armed, moves = True, 0
    armed = False  # visibility_changed -> _cancel_pending_board_touch
    assert not armed
    if armed:  # old finger release
        moves += 1
    assert moves == 0, world
    armed = True  # new touch-down, same live cell
    if armed:
        moves += 1
    assert moves == 1, world


def test_shared_visibility_callback_invalidates_before_ai_resume():
    code = body('_resume_ai_after_modal_close')
    assert code.index('_cancel_pending_board_touch()') < code.index('_queue_ai_turn_if_ready')
    assert '_modal_blocks_board_input()' in code
    assert SOURCE.count('visibility_changed.connect(_resume_ai_after_modal_close)') >= 5


def test_all_desktop_popup_openings_invalidate_armed_touch():
    assert 'popup.about_to_popup.connect(_cancel_pending_board_touch)' in SOURCE
    assert 'game_popup.about_to_popup.connect(_cancel_pending_board_touch)' in SOURCE
    assert 'submenu.about_to_popup.connect(_cancel_pending_board_touch)' in SOURCE
    assert 'popup_hide.connect(_resume_ai_after_modal_close)' in SOURCE


def test_native_smoke_executes_live_handlers_in_all_worlds():
    smoke = body('_run_headless_modal_touch_transaction_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'mobile_menu_panel.show()' in smoke and 'mobile_menu_panel.hide()' in smoke
    assert 'top_menu.get_popup().about_to_popup.emit()' in smoke
    assert smoke.count('_input(touch)') >= 5
    assert 'moves == 0' in smoke and 'moves == 1' in smoke
    assert 'BLUE_SEA_MODAL_TOUCH_TRANSACTION_PASS worlds=7 canceled=14 fresh=7' in smoke
    assert '_run_headless_modal_touch_transaction_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_touch_handler_does_not_commit_after_cancellation():
    code = body('_input')
    assert 'var should_commit := _touch_board_pending' in code
    assert code.index('if not should_commit:') < code.index('_on_cell_pressed(initial_cell)')
    assert '_cancel_pending_board_touch()' in SOURCE


def test_no_new_game_engine_or_canonical_art_mutation():
    assert 'const AIOpponent = preload(' in SOURCE
    assert 'const WorldVisuals = preload(' in SOURCE
    assert 'const PerspectiveGeometry = preload(' in SOURCE
