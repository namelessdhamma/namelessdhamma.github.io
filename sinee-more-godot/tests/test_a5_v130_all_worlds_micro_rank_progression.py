"""A5 v130: 7-world source-loaded rank silhouettes at phone micro-raster sizes.

Offline pixel evidence, NOT native Godot render or real-touch acceptance.
"""
from pathlib import Path
import hashlib
import json

from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
WORLDS = [
    ('a5_void_ranked', 'void'),
    ('a5_pirate_ranked', 'pirate'),
    ('a5_atlantis_ranked', 'atlantis'),
    ('a5_gods_ranked', 'gods'),
    ('a5_sand_ranked', 'sand'),
    ('a5_night_ranked', 'night'),
    ('a5_northern_runed', 'north_runed'),
]
SIZES = (12, 14, 16, 18, 20, 22, 24, 28, 32)


def test_all_126_live_rank_textures_are_strictly_increasing_at_nine_rasters():
    for folder, prefix in WORLDS:
        for player in (1, 2):
            images = [Image.open(ASSETS / folder / f'{prefix}_rank_{rank:02d}_p{player}.png').convert('RGBA')
                      for rank in range(1, 10)]
            assert all(image.size == (128, 128) for image in images)
            for raster in SIZES:
                areas = [int(np.count_nonzero(np.asarray(image.getchannel('A').resize(
                    (raster, raster), Image.Resampling.LANCZOS)) > 100)) for image in images]
                assert all(a < b for a, b in zip(areas, areas[1:])), (folder, player, raster, areas)


def test_gods_manifest_hashes_and_strict_native_footprints():
    manifest = json.loads((ASSETS / 'a5_gods_ranked/asset_manifest.json').read_text())
    assert len(manifest['assets']) == 18
    for player in (1, 2):
        rows = sorted((row for row in manifest['assets'] if row['player'] == player),
                      key=lambda row: row['rank'])
        assert [row['rank'] for row in rows] == list(range(1, 10))
        for key in ('visible_width', 'visible_height', 'alpha_area_gt100'):
            assert all(a[key] < b[key] for a, b in zip(rows, rows[1:])), (player, key)
        for row in rows:
            path = ASSETS / 'a5_gods_ranked' / row['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
            alpha = np.asarray(Image.open(path).convert('RGBA').getchannel('A'))
            assert int(np.count_nonzero(alpha > 100)) == row['alpha_area_gt100']


def test_approved_reference_pngs_unchanged_and_separate_from_live_sprites():
    canon = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    assert len(canon['images']) == 7
    for row in canon['images']:
        paths = list(ASSETS.rglob(row['file'].replace('.png', '_canon_source.png')))
        assert len(paths) == 1, row['file']
        assert hashlib.sha256(paths[0].read_bytes()).hexdigest() == row['sha256']
    world_visuals = (ROOT / 'scripts/world_visuals.gd').read_text()
    for rank in (5, 8):
        for player in (1, 2):
            assert (ASSETS / f'a5_gods_ranked/gods_rank_{rank:02d}_p{player}.png').is_file()
    assert 'a5_gods_ranked/gods_rank_%02d_p%d.png' in world_visuals
    main = (ROOT / 'scripts/main.gd').read_text()
    assert 'number.text = str(rank) if rank > 0 else ""' in main
    assert 'rank.text = str(int(top.rank))' in main
