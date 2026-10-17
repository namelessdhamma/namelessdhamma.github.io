"""A5 v108: Atlantis live source-derived, unoccupied, upright cell art."""
from __future__ import annotations
import hashlib,json,runpy,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/atlantis'
SOURCE=ROOT/'assets/a5_atlantis_ranked/03_atlantis_canon_source.png'
BUILDER=ROOT/'tools/build_atlantis_canonical_live_cells.py'
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
M=json.loads((ART/'asset_manifest.json').read_text())

def test_source_locked_and_nine_distinct_tiles():
    assert M['version']=='A5-v108' and M['world']=='atlantis'
    assert SHA(SOURCE)==M['source_sha256']=='2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'
    assert M['donor_cells']==[1,5,6] and len(M['cells'])==9
    seen=set()
    for i,rec in enumerate(M['cells']):
        assert rec['cell']==i and rec['turns_ccw']==0
        assert rec['occupied_reference_cell_baked'] is False
        assert rec['donor_empty_cell'] in {1,5,6}
        path=ART/rec['file']; assert SHA(path)==rec['sha256']
        with Image.open(path) as im: assert im.size==(192,192) and im.mode=='RGB'
        seen.add(rec['sha256'])
    assert len(seen)==9

def test_only_safe_top_edges_are_used_from_partial_donors():
    builder=runpy.run_path(str(BUILDER))
    with Image.open(SOURCE) as im: source=np.asarray(im.convert('RGB'))
    for rec in M['cells']:
        i=rec['cell']; donor=rec['donor_empty_cell']; inset=rec['inset']
        with Image.open(ART/rec['file']) as im: actual=np.asarray(im)
        assert np.array_equal(actual,builder['empty_tile'](source,donor,inset))
        if donor in {1,5}:
            # A baked pyramid occupies the lower part of donor 1/5.
            # Every output pixel below y=48 MUST instead come from
            # the genuinely unoccupied donor 6, byte for byte.
            safe=builder['extract'](source,6,inset)
            assert np.array_equal(actual[48:],safe[48:])
            assert rec['source_upper_only'] is True
            assert rec['safe_upper_end']==22
        else:
            assert rec['source_upper_only'] is False

def test_shared_runtime_loader_and_live_occupancy():
    visual=(ROOT/'scripts/world_visuals.gd').read_text()
    main=(ROOT/'scripts/main.gd').read_text()
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in visual
    assert 'tile.texture = art.texture' in main
    assert '_on_cell_pressed(index)' in main
    assert (ROOT/'tests/a5_v108_atlantis_canonical_cells_runtime_smoke.gd').exists()

def test_builder_deterministic_and_dispatch_safe():
    files=[ART/f'cell_{i:02d}.png' for i in range(9)]+[ART/'asset_manifest.json',ART/'atlantis_empty_cells_preview.jpg']
    before={p.name:SHA(p) for p in files}
    subprocess.run([sys.executable,str(BUILDER)],capture_output=True,check=True)
    assert before=={p.name:SHA(p) for p in files}
    trio=(ROOT/'tools/build_reference_empty_cells_trio.py').read_text()
    assert "if name == 'atlantis':" in trio
    assert 'build_atlantis_canonical_live_cells.py' in trio

def test_other_recent_canonical_art_unchanged():
    for world,version in [('pirate','A5-v105'),('gods','A5-v106'),('sand','A5-v107')]:
        folder=ROOT/'assets/a5_reference_cells'/world
        manifest=json.loads((folder/'asset_manifest.json').read_text())
        assert manifest['version']==version
        for rec in manifest['cells']:
            assert SHA(folder/rec['file'])==rec['sha256']

def test_native_fixture_checks_actual_placement():
    text=(ROOT/'tests/a5_v108_atlantis_canonical_cells_runtime_smoke.gd').read_text()
    for term in ['_set_world", 2','projected[i].texture != art.texture','board_stacks',
                 'reserve_available','_on_cell_pressed", 2','A5_V108_ATLANTIS_CANON_PASS']:
        assert term in text
