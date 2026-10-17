"""A5 v81 source-contract checks; native Godot smoke is NOT executed here."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")


def fn(name):
    match = re.search(rf"^func {re.escape(name)}\(.*?(?=^func |\Z)", MAIN, re.M | re.S)
    assert match, f"Missing {name}"
    return match.group(0)


def test_snapshot_contains_full_shared_match_not_world_specific_engine():
    s = fn("_match_snapshot")
    for field in ('"board"', '"reserves"', '"turn"', '"moves"', '"round"',
                  '"score"', '"winner"', '"win_line"', '"game_over"',
                  '"draw"', '"match_winner"', '"blocked_player"', '"rule"'):
        assert field in s
    assert 'current_world' not in s  # world selection remains in preferences
    assert MAIN.count('func _on_primary()') == 1
    assert MAIN.count('func _winning_line(') == 1


def test_reload_occurs_before_scene_refresh_and_keeps_headless_deterministic():
    ready = fn('_ready')
    assert ready.index('_load_preferences()') < ready.index('_load_match()') < ready.index('_set_world(current_world)')
    load = fn('_load_match')
    assert 'DisplayServer.get_name() == "headless"' in load
    assert '_read_valid_match_at(MATCH_STATE_PATH)' in load
    assert '_read_valid_match_at(MATCH_STATE_BACKUP_PATH)' in load
    assert load.index('_read_valid_match_at(MATCH_STATE_PATH)') < load.index('_apply_match_snapshot(restored)')
    assert 'FileAccess.file_exists(MATCH_STATE_PATH)' in load


def test_real_legal_commit_and_reset_persist_without_saving_illegal_moves():
    move = fn('_on_primary')
    assert move.index('if not _is_legal_move(') < move.index('board_stacks[selected_cell].append(')
    assert move.index('board_stacks[selected_cell].append(') < move.index('_save_match()')
    assert move.count('_save_match()') == 1
    reset = fn('_reset_round')
    assert reset.index('board_stacks = [') < reset.index('_save_match()')
    assert '_save_match()' in fn('_on_game_menu_item')  # changed rules get new snapshot
    assert '_save_match()' not in fn('_on_reserve_pressed')
    assert '_save_match()' not in fn('_on_cell_pressed')


def test_validator_checks_used_rank_and_stack_legality():
    s = fn('_match_snapshot_valid')
    for token in ('used[owner - 1][rank - 1]', 'rank <= prior_rank',
                  'owner == prior_player', 'stack.size() > 2',
                  'bool(reserves[player][rank]) == used[player][rank]',
                  'piece_count != count', 'LINES.has(line)',
                  'match_id != winner_id', 'score[match_id - 1]'):
        assert token in s
    assert 'return true' in s


def test_json_roundtrip_rebuilds_typed_state_and_clears_transient_selection():
    restore = fn('_apply_match_snapshot')
    assert 'board_stacks.clear()' in restore
    assert 'reserve_available.clear()' in restore
    assert 'match_score.clear()' in restore
    assert 'selected_reserve = -1' in restore
    assert 'selected_cell = -1' in restore
    save = fn('_save_match')
    assert 'DisplayServer.get_name() == "headless"' in save
    assert '_write_match_atomically(MATCH_STATE_PATH, _match_snapshot())' in save
    assert 'JSON.stringify(state)' in fn('_write_match_atomically')
    assert 'file.close()' in fn('_write_match_atomically')


def test_native_smoke_checks_clean_and_terminal_restore_and_corrupt_rejection():
    smoke = fn('_run_headless_match_snapshot_smoke')
    assert '_match_snapshot_valid(original)' in smoke
    assert '_match_snapshot_valid(played)' in smoke
    assert '_match_snapshot_valid(terminal)' in smoke
    assert smoke.count('assert(not _match_snapshot_valid(invalid)') >= 4
    assert '_apply_match_snapshot(original)' in smoke
    assert '_match_snapshot() == original' in smoke
    assert '_run_headless_match_snapshot_smoke()' in fn('_run_headless_geometry_and_interaction_smoke')


def test_seven_worlds_and_ai_and_pirate_controller_preserved():
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in fn('_run_headless_full_match_smoke')
    assert 'for mode in ["C", "D", "CD"]:' in fn('_run_headless_full_match_smoke')
    assert 'PirateOpeningCampaign' in (ROOT / 'project.godot').read_text()
    assert 'call_deferred("_play_ai_turn")' in fn('_queue_ai_turn_if_ready')
