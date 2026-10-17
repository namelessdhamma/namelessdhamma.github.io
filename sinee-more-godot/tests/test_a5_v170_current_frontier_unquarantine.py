"""A5 v170: qualified current source frontier cannot silently quarantine v142.

This verifies the CI wiring only. It is not Godot execution, touch evidence,
or proof that historical pre-v120 fixtures remain valid.
"""
from pathlib import Path
import importlib.util
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT.parent / '.github/workflows/a5-seven-worlds-native-qualification.yml'
RUNNER = ROOT / 'tools/run_a5_current_static_regression.py'


def _runner_module():
    spec = importlib.util.spec_from_file_location('a5_current_frontier_v170', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v142_easy_ai_regression_is_real_and_in_current_frontier():
    selected = _runner_module().discover_tests(ROOT / 'tests', 120)
    names = [p.name for p in selected]
    assert 'test_a5_v142_easy_difficulty.py' in names
    assert 'test_a5_v169_modal_open_input_transaction.py' in names
    assert 'test_a5_v170_current_frontier_unquarantine.py' in names
    assert len(selected) >= 52


def test_ci_runs_all_current_tests_without_exclusions():
    source = WORKFLOW.read_text()
    assert 'python3 tools/run_a5_current_static_regression.py --min-version 120' in source
    assert '--exclude-version' not in source
    assert 'v142: 4/4 PASS' in source
    assert 'NOT_REAL_PHONE_TOUCH' in source
    assert 'LEGACY_PRODUCT_PARITY_PASS=OPEN' in source


def test_ci_frontier_cli_lists_v142_and_v170_without_quarantine():
    run = subprocess.run([sys.executable, str(RUNNER), '--min-version', '120',
                          '--list-only'], cwd=ROOT, text=True, capture_output=True, check=True)
    assert 'test_a5_v142_easy_difficulty.py' in run.stdout
    assert 'test_a5_v170_current_frontier_unquarantine.py' in run.stdout
    assert 'A5_HISTORICAL_QUARANTINE_NOT_GREEN' not in run.stdout


def test_native_acceptance_gate_remains_open():
    source = WORKFLOW.read_text()
    assert '21 full matches through production AI and move handlers' in source
    assert 'Capture 14 actual rendered frames at 746x280' in source
    assert 'Capture 14 actual rendered frames at 844x390' in source
    assert 'PLAYABLE=UNVERIFIED_UNTIL_REAL_TOUCH' in source
    assert 'VISUAL_PARITY=REVIEW_REQUIRED_ALL_SEVEN' in source
