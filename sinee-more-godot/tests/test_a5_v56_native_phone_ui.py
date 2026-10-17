"""A5 v56 independent source + native phone DPI regression (Godot not available)."""
from pathlib import Path
import math
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/'scripts/main.gd').read_text()

def function(name):
    m=re.search(r'^((?:static )?func '+re.escape(name)+r'\([^\n]*\)[^\n]*:\n.*?)(?=^(?:static )?func |\Z)',SRC,re.M|re.S)
    assert m, name
    return m.group(1)

def mobile_profile(backend,short,scale,touch):
    return backend in ('Android','iOS') or short<=360 or (backend=='web' and touch and short/max(1,scale)<=480)

def native_density(backend,dpi=160,scale=1):
    return min(4,max(1,dpi/160)) if backend=='Android' else min(4,max(1,scale)) if backend=='iOS' else 1

class NativeMobileTouchUI(unittest.TestCase):
    def test_android_full_resolution(self):
        self.assertTrue(mobile_profile('Android',1080,3,True))
        self.assertTrue(mobile_profile('Android',1440,4,True))
    def test_ios_full_resolution(self):
        self.assertTrue(mobile_profile('iOS',1170,3,True))
    def test_web_css_and_backing_pixels(self):
        self.assertTrue(mobile_profile('web',280,1,False))
        self.assertTrue(mobile_profile('web',840,3,True))
        self.assertFalse(mobile_profile('web',840,3,False))
    def test_desktop_retains_original_route(self):
        self.assertFalse(mobile_profile('X11',1080,2,True))
        self.assertFalse(mobile_profile('web',1080,1,False))
    def test_android_44_dp_target(self):
        for dpi in (160,240,320,480,640):
            physical=44*native_density('Android',dpi)
            logical=math.ceil(physical/(1080/720))
            self.assertGreaterEqual(logical*(1080/720),physical)
            self.assertGreaterEqual(physical/(dpi/160),44)
    def test_ios_44_pt_target(self):
        for dpr in (1,2,3):
            self.assertEqual(44*native_density('iOS',scale=dpr)/dpr,44)
    def test_browser_746x280_unchanged(self):
        density=native_density('web',dpi=300,scale=3)
        self.assertEqual(density,1)
        self.assertEqual(math.ceil(44/(280/720)),114)
    def test_native_mobile_api_route_is_live(self):
        self.assertIn('DisplayServer.get_name()',function('_use_mobile_menu'))
        self.assertIn('DisplayServer.screen_get_scale()',function('_use_mobile_menu'))
        self.assertIn('DisplayServer.is_touchscreen_available()',function('_use_mobile_menu'))
        profile=function('_mobile_profile')
        self.assertIn('backend == "Android" or backend == "iOS"',profile)
        self.assertIn('short_side <= 360',profile)
    def test_density_is_used_by_all_touch_surfaces(self):
        self.assertIn('screen_get_dpi()',function('_native_touch_density'))
        self.assertIn('screen_get_scale()',function('_native_touch_density'))
        for name in ('_ensure_physical_touch_targets','_mobile_menu_add','_layout_reference_menu_hotspot'):
            self.assertIn('_minimum_touch_physical_px()',function(name),name)
        self.assertIn('_minimum_touch_physical_px()',function('_assert_landscape_geometry'))
    def test_density_resizes_existing_menu(self):
        self.assertIn('_mobile_menu_last_density',function('_sync_mobile_menu_trigger'))
        self.assertIn('_last_touch_density',function('_ensure_physical_touch_targets'))
        self.assertIn('_last_reference_hotspot_density',function('_layout_reference_menu_hotspot'))
    def test_headless_profile_cases_wired(self):
        smoke=function('_run_headless_native_mobile_profile_smoke')
        for key in ('Android','iOS','web','X11'):
            self.assertIn('"'+key+'"',smoke)
        self.assertIn('_run_headless_native_mobile_profile_smoke()',function('_run_headless_geometry_and_interaction_smoke'))
    def test_no_gameplay_or_canon_edits(self):
        self.assertIn('func _on_primary() -> void:',SRC)
        self.assertIn('func _run_headless_full_match_smoke() -> void:',SRC)
        self.assertIn('func _set_world(world: int) -> void:',SRC)

if __name__=='__main__':unittest.main()
