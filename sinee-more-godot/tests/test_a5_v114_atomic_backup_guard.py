"""A5 v114: source transaction ordering and independent filesystem model.

These are offline checks. They do NOT assert Godot 4.7.2 runtime PASS.
"""
from pathlib import Path
import json
import shutil

SOURCE = (Path(__file__).resolve().parents[1] / "scripts/main.gd").read_text()
NATIVE = (Path(__file__).resolve().parent / "a5_v114_atomic_backup_guard_smoke.gd").read_text()


def transaction(old, new, *, fail_backup=False, corrupt_temp=False, corrupt_backup=False, corrupt_primary=False):
    """Independent Python filesystem oracle, not a GDScript interpreter."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        primary = root / "match.json"
        backup = root / "match.json.bak"
        temporary = root / "match.json.tmp"
        primary.write_text(json.dumps(old))
        temporary.write_text(json.dumps(new if not corrupt_temp else old))
        if json.loads(temporary.read_text()) != new:
            return False, json.loads(primary.read_text()), None
        if fail_backup:
            return False, json.loads(primary.read_text()), None
        shutil.copyfile(primary, backup)
        if corrupt_backup:
            backup.write_text(json.dumps({"broken": True}))
        if json.loads(backup.read_text()) != old:
            return False, json.loads(primary.read_text()), json.loads(backup.read_text())
        temporary.replace(primary)
        if corrupt_primary:
            primary.write_text(json.dumps({"broken": True}))
        return (json.loads(primary.read_text()) == new,
                json.loads(primary.read_text()), json.loads(backup.read_text()))


def test_guard_before_primary_replace():
    block = SOURCE.split("func _write_match_atomically(", 1)[1].split("\nfunc ", 1)[0]
    checks = [
        "var payload := JSON.stringify(state)",
        "var expected_snapshot = JSON.parse_string(payload)",
        "if _read_valid_match_at(temporary) != expected_snapshot:",
        "var previous_snapshot := _read_valid_match_at(path)",
        "if backup_result != OK:",
        'if _read_valid_match_at(path + ".bak") != previous_snapshot:',
        "var result := DirAccess.rename_absolute(",
        "if _read_valid_match_at(path) != expected_snapshot:",
    ]
    indices = [block.index(item) for item in checks]
    assert indices == sorted(indices)
    # Both backup failures return BEFORE rename, not merely emit a warning.
    assert "backup_result != OK:\n\t\t\tpush_warning" in block
    assert "preserving last valid primary: %d" in block
    assert "backup readback mismatch; preserving last valid primary" in block
    assert block.count("\t\t\treturn false") >= 2


def test_normal_replace_retains_predecessor():
    success, primary, backup = transaction({"turn": 1}, {"turn": 2})
    assert success and primary == {"turn": 2} and backup == {"turn": 1}


def test_backup_copy_failure_preserves_only_good_primary():
    success, primary, backup = transaction({"turn": 1}, {"turn": 2}, fail_backup=True)
    assert not success and primary == {"turn": 1} and backup is None


def test_backup_readback_mismatch_preserves_primary():
    success, primary, backup = transaction({"turn": 1}, {"turn": 2}, corrupt_backup=True)
    assert not success and primary == {"turn": 1} and backup != primary


def test_temp_mismatch_preserves_primary():
    success, primary, backup = transaction({"turn": 1}, {"turn": 2}, corrupt_temp=True)
    assert not success and primary == {"turn": 1} and backup is None


def test_primary_post_replace_mismatch_is_not_success():
    success, primary, backup = transaction({"turn": 1}, {"turn": 2}, corrupt_primary=True)
    assert not success and primary != {"turn": 2} and backup == {"turn": 1}


def test_native_fixture_integration_is_explicit_and_nonproduction():
    assert "extends SceneTree" in NATIVE
    assert "Backup failure must fail closed" in NATIVE
    assert "A5_V114_ATOMIC_BACKUP_GUARD_PASS" in NATIVE
    assert '"user://a5_v114_atomic_backup_guard.json"' in NATIVE
    assert "quit(0)" in NATIVE
