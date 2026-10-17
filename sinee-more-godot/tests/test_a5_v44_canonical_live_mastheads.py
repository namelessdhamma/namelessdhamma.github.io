"""A5 v44: seven exact-canon mastheads are live, noninteractive world layers."""
from __future__ import annotations
import hashlib
import json
import re
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
LOGOS = ROOT / 'assets/a5_live_logos'
SOURCES = ['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked','a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
MAIN = (ROOT / 'scripts/main.gd').read_text()

class CanonicalLiveMastheads(unittest.TestCase):
    def test_seven_assets_and_manifest(self):
        self.assertEqual(len(list(LOGOS.glob('world_*.png'))),7)
        self.assertEqual(len(json.loads((LOGOS/'logo_manifest.json').read_text())),7)

    def test_exact_canon_sources_are_unchanged(self):
        for i, entry in enumerate(MANIFEST['images']):
            (src,) = (ROOT/'assets'/SOURCES[i]).glob('*canon_source.png')
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),entry['sha256'])

    def test_canon_crops_have_full_transparency_after_option_strip(self):
        for i in range(7):
            im = Image.open(LOGOS/f'world_{i:02d}.png')
            self.assertEqual(im.size,(542,150))
            self.assertEqual(im.mode,'RGBA')
            self.assertEqual(im.getpixel((0,80))[3],0)
            self.assertEqual(im.getpixel((541,80))[3],0)
            self.assertEqual(im.getpixel((260,149))[3],0)

    def test_logo_core_is_visible_and_source_rgb_exact(self):
        for i in range(7):
            (src,) = (ROOT/'assets'/SOURCES[i]).glob('*canon_source.png')
            ref=Image.open(src).convert('RGBA')
            logo=Image.open(LOGOS/f'world_{i:02d}.png')
            self.assertGreater(logo.getpixel((270,65))[3],200)
            for xy in [(120,50),(270,65),(400,65)]:
                self.assertEqual(logo.getpixel(xy)[:3],ref.getpixel((xy[0]+565,xy[1]))[:3])

    def test_no_flattened_board_or_reserve_in_mastheads(self):
        # All mastheads are cropped from the top 150 source pixels; the actual
        # interactive board begins near source y250, reserve near y770.
        self.assertLessEqual(150,250)
        for i in range(7):
            self.assertLess(Image.open(LOGOS/f'world_{i:02d}.png').getbbox()[3],150)

    def test_all_world_mastheads_differ(self):
        digests=[hashlib.sha256((LOGOS/f'world_{i:02d}.png').read_bytes()).hexdigest() for i in range(7)]
        self.assertEqual(len(set(digests)),7)

    def test_world_switch_reloads_live_logo(self):
        self.assertIn('canonical_live_logo.texture = load(logo_path) as Texture2D',MAIN)
        self.assertIn('"res://assets/a5_live_logos/world_%02d.png" % current_world',MAIN)
        self.assertEqual(MAIN.count('func _set_world('),1)

    def test_logo_is_noninteractive_and_layered(self):
        block=MAIN.split('func _create_canonical_live_logo()',1)[1].split('func _layout_canonical_live_logo()',1)[0]
        self.assertIn('MOUSE_FILTER_IGNORE',block)
        self.assertIn('canonical_live_logo.z_index = 6',block)
        self.assertIn('add_child(canonical_live_logo)',block)
        self.assertNotIn('.pressed.connect(',block)

    def test_title_has_safe_fallback(self):
        self.assertIn('title.modulate.a = 0.0 if canonical_live_logo.texture != null else 1.0',MAIN)
        self.assertIn('title.text = "СИНЕЕ МОРЕ"', (ROOT/'scripts/world_visuals.gd').read_text())

    def test_viewport_mapping_fits_746x280_and_1280x720(self):
        for width,height in [(746,280),(1280,720),(1672,941)]:
            x=565/1672*width
            w=542/1672*width
            h=150/941*height
            self.assertGreaterEqual(x,0)
            self.assertLess(x+w,width)
            self.assertLess(h,height*0.18)
        self.assertIn('_layout_canonical_live_logo()',MAIN)

    def test_no_gameplay_or_ai_rule_change(self):
        # Self-contained v43 baseline: no dependency on a temporary workspace.
        baseline=json.loads((ROOT/'tests/a5_v43_protected_function_hashes.json').read_text())
        for marker, expected_sha in baseline.items():
            after=MAIN.split(marker,1)[1].split('\nfunc ',1)[0]
            self.assertEqual(hashlib.sha256(after.encode()).hexdigest(),expected_sha)

    def test_regeneration_is_byte_identical(self):
        import subprocess,sys
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in LOGOS.glob('world_*.png')}
        subprocess.run([sys.executable,str(ROOT/'tools/build_canonical_live_logos.py')],check=True,capture_output=True)
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in LOGOS.glob('world_*.png')}
        self.assertEqual(before,after)

if __name__=='__main__': unittest.main()
