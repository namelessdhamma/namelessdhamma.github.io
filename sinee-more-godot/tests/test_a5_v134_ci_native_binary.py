"""Static gate for the native Godot CI route. Does not claim a native run."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/a5-seven-worlds-native-qualification.yml'
# GitHub's release-assets API digest for Godot 4.7.2 standard Linux x86_64.
GODOT_SHA = 'cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4'


def test_native_binary_is_official_standard_godot_472_pinned():
    text = WORKFLOW.read_text()
    assert 'godotengine/godot-builds/releases/download/4.7.2-stable/Godot_v4.7.2-stable_linux.x86_64.zip' in text
    assert GODOT_SHA + '  /tmp/a5-godot.zip' in text
    assert "-name 'Godot_v4.7.2-stable_linux.x86_64'" in text
    assert 'stable_mono_linux' not in text
    assert 'sha256sum -c -' in text


def test_native_workflow_gates_and_read_only_permission():
    raw = WORKFLOW.read_text()
    doc = yaml.safe_load(raw)
    assert doc['permissions'] == {'contents': 'read'}
    assert doc['jobs']['qualify']['timeout-minutes'] == 40
    steps = doc['jobs']['qualify']['steps']
    titles = [s['name'] for s in steps if 'name' in s]
    assert titles.index('Current source-level regression before native qualification') < titles.index('Godot import and parse')
    assert titles.index('Godot import and parse') < titles.index('21 full matches through production AI and move handlers')
    assert titles.index('21 full matches through production AI and move handlers') < titles.index('Capture 14 actual rendered frames at 746x280')
    assert 'NOT_REAL_PHONE_TOUCH' in raw and 'LEGACY_PRODUCT_PARITY_PASS=OPEN' in raw
    assert 'PLAYABLE=UNVERIFIED_UNTIL_REAL_TOUCH' in raw
    assert 'python3 tools/run_a5_current_static_regression.py --min-version 120' in raw
    assert "'a5/seven-worlds-native-*'" in raw
