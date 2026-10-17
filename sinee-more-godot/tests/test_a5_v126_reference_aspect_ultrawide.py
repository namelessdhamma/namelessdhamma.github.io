"""v126: source-backed, non-native guard for seven approved art proportions.

This is NOT a rendered Godot parity check. Native smoke exercises the actual
TextureRect properties when Godot becomes available.
"""
from pathlib import Path
import re
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
VISUAL = (ROOT / 'scripts/world_visuals.gd').read_text()


def logo_rect(width, height):
    srcw, srch = 542.0, 150.0
    left = 565.0 / 1672.0 * width
    bw = srcw / 1672.0 * width
    bh = srch / 941.0 * height
    scale = min(bw / srcw, bh / srch)
    rw, rh = srcw * scale, srch * scale
    return left + (bw-rw)/2, (bh-rh)/2, rw, rh


class SevenWorldReferenceAspect(unittest.TestCase):
    def test_live_world_background_and_perimeter_are_not_anamorphic(self):
        self.assertIn('backdrop.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED', VISUAL)
        self.assertIn('scenery.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED', VISUAL)
        self.assertNotIn('backdrop.stretch_mode = TextureRect.STRETCH_SCALE', VISUAL)
        self.assertNotIn('scenery.stretch_mode = TextureRect.STRETCH_SCALE', VISUAL)
        self.assertIn('foundation.stretch_mode = TextureRect.STRETCH_SCALE', VISUAL)
        self.assertIn('chart.stretch_mode = TextureRect.STRETCH_SCALE', VISUAL)

    def test_real_source_logos_have_expected_unchanged_shape(self):
        for world in range(7):
            with self.subTest(world=world):
                im = Image.open(ROOT / 'assets/a5_live_logos' / f'world_{world:02d}.png')
                self.assertEqual(im.size, (542, 150))

    def test_746_280_844_390_and_native_16_9_contain_the_logo(self):
        for width, height in [(746,280),(844,390),(932,430),(1280,720),(1920,1080)]:
            with self.subTest(viewport=(width,height)):
                x,y,w,h=logo_rect(width,height)
                self.assertAlmostEqual(w/h,542/150,places=8)
                self.assertGreater(w,0)
                self.assertGreater(h,0)
                self.assertGreaterEqual(x,565/1672*width-1e-6)
                self.assertLessEqual(x+w,1107/1672*width+1e-6)
                self.assertLessEqual(y+h,150/941*height+1e-6)
                self.assertAlmostEqual(x+w/2,836/1672*width,places=7)

    def test_runtime_geometry_is_used_not_just_test_math(self):
        self.assertIn('static func _canonical_logo_rect(viewport: Vector2) -> Rect2:',MAIN)
        self.assertIn('var logo_rect := _canonical_logo_rect(viewport)',MAIN)
        self.assertIn('canonical_live_logo.position = logo_rect.position',MAIN)
        self.assertIn('canonical_live_logo.size = logo_rect.size',MAIN)
        self.assertIn('_run_headless_reference_aspect_smoke()',MAIN)
        self.assertIn('BLUE_SEA_CANONICAL_ART_ASPECT_PASS',MAIN)
        self.assertIn('TextureRect.STRETCH_KEEP_ASPECT_COVERED',MAIN)
        self.assertIn('world_visuals.apply_world(self, current_world)',MAIN)

    def test_legacy_gameplay_and_pirate_controller_not_replaced(self):
        for token in ('const AIOpponent = preload(', 'func _on_primary() -> void:',
                      'func _is_legal_move(', 'func _play_ai_turn() -> void:',
                      'func _set_world(world: int) -> void:',
                      'PirateOpeningChoiceSurface'):
            self.assertIn(token,MAIN)

if __name__ == '__main__':
    unittest.main()
