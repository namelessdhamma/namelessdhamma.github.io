"""CI wiring checks only; do not mistake these for Godot runtime results."""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/a5-seven-worlds-native-qualification.yml'
PROJECT = ROOT / 'sinee-more-godot'


def test_native_ci_exists_and_is_non_deploying():
    content = WORKFLOW.read_text(encoding='utf-8')
    assert "branches:\n      - 'a5/seven-worlds-native-*'" in content
    assert 'permissions:\n  contents: read' in content
    assert 'persist-credentials: false' in content
    assert 'cancel-in-progress: false' in content
    assert not re.search(r'^\s*(?:deploy|release|publish):', content, re.M)
    assert not re.search(r'^\s*- main\s*$', content, re.M)


def test_native_ci_pins_engine_hash_and_checks_art():
    content = WORKFLOW.read_text(encoding='utf-8')
    assert 'Godot_v4.7.2-stable_linux.x86_64.zip' in content
    assert 'cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4' in content
    assert 'sha256sum -c -' in content
    assert 'canon_paths(Path(\'sinee-more-godot\'))' in content
    assert (PROJECT / 'tools/approved_seven_world_manifest.json').is_file()


def test_native_ci_uses_real_gameplay_and_native_capture():
    content = WORKFLOW.read_text(encoding='utf-8')
    main = (PROJECT / 'scripts/main.gd').read_text(encoding='utf-8')
    for flag in ('--nd-run-smoke', '--nd-run-full-match', '--nd-capture-seven'):
        assert flag in main
    for marker in ('BLUE_SEA_HEADLESS_SMOKE_SUITE_PASS',
                   'BLUE_SEA_FULL_MATCH_SUITE_PASS matches=21',
                   'BLUE_SEA_FULL_MATCH_CASE_PASS'):
        assert marker in content
    assert 'a5_native_seven_world_capture.py' in content
    assert '--size 746x280' in content
    assert 'xvfb-run' in content
    assert 'native_visual_comparison_REVIEW_REQUIRED.jpg' in content


def test_native_ci_cannot_claim_real_touch_or_parity():
    content = WORKFLOW.read_text(encoding='utf-8')
    assert 'native_touch_simulation=NOT_REAL_PHONE_TOUCH' in content
    assert 'PLAYABLE=UNVERIFIED_UNTIL_REAL_TOUCH' in content
    assert 'VISUAL_PARITY=REVIEW_REQUIRED_ALL_SEVEN' in content
    assert 'LEGACY_PRODUCT_PARITY_PASS=OPEN' in content


def test_workflow_is_valid_yaml_if_parser_available():
    yaml = pytest.importorskip('yaml')
    doc = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert 'on' in doc and 'jobs' in doc
    assert list(doc['jobs']) == ['qualify']
    steps = doc['jobs']['qualify']['steps']
    # The source-admission gate added in v172 is an intentional new step.
    # Avoid a brittle historical step count: enforce ordered, unique, material
    # stages so the CI can grow without silently dropping native qualification.
    names = [step.get('name', step.get('uses', '')) for step in steps]
    assert len(names) == len(set(names))
    required = [
        'actions/checkout@v4',
        'Verify exact integrated seven-world source before installing Godot',
        'Install pinned Godot 4.7.2 and display dependencies',
        'Validate immutable approved art before native execution',
        'Current source-level regression before native qualification',
        'Godot import and parse',
        'Seven-world gameplay, touch and AI smoke',
        '21 full matches through production AI and move handlers',
        'Capture 14 actual rendered frames at 746x280',
        'Capture 14 actual rendered frames at 844x390',
        'Evidence disposition (never auto-accept visual or real-touch parity)',
        'Upload exact native evidence for independent review',
    ]
    assert all(name in names for name in required)
    assert [names.index(name) for name in required] == sorted(names.index(name) for name in required)
    # No phase after the final evidence disposition may silently deploy.
    assert names[-1] == required[-1]


def test_windowed_capture_disables_unavailable_ci_audio_without_headless():
    runner = (PROJECT / 'tools/a5_native_seven_world_capture.py').read_text(encoding='utf-8')
    assert '"--audio-driver", "Dummy", "--path"' in runner
    assert '"--windowed", "--resolution"' in runner
    assert '"--headless"' not in runner
