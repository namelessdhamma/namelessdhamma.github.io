"""v111: offline oracle and native-smoke presence; NOT Godot gameplay proof."""
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/void'
SOURCE=ROOT/'assets/a5_void_ranked/01_nd_premium_void_canon_source.png'
BUILDER=ROOT/'tools/build_void_empty_cells.py'
MAN=json.loads((ART/'asset_manifest.json').read_text())
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CANON='00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'

def test_source_is_immutable_exact_approved_void_png():
    assert SHA(SOURCE)==CANON==MAN['source_sha256']
    assert MAN['version']=='A5-v111' and MAN['world']=='nd_premium_void'
    assert MAN['source_size']==[1672,941]

def test_only_two_unoccupied_donors_and_no_baked_figures():
    assert MAN['donors']==['top_middle','middle_middle_compass']
    assert 'no figures, ranks, UI or occupancy' in MAN['purpose']
    assert all(not a['occupied_reference_cell_baked'] for a in MAN['assets'])
    assert all(set(a['empty_donors']).issubset(set(MAN['donors'])) for a in MAN['assets'])

def test_nine_unique_upright_source_derived_tiles():
    assert [a['cell'] for a in MAN['assets']]==list(range(9))
    assert len({a['sha256'] for a in MAN['assets']})==9
    for a in MAN['assets']:
        p=ART/a['file'];assert SHA(p)==a['sha256']
        assert a['rotation_ccw_quarters']==0
        with Image.open(p) as im:assert im.size==(192,192) and im.mode=='RGB'

def test_no_baked_white_rank_glyphs_or_glass_domes():
    for a in MAN['assets']:
        arr=np.asarray(Image.open(ART/a['file']).convert('RGB'))
        neutral_white=((arr.min(axis=2)>200)&((arr.max(axis=2)-arr.min(axis=2))<35)).mean()
        assert neutral_white<0.035,a['file']

def test_compass_only_in_live_center_tile():
    assert MAN['assets'][4]['empty_donors']==['top_middle','middle_middle_compass']
    assert all(a['empty_donors']==['top_middle'] for i,a in enumerate(MAN['assets']) if i!=4)

def test_builder_is_deterministic_and_does_not_mutate_canon():
    tracked=[ART/f'cell_{i:02d}.png' for i in range(9)]+[ART/'asset_manifest.json',ART/'void_empty_cells_preview.jpg']
    before={p.name:SHA(p) for p in tracked}
    subprocess.run([sys.executable,str(BUILDER)],check=True,capture_output=True,timeout=25)
    assert before=={p.name:SHA(p) for p in tracked}
    assert SHA(SOURCE)==CANON

def test_shared_seven_world_loader_and_real_perspective_binding():
    world=(ROOT/'scripts/world_visuals.gd').read_text()
    main=(ROOT/'scripts/main.gd').read_text()
    assert 'var folders := ["void", "pirate", "atlantis", "gods", "sand", "night", "north"]' in world
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in world
    assert 'chart.visible = world >= 0 and world <= 6' in world
    assert 'tile.texture = art.texture' in main
    assert '_run_headless_void_canonical_cells_smoke()' in main
    assert 'BLUE_SEA_VOID_EMPTY_CANONICAL_CELLS_PASS' in main

def test_void_floats_without_support_while_other_six_are_grounded():
    main=(ROOT/'scripts/main.gd').read_text()
    world=(ROOT/'scripts/world_visuals.gd').read_text()
    assert 'var has_support := current_world != 0' in main
    assert 'support.visible = world != 0' in world
    assert 'foundation.texture = null' in world

def test_all_seven_approved_source_hashes_unchanged():
    expected=[
      ('a5_void_ranked/01_nd_premium_void_canon_source.png',CANON),
      ('a5_pirate_ranked/02_pirate_sea_canon_source.png','0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1'),
      ('a5_atlantis_ranked/03_atlantis_canon_source.png','2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'),
      ('a5_gods_ranked/04_gods_of_the_deep_canon_source.png','10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'),
      ('a5_sand_ranked/05_sand_sea_canon_source.png','01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'),
      ('a5_night_ranked/06_night_sea_canon_source.png','ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'),
      ('a5_northern_ranked/07_northern_sea_canon_source.png','3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775')]
    for path,sha in expected:assert SHA(ROOT/'assets'/path)==sha
