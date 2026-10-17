"""Offline structural/model checks; native Godot smoke is deliberately not claimed here."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()


def section(begin, end):
    # The v156 reserve-scroll intent observer legitimately added a second
    # ScreenTouch/ScreenDrag branch in _track_reserve_scroll_intent(). These
    # tests target the BOARD gesture handler only; global string uniqueness
    # incorrectly failed while the actual _input guard remained unchanged.
    scope = MAIN
    if begin in ('if event is InputEventScreenTouch:', 'if event is InputEventScreenDrag:'):
        scope = MAIN.split('func _input(event: InputEvent) -> void:', 1)[1].split('func _process(', 1)[0]
    assert scope.count(begin) == 1, begin
    assert scope.count(end) == 1, end
    return scope.split(begin, 1)[1].split(end, 1)[0]


def old_mouse_accepts_ghost(primary_held, secondary_held, mouse_near_primary, mouse_near_last_secondary):
    # v124 checked only near primary touch origin or last secondary press;
    # moving the second finger >6 px made its emulated click appear genuine.
    return not ((primary_held or secondary_held) and (mouse_near_primary or mouse_near_last_secondary))


def new_mouse_accepts_ghost(primary_held, secondary_held, global_echo_active, local_echo_active):
    return not (primary_held or secondary_held or global_echo_active or local_echo_active)


def test_01_previous_multifinger_drag_exposes_real_board_commit_risk():
    assert old_mouse_accepts_ghost(True, True, False, False)
    assert not new_mouse_accepts_ghost(True, True, False, False)


def test_02_secondary_drag_refreshes_both_echo_deadlines():
    body = section('if event is InputEventScreenDrag:', 'if not (event is InputEventMouseButton):')
    assert 'if drag.index != 0:' in body
    assert 'if _touch_secondary_indices.has(drag.index):' in body
    assert '_touch_mouse_echo_position = drag.position' in body
    assert '_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec' in body
    assert body.index('if drag.index != 0:') < body.index('if not _touch_primary_active:')


def test_03_held_touch_blocks_board_mouse_independent_of_position():
    body = section('if not (event is InputEventMouseButton):', 'func _process(')
    assert 'if _touch_primary_active or not _touch_secondary_indices.is_empty():' in body
    assert body.index('if _touch_primary_active or not _touch_secondary_indices.is_empty():') < body.index('var frame := Engine.get_process_frames()')
    assert 'get_viewport().set_input_as_handled()' in body


def test_04_secondary_touch_press_and_release_rearm_bounded_guard():
    body = section('if event is InputEventScreenTouch:', 'if event is InputEventScreenDrag:')
    assert 'if touch.index != 0:' in body
    assert '_touch_secondary_indices.erase(touch.index)' in body
    assert '_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec' in body


def test_05_after_release_guard_catches_nonlocal_delayed_echo():
    body = section('if not (event is InputEventMouseButton):', 'func _process(')
    assert '_touch_multifinger_mouse_echo_deadline_msec > 0' in body
    assert 'Time.get_ticks_msec() <= _touch_multifinger_mouse_echo_deadline_msec' in body
    assert body.index('_touch_multifinger_mouse_echo_deadline_msec > 0') < body.index('mouse.position.distance_squared_to(_touch_mouse_echo_position)')
    assert not new_mouse_accepts_ghost(False, False, True, False)
    assert new_mouse_accepts_ghost(False, False, False, False)


def test_06_only_board_mouse_events_get_global_suppression():
    body = section('if not (event is InputEventMouseButton):', 'func _process(')
    assert body.index('var index := PerspectiveGeometry.cell_at(') < body.index('if _touch_primary_active or not _touch_secondary_indices.is_empty():')
    assert 'if topbar.get_global_rect().has_point(mouse.position) or dock.get_global_rect().has_point(mouse.position):' in body


def test_07_native_opt_in_smoke_seven_worlds_and_real_mouse_recovery():
    smoke = section('func _run_headless_secondary_drag_mouse_echo_smoke()', 'func _run_headless_reference_menu_smoke()')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'secondary_drag.index = 1' in smoke
    assert '_input(secondary_drag)' in smoke
    assert '_input(mouse)' in smoke
    assert 'moves == 0' in smoke
    assert 'moves == 1' in smoke
    assert 'BLUE_SEA_SECONDARY_DRAG_ECHO_PASS' in smoke
    suite = section('func _run_headless_geometry_and_interaction_smoke()', 'func _run_headless_full_match_smoke()')
    assert suite.count('_run_headless_secondary_drag_mouse_echo_smoke()') == 1


def test_08_engine_test_remains_opt_in_no_normal_launch_mutation():
    ready = section('func _ready()', 'func _prepare_world_shell()')
    assert '"smoke":' in ready and 'call_deferred("_run_headless_geometry_and_interaction_smoke")' in ready
    assert '_run_headless_secondary_drag_mouse_echo_smoke' not in ready
    assert '"--nd-run-smoke" in args' in MAIN


def test_09_touch_guard_is_bounded_and_clears_after_real_mouse_recovery():
    assert 'const TOUCH_MOUSE_ECHO_MS := 350' in MAIN
    smoke = section('func _run_headless_secondary_drag_mouse_echo_smoke()', 'func _run_headless_reference_menu_smoke()')
    assert '_touch_multifinger_mouse_echo_deadline_msec = 0' in smoke
    assert '_touch_mouse_echo_deadline_msec = 0' in smoke


def test_10_lifecycle_focus_reset_prevents_delayed_ghost():
    lifecycle = section('func _notification(what: int)', 'func _handle_mobile_back()')
    assert '_touch_secondary_indices.clear()' in lifecycle
    assert '_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec' in lifecycle
