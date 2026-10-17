"""A5 v64: source-derived ranks remain ordered after phone-scale rasterization.

Offline sprite/render approximation only: this is not a Godot build, physical
phone touch test, or visual-parity acceptance of the seven playable worlds.
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
ASSETS = ROOT / 'assets'
FAMILIES = {
    'void': 'a5_void_ranked', 'pirate': 'a5_pirate_ranked',
    'atlantis': 'a5_atlantis_ranked', 'gods': 'a5_gods_ranked',
    'sand': 'a5_sand_ranked', 'night': 'a5_night_ranked',
    'north': 'a5_northern_ranked',
}
SIZES = (22, 24, 26, 28, 30, 31, 32, 34, 36, 40, 44, 48)


def area(path, pixels):
    image = Image.open(path).convert('RGBA').resize((pixels, pixels), Image.Resampling.LANCZOS)
    return int((np.asarray(image)[:, :, 3] > 100).sum())


class PhoneRankGrowth(unittest.TestCase):
    def test_01_seven_worlds_two_sides_strict_on_12_live_sizes(self):
        for prefix, folder in FAMILIES.items():
            for player in (1, 2):
                for pixels in SIZES:
                    areas = [area(ASSETS / folder / f'{prefix}_rank_{r:02d}_p{player}.png', pixels)
                             for r in range(1, 10)]
                    self.assertTrue(all(a < b for a, b in zip(areas, areas[1:])),
                                    f'{prefix} p{player} {pixels}px: {areas}')

    def test_02_exact_seven_canon_source_hashes(self):
        source_map = {
            'nd_premium_void': 'a5_void_ranked/01_nd_premium_void_canon_source.png',
            'pirate_sea': 'a5_pirate_ranked/02_pirate_sea_canon_source.png',
            'atlantis': 'a5_atlantis_ranked/03_atlantis_canon_source.png',
            'gods_of_the_deep': 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
            'sand_sea': 'a5_sand_ranked/05_sand_sea_canon_source.png',
            'night_sea': 'a5_night_ranked/06_night_sea_canon_source.png',
            'northern_sea': 'a5_northern_ranked/07_northern_sea_canon_source.png',
        }
        manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        for item in manifest['images']:
            self.assertEqual(hashlib.sha256((ASSETS / source_map[item['world']]).read_bytes()).hexdigest(),
                             item['sha256'])

    def test_03_rank7_change_does_not_replace_distinct_creatures(self):
        folder = ASSETS / 'a5_gods_ranked'
        manifest = json.loads((folder / 'asset_manifest.json').read_text())
        self.assertEqual(len(manifest['assets']), 18)
        for player in (1, 2):
            digests = set()
            for rank in range(1, 10):
                path = folder / f'gods_rank_{rank:02d}_p{player}.png'
                digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
                item = next(x for x in manifest['assets'] if x['rank'] == rank and x['player'] == player)
                self.assertEqual(item['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(len(digests), 9)
            for pixels in (22, 26, 34, 44):
                r6, r7, r8 = [area(folder / f'gods_rank_{r:02d}_p{player}.png', pixels)
                              for r in (6, 7, 8)]
                self.assertLess(r6, r7)
                self.assertLess(r7, r8)

    def test_04_deterministic_rebuild_and_shared_live_binding(self):
        folder = ASSETS / 'a5_gods_ranked'
        paths = sorted(folder.glob('gods_rank_*_p*.png')) + [folder/'asset_manifest.json',
                                                             folder/'gods_ranked_preview.jpg']
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        run = subprocess.run([sys.executable, str(ROOT / 'tools/build_gods_ranked_assets.py')],
                             capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        main = (ROOT / 'scripts/main.gd').read_text()
        visuals = (ROOT / 'scripts/world_visuals.gd').read_text()
        self.assertIn('world_visuals.piece_texture(current_world,', main)
        self.assertIn('gods_rank_%02d_p%d.png', visuals)
        self.assertIn('rank.text = str(int(top.rank))', main)


if __name__ == '__main__':
    unittest.main(verbosity=2)
