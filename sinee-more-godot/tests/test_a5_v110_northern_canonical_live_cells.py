"""A5 v110: immutable-canon source oracle; NOT evidence of native gameplay."""
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'assets/a5_reference_cells/north'
SOURCE = ROOT / 'assets/a5_northern_ranked/07_northern_sea_canon_source.png'
BUILDER = ROOT / 'tools/build_northern_empty_cells.py'
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
MAN = json.loads((ART/'asset_manifest.json').read_text())
CANON_SHA = '3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775'

def test_source_locked_and_not_overwritten():
    assert SHA(SOURCE) == MAN['source_sha256'] == CANON_SHA
    assert MAN['version'] == 'A5-v110' and MAN['world'] == 'northern_sea'
    assert MAN['source_size'] == [1672,941]

def test_two_unoccupied_reference_donors_only():
    assert set(MAN['donors']) == {'top_middle','bottom_left'}
    assert all(r['empty_source_cell'] in MAN['donors'] and not r['occupied_reference_cell_baked'] for r in MAN['assets'])
    assert 'no figures, ranks, UI or occupancy' in MAN['purpose']

def test_nine_distinct_upright_rune_circles():
    assert len(MAN['assets']) == 9
    assert [r['cell'] for r in MAN['assets']] == list(range(9))
    assert len({r['sha256'] for r in MAN['assets']}) == 9
    assert all(r['rotation_ccw_quarters'] == 0 for r in MAN['assets'])
    for r in MAN['assets']:
        p=ART/r['file'];assert SHA(p)==r['sha256']
        with Image.open(p) as img:assert img.size==(192,192) and img.mode=='RGB'

def test_exact_donor_projection_oracle():
    ns = runpy.run_path(str(BUILDER))
    with Image.open(SOURCE) as img: src=np.asarray(img.convert('RGB'))
    for r in MAN['assets']:
        with Image.open(ART/r['file']) as img: actual=np.asarray(img)
        assert np.array_equal(actual,ns['extract'](src,r['empty_source_cell'],r['inset']))

def test_center_dark_no_baked_tokens():
    for r in MAN['assets']:
        arr=np.asarray(Image.open(ART/r['file']).convert('RGB'))
        center=arr[66:126,66:126]
        luminous=((center.max(axis=2)>220)&((center.max(axis=2)-center.min(axis=2))>80)).mean()
        assert luminous < 0.07, r['file']

def test_builder_deterministic_and_canon_immutable():
    files=[ART/f'cell_{i:02d}.png' for i in range(9)]+[ART/'asset_manifest.json',ART/'northern_empty_cells_preview.jpg']
    before={p.name:SHA(p) for p in files}
    subprocess.run([sys.executable,str(BUILDER)],check=True,capture_output=True,timeout=20)
    assert before=={p.name:SHA(p) for p in files}
    assert SHA(SOURCE)==CANON_SHA

def test_shared_live_board_uses_northern_cell_atlas():
    world=(ROOT/'scripts/world_visuals.gd').read_text()
    main=(ROOT/'scripts/main.gd').read_text()
    assert '"night", "north"' in world
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in world
    assert 'tile.texture = art.texture' in main
    assert 'PerspectiveGeometry.cell_at(current_world, mouse.position, perspective_rect)' in main

def test_native_smoke_exists_but_is_not_claimed_passed():
    smoke=(ROOT/'tests/a5_v110_northern_canonical_cells_runtime_smoke.gd').read_text()
    for token in ['_set_world", 6', 'perspective_tiles', 'board_stacks', 'reserve_available',
                  '_on_cell_pressed", 1', 'A5_V110_NORTH_CANON_PASS']:
        assert token in smoke

def test_all_seven_reference_png_sha_unchanged():
    for path,sha in [
        ('a5_void_ranked/01_nd_premium_void_canon_source.png','00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'),
        ('a5_pirate_ranked/02_pirate_sea_canon_source.png','0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1'),
        ('a5_atlantis_ranked/03_atlantis_canon_source.png','2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'),
        ('a5_gods_ranked/04_gods_of_the_deep_canon_source.png','10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'),
        ('a5_sand_ranked/05_sand_sea_canon_source.png','01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'),
        ('a5_night_ranked/06_night_sea_canon_source.png','ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'),
        ('a5_northern_ranked/07_northern_sea_canon_source.png',CANON_SHA),
    ]:
        assert SHA(ROOT/'assets'/path)==sha
