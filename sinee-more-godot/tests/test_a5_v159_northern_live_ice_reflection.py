"""A5 v159: source and independent geometric evidence; NOT native Godot acceptance."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text()


def body(name: str) -> str:
    match = re.search(rf"^(?:static )?func {re.escape(name)}\(", MAIN, re.M)
    assert match, name
    following = re.search(r"\n(?:static )?func ", MAIN[match.end():])
    return MAIN[match.start():match.end() + following.start() if following else len(MAIN)]


def test_northern_source_canon_unchanged():
    manifest = json.loads((ROOT / "tools/approved_seven_world_manifest.json").read_text())
    entry = next(e for e in manifest["images"] if e["world"] == "northern_sea")
    source = ROOT / "assets/a5_northern_ranked/07_northern_sea_canon_source.png"
    assert source.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]


def test_northern_uses_same_small_shared_radial_texture_not_a_flattened_screenshot():
    creation = body("_create_perspective_layer")
    assert MAIN.count("_night_beacon_pool_texture = _make_night_beacon_pool_texture()") == 1
    assert 'northern_reflection.texture = _night_beacon_pool_texture' in creation
    assert 'perspective_touch_preview_northern_reflection.texture = _night_beacon_pool_texture' in creation
    assert 'northern_reflection := Sprite2D.new()' in creation
    assert 'northern_reflection.z_index = 3' in creation
    assert 'northern_reflection.visible = false' in creation
    assert 'perspective_northern_rune_reflections.append(northern_reflection)' in creation
    assert 'HeldNorthernRuneReflection' in creation
    assert 'Button.new()' not in creation


def test_northern_ice_reflection_world_and_occupancy_gated():
    update = body("_update_northern_rune_reflection")
    assert 'world == 6 and rank >= 1 and rank <= 9 and player in [1, 2]' in update
    assert 'pool.visible = show' in update
    assert 'if not show:\n\t\treturn' in update
    assert 'PieceGrounding.bottom_fraction(world, rank)' in update
    assert 'pool.position = base + Vector2(0.0, extent * 0.025)' in update
    assert 'pool.scale = Vector2(3.1 * radius_x / 96.0, 2.7 * radius_y / 96.0)' in update
    assert 'Color(0.98, 0.55, 0.29, 0.45)' in update
    assert 'Color(0.32, 0.80, 1.0, 0.45)' in update


def test_northern_reflection_grows_monotonically_rank_1_to_9():
    for rank in range(1, 9):
        r0 = (3.1 * (0.24 + 0.014 * rank), 2.7 * (0.080 + 0.003 * rank))
        r1 = (3.1 * (0.24 + 0.014 * (rank + 1)), 2.7 * (0.080 + 0.003 * (rank + 1)))
        assert r0[0] < r1[0] and r0[1] < r1[1]
    # Even rank 9 is local to the target cell; no full-screen glow overlay.
    assert 3.1 * (0.24 + 0.014 * 9) < 1.2


def test_reflection_falloff_is_zero_at_edges_and_finite():
    def alpha(x: int, y: int) -> float:
        r = math.hypot((x + 0.5 - 48) / 48, (y + 0.5 - 48) / 48)
        return 0.58 * max(0, 1 - r) ** 1.8
    assert 0.55 < alpha(47, 47) < 0.58
    assert alpha(0, 0) == alpha(95, 95) == 0
    assert alpha(47, 47) > alpha(23, 47) > alpha(5, 47) >= 0


def test_live_and_held_reflections_share_exact_update_and_clear():
    live = body("_refresh_perspective_layer")
    held = body("_refresh_touch_preview")
    assert '_update_northern_rune_reflection(perspective_northern_rune_reflections[i]' in live
    assert '_update_northern_rune_reflection(perspective_touch_preview_northern_reflection' in held
    assert 'perspective_touch_preview_northern_reflection.visible = false' in held
    assert '_is_legal_move(turn, rank, _touch_board_cell)' in held
    assert MAIN.count('_update_northern_rune_reflection(') == 3


def test_native_21_matches_and_held_cover_fixture_registered_not_executed():
    matches = body("_run_headless_full_match_smoke")
    held = body("_run_headless_held_preview_grounding_smoke")
    assert 'perspective_northern_rune_reflections[light_cell].visible == rune_expected' in matches
    assert 'rune_expected := world == 6 and occupied' in matches
    assert 'perspective_touch_preview_northern_reflection.visible' in held
    assert 'perspective_northern_rune_reflections[4].visible' in held


def test_production_handlers_do_not_invoke_reflection_logic():
    for name in ("_on_primary", "_is_legal_move", "_on_cell_pressed", "_play_ai_turn", "_reset_round", "_on_reserve_pressed", "_on_secondary"):
        assert '_update_northern_rune_reflection' not in body(name), name


def test_qualification_quarantine_is_available_but_no_longer_used_for_v142():
    runner = (ROOT / "tools/run_a5_current_static_regression.py").read_text()
    workflow = (ROOT.parent / ".github/workflows/a5-seven-worlds-native-qualification.yml").read_text()
    assert 'A5_HISTORICAL_QUARANTINE_NOT_GREEN' in runner
    assert 'unknown version requested' in runner
    assert '--exclude-version 142' not in workflow
    assert 'python3 tools/run_a5_current_static_regression.py --min-version 120' in workflow
    assert '--exclude-version 125' not in workflow
    assert 'Godot import and parse' in workflow
    assert '21 full matches through production AI and move handlers' in workflow
    assert 'never auto-accept visual or real-touch parity' in workflow
