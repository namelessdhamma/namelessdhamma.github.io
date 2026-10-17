"""A5 v128: static and model checks, NOT native Godot or physical touch."""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")


def body(name):
    found = re.search(r"^(?:static )?func " + re.escape(name) + r"\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)", SOURCE, re.M | re.S)
    assert found, name
    return found.group(1)


def geometry_token(viewport, physical, board, density):
    return viewport, physical, board, round(density, 3)


@pytest.mark.parametrize("change", ["viewport", "physical", "board", "density"])
def test_geometry_changes_invalidate_press_token_in_all_worlds(change):
    baseline = dict(viewport=(746, 280), physical=(746, 280), board=(0, 0, 746, 190), density=1.0)
    variants = dict(viewport=(844, 390), physical=(1492, 560), board=(0, 0, 746, 170), density=2.0)
    for world in range(7):
        initial = (world, geometry_token(**baseline))
        after = dict(baseline)
        after[change] = variants[change]
        assert initial != (world, geometry_token(**after))
        assert initial == (world, geometry_token(**baseline))


def test_real_touch_token_uses_live_viewport_physical_dock_and_density():
    signature = body("_touch_geometry_token")
    for part in ("viewport_size", "physical_size", "board_rect", "density"):
        assert part in signature
    token = body("_touch_board_state_token")
    for part in ("get_viewport_rect().size", "get_window().size", "_perspective_board_rect()", "_native_touch_density()"):
        assert part in token
    assert "match_score.duplicate()" in token


def test_live_resize_cancels_pending_move_before_relayout():
    code = body("_process")
    resize = code.split("if perspective_tiles.size() == 9 and (", 1)[1].split("var size :=", 1)[0]
    assert resize.index("_cancel_pending_board_touch()") < resize.index("_refresh_perspective_layer()")
    assert "_physical_pixel_scale()" in resize
    assert "_native_touch_density()" in resize
    assert "perspective_rect != _perspective_board_rect()" in resize


def test_release_still_checks_bound_token_before_gameplay_commit():
    code = body("_input")
    release = code.split("if not touch.pressed:", 1)[1].split("# Track ALL primary touches", 1)[0]
    assert release.index("initial_state != _touch_board_state_token()") < release.index("_on_cell_pressed(initial_cell)")
    assert "_touch_board_pending = false" in release


def test_native_opt_in_smoke_reaches_all_worlds_and_no_live_writes():
    smoke = body("_run_headless_touch_geometry_resize_smoke")
    assert "for world in range(WorldVisuals.WORLDS.size()):" in smoke
    assert "_input(touch)" in smoke
    assert "moves == 0" in smoke and "moves == 1" in smoke
    assert "BLUE_SEA_TOUCH_RESIZE_TRANSACTION_PASS" in smoke
    assert "_run_headless_touch_geometry_resize_smoke()" in body("_run_headless_geometry_and_interaction_smoke")
    for forbidden in ("_save_match()", "_save_preferences()", "FileAccess.open("):
        assert forbidden not in smoke


def test_preserved_single_shared_game_engine_and_reference_sources():
    assert "extends Control" in SOURCE
    assert "const WorldVisuals = preload(" in SOURCE
    assert "const AIOpponent = preload(" in SOURCE
    assert "const PerspectiveGeometry = preload(" in SOURCE
    assert "func _on_primary() -> void:" in SOURCE
    assert "func _run_seven_world_visual_capture() -> void:" in SOURCE
