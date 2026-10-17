"""A5 v173: source integrity pin and ordered native qualification preflight."""
from pathlib import Path
import hashlib
import json
import re
import pytest

PROJECT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT.parent / '.github/workflows/a5-seven-worlds-native-qualification.yml'
MANIFEST = PROJECT / 'tools/a5_source_admission_manifest_v173.json'


def test_manifest_pin_is_exact_and_precedes_admission_and_download():
    text = WORKFLOW.read_text(encoding='utf-8')
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert f'{digest}  sinee-more-godot/tools/a5_source_admission_manifest_v173.json' in text
    assert text.index('sha256sum -c -') < text.index('python3 sinee-more-godot/tools/a5_branch_admission_gate.py')
    assert text.index('python3 sinee-more-godot/tools/a5_branch_admission_gate.py') < text.index('Install pinned Godot 4.7.2')


def test_manifest_pins_current_regression_and_complete_assets():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert manifest['source_version'] == 'v173'
    assert manifest['native_playable_verified'] is False
    assert manifest['visual_parity_verified'] is False
    entries = manifest['files']
    assert 'tests/test_a5_v129_native_ci_gate.py' in entries
    assert 'tests/test_a5_v173_ci_admission_integrity.py' in entries
    assert len([p for p in entries if p.startswith('assets/')]) == 288
    assert len([p for p in entries if p.startswith('scripts/')]) == 7


def test_yaml_workflow_has_ordered_non_deploying_qualifications():
    yaml = pytest.importorskip('yaml')
    doc = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    steps = doc['jobs']['qualify']['steps']
    names = [step.get('name', step.get('uses', '')) for step in steps]
    assert names[0] == 'actions/checkout@v4'
    assert names.index('Verify exact integrated seven-world source before installing Godot') < names.index('Install pinned Godot 4.7.2 and display dependencies')
    assert names.index('21 full matches through production AI and move handlers') < names.index('Capture 14 actual rendered frames at 746x280')
    assert names.index('Capture 14 actual rendered frames at 746x280') < names.index('Capture 14 actual rendered frames at 844x390')
    assert names[-2:] == ['Evidence disposition (never auto-accept visual or real-touch parity)', 'Upload exact native evidence for independent review']
    assert doc['permissions'] == {'contents': 'read'}
