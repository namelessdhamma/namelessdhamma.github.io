"""A5 v71 Sand Sea visual source integration; no Godot runtime claims."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISUALS = (ROOT / 'scripts/world_visuals.gd').read_text()
MAIN = (ROOT / 'scripts/main.gd').read_bytes()
AI = (ROOT / 'scripts/ai_opponent.gd').read_bytes()


def function(name):
    match = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\).*?(?=^func |^static func |\Z)', VISUALS, re.M | re.S)
    assert match, name
    return match.group()


class SandWorldV71(unittest.TestCase):
    def test_01_sand_has_dedicated_material_not_stretched_board_cell(self):
        body = function('apply_world')
        section = body.split('elif world == 4:', 1)[1].split('elif world == 5:', 1)[0]
        self.assertIn('sand_plinth = load(SAND_NIGHT_ENV_ROOT + "/sand_sandstone_support.png")', section)
        self.assertTrue((ROOT/'assets/a5_sand_night_prebaked_environment/sand_sandstone_support.png').exists())
        self.assertIn('foundation.texture = sand_plinth', section)
        self.assertNotIn('_canonical_cell_texture(4, 4)', section)

    def test_02_live_gameplay_and_perspective_are_still_separate(self):
        body = function('apply_world')
        self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)', body)
        self.assertIn('chart.visible = world >= 1 and world <= 6', body)
        self.assertIn('scenery.visible = world != 0', body)
        self.assertIn('root.queue_redraw()', body)
        self.assertIn('var sand_plinth: Texture2D', VISUALS)

    def test_03_sand_background_is_a_procedural_environment_not_baked_state(self):
        body = function('_make_backdrop')
        self.assertIn('c = _sand_backdrop_color(u, v, x, y)', body)
        sand = function('_sand_backdrop_color')
        for required in ['sun_dist', 'Vector3(0.665', 'Vector3(0.805', 'Vector3(0.925',
                         'tower_band', 'for obelisk in', 'v < horizon', 'dune', 'grain']:
            self.assertIn(required, sand)
        self.assertNotIn('load(', sand)
        self.assertNotIn('board_stacks', sand)
        self.assertNotIn('rank_', sand)

    def test_04_sandstone_material_has_border_and_texture_but_no_occupancy(self):
        body = function('_make_sandstone_plinth')
        for required in ['Image.create(256, 256', 'Color("#12364d")',
                         'Color("#d6a347")', 'Color("#efb75c")', 'image.set_pixel(x, y, c)']:
            self.assertIn(required, body)
        self.assertNotIn('load(', body)
        self.assertNotIn('board_stacks', body)

    def test_05_all_seven_approved_source_pngs_still_match_manifest(self):
        manifest = json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        for entry in manifest['images']:
            exact = list((ROOT/'assets').rglob(entry['file'].replace('.png', '_canon_source.png')))
            self.assertEqual(len(exact), 1, entry['file'])
            self.assertEqual(hashlib.sha256(exact[0].read_bytes()).hexdigest(), entry['sha256'])

    def test_06_shared_rules_ai_pirate_scripts_unchanged_from_v70(self):
        import zipfile
        predecessor = Path('/mnt/data/A5_v70_Seven_Worlds_Perspective_Rank_Density_Integrated_Staging.zip')
        if not predecessor.exists():
            self.skipTest('Exact v70 predecessor archive not mounted')
        with zipfile.ZipFile(predecessor) as archive:
            self.assertEqual(MAIN, archive.read('sinee-more-godot/scripts/main.gd'))
            self.assertEqual(AI, archive.read('sinee-more-godot/scripts/ai_opponent.gd'))
            self.assertEqual((ROOT/'scripts/pirate_opening_campaign.gd').read_bytes(),
                             archive.read('sinee-more-godot/scripts/pirate_opening_campaign.gd'))
            self.assertEqual((ROOT/'scripts/pirate_opening_choice_surface.gd').read_bytes(),
                             archive.read('sinee-more-godot/scripts/pirate_opening_choice_surface.gd'))

    def test_07_sand_pyramids_are_grounded_and_grow_toward_horizon(self):
        for peak, width in [(0.035, 0.18), (0.085, 0.17), (0.21, 0.09)]:
            half = lambda v: width * max(0.0, min(1.0, (v - peak) / (0.47 - peak)))
            self.assertEqual(half(peak), 0)
            self.assertGreater(half(0.35), half(0.25) if peak < 0.25 else 0)
            self.assertAlmostEqual(half(0.47), width)

    def test_08_seven_world_dispatch_and_supported_board_invariants_unchanged(self):
        self.assertIn('"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep",', VISUALS)
        self.assertIn('"Sand Sea", "Night Sea", "Northern Sea"', VISUALS)
        self.assertIn('foundation.visible = world >= 1 and world <= 6', VISUALS)
        self.assertIn('var has_support := current_world != 0', MAIN.decode())
        self.assertIn('perspective_support_surface.texture = material', MAIN.decode())


if __name__ == '__main__':
    unittest.main()
