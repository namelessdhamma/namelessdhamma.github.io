"""v121: Northern Sea's playable rank sprites now have distinct rune engravings.

Offline source/asset checks. Godot runtime and physical touch remain unverified.
"""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'assets/a5_northern_ranked'
RUNED = ROOT / 'assets/a5_northern_runed'
MAIN = (ROOT / 'scripts/main.gd').read_text()
VISUALS = (ROOT / 'scripts/world_visuals.gd').read_text()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NorthernRunicRanked(unittest.TestCase):
    def test_01_all_18_original_stones_and_seven_reference_pngs_preserved(self):
        source_manifest = json.loads((BASE/'asset_manifest.json').read_text())
        for item in source_manifest['assets']:
            original = BASE / item['file']
            self.assertEqual(digest(original), item['sha256'], original)
        approved = json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(approved['images']), 7)
        for item in approved['images']:
            candidates = list((ROOT/'assets').rglob(item['file'].replace('.png','_canon_source.png')))
            self.assertEqual(len(candidates), 1, item['file'])
            self.assertEqual(digest(candidates[0]), item['sha256'])

    def test_02_exact_18_distinct_runic_sprites_with_original_alpha_and_size(self):
        manifest = json.loads((RUNED/'asset_manifest.json').read_text())
        self.assertEqual(len(manifest['assets']), 18)
        digests = set()
        for item in manifest['assets']:
            rank, player = item['rank'], item['player']
            original_path = BASE / f'north_rank_{rank:02d}_p{player}.png'
            derivative_path = RUNED / f'north_runed_rank_{rank:02d}_p{player}.png'
            a = Image.open(original_path).convert('RGBA')
            b = Image.open(derivative_path).convert('RGBA')
            self.assertEqual(a.size, (128,128))
            self.assertEqual(a.getchannel('A').tobytes(), b.getchannel('A').tobytes())
            self.assertEqual(item['original_sha256'], digest(original_path))
            self.assertEqual(item['sha256'], digest(derivative_path))
            diff = ImageChops.difference(a.convert('RGB'),b.convert('RGB'))
            self.assertGreater(sum(1 for v in diff.convert('L').get_flattened_data() if v>15), 10,
                               f'Rune not visibly etched: {derivative_path.name}')
            digests.add(item['sha256'])
        self.assertEqual(len(digests), 18)

    def test_03_monotonic_visible_size_and_safe_unchanged_alpha_at_phone_scale(self):
        for player in (1,2):
            for size in (22,26,30,36,44,48):
                areas=[]
                for rank in range(1,10):
                    image = Image.open(RUNED/f'north_runed_rank_{rank:02d}_p{player}.png')
                    resized = image.resize((size,size),Image.Resampling.LANCZOS)
                    areas.append(sum(1 for a in resized.getchannel('A').get_flattened_data() if a>100))
                self.assertTrue(all(a<b for a,b in zip(areas,areas[1:])),(player,size,areas))

    def test_04_live_texture_binding_and_lower_numeric_rank_without_hitbox_change(self):
        self.assertIn('a5_northern_runed/north_runed_rank_%02d_p%d.png',VISUALS)
        self.assertIn('if current_world == 6:\n\t\tnumber.anchor_top = 0.68',MAIN)
        self.assertIn('rank.position = rect.position + Vector2(0.0, rect.size.y * 0.68)',MAIN)
        self.assertIn('_run_headless_northern_rune_stones_smoke()',MAIN)
        self.assertIn('perspective_ranks[0].text == "9"',MAIN)
        self.assertIn('BLUE_SEA_NORTHERN_RUNE_ENGRAVING_PASS',MAIN)
        self.assertNotIn('north_runed_rank_', (ROOT/'scripts/perspective_board_geometry.gd').read_text())

    def test_05_builder_is_deterministic(self):
        paths = sorted(RUNED.glob('*.png'))+[RUNED/'asset_manifest.json']
        before={p.name:digest(p) for p in paths}
        result=subprocess.run([sys.executable,str(ROOT/'tools/build_northern_runed_assets.py')],
                              capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(before,{p.name:digest(p) for p in paths})

if __name__=='__main__':unittest.main()
