"""Offline source-level regression for v43 selection and legal-move feedback.
Does NOT certify Godot compilation or real-device gameplay.
"""
from pathlib import Path
import unittest, hashlib, json, re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
BASELINE = json.loads((ROOT / 'tests/a5_v42_source_baseline.json').read_text())


def func(src, name):
    m = re.search(rf'(?ms)^func {re.escape(name)}\(.*?(?=^func |\Z)', src)
    assert m, f'missing {name}'
    return m.group(0)

class TouchSelectionFeedback(unittest.TestCase):
    def test_nine_live_outlines_not_screenshot(self):
        src = func(MAIN, '_create_perspective_layer')
        self.assertIn('for i in range(9):', src)
        self.assertIn('var outline := Line2D.new()', src)
        self.assertIn('perspective_legal_outlines.append(outline)', src)
        self.assertIn('var icon := TextureRect.new()', src)
        self.assertIn('outline.z_index = 4', src)
        self.assertNotIn('InputEvent', src)

    def test_outlines_follow_actual_perspective_geometry(self):
        src = func(MAIN, '_refresh_perspective_layer')
        self.assertIn('PerspectiveGeometry.cell_quad(current_world, i, perspective_rect)', src)
        self.assertIn('outline.points = PackedVector2Array([quad[0], quad[1], quad[2], quad[3], quad[0]])', src)
        self.assertIn('outline.width = maxf(2.0, 2.5 / _physical_pixel_scale())', src)
        self.assertIn('_refresh_selection_feedback()', src)

    def test_legality_is_game_engine_authority(self):
        src = func(MAIN, '_refresh_selection_feedback')
        self.assertIn('_is_legal_move(turn, selected_reserve + 1, i)', src)
        self.assertIn('not game_over and not (ai_enabled and turn == 2)', src)
        self.assertIn('legal or chosen_cell', src)
        self.assertIn('selected_cell == i', src)
        self.assertIn('Color("#6be7e6") if chosen_cell', src)

    def test_reserve_ring_does_not_consume_touch_or_modify_art(self):
        src = func(MAIN, '_refresh_selection_feedback')
        self.assertIn('ring.mouse_filter = Control.MOUSE_FILTER_IGNORE', src)
        self.assertIn('style.bg_color = Color.TRANSPARENT', src)
        self.assertIn('style.set_border_width_all(logical_border)', src)
        self.assertIn('piece.move_child(ring, piece.get_child_count() - 1)', src)
        self.assertIn('player == turn and i == selected_reserve and reserve.visible', src)

    def test_clear_commit_reserve_and_cell_update_feedback(self):
        for f in ['_on_reserve_pressed', '_on_cell_pressed', '_on_secondary', '_refresh_surface']:
            with self.subTest(function=f):
                self.assertIn('_refresh_selection_feedback()', func(MAIN, f))
        self.assertIn('_refresh_surface()', func(MAIN, '_on_primary'))
        self.assertIn('_refresh_selection_feedback()', func(MAIN, '_ensure_physical_touch_targets'))

    def test_headless_test_hook_checks_legal_and_illegal(self):
        self.assertIn('_run_headless_selection_feedback_smoke()', func(MAIN, '_run_headless_geometry_and_interaction_smoke'))
        src = func(MAIN, '_run_headless_selection_feedback_smoke')
        for text in ['_set_world(6)', '_on_reserve_pressed(1, 2)',
                     'not perspective_legal_outlines[0].visible',
                     'not perspective_legal_outlines[1].visible',
                     'perspective_legal_outlines[2].visible',
                     '_on_cell_pressed(4)', '_on_cell_pressed(5)', '_on_secondary()',
                     '_set_world(saved_world)']:
            self.assertIn(text, src)

    def test_all_seven_reference_hashes_unchanged(self):
        manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
        files = {'nd_premium_void':'a5_void_ranked/01_nd_premium_void_canon_source.png',
                 'pirate_sea':'a5_pirate_ranked/02_pirate_sea_canon_source.png',
                 'atlantis':'a5_atlantis_ranked/03_atlantis_canon_source.png',
                 'gods_of_the_deep':'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
                 'sand_sea':'a5_sand_ranked/05_sand_sea_canon_source.png',
                 'night_sea':'a5_night_ranked/06_night_sea_canon_source.png',
                 'northern_sea':'a5_northern_ranked/07_northern_sea_canon_source.png'}
        self.assertEqual(len(manifest['images']), 7)
        for item in manifest['images']:
            with self.subTest(world=item['world']):
                p = ROOT / 'assets' / files[item['world']]
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), item['sha256'])

    def test_rules_and_ai_source_unchanged(self):
        for name, expected in BASELINE['protected_function_sha256'].items():
            with self.subTest(function=name):
                actual = hashlib.sha256(func(MAIN, name).encode()).hexdigest()
                self.assertEqual(actual, expected)
        expected = BASELINE['unchanged_file_sha256']['scripts/ai_opponent.gd']
        self.assertEqual(hashlib.sha256((ROOT/'scripts/ai_opponent.gd').read_bytes()).hexdigest(), expected)

    def test_existing_files_unchanged_except_main(self):
        for rel, expected in BASELINE['unchanged_file_sha256'].items():
            with self.subTest(file=rel):
                self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
