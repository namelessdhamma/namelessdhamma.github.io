"""Portable A5 v106 acceptance: Gods 3 exact empty motifs, live gameplay."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'assets/a5_reference_cells/gods'
SOURCE = ROOT / 'assets/a5_gods_ranked/04_gods_of_the_deep_canon_source.png'
BUILDER = ROOT / 'tools/build_gods_canonical_live_cells.py'
MANIFEST = json.loads((ART / 'asset_manifest.json').read_text())
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def test_immutable_accepted_gods_reference():
    assert SHA(SOURCE) == MANIFEST['source_sha256']
    assert MANIFEST['source_sha256'] == '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'
    assert MANIFEST['source_size'] == [1672, 941]


def test_actual_three_empty_canonical_motifs_not_two_rotated_donors():
    assert MANIFEST['version'] == 'A5-v106'
    assert MANIFEST['donor_cells'] == [1, 5, 6]
    assert MANIFEST['canonical_empty_motifs'] == {'1': 'spiral', '5': 'trident', '6': 'eye'}
    assert len(MANIFEST['cells']) == 9
    for index, symbol in [(1, 'spiral'), (5, 'trident'), (6, 'eye')]:
        record = MANIFEST['cells'][index]
        assert record['reference_cell_is_empty'] is True
        assert record['donor_empty_cell'] == index
        assert record['donor_symbol'] == symbol
        assert record['turns_ccw'] == 0


def test_nine_distinct_tiles_and_no_baked_occupied_screenshot():
    hashes = set()
    for i, record in enumerate(MANIFEST['cells']):
        assert record['cell'] == i
        assert record['donor_empty_cell'] in {1, 5, 6}
        assert record['occupied_reference_cell_baked'] is False
        assert record['turns_ccw'] == 0
        file = ART / f'cell_{i:02d}.png'
        assert SHA(file) == record['sha256']
        with Image.open(file) as im:
            assert im.size == (192, 192) and im.mode == 'RGB'
        hashes.add(record['sha256'])
    assert len(hashes) == 9


def test_spiral_uses_real_source_art_and_adjacent_piece_spill_is_repaired():
    import runpy
    code = runpy.run_path(str(BUILDER))
    with Image.open(SOURCE) as im:
        src = np.array(im.convert('RGB'))
    original = code['extract'](src, 1, .82)
    with Image.open(ART / 'cell_01.png') as im:
        actual = np.array(im)
    assert np.array_equal(actual[:122], original[:122])
    assert not np.array_equal(actual[146:], original[146:])
    assert MANIFEST['cells'][1]['reference_spill_repaired'] is True
    assert MANIFEST['cells'][1]['sha256'] != 'c943a3c9099457e40a9362e76e522d0028acc632e75611d5089567b0fe329328'


def test_actual_godot_world_routes_to_live_dynamic_cells_and_native_smoke():
    visuals = (ROOT / 'scripts/world_visuals.gd').read_text()
    main = (ROOT / 'scripts/main.gd').read_text()
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in visuals
    assert '"pirate", "atlantis", "gods"' in visuals
    assert 'tile.texture = art.texture' in main
    assert '_on_cell_pressed(index)' in main
    assert (ROOT / 'tests/a5_v106_gods_live_canonical_cells_smoke.gd').exists()


def test_legacy_rebuild_entrypoint_preserves_new_gods_canon():
    text = (ROOT / 'tools/build_reference_empty_cells_trio.py').read_text()
    assert "if name == 'gods':" in text
    assert 'build_gods_canonical_live_cells.py' in text


def test_builder_idempotence_and_canon_immutability():
    files = [ART / f'cell_{i:02d}.png' for i in range(9)]
    files += [ART / 'asset_manifest.json', ART / 'gods_empty_cells_preview.jpg']
    before = {p.name: SHA(p) for p in files}
    source_sha = SHA(SOURCE)
    subprocess.run([sys.executable, str(BUILDER)], capture_output=True, text=True, check=True)
    assert before == {p.name: SHA(p) for p in files}
    assert SHA(SOURCE) == source_sha
