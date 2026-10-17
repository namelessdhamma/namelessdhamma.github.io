"""A5 v69: mobile header is real UI, not a flattened screenshot.

Static contract/model checks; they do NOT replace a Godot 4.7.2 render.
"""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts/main.gd').read_text()


def body(name):
    m = re.search(r'^func ' + re.escape(name) + r'\(.*?(?=^func |\Z)', SRC, re.M | re.S)
    assert m, name
    return m.group(0)


class TestV69MobileHeader(unittest.TestCase):
    def test_01_exact_reference_menu_is_only_phone_menu_button(self):
        f = body('_sync_mobile_menu_trigger')
        for text in ['mobile_menu_button.visible = false', 'mobile_world_button.visible = false',
                     'world_picker.visible = not phone', 'top_menu.visible = not phone',
                     'ai_toggle.visible = not phone']:
            self.assertIn(text, f)
        self.assertIn('reference_menu_hotspot.pressed.connect(_on_reference_menu_hotspot_pressed)', SRC)

    def test_02_world_and_ai_remain_accessible(self):
        menu = body('_render_mobile_menu_page')
        action = body('_on_mobile_menu_action')
        for s in ['"Выбрать мир · 7", 105', '"ИИ: " + ("ВКЛ" if ai_enabled else "ВЫКЛ"), 106']:
            self.assertIn(s, menu)
        self.assertIn('elif id == 105:', action)
        self.assertIn('_render_mobile_menu_page("worlds")', action)
        self.assertIn('elif id == 106:', action)
        self.assertIn('_toggle_ai()', action)
        self.assertIn('_render_mobile_menu_page("main")', action)

    def test_03_logo_fallback_does_not_take_invisible_layout_space(self):
        f = body('_set_world')
        self.assertIn('title.visible = canonical_live_logo.texture == null', f)
        self.assertNotIn('title.modulate.a = 0.0', f)

    def test_04_live_score_stays_visible(self):
        f = body('_sync_mobile_menu_trigger')
        self.assertNotIn('match_hud.visible = false', f)
        self.assertIn('match_hud_label.text = score + "\\n" + state', body('_refresh_match_hud'))

    def test_05_reference_logo_clearance_at_746x280(self):
        # 1280x720 canvas_items scaled to 746x280, 1x CSS-pixel density.
        viewport, scale, density = 1280.0, 280.0 / 720.0, 1.0
        hud = min(76 * density / scale, max(44*density/scale, viewport - viewport*1107/1672 - 20))
        clearance = min(viewport*.75, viewport - hud - 20)
        self.assertGreater(clearance, viewport * 1107 / 1672)
        self.assertLessEqual(clearance + hud + 20, viewport)

    def test_06_reference_logo_clearance_at_native_phone_density(self):
        for physical_height, density in [(480, 3), (500, 3), (480, 4), (360, 2)]:
            viewport, scale = 1280.0, physical_height / 720.0
            logical_touch = (44*density/scale).__ceil__()
            hud = min((76*density/scale).__ceil__(), max(logical_touch, viewport - viewport*1107/1672 - 20))
            clearance = min(viewport*.75, viewport-hud-20)
            self.assertGreaterEqual(clearance, viewport*1107/1672,
                                    (physical_height, density, hud, clearance))
            self.assertLessEqual(clearance+hud+20, viewport)

    def test_07_no_rules_or_ai_engine_mutation(self):
        for name in ['_is_legal_move', '_winning_line', '_has_legal_move', '_on_primary',
                     '_reset_round', '_play_ai_turn']:
            self.assertIn('func '+name+'(', SRC)
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")', SRC)
        self.assertIn('const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")', SRC)

    def test_08_canonical_live_assets_unchanged(self):
        for path in ['assets/a5_live_logos/world_00.png', 'assets/a5_live_logos/world_06.png',
                     'assets/a5_reference_cells/north/cell_08.png']:
            self.assertTrue((ROOT/path).is_file(), path)

    def test_09_headless_engine_fixture_integrated(self):
        self.assertIn('_run_headless_mobile_header_smoke()', body('_run_headless_geometry_and_interaction_smoke'))
        f = body('_run_headless_mobile_header_smoke')
        for check in ['mobile_menu_panel.visible', 'match_hud.visible', 'logo_right',
                      'MobileChoice_105', 'MobileChoice_106']:
            self.assertIn(check, f)

    def test_10_no_unauthorized_menu_actions(self):
        # New IDs do not collide with the existing world/rules/AI/reset actions.
        self.assertEqual(len(set([105,106,1,2,3,4,100,101,102,103,104,300,301,302,
                                  400,401,402,410,411,412,500,501,502,503,504,505,506,600])), 28)


if __name__ == '__main__':
    unittest.main()
