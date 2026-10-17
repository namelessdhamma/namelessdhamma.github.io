"""A5 v124: improve actual live Gods rank-7 creature separation at phone sizes.

Asset-level oracle only. A Godot render and physical touch are not claimed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'assets/a5_gods_ranked'


def alpha(path: Path, pixels: int = 128) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert('RGBA').resize((pixels, pixels), Image.Resampling.LANCZOS))[:, :, 3]


def area(path: Path, pixels: int) -> int:
    return int(np.count_nonzero(alpha(path, pixels) > 100))


class GodsMobileRank7Separation(unittest.TestCase):
    def test_01_both_sides_mobile_rank7_clearly_above_rank6(self):
        for player in (1, 2):
            paths = [ART / f'gods_rank_{rank:02d}_p{player}.png' for rank in (6, 7, 8)]
            for pixels in (22, 28, 36, 44):
                a6, a7, a8 = [area(path, pixels) for path in paths]
                self.assertGreater(a7, a6, (player, pixels, a6, a7))
                self.assertGreater(a8, a7, (player, pixels, a7, a8))
                self.assertGreaterEqual(a7 / a6, 1.10, (player, pixels, a6, a7))
            self.assertGreaterEqual(area(paths[1], 22), 127)
            self.assertEqual(area(paths[0], 22), 113)

    def test_02_full_native_silhouette_remains_monotonic_and_inside_canvas(self):
        for player in (1, 2):
            measurements = []
            for rank in range(1, 10):
                path = ART / f'gods_rank_{rank:02d}_p{player}.png'
                a = alpha(path)
                ys, xs = np.where(a > 100)
                measurements.append((int(xs.max() - xs.min() + 1),
                                     int(ys.max() - ys.min() + 1), int(len(xs))))
                self.assertGreaterEqual(int(xs.min()), 1)
                self.assertGreaterEqual(int(ys.min()), 1)
                self.assertLessEqual(int(xs.max()), 126)
                self.assertLessEqual(int(ys.max()), 126)
            for dimension in range(3):
                sequence = [item[dimension] for item in measurements]
                self.assertTrue(all(a < b for a, b in zip(sequence, sequence[1:])),
                                (player, dimension, sequence))

    def test_03_only_source_derived_creatures_and_live_ranks(self):
        manifest = json.loads((ART / 'asset_manifest.json').read_text())
        self.assertEqual(len(manifest['assets']), 18)
        for item in manifest['assets']:
            path = ART / item['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
        main = (ROOT / 'scripts/main.gd').read_text()
        visual = (ROOT / 'scripts/world_visuals.gd').read_text()
        self.assertIn('gods_rank_%02d_p%d.png', visual)
        self.assertIn('world_visuals.piece_texture(current_world,', main)
        self.assertIn('rank.text = str(int(top.rank))', main)
        self.assertIn('number.text = str(rank) if rank > 0 else ""', main)
        self.assertIn('No source PNG is altered',
                      (ROOT / 'tools/build_gods_ranked_assets.py').read_text())

    def test_04_canonical_reference_bytes_unchanged(self):
        approved = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(approved['images']), 7)
        paths = {
            'nd_premium_void': 'a5_void_ranked/01_nd_premium_void_canon_source.png',
            'pirate_sea': 'a5_pirate_ranked/02_pirate_sea_canon_source.png',
            'atlantis': 'a5_atlantis_ranked/03_atlantis_canon_source.png',
            'gods_of_the_deep': 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
            'sand_sea': 'a5_sand_ranked/05_sand_sea_canon_source.png',
            'night_sea': 'a5_night_ranked/06_night_sea_canon_source.png',
            'northern_sea': 'a5_northern_ranked/07_northern_sea_canon_source.png',
        }
        for entry in approved['images']:
            actual = ROOT / 'assets' / paths[entry['world']]
            self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(), entry['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
