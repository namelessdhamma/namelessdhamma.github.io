"""A5 v72: Night Sea live art and floating-Void support regression (staging)."""
import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISUALS = (ROOT / 'scripts/world_visuals.gd').read_text(encoding='utf-8')
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
PREDECESSOR = Path('/mnt/data/A5_v71_Sand_Sea_Physical_Support_Sunset_Integrated_Staging.zip')


def function(name):
    match = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\).*?(?=^func |^static func |\Z)', VISUALS, re.M | re.S)
    assert match, name
    return match.group()


class NightSeaV72(unittest.TestCase):
    def test_01_night_uses_dedicated_gothic_masonry_support(self):
        body = function('apply_world')
        section = body.split('elif world == 5:', 1)[1].split('elif world == 6:', 1)[0]
        self.assertIn('night_plinth = load(SAND_NIGHT_ENV_ROOT + "/night_masonry_support.png")', section)
        self.assertTrue((ROOT/'assets/a5_sand_night_prebaked_environment/night_masonry_support.png').exists())
        self.assertIn('foundation.texture = night_plinth', section)
        self.assertNotIn('load("res://assets/a5_reference_cells/night/cell_04.png")', section)

    def test_02_void_cannot_show_a_physical_panel(self):
        body = function('apply_world')
        self.assertIn('support.visible = world != 0', body)
        self.assertIn('foundation.visible = world >= 1 and world <= 6', body)
        self.assertIn('scenery.visible = world != 0', body)
        self.assertIn('var has_support := current_world != 0', MAIN)
        self.assertIn('perspective_support_surface.visible = has_support', MAIN)

    def test_03_night_live_backdrop_dispatch(self):
        body = function('_make_backdrop')
        self.assertIn('5:\n\t\t\t\t\tc = _night_backdrop_color(u, v, x, y)', body)
        self.assertNotIn('if x % 61 < 2 or y % 35 < 2', body)

    def test_04_harbor_has_moon_clouds_ships_and_water(self):
        body = function('_night_backdrop_color')
        for expected in ['moon_distance', 'moon_reflection', 'cloud', 'for tower in',
                         'for ship in', 'wave', 'for lamp in', 'foreground quay', 'return c']:
            self.assertIn(expected, body)
        self.assertNotIn('board_stacks', body)
        self.assertNotIn('reserve_available', body)
        self.assertNotIn('rank_', body)
        self.assertNotIn('load(', body)

    def test_05_night_material_is_full_size_and_no_baked_game_state(self):
        body = function('_make_night_masonry_plinth')
        for expected in ['Image.create(256, 256', 'Color("#101326")',
                         'Color("#c78c49")', 'radius', 'image.set_pixel(x, y, c)',
                         'ImageTexture.create_from_image(image)']:
            self.assertIn(expected, body)
        self.assertNotIn('board_stacks', body)
        self.assertNotIn('load(', body)

    def test_06_interactive_cells_and_rank_text_remain_live(self):
        body = function('apply_world')
        self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)', body)
        self.assertIn('chart.mouse_filter = Control.MOUSE_FILTER_IGNORE', body)
        self.assertIn('cell.add_theme_stylebox_override("normal", normal)', body)
        self.assertIn('world_visuals.piece_texture(current_world', MAIN)
        self.assertIn('rank.text = str(int(top.rank))', MAIN)

    def test_07_seven_approved_source_pngs_are_exact(self):
        manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        for item in manifest['images']:
            matches = list((ROOT/'assets').rglob(item['file'].replace('.png','_canon_source.png')))
            self.assertEqual(len(matches), 1, item['file'])
            self.assertEqual(hashlib.sha256(matches[0].read_bytes()).hexdigest(), item['sha256'])

    def test_08_shared_gameplay_ai_pirate_unchanged(self):
        if not PREDECESSOR.exists():
            self.skipTest('Exact v71 predecessor not mounted')
        with zipfile.ZipFile(PREDECESSOR) as z:
            for name in ['scripts/main.gd', 'scripts/ai_opponent.gd',
                         'scripts/pirate_opening_campaign.gd',
                         'scripts/pirate_opening_choice_surface.gd',
                         'scripts/perspective_board_geometry.gd',
                         'main.tscn', 'project.godot']:
                self.assertEqual((ROOT/name).read_bytes(), z.read('sinee-more-godot/'+name), name)

    def test_09_seven_world_selection_and_real_board_support(self):
        self.assertIn('"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep",', VISUALS)
        self.assertIn('"Sand Sea", "Night Sea", "Northern Sea"', VISUALS)
        self.assertIn('perspective_support_surface.texture = material', MAIN)
        self.assertIn('tile.texture = art.texture', MAIN)
        self.assertIn('perspective_tiles.size() != 9', MAIN)

    def test_10_only_one_live_night_backdrop_and_plinth_function(self):
        self.assertEqual(VISUALS.count('func _night_backdrop_color('), 1)
        self.assertEqual(VISUALS.count('func _make_night_masonry_plinth('), 1)
        self.assertEqual(VISUALS.count('night_plinth = load(SAND_NIGHT_ENV_ROOT + "/night_masonry_support.png")'), 1)


if __name__ == '__main__':
    unittest.main()
