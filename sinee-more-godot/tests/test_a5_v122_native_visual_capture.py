"""v122 source/contract checks. These are NOT Godot render or phone-touch tests."""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text()
RUNNER = ROOT / "tools/a5_native_seven_world_capture.py"
SPEC = importlib.util.spec_from_file_location("a5_native_capture", RUNNER)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_01_approved_seven_immutable_hashes_verified():
    paths = MOD.canon_paths(ROOT)
    assert len(paths) == 7
    assert set(paths) == set(MOD.WORLDS)


def test_02_real_live_scene_not_static_reference_overlay():
    assert 'call_deferred("_run_seven_world_visual_capture")' in MAIN
    assert 'await RenderingServer.frame_post_draw' in MAIN
    assert 'get_viewport().get_texture().get_image()' in MAIN
    assert '_on_reserve_pressed(turn, rank - 1)' in MAIN
    assert '_on_cell_pressed(cell)' in MAIN
    assert '"source": "Godot live scene"' in MAIN


def test_03_capture_does_not_load_or_write_player_state():
    for signature in ('func _load_preferences() -> void:',
                      'func _save_preferences() -> void:',
                      'func _load_match() -> bool:',
                      'func _save_match() -> void:',
                      'func _queue_ai_turn_if_ready() -> void:'):
        assert MAIN.split(signature, 1)[1].lstrip().startswith('if _is_visual_capture_run():')
    assert 'return "--nd-capture-seven" in OS.get_cmdline_user_args()' in MAIN


def test_04_only_explicit_windowed_capture_can_write():
    assert 'if DisplayServer.get_name() == "headless":' in MAIN.split('func _run_seven_world_visual_capture()', 1)[1]
    assert 'not output_dir.is_absolute_path()' in MAIN
    assert '"--nd-capture-dir="' in MAIN
    assert 'NATIVE_CAPTURED_NOT_VISUAL_PARITY_ACCEPTED' in MAIN


def test_05_seven_worlds_two_phases_and_six_legal_moves():
    assert len(MOD.WORLDS) == 7
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in MAIN
    assert '"empty", output_dir' in MAIN and '"played", output_dir' in MAIN
    assert '[[1, 0], [2, 4], [3, 8], [4, 2], [5, 6], [6, 3]]' in MAIN
    assert 'if moves != 6 or game_over or winner != 0:' in MAIN
    assert 'get_tree().quit(0)' in MAIN


def test_06_fixture_is_legal_under_all_three_rule_variants():
    moves = [(1, 0), (2, 4), (3, 8), (4, 2), (5, 6), (6, 3)]
    lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
             (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
    assert len({rank for rank, _ in moves}) == len(moves)
    assert len({cell for _, cell in moves}) == len(moves)
    occupied = {cell: (i % 2 + 1, rank) for i, (rank, cell) in enumerate(moves)}
    for player in (1, 2):
        assert not any(all(cell in occupied and occupied[cell][0] == player for cell in line)
                       for line in lines)


def test_07_missing_native_manifest_fails_closed():
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(RuntimeError, match='No Godot native capture manifest'):
            MOD.inspect_captures(Path(directory), ROOT, (1280, 720))


def test_08_forged_incomplete_manifest_fails_closed():
    with tempfile.TemporaryDirectory() as directory:
        (Path(directory) / 'capture_manifest.json').write_text(json.dumps({
            'status': 'NATIVE_CAPTURED_NOT_VISUAL_PARITY_ACCEPTED',
            'capture_count': 13, 'world_count': 7, 'real_gameplay_handlers': True,
            'captures': [],
        }))
        with pytest.raises(RuntimeError, match='Incomplete or non-native'):
            MOD.inspect_captures(Path(directory), ROOT, (1280, 720))


def test_09_missing_engine_fails_without_creating_fake_capture():
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / 'native'
        result = subprocess.run([sys.executable, str(RUNNER), '--godot', str(Path(directory) / 'not-installed'),
                                 '--output', str(out)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 2
        assert 'A5_NATIVE_CAPTURE_BLOCKED' in result.stderr
        assert not (out / 'capture_manifest.json').exists()


def test_10_capture_does_not_claim_playable_or_visual_parity():
    text = RUNNER.read_text()
    assert '"PLAYABLE": "UNVERIFIED", "VISUAL_PARITY": "UNVERIFIED"' in text
    assert '"LEGACY_PRODUCT_PARITY_PASS": "OPEN"' in text
    assert '"real_touch": "NOT_TESTED", "21_ai_matches": "NOT_TESTED"' in text
    assert 'REVIEW_REQUIRED' in text
