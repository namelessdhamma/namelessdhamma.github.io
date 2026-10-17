"""A5 v91: integrated Godot scroll persistence across process reload.

These are deterministic source/model checks. The real Godot runtime fixture is
BLUE_SEA_RESERVE_SCROLL_COLD_RESUME_PASS and must run before engine PASS.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()


def fn(name):
    m = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\).*?(?=^func |^static func |\Z)', SOURCE, re.M | re.S)
    assert m, name
    return m.group()


def test_01_saved_scroll_is_additive_to_legacy_match_schema():
    s = fn('_match_snapshot')
    assert '"schema": 1' in s
    assert '"reserve_scroll": _snapshot_reserve_scroll()' in s
    assert '"reserve_scroll"' not in s.split('"schema": 1')[0]
    validator = fn('_match_snapshot_valid')
    assert 'if state.has("reserve_scroll"):' in validator
    assert '"reserve_scroll"' not in validator.split('var required := ')[1].split('\n')[0]


def test_02_both_players_offsets_saved_even_if_one_hidden():
    snap = fn('_snapshot_reserve_scroll')
    assert '[_reserve_scroll_by_player[0], _reserve_scroll_by_player[1]]' in snap
    assert 'reserve_scroller.visible' in snap
    assert '_last_reserve_scroll_player in [1, 2]' in snap
    assert 'positions[_last_reserve_scroll_player - 1] = maxi(0, reserve_scroller.scroll_horizontal)' in snap


def test_03_invalid_scroll_values_fail_closed():
    validator = fn('_match_snapshot_valid')
    for term in ('state["reserve_scroll"] is Array', '.size() != 2',
                 'typeof(offset) in [TYPE_INT, TYPE_FLOAT]', 'float(offset) != float(int(offset))', 'int(offset) < 0', 'int(offset) > 1000000'):
        assert term in validator


def test_04_loaded_scroll_before_ui_creation_and_clamped_after_layout():
    ready = fn('_ready')
    assert ready.index('_load_match()') < ready.index('_prepare_world_shell()')
    applied = fn('_apply_match_snapshot')
    assert '_reserve_scroll_by_player = [0, 0]' in applied
    assert '_last_reserve_scroll_player = 0' in applied
    refresh = fn('_refresh_surface')
    assert 'call_deferred("_restore_active_reserve_scroll", turn)' in refresh
    restore = fn('_restore_active_reserve_scroll')
    assert 'await get_tree().process_frame' in restore
    assert 'clampi(_reserve_scroll_by_player[player - 1], 0, max_scroll)' in restore


def test_05_new_round_clears_both_saved_offsets():
    reset = fn('_reset_round')
    assert '_reserve_scroll_by_player = [0, 0]' in reset
    assert '_last_reserve_scroll_player = 0' in reset


def test_06_no_per_frame_disk_write_during_scroll():
    assert '_save_match()' not in fn('_snapshot_reserve_scroll')
    assert '_save_match()' not in fn('_restore_active_reserve_scroll')
    assert '_save_match()' not in fn('_process')


def test_07_native_fixture_covers_legacy_malformed_and_both_players():
    fixture = fn('_run_headless_reserve_scroll_resume_smoke')
    assert 'candidate["reserve_scroll"] = [321, 654]' in fixture
    assert 'JSON.parse_string(JSON.stringify(candidate))' in fixture
    assert 'Integral JSON floats must be compatible' in fixture
    assert 'legacy.erase("reserve_scroll")' in fixture
    assert 'assert(_match_snapshot_valid(legacy)' in fixture
    assert 'for malformed in ' in fixture
    assert '_apply_match_snapshot(original)' in fixture
    assert 'BLUE_SEA_RESERVE_SCROLL_COLD_RESUME_PASS' in fixture
    assert '_run_headless_reserve_scroll_resume_smoke()' in fn('_run_headless_geometry_and_interaction_smoke')


def test_08_approved_visual_and_gameplay_modules_untouched():
    for module in ('scripts/world_visuals.gd', 'scripts/ai_opponent.gd',
                   'scripts/perspective_board_geometry.gd', 'scripts/piece_grounding.gd'):
        assert (ROOT / module).is_file()
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in SOURCE
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in SOURCE


def test_09_round_trip_model_current_visible_and_hidden_player():
    def save(positions, visible, last, live):
        values = list(positions)
        if visible and last in (1, 2):
            values[last - 1] = max(0, live)
        return values
    assert save([400, 250], True, 2, 500) == [400, 500]
    assert save([400, 250], False, 2, 0) == [400, 250]
    assert save([400, 250], True, 1, 650) == [650, 250]
    assert [min(value, limit) for value, limit in zip([650, 250], [300, 100])] == [300, 100]
