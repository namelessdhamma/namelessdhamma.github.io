"""A5 v109 source-locked live Night Sea cells; offline evidence only."""
from __future__ import annotations
import hashlib,json,runpy,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/night'
SOURCE=ROOT/'assets/a5_night_ranked/06_night_sea_canon_source.png'
BUILDER=ROOT/'tools/build_night_canonical_live_cells.py'
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
MANIFEST=json.loads((ART/'asset_manifest.json').read_text())

def test_approved_reference_is_sha_locked():
    assert MANIFEST['version']=='A5-v109' and MANIFEST['world']=='night_sea'
    assert SHA(SOURCE)==MANIFEST['source_sha256']=='ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'
    assert MANIFEST['source_size']==[1672,941]

def test_only_unoccupied_donors_no_baked_beacon():
    # The screenshot's middle-right nominally empty cell contains an overhanging
    # beacon from the occupied lower-right cell. Exclude it completely.
    assert MANIFEST['donor_cells']==[1,6]
    assert set(MANIFEST['donor_quads'])=={'1','6'}
    assert MANIFEST['donor_quads']['1'][2][1]<=365
    assert all(r['donor_empty_cell'] in {1,6} and not r['occupied_reference_cell_baked']
               for r in MANIFEST['cells'])

def test_nine_unique_upright_live_textures():
    assert len(MANIFEST['cells'])==9
    seen=set()
    for i,rec in enumerate(MANIFEST['cells']):
        assert rec['cell']==i and rec['turns_ccw']==0
        path=ART/rec['file'];assert SHA(path)==rec['sha256']
        with Image.open(path) as im: assert im.size==(192,192) and im.mode=='RGB'
        seen.add(rec['sha256'])
    assert len(seen)==9

def test_exact_source_pixel_extraction():
    ns=runpy.run_path(str(BUILDER))
    with Image.open(SOURCE) as im:source=np.asarray(im.convert('RGB'))
    for rec in MANIFEST['cells']:
        with Image.open(ART/rec['file']) as im:actual=np.asarray(im)
        assert np.array_equal(actual,ns['extract'](source,rec['donor_empty_cell'],rec['inset']))

def test_deterministic_builder_does_not_touch_canon():
    files=[ART/f'cell_{i:02d}.png' for i in range(9)]+[ART/'asset_manifest.json',ART/'night_empty_cells_preview.jpg']
    before={p.name:SHA(p) for p in files}
    subprocess.run([sys.executable,str(BUILDER)],capture_output=True,check=True)
    assert before=={p.name:SHA(p) for p in files}
    assert SHA(SOURCE)==MANIFEST['source_sha256']

def test_shared_godot_live_texture_not_flat_screenshot():
    visuals=(ROOT/'scripts/world_visuals.gd').read_text()
    main=(ROOT/'scripts/main.gd').read_text()
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in visuals
    assert '"pirate", "atlantis", "gods", "sand", "night", "north"' in visuals
    assert 'tile.texture = art.texture' in main
    assert '_on_cell_pressed(index)' in main

def test_native_fixture_guards_live_move_and_occupancy():
    p=ROOT/'tests/a5_v109_night_canonical_cells_runtime_smoke.gd'
    s=p.read_text()
    for needle in ['_set_world", 5','projected[i].texture != art.texture',
                   'board_stacks','reserve_available','_on_cell_pressed", 2',
                   'A5_V109_NIGHT_CANON_PASS']:
        assert needle in s

def test_prior_four_world_manifest_hashes_unchanged():
    for world,version in [('pirate','A5-v105'),('gods','A5-v106'),('sand','A5-v107'),('atlantis','A5-v108')]:
        folder=ROOT/'assets/a5_reference_cells'/world
        manifest=json.loads((folder/'asset_manifest.json').read_text())
        assert manifest['version']==version
        for rec in manifest['cells']:
            assert SHA(folder/rec['file'])==rec['sha256']
