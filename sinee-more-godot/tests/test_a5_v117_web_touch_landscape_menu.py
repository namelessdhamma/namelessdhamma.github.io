"""A5 v117: independently exercise actual shared web/mobile route thresholds.

Offline source/model tests, not a Godot render or physical touchscreen PASS.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def function(name):
    match = re.search(r'^((?:static )?func ' + re.escape(name) + r'\([^\n]*\)[^\n]*:\n.*?)(?=^(?:static )?func |\Z)', SRC, re.M | re.S)
    assert match, name
    return match.group(1)


def production_web_cutoff():
    source = function('_mobile_profile')
    match = re.search(r'float\(short_side\) / maxf\(1\.0, display_scale\) <= (\d+\.\d+)', source)
    assert match, 'Production touch cutoff not found'
    return float(match.group(1))


def profile(backend, short_side, display_scale, touch_available):
    return (backend in ('Android', 'iOS') or short_side <= 360 or
            (backend == 'web' and touch_available and
             short_side / max(1.0, display_scale) <= production_web_cutoff()))


class WebTouchLandscapeMenu(unittest.TestCase):
    def test_actual_source_threshold(self):
        self.assertEqual(production_web_cutoff(), 480.0)

    def test_accepted_touch_phone_sizes(self):
        for width, height in [(746, 280), (844, 390), (932, 430), (960, 440)]:
            with self.subTest(viewport=(width, height)):
                self.assertTrue(profile('web', height, 1, True))

    def test_css_vs_backing_pixels(self):
        self.assertTrue(profile('web', 1170, 3, True))  # 390 CSS pixels
        self.assertTrue(profile('web', 1290, 3, True))  # 430 CSS pixels
        self.assertFalse(profile('web', 1500, 3, True)) # 500 CSS pixels

    def test_mouse_desktop_unchanged(self):
        for short in [390, 430, 480, 720, 1080]:
            self.assertFalse(profile('web', short, 1, False))
        self.assertTrue(profile('web', 280, 1, False)) # tiny mouse window
        self.assertFalse(profile('X11', 390, 1, True))
        self.assertFalse(profile('web', 720, 1, True))

    def test_native_phone_unchanged(self):
        for backend in ['Android', 'iOS']:
            self.assertTrue(profile(backend, 1080, 3, True))
            self.assertTrue(profile(backend, 1440, 4, False))

    def test_mobile_route_has_live_safe_controls(self):
        trigger = function('_sync_mobile_menu_trigger')
        self.assertIn('var phone := _use_mobile_menu()', trigger)
        self.assertIn('world_picker.visible = not phone', trigger)
        self.assertIn('top_menu.visible = not phone', trigger)
        self.assertIn('ai_toggle.visible = not phone', trigger)
        self.assertIn('status.visible = not phone', trigger)
        self.assertIn('mobile_menu_panel', function('_open_mobile_menu'))
        self.assertIn('ceilf(_minimum_touch_physical_px() / _physical_pixel_scale())', function('_mobile_menu_add'))
        self.assertIn('mobile_menu_panel.show()', function('_open_mobile_menu'))

    def test_live_gameplay_preserved(self):
        for name in ['_on_primary', '_on_cell_pressed', '_set_world', '_queue_ai_turn_if_ready',
                     '_run_headless_full_match_smoke', '_run_headless_touch_emulation_smoke']:
            self.assertIn('func ' + name + '(', SRC)
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', function('_run_headless_full_match_smoke'))

    def test_native_smoke_coverage(self):
        smoke = function('_run_headless_native_mobile_profile_smoke')
        for value in ['"web", 390, 1.0, true', '"web", 430, 1.0, true',
                      '"web", 390, 1.0, false', '"web", 720, 1.0, true']:
            self.assertIn(value, smoke)


if __name__ == '__main__':
    unittest.main()
