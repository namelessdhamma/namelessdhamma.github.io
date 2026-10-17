"""A5 v88: supported-world board contact faces are LIVE, not flattened screenshots.

Static geometry/source checks only. The native Godot smoke is registered but cannot
be considered passed until a Godot binary executes it.
"""
import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
GEOMETRY = (ROOT / 'scripts/perspective_board_geometry.gd').read_text(encoding='utf-8')
PREDECESSOR = Path('/mnt/data/A5_v87_Seven_Worlds_AI_Invalid_Proposal_Recovery_Integrated_Staging.zip')


def fn(name):
    match = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\).*?(?=^func |^static func |\Z)', MAIN, re.M | re.S)
    assert match, f'missing {name}'
    return match.group()


class GroundedBoardContact(unittest.TestCase):
    def test_01_six_supported_worlds_use_live_3d_contact_faces(self):
        create = fn('_create_perspective_layer')
        refresh = fn('_refresh_perspective_layer')
        for token in ('perspective_board_front_fascia = Polygon2D.new()',
                      'perspective_board_right_fascia = Polygon2D.new()',
                      'add_child(perspective_board_front_fascia)',
                      'add_child(perspective_board_right_fascia)'):
            self.assertIn(token, create)
        self.assertIn('var has_support := current_world != 0', refresh)
        for side in ('front', 'right'):
            self.assertIn(f'perspective_board_{side}_fascia.visible = has_support', refresh)
            self.assertIn(f'perspective_board_{side}_fascia.polygon = PackedVector2Array([', refresh)
        self.assertIn('perspective_board_front_fascia.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.57)', refresh)
        self.assertIn('perspective_board_right_fascia.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.68)', refresh)
        self.assertIn('perspective_support_surface.texture = material', refresh)
        self.assertIn('perspective_tiles[i]', refresh)

    def test_02_void_never_has_contact_fascia_or_physical_shadow(self):
        refresh = fn('_refresh_perspective_layer')
        self.assertIn('perspective_support_shadow.visible = has_support', refresh)
        self.assertIn('perspective_support_surface.visible = has_support', refresh)
        self.assertIn('perspective_board_front_fascia.polygon = PackedVector2Array()', refresh)
        self.assertIn('perspective_board_right_fascia.polygon = PackedVector2Array()', refresh)
        self.assertIn('perspective_support_surface.texture = null', refresh)

    def test_03_levitating_shadow_offset_removed_and_contact_scale_bounded(self):
        refresh = fn('_refresh_perspective_layer')
        self.assertIn('shadow.append(corner + Vector2(0.0, 3.0 * scale))', refresh)
        self.assertNotIn('12.0 * scale', refresh)
        self.assertIn('var contact_scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)', refresh)
        self.assertIn('var contact_depth := maxf(3.0, 11.0 * contact_scale)', refresh)
        self.assertIn('base[3], base[2], base[2] + down, base[3] + down', refresh)
        self.assertIn('base[1], base[2], base[2] + down, base[1] + down', refresh)

    def test_04_contact_faces_are_not_hit_targets_and_live_cells_remain(self):
        create = fn('_create_perspective_layer')
        self.assertEqual(create.count('perspective_board_front_fascia.z_index = 1'), 1)
        self.assertEqual(create.count('perspective_board_right_fascia.z_index = 1'), 1)
        self.assertIn('tile.z_index = 2', create)
        self.assertIn('icon.mouse_filter = Control.MOUSE_FILTER_IGNORE', create)
        self.assertIn('PerspectiveGeometry.cell_at_touch(', fn('_input'))
        self.assertIn('_on_cell_pressed(index)', fn('_input'))

    def test_05_native_smoke_checks_seven_world_switches_and_live_material(self):
        smoke = fn('_run_headless_grounded_board_contact_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', smoke)
        self.assertIn('assert(perspective_support_surface.texture != null)', smoke)
        self.assertIn('assert(front.size() == 4 and right.size() == 4)', smoke)
        self.assertIn('assert(front[0].distance_to(base[3]) < 0.01)', smoke)
        self.assertIn('assert(right[0].distance_to(base[1]) < 0.01)', smoke)
        self.assertIn('assert(perspective_board_front_fascia.polygon.is_empty())', smoke)
        self.assertIn('_set_world(saved_world)', smoke)
        self.assertIn('_run_headless_grounded_board_contact_smoke()', fn('_run_headless_geometry_and_interaction_smoke'))

    def test_06_reference_art_remains_exact_and_gameplay_is_shared(self):
        manifest = json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        for image in manifest['images']:
            p = list((ROOT/'assets').rglob(image['file'].replace('.png', '_canon_source.png')))
            self.assertEqual(len(p), 1, image['world'])
            self.assertEqual(hashlib.sha256(p[0].read_bytes()).hexdigest(), image['sha256'])
        for source in ('scripts/ai_opponent.gd', 'scripts/pirate_opening_campaign.gd',
                       'scripts/world_visuals.gd', 'main.tscn', 'project.godot'):
            self.assertTrue((ROOT/source).is_file(), source)
        self.assertIn('const WorldVisuals = preload(', MAIN)
        self.assertIn('const AIOpponent = preload(', MAIN)

    def test_07_unchanged_predecessor_files_are_byte_identical(self):
        if not PREDECESSOR.is_file():
            self.skipTest('Predecessor archive unavailable')
        with zipfile.ZipFile(PREDECESSOR) as z:
            names = [n for n in z.namelist() if n.startswith('sinee-more-godot/') and not n.endswith('/')]
            self.assertEqual(len(names), 381)
            for name in names:
                if name == 'sinee-more-godot/scripts/main.gd':
                    continue
                self.assertEqual((ROOT/name.removeprefix('sinee-more-godot/')).read_bytes(), z.read(name), name)

    def test_08_support_contact_projection_remains_inside_small_and_large_landscape(self):
        # Conservative geometry oracle: world quad source corners are transformed
        # exactly by PerspectiveGeometry.board_quad, without a Godot renderer.
        assert 'const ENLARGE := 1.12' in GEOMETRY
        corners = re.findall(r'PackedVector2Array\(\[Vector2\(([^)]+)\), Vector2\(([^)]+)\), Vector2\(([^)]+)\), Vector2\(([^)]+)\)\]\)', GEOMETRY)
        self.assertEqual(len(corners), 7)
        for width, height in ((746, 280), (1280, 720), (1920, 1080)):
            board_height = height
            scale = min(max(board_height / 720.0, 0.35), 1.0)
            contact_depth = max(3.0, 11.0 * scale)
            shift = -min(board_height * .045, 13)
            for world, q in enumerate(corners):
                pts = [tuple(float(n.strip()) for n in s.split(',')) for s in q]
                cy = sum(p[1] for p in pts) / 4
                front_y = max(cy + (pts[i][1] - cy) * 1.12 for i in (2, 3)) / 941.0 * board_height + shift
                if world > 0:
                    self.assertGreater(front_y, 0)
                    self.assertLess(front_y + contact_depth, height - 5, (world, width, height))


if __name__ == '__main__':
    unittest.main()
