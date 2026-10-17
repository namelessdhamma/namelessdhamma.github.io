"""A5 v115 offline source/gesture oracle; native Godot and real touch NOT RUN."""
from pathlib import Path
import importlib.util
import math

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")
MOD = ROOT / "tests/test_a5_v112_offcenter_edge_touch.py"
spec = importlib.util.spec_from_file_location("v112_geometry", MOD)
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


def gesture(world, start, end, *, secondary=False, blocked=False, threshold=16.0):
    """Independent Python geometry/gesture model, not GDScript execution."""
    if secondary or blocked or math.dist(start, end) > threshold:
        return -1
    initial = geometry.revised_touch(world, start)
    released = geometry.revised_touch(world, end)
    return initial if initial >= 0 and initial == released else -1


def center(world, cell):
    quad = geometry.BASE.cell_quad(world, cell)
    return (sum(p[0] for p in quad) / 4, sum(p[1] for p in quad) / 4)


def test_all_seven_worlds_same_cell_taps_commit_in_oracle():
    for world in range(7):
        for cell in range(9):
            c = center(world, cell)
            assert gesture(world, c, (c[0] + 1, c[1] + 1)) == cell


def test_all_seven_worlds_drag_to_other_cell_is_canceled():
    for world in range(7):
        for cell in range(8):
            assert gesture(world, center(world, cell), center(world, cell + 1)) == -1


def test_multitouch_and_modal_cancel_every_world():
    for world in range(7):
        p = center(world, 4)
        assert gesture(world, p, p, secondary=True) == -1
        assert gesture(world, p, p, blocked=True) == -1


def test_short_drift_and_long_drift():
    for world in range(7):
        p = center(world, 4)
        assert gesture(world, p, (p[0] + 4, p[1] + 4)) == 4
        assert gesture(world, p, (p[0] + 17, p[1])) == -1


def test_source_only_commits_touch_on_release():
    source = SOURCE.split("func _input(event: InputEvent) -> void:", 1)[1].split("\nfunc _process(", 1)[0]
    assert "if not touch.pressed:" in source
    press_branch = source.split("# Track ALL primary touches", 1)[1].split("\n\tif event is InputEventScreenDrag:", 1)[0]
    assert "_on_cell_pressed(" not in press_branch
    release_branch = source.split("if not touch.pressed:", 1)[1].split("# Track ALL primary touches", 1)[0]
    assert release_branch.count("_on_cell_pressed(initial_cell)") == 1
    assert "if released_cell != initial_cell:" in release_branch
    assert "distance_squared_to(origin) > max_drift * max_drift" in release_branch


def test_mouse_echo_suppression_covers_both_endpoints():
    source = SOURCE.split("func _input(event: InputEvent) -> void:", 1)[1].split("\nfunc _process(", 1)[0]
    assert "_touch_mouse_echo_origin" in source
    assert "_touch_mouse_echo_position" in source
    assert "TOUCH_MOUSE_ECHO_MS := 350" in SOURCE
    assert "mouse.position.distance_squared_to(_touch_mouse_echo_origin) <= 36.0" in source
    assert "mouse.position.distance_squared_to(_touch_mouse_echo_position) <= 36.0" in source
    assert "_last_board_press_kind == \"touch\"" in source


def test_real_gameplay_and_native_smoke_are_wired():
    assert "_run_headless_touch_emulation_smoke()" in SOURCE
    assert "BLUE_SEA_TOUCH_RELEASE_GATE_PASS" in SOURCE
    assert "_on_cell_pressed(initial_cell)" in SOURCE
    assert "func _on_primary() -> void:" in SOURCE
    assert "func _play_ai_turn() -> void:" in SOURCE


def test_touch_does_not_bypass_modal_or_ai_turn():
    source = SOURCE.split("func _input(event: InputEvent) -> void:", 1)[1].split("\nfunc _process(", 1)[0]
    assert source.count("_modal_blocks_board_input() or (ai_enabled and turn == 2)") >= 2
    assert "if touch.index != 0:" in source
    assert "_touch_board_pending = false" in source
    assert "topbar.get_global_rect().has_point(touch.position)" in source
    assert "dock.get_global_rect().has_point(touch.position)" in source
