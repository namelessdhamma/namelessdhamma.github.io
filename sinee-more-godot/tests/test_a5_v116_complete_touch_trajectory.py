"""v116 offline gesture model + source contracts; Godot/physical touch NOT executed."""
from pathlib import Path
import importlib.util
import math

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")
INPUT = SOURCE.split("func _input(event: InputEvent) -> void:", 1)[1].split("\nfunc _process(", 1)[0]
spec = importlib.util.spec_from_file_location("geometry", ROOT / "tests/test_a5_v112_offcenter_edge_touch.py")
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


def center(world, cell):
    quad = geometry.BASE.cell_quad(world, cell)
    return tuple(sum(p[axis] for p in quad) / 4 for axis in (0, 1))


def path_result(world, start, samples, end, *, second_finger=False, started_on_board=True, max_drift=16):
    """Independent offline oracle: a move needs uninterrupted same-cell travel."""
    if not started_on_board or second_finger:
        return -1
    origin_cell = geometry.revised_touch(world, start)
    if origin_cell < 0:
        return -1
    for sample in samples + [end]:
        if math.dist(start, sample) > max_drift:
            return -1
        if geometry.revised_touch(world, sample) != origin_cell:
            return -1
    return origin_cell


def test_returning_swipes_cancel_all_seven_worlds():
    for world in range(7):
        for cell in range(8):
            a, b = center(world, cell), center(world, cell + 1)
            assert path_result(world, a, [b, a], a) == -1


def test_ordinary_same_cell_jitter_still_commits_all_seven_worlds():
    for world in range(7):
        for cell in range(9):
            x, y = center(world, cell)
            assert path_result(world, (x, y), [(x + 1, y), (x + 2, y + 1)], (x, y + 2)) == cell


def test_canceled_secondary_and_ui_to_board_do_not_commit():
    for world in range(7):
        a = center(world, 4)
        assert path_result(world, a, [], a, second_finger=True) == -1
        assert path_result(world, a, [], a, started_on_board=False) == -1


def test_source_tracks_full_primary_trajectory_and_permanent_cancel():
    assert "if event is InputEventScreenDrag:" in INPUT
    drag = INPUT.split("if event is InputEventScreenDrag:", 1)[1].split("if not (event is InputEventMouseButton):", 1)[0]
    # v125 additionally tracks secondary drags; preserve the original
    # primary-only trajectory/cancellation contract without a literal branch snapshot.
    assert "if drag.index != 0:" in drag
    assert "if not _touch_primary_active:" in drag
    assert drag.index("if drag.index != 0:") < drag.index("if not _touch_primary_active:")
    assert "drag.position.distance_squared_to(_touch_board_origin)" in drag
    assert "traversed_cell != _touch_board_cell" in drag
    assert "_cancel_pending_board_touch()" in drag
    cancel = SOURCE.split("func _cancel_pending_board_touch() -> void:", 1)[1].split("\nfunc ", 1)[0]
    assert "_touch_board_pending = false" in cancel
    assert "_touch_board_pending = true" not in drag
    assert "_on_cell_pressed(" not in drag


def test_release_rearms_echo_even_after_multitouch_or_ui_start():
    release = INPUT.split("if not touch.pressed:", 1)[1].split("# Track ALL primary touches", 1)[0]
    assert release.index("_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS") < release.index("if not should_commit:")
    assert release.index("_touch_primary_active = false") < release.index("if not should_commit:")
    assert "if was_board:" in release
    assert "if not should_commit:" in release
    press = INPUT.split("# Track ALL primary touches", 1)[1].split("if event is InputEventScreenDrag:", 1)[0]
    assert press.index("_touch_primary_active = true") < press.index("if perspective_tiles.size() != 9")
    assert press.index("_touch_board_started = false") < press.index("if touch_topbar.get_global_rect()")


def test_synthetic_mouse_filter_is_board_only_and_active_hold_safe():
    mouse = INPUT.split("if not (event is InputEventMouseButton):", 1)[1]
    held_guard = "if _touch_primary_active or not _touch_secondary_indices.is_empty():"
    assert mouse.index("topbar.get_global_rect().has_point(mouse.position)") < mouse.index(held_guard)
    assert mouse.index("PerspectiveGeometry.cell_at(current_world, mouse.position, perspective_rect)") < mouse.index(held_guard)
    assert mouse.index(held_guard) < mouse.index("_touch_multifinger_mouse_echo_deadline_msec > 0")
    assert "mouse.position.distance_squared_to(_touch_mouse_echo_position) <= 36.0" in mouse
    assert "mouse.position.distance_squared_to(_touch_mouse_echo_origin) <= 36.0" in mouse


def test_native_smoke_exercises_return_swipe_multitouch_and_ui_drag():
    smoke = SOURCE.split("func _run_headless_touch_emulation_smoke() -> void:", 1)[1].split("\nfunc _run_headless_reference_menu_smoke()", 1)[0]
    assert "InputEventScreenDrag.new()" in smoke
    assert "Return swipe must not commit" in smoke
    assert "Multitouch release mouse echo must not spend a rank" in smoke
    assert "UI-to-board synthetic mouse must not place a piece" in smoke
