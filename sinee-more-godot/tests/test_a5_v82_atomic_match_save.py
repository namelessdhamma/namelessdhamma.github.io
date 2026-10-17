"""A5 v82 source and model checks; Godot native IO smoke remains unexecuted."""
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')

def fn(name):
    match = re.search(rf'^func {re.escape(name)}\(.*?(?=^func |\Z)', MAIN, re.M | re.S)
    assert match, name
    return match.group(0)

def test_existing_v81_user_save_path_and_schema_unchanged():
    assert 'const MATCH_STATE_PATH := "user://blue_sea_match_v1.json"' in MAIN
    assert 'const MATCH_STATE_BACKUP_PATH := "user://blue_sea_match_v1.json.bak"' in MAIN
    assert '"schema": 1' in fn('_match_snapshot')

def test_no_destructive_primary_open_in_normal_save_path():
    writer = fn('_write_match_atomically')
    assert 'FileAccess.open(temporary, FileAccess.WRITE)' in writer
    assert 'FileAccess.open(path, FileAccess.WRITE)' not in writer
    assert writer.index('file.store_string(payload)') < writer.index('file.flush()') < writer.index('file.close()')
    assert writer.index('_read_valid_match_at(temporary)') < writer.index('DirAccess.rename_absolute(')

def test_previous_valid_primary_backed_up_before_atomic_replace():
    writer = fn('_write_match_atomically')
    assert writer.index('if not previous_snapshot.is_empty()') < writer.index('DirAccess.copy_absolute(') < writer.index('DirAccess.rename_absolute(')
    assert 'ProjectSettings.globalize_path(temporary)' in writer
    assert 'ProjectSettings.globalize_path(path + ".bak")' in writer
    assert 'if result != OK:' in writer

def test_corrupt_primary_restores_backup_without_touching_headless_user_data():
    load = fn('_load_match')
    assert 'DisplayServer.get_name() == "headless"' in load
    assert load.index('_read_valid_match_at(MATCH_STATE_PATH)') < load.index('_read_valid_match_at(MATCH_STATE_BACKUP_PATH)')
    assert load.index('_read_valid_match_at(MATCH_STATE_BACKUP_PATH)') < load.index('_apply_match_snapshot(restored)')
    assert '_save_match()' in load
    assert 'DisplayServer.get_name() == "headless"' in fn('_save_match')

def test_validator_still_guards_every_file_and_no_deserialization_bypass():
    reader = fn('_read_valid_match_at')
    assert 'JSON.parse_string(file.get_as_text())' in reader
    assert '_match_snapshot_valid(parsed)' in reader
    assert '_apply_match_snapshot(' not in reader
    assert 'if not _match_snapshot_valid(state):' in fn('_write_match_atomically')

def test_native_smoke_writes_only_disposable_name_and_removes_files():
    smoke = fn('_run_headless_match_atomic_io_smoke')
    assert 'a5_v82_disposable_match_io_qualification.json' in smoke
    assert 'MATCH_STATE_PATH' not in smoke.replace('Production MATCH_STATE_PATH and preferences are never touched here.', '')
    assert 'assert(_write_match_atomically(path, original)' in smoke
    assert 'assert(_write_match_atomically(path, played)' in smoke
    assert 'damaged.store_string("{incomplete")' in smoke
    assert 'assert(_read_valid_match_at(path + ".bak") == original' in smoke
    assert 'DirAccess.remove_absolute(' in smoke
    assert '_run_headless_match_atomic_io_smoke()' in fn('_run_headless_match_snapshot_smoke')

def test_single_shared_game_engine_and_preserved_qualified_controllers():
    assert MAIN.count('func _on_primary()') == 1
    assert MAIN.count('func _winning_line(') == 1
    assert 'PirateOpeningCampaign' in (ROOT/'project.godot').read_text()
    assert 'call_deferred("_play_ai_turn")' in fn('_queue_ai_turn_if_ready')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in fn('_run_headless_full_match_smoke')
