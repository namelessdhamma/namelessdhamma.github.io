"""A5 v63: exact-source Gods silhouettes strictly grow in visible width, height and area.
Offline raster qualification only; no Godot engine/render or touch PASS is asserted.
"""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'assets'
FAMILIES = {
    'a5_void_ranked': 'void', 'a5_pirate_ranked': 'pirate',
    'a5_atlantis_ranked': 'atlantis', 'a5_gods_ranked': 'gods',
    'a5_sand_ranked': 'sand', 'a5_night_ranked': 'night',
    'a5_northern_ranked': 'north',
}
GODS_SOURCE = '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'


def metric(path):
    rgba = np.asarray(Image.open(path).convert('RGBA'))
    assert rgba.shape[:2] == (128, 128)
    a = rgba[:, :, 3] > 100
    yy, xx = np.where(a)
    return {'width': int(xx.max()-xx.min()+1), 'height': int(yy.max()-yy.min()+1),
            'area': int(a.sum()), 'bounds': (int(xx.min()), int(yy.min()), int(xx.max()+1), int(yy.max()+1))}


class GodsFullGrowth(unittest.TestCase):
    def test_01_canonical_gods_source_immutable(self):
        source = ART / 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), GODS_SOURCE)
        self.assertEqual(Image.open(source).size, (1672, 941))

    def test_01b_all_seven_approved_reference_hashes(self):
        manifest = json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        sources = {
            'nd_premium_void': 'a5_void_ranked/01_nd_premium_void_canon_source.png',
            'pirate_sea': 'a5_pirate_ranked/02_pirate_sea_canon_source.png',
            'atlantis': 'a5_atlantis_ranked/03_atlantis_canon_source.png',
            'gods_of_the_deep': 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
            'sand_sea': 'a5_sand_ranked/05_sand_sea_canon_source.png',
            'night_sea': 'a5_night_ranked/06_night_sea_canon_source.png',
            'northern_sea': 'a5_northern_ranked/07_northern_sea_canon_source.png',
        }
        for entry in manifest['images']:
            source = ART / sources[entry['world']]
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), entry['sha256'])

    def test_02_all_fourteen_rank_families_width_height_area_strict(self):
        for folder, prefix in FAMILIES.items():
            for player in (1, 2):
                values = [metric(ART / folder / f'{prefix}_rank_{r:02d}_p{player}.png') for r in range(1, 10)]
                for dimension in ('width', 'height', 'area'):
                    sizes = [v[dimension] for v in values]
                    self.assertTrue(all(a < b for a, b in zip(sizes, sizes[1:])),
                                    f'{folder} player {player} {dimension}: {sizes}')

    def test_03_prior_gods_height_regressions_resolved(self):
        # Independent measurements of the v62 source sprites at alpha >100.
        previous = [47, 62, 56, 66, 73, 70, 87, 83, 78]
        self.assertTrue(any(a >= b for a, b in zip(previous, previous[1:])))
        for player in (1, 2):
            current = [metric(ART / 'a5_gods_ranked' / f'gods_rank_{r:02d}_p{player}.png')['height'] for r in range(1, 10)]
            self.assertTrue(all(a < b for a, b in zip(current, current[1:])))
            self.assertGreater(current[8], previous[8])

    def test_04_all_creatures_distinct_and_uncropped(self):
        for player in (1, 2):
            digests = set()
            for rank in range(1, 10):
                path = ART / 'a5_gods_ranked' / f'gods_rank_{rank:02d}_p{player}.png'
                digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
                x0, y0, x1, y1 = metric(path)['bounds']
                self.assertGreaterEqual(x0, 1)
                self.assertGreaterEqual(y0, 1)
                self.assertLessEqual(x1, 127)
                self.assertLessEqual(y1, 127)
            self.assertEqual(len(digests), 9)

    def test_05_manifest_hashes_and_dimensions_match_files(self):
        manifest = json.loads((ART / 'a5_gods_ranked/asset_manifest.json').read_text())
        self.assertEqual(manifest['source_sha256'], GODS_SOURCE)
        self.assertEqual(len(manifest['assets']), 18)
        self.assertIn('width, height and area', manifest['rank_growth_policy'])
        for item in manifest['assets']:
            path = ART / 'a5_gods_ranked' / item['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
            m = metric(path)
            self.assertEqual((m['width'], m['height'], m['area']),
                             (item['visible_width'], item['visible_height'], item['alpha_area_gt100']))

    def test_06_rebuild_idempotent(self):
        directory = ART / 'a5_gods_ranked'
        files = sorted(directory.glob('gods_rank_*_p*.png')) + [directory/'asset_manifest.json', directory/'gods_ranked_preview.jpg']
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        run = subprocess.run([sys.executable, str(ROOT/'tools/build_gods_ranked_assets.py')],
                             capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stdout + '\n' + run.stderr)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        self.assertEqual(before, after)

    def test_07_live_gameplay_and_ranks_not_baked(self):
        main = (ROOT/'scripts/main.gd').read_text()
        visual = (ROOT/'scripts/world_visuals.gd').read_text()
        self.assertIn('rank.text = str(int(top.rank))', main)
        self.assertIn('number.text = str(rank) if rank > 0 else ""', main)
        self.assertIn('gods_rank_%02d_p%d.png', visual)
        self.assertIn('tile.texture = art.texture', main)
        self.assertIn('call_deferred("_play_ai_turn")', main)


if __name__ == '__main__':
    unittest.main(verbosity=2)
