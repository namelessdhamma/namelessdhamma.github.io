"""Offline source/art regression for A5 v42.
Not a substitute for Godot compilation, real-phone touch, or visual parity.
"""
import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/mnt/data/A5_v41_Three_Worlds_Canonical_Empty_Board_Cells_Integrated_Staging.zip')
MAIN = (ROOT / 'scripts/main.gd').read_text()
VISUAL = (ROOT / 'scripts/world_visuals.gd').read_text()
MANIFEST = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def func(src, name):
    pat = rf'(?ms)^func {re.escape(name)}\(.*?(?=^func |\Z)'
    match = re.search(pat, src)
    if match is None:
        raise AssertionError(f'missing {name}')
    return match.group(0)


class MaterialSupport(unittest.TestCase):
    def test_six_materials_and_void_only_floats(self):
        self.assertIn('foundation.visible = world >= 1 and world <= 6', VISUAL)
        self.assertIn('perspective_support_surface.visible = has_support', MAIN)
        self.assertIn('var has_support := current_world != 0', MAIN)
        self.assertIn('perspective_support_surface.texture = null', MAIN)
        self.assertIn('perspective_support_surface.uv = PackedVector2Array()', MAIN)

    def test_sandstone_is_real_canonical_empty_tile(self):
        self.assertIn('foundation.texture = _canonical_cell_texture(4, 4)', VISUAL)
        p = ROOT / 'assets/a5_reference_cells/sand/cell_04.png'
        with Image.open(p) as im:
            self.assertEqual(im.size, (192, 192))
            self.assertEqual(im.mode, 'RGB')

    def test_other_five_materials_reused_without_new_engine(self):
        for expression in [
            'foundation.texture = pirate_plinth',
            'foundation.texture = atlantis_plinth',
            'foundation.texture = gods_plinth',
            'foundation.texture = night_plinth',
            'foundation.texture = northern_plinth',
        ]:
            self.assertIn(expression, VISUAL)
        self.assertEqual(MAIN.count('const WorldVisuals = preload'), 1)
        self.assertEqual(MAIN.count('const AIOpponent = preload'), 1)

    def test_support_uses_actual_world_material_not_flat_fill(self):
        f = func(MAIN, '_refresh_perspective_layer')
        self.assertIn('var material := foundation.texture', f)
        self.assertIn('perspective_support_surface.texture = material', f)
        self.assertIn('perspective_support_surface.color = Color.WHITE', f)
        self.assertNotIn('perspective_support_surface.color = SUPPORT_SURFACE_COLORS[current_world]', f)
        self.assertIn('perspective_support_shadow.color = Color(0.0, 0.0, 0.0, 0.70)', f)

    def test_uv_four_corner_mapping_and_no_screenshot_overlay(self):
        f = func(MAIN, '_refresh_perspective_layer')
        self.assertIn('perspective_support_surface.uv = PackedVector2Array([', f)
        self.assertIn('Vector2.ZERO, Vector2(texture_size.x, 0.0)', f)
        self.assertIn('texture_size, Vector2(0.0, texture_size.y)', f)
        self.assertIn('tile.texture = art.texture', f)
        self.assertIn('rank.text = str(int(top.rank))', f)
        self.assertIn('icon.texture = world_visuals.piece_texture(', f)

    def test_headless_smoke_protects_six_worlds_and_void(self):
        f = func(MAIN, '_run_headless_six_supported_world_cells_smoke')
        for s in ['for world in range(1, 7)',
                  'perspective_support_surface.texture == foundation.texture',
                  'perspective_support_surface.uv.size() == 4',
                  'board_stacks == saved_stacks',
                  'turn == saved_turn and moves == saved_moves',
                  'perspective_support_surface.texture == null']:
            self.assertIn(s, f)

    def test_original_reference_hashes_all_seven(self):
        prefixes = {
            'nd_premium_void':'a5_void_ranked/01_nd_premium_void_canon_source.png',
            'pirate_sea':'a5_pirate_ranked/02_pirate_sea_canon_source.png',
            'atlantis':'a5_atlantis_ranked/03_atlantis_canon_source.png',
            'gods_of_the_deep':'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
            'sand_sea':'a5_sand_ranked/05_sand_sea_canon_source.png',
            'night_sea':'a5_night_ranked/06_night_sea_canon_source.png',
            'northern_sea':'a5_northern_ranked/07_northern_sea_canon_source.png',
        }
        for item in MANIFEST['images']:
            p = ROOT / 'assets' / prefixes[item['world']]
            with self.subTest(world=item['world']):
                self.assertEqual(digest(p), item['sha256'])

    def test_gameplay_rules_ai_unchanged_from_v41(self):
        with zipfile.ZipFile(BASE) as z:
            old = z.read('sinee-more-godot/scripts/main.gd').decode()
            for name in ['_on_primary','_input','_is_legal_move','_is_legal_move_for',
                         '_winning_line','_play_ai_turn','_reset_round','_refresh_surface',
                         '_on_reserve_pressed','_on_cell_pressed']:
                with self.subTest(function=name):
                    self.assertEqual(func(MAIN, name), func(old, name))
            old_ai = z.read('sinee-more-godot/scripts/ai_opponent.gd')
            self.assertEqual((ROOT/'scripts/ai_opponent.gd').read_bytes(), old_ai)

    def test_only_expected_existing_files_changed(self):
        with zipfile.ZipFile(BASE) as z:
            for name in z.namelist():
                if not name.startswith('sinee-more-godot/') or name.endswith('/'):
                    continue
                relative = name.removeprefix('sinee-more-godot/')
                if relative in {'scripts/main.gd', 'scripts/world_visuals.gd'}:
                    continue
                with self.subTest(file=relative):
                    self.assertEqual((ROOT/relative).read_bytes(), z.read(name))

    def test_live_source_keeps_menu_reserve_and_seven_worlds(self):
        for marker in ['title.text = "СИНЕЕ МОРЕ"',
                       'title.add_theme_color_override("font_color", Color("#f33c39"))']:
            self.assertIn(marker, VISUAL)
        for marker in ['reserve.visible = player == turn and not game_over',
                       'next_round_button.visible = game_over',
                       'var world_picker: MenuButton',
                       'for i in range(WorldVisuals.WORLDS.size())']:
            self.assertIn(marker, MAIN)
        self.assertEqual(len(re.findall(r'"(?:ND Premium Void|Pirate Sea|Atlantis|Gods of the Deep|Sand Sea|Night Sea|Northern Sea)"', VISUAL)),7)

if __name__ == '__main__':
    unittest.main(verbosity=2)
