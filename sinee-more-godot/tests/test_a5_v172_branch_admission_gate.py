"""v172: reject incomplete source before costly native qualification."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("admission", ROOT / "tools/a5_branch_admission_gate.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
MANIFEST = json.loads((ROOT / "tools/a5_source_admission_manifest_v173.json").read_text())


def test_local_exact_staging_passes():
    assert module.verify_local(ROOT, MANIFEST) == []


def test_manifest_has_full_seven_world_runtime_assets():
    assert len([k for k in MANIFEST["files"] if k.startswith("assets/")]) == 288
    assert len([k for k in MANIFEST["files"] if k.startswith("scripts/")]) == 7


def test_missing_main_scene_fails_closed(tmp_path):
    assert any(x["reason"] == "MISSING_OR_UNSAFE_FILE" for x in module.verify_local(tmp_path, MANIFEST))


def test_changed_hash_fails_closed():
    bad = json.loads(json.dumps(MANIFEST))
    bad["files"]["project.godot"]["sha256"] = "0" * 64
    assert any(x["reason"] == "CONTENT_MISMATCH" for x in module.verify_local(ROOT, bad))


def test_missing_critical_binding_fails_closed():
    bad = json.loads(json.dumps(MANIFEST))
    bad["files"].pop("scripts/ai_opponent.gd")
    assert any(x["reason"] == "MISSING_CRITICAL_BINDING" for x in module.verify_local(ROOT, bad))


def test_remote_old_shell_fails_closed():
    old_tree = {"truncated": False, "tree": [
        {"path": "sinee-more-godot/project.godot", "type": "blob", "sha": "old"},
        {"path": "sinee-more-godot/scripts/main.gd", "type": "blob", "sha": "old"},
    ]}
    defects = module.verify_remote_tree(MANIFEST, old_tree)
    assert len(defects) >= 280
    assert any(x["reason"] == "MISSING_IN_REMOTE_BRANCH" for x in defects)


def test_truncated_tree_fails_closed():
    assert module.verify_remote_tree(MANIFEST, {"truncated": True, "tree": []})[0]["reason"] == "TRUNCATED_OR_UNKNOWN_REMOTE_TREE"


def test_clean_remote_tree_passes():
    tree = {"truncated": False, "tree": [
        {"path": "sinee-more-godot/" + name, "type": "blob", "sha": meta["git_blob_sha1"]}
        for name, meta in MANIFEST["files"].items()
    ]}
    assert module.verify_remote_tree(MANIFEST, tree) == []


def test_workflow_runs_gate_before_engine_download():
    s = (ROOT.parent / ".github/workflows/a5-seven-worlds-native-qualification.yml").read_text()
    assert s.index("Verify exact integrated seven-world source") < s.index("Install pinned Godot 4.7.2")
    assert "python3 sinee-more-godot/tools/a5_branch_admission_gate.py" in s


def test_unmanifested_script_fails_closed(tmp_path):
    # An extra scene/script in the checked-out branch must not bypass review.
    import shutil
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    extra = project / "scripts" / "unexpected_autoload.gd"
    extra.write_text("extends Node\n")
    assert any(x["reason"] == "UNMANIFESTED_RUNTIME_SOURCE" for x in module.verify_local(project, MANIFEST))
