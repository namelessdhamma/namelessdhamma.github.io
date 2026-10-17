"""A5 v107 Sand: source-locked motifs at their actual playable cells."""
from __future__ import annotations
import hashlib,json,runpy,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/sand'
SOURCE=ROOT/'assets/a5_sand_ranked/05_sand_sea_canon_source.png'
BUILDER=ROOT/'tools/build_sand_canonical_live_cells.py'
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
MANIFEST=json.loads((ART/'asset_manifest.json').read_text())

def test_approved_sand_source_is_unchanged():
    assert SHA(SOURCE)==MANIFEST['source_sha256']=='01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'
    assert MANIFEST['source_size']==[1672,941]

def test_three_genuinely_empty_motifs_in_canonical_positions():
    assert MANIFEST['version']=='A5-v107'
    assert MANIFEST['donor_cells']==[2,4,6]
    assert MANIFEST['canonical_empty_motifs']=={'2':'sun','4':'ankh','6':'eye_of_horus'}
    for i,motif in [(2,'sun'),(4,'ankh'),(6,'eye_of_horus')]:
        rec=MANIFEST['cells'][i]
        assert rec['donor_empty_cell']==i
        assert rec['donor_symbol']==motif
        assert rec['reference_cell_is_empty'] is True
        assert rec['turns_ccw']==0

def test_nine_distinct_source_derived_empty_tiles():
    assert len(MANIFEST['cells'])==9
    seen=set()
    for i,rec in enumerate(MANIFEST['cells']):
        assert rec['cell']==i
        assert rec['donor_empty_cell'] in {2,4,6}
        assert rec['occupied_reference_cell_baked'] is False
        assert rec['turns_ccw']==0
        p=ART/f'cell_{i:02d}.png'
        assert SHA(p)==rec['sha256']
        with Image.open(p) as im:
            assert im.size==(192,192) and im.mode=='RGB'
        seen.add(rec['sha256'])
    assert len(seen)==9

def test_source_extraction_matches_actual_unoccupied_cells():
    builder=runpy.run_path(str(BUILDER))
    with Image.open(SOURCE) as im:
        pixels=np.asarray(im.convert('RGB'))
    for i in (2,4,6):
        expected=builder['extract'](pixels,i,MANIFEST['cells'][i]['inset'])
        with Image.open(ART/f'cell_{i:02d}.png') as im:
            assert np.array_equal(np.asarray(im),expected)

def test_visuals_are_live_and_game_state_is_not_baked():
    visuals=(ROOT/'scripts/world_visuals.gd').read_text()
    main=(ROOT/'scripts/main.gd').read_text()
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in visuals
    assert 'tile.texture = art.texture' in main
    assert '_on_cell_pressed(index)' in main
    assert (ROOT/'tests/a5_v107_sand_canonical_cells_runtime_smoke.gd').exists()

def test_previous_gods_pirate_art_remains_unmodified():
    for folder,version in [('pirate','A5-v105'),('gods','A5-v106')]:
        m=json.loads((ROOT/'assets/a5_reference_cells'/folder/'asset_manifest.json').read_text())
        assert m['version']==version
        for rec in m['cells']:
            assert SHA(ROOT/'assets/a5_reference_cells'/folder/rec['file'])==rec['sha256']

def test_builder_is_deterministic_and_preserves_canon():
    files=[ART/f'cell_{i:02d}.png' for i in range(9)]+[ART/'asset_manifest.json',ART/'sand_empty_cells_preview.jpg']
    before={p.name:SHA(p) for p in files}
    subprocess.run([sys.executable,str(BUILDER)],capture_output=True,text=True,check=True)
    assert before=={p.name:SHA(p) for p in files}
    assert SHA(SOURCE)==MANIFEST['source_sha256']

def test_native_fixture_has_legal_placement_and_state_preservation_guards():
    smoke=(ROOT/'tests/a5_v107_sand_canonical_cells_runtime_smoke.gd').read_text()
    for needle in ['_set_world", 4','projected[i].texture != art.texture',
                   'board_stacks','reserve_available','_on_cell_pressed", 2',
                   'A5_V107_SAND_CANON_PASS']:
        assert needle in smoke
