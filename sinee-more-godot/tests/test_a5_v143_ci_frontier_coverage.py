"""A5 v143: native CI must never silently omit current versioned tests."""
from pathlib import Path
import importlib.util
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "run_a5_current_static_regression.py"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "a5-seven-worlds-native-qualification.yml"


def _module():
    spec = importlib.util.spec_from_file_location("a5_ci_frontier", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_native_workflow_calls_version_aware_frontier_runner():
    source = WORKFLOW.read_text()
    assert "python3 tools/run_a5_current_static_regression.py --min-version 120" in source
    assert "tests/test_a5_v1[2-3][0-9]*.py" not in source


def test_latest_ai_and_touch_regressions_are_selected():
    files = {p.name for p in _module().discover_tests(ROOT / "tests")}
    for version in (120, 137, 138, 139, 140, 141, 142, 143):
        assert any(name.startswith(f"test_a5_v{version}_") for name in files)
    assert len(files) >= 25


def test_numeric_version_sort_includes_future_decades(tmp_path):
    for version in (99, 120, 129, 139, 140, 142, 143, 150, 200):
        (tmp_path / f"test_a5_v{version}_regression.py").write_text("")
    files = _module().discover_tests(tmp_path, 120)
    assert [p.name for p in files] == [
        f"test_a5_v{v}_regression.py" for v in (120, 129, 139, 140, 142, 143, 150, 200)
    ]


def test_ignores_non_regression_files_and_fails_closed_on_empty(tmp_path):
    (tmp_path / "test_a5_v143_regression.py").write_text("")
    (tmp_path / "test_a5_v143_regression.py.bak").write_text("")
    (tmp_path / "test_a5_vfuture_regression.py").write_text("")
    (tmp_path / "test_a5_v143_bad-name.py").write_text("")
    assert [p.name for p in _module().discover_tests(tmp_path, 143)] == [
        "test_a5_v143_regression.py"
    ]
    assert _module().discover_tests(tmp_path, 144) == []


def test_cli_list_only_reports_latest_without_running_godot():
    result = subprocess.run(
        [sys.executable, str(HELPER), "--min-version", "120", "--list-only"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    assert "test_a5_v140_unplayable_rank_phone_feedback.py" in result.stdout
    assert "test_a5_v141_persona_behavior.py" in result.stdout
    assert "test_a5_v142_easy_difficulty.py" in result.stdout
    assert "test_a5_v143_ci_frontier_coverage.py" in result.stdout
    assert "A5_NATIVE_CI_FRONTIER selected=" in result.stdout
