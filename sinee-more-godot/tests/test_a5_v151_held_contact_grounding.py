"""A5 v151: held rank's contact/glow is the same as committed live piece.

These are independent source/geometry checks, not a Godot render or real touch.
The actual production Godot smoke in main.gd is separately opt-in and UNRUN.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
GROUNDING = (ROOT / 'scripts/piece_grounding.gd').read_text(encoding='utf-8')


def bottoms():
    block = GROUNDING.split('const BOTTOM_PX := [', 1)[1].split(']\nconst TARGET_BASE_PX', 1)[0]
    return [[int(n) for n in re.findall(r'\d+', line.split(']')[0])]
            for line in block.splitlines() if line.lstrip().startswith('[')]


class HeldContactGrounding(unittest.TestCase):
    def test_one_contact_helper_drives_live_and_held_geometry(self):
        self.assertEqual(MAIN.count('func _apply_piece_contact('), 1)
        helper = MAIN.split('func _apply_piece_contact(', 1)[1].split('\nfunc _refresh_perspective_layer(', 1)[0]
        self.assertIn('PieceGrounding.bottom_fraction(world, rank)', helper)
        self.assertIn('PieceGrounding.ellipse(center, extent * (0.14 + 0.035 * rank), extent * 0.065)', helper)
        self.assertIn('if world == 0:', helper)
        self.assertIn('center.y += extent * 0.24', helper)
        self.assertIn('Color(0.015, 0.02, 0.035, 0.43)', helper)
        live = MAIN.split('func _refresh_perspective_layer() -> void:', 1)[1].split('\nfunc _refresh_touch_preview()', 1)[0]
        held = MAIN.split('func _refresh_touch_preview() -> void:', 1)[1].split('\nfunc _refresh_selection_feedback()', 1)[0]
        self.assertIn('_apply_piece_contact(contact, current_world, rect, extent,', live)
        self.assertIn('_apply_piece_contact(perspective_touch_preview_contact, current_world,', held)
        self.assertEqual(MAIN.count('PieceGrounding.ellipse('), 2, 'Only the shared helper should create contacts')

    def test_contact_does_not_intercept_touch_and_clears_on_cancellation(self):
        create = MAIN.split('perspective_touch_preview_contact = Polygon2D.new()', 1)[1].split('perspective_touch_preview_icon = TextureRect.new()', 1)[0]
        self.assertIn('perspective_touch_preview_contact.z_index = 3', create)
        self.assertIn('perspective_touch_preview_contact.modulate.a = 0.57', create)
        self.assertIn('perspective_touch_preview_contact.visible = false', create)
        self.assertNotIn('Button.new()', create)
        held = MAIN.split('func _refresh_touch_preview() -> void:', 1)[1].split('\nfunc _refresh_selection_feedback()', 1)[0]
        self.assertLess(held.index('perspective_touch_preview_contact.visible = false'), held.index('if not _touch_board_pending'))
        self.assertLess(held.index('if not _is_legal_move('), held.index('perspective_touch_preview_contact.visible = true'))
        self.assertIn('perspective_touch_preview_contact.visible = true', held)
        cancel = MAIN.split('func _cancel_pending_board_touch() -> void:', 1)[1].split('\nfunc _input(', 1)[0]
        self.assertIn('_refresh_touch_preview()', cancel)

    def test_physical_contact_stays_on_same_plane_for_all_ranks(self):
        rows = bottoms()
        self.assertEqual(len(rows), 7)
        for world in range(1, 7):
            self.assertEqual(len(rows[world]), 9)
            for extent in (22.0, 44.0, 88.0):
                expected = extent * (124 / 128 - 0.5)
                for rank in range(1, 10):
                    alpha_bottom = rows[world][rank - 1] / 128
                    baseline_shift = extent * (124 / 128 - alpha_bottom)
                    rect_top = -extent / 2 + baseline_shift
                    shadow_y = rect_top + extent * alpha_bottom
                    self.assertAlmostEqual(shadow_y, expected, places=8,
                                           msg=f'world={world},rank={rank},extent={extent}')
        self.assertNotEqual(rows[6][0], rows[6][8], 'North must test rank-dependent alpha bounds')

    def test_native_fixture_checks_contact_before_after_commit_in_seven_worlds(self):
        smoke = MAIN.split('func _run_headless_held_preview_grounding_smoke() -> void:', 1)[1].split('\n# Engine-level geometry assertion', 1)[0]
        for token in ('for world in range(WorldVisuals.WORLDS.size())',
                      'perspective_touch_preview_contact.visible',
                      'preview_contact_polygon := perspective_touch_preview_contact.polygon.duplicate()',
                      'preview_contact_color := perspective_touch_preview_contact.color',
                      'perspective_piece_contacts[4].polygon == preview_contact_polygon',
                      'perspective_piece_contacts[4].color == preview_contact_color',
                      'not perspective_touch_preview_contact.visible'):
            self.assertIn(token, smoke)


if __name__ == '__main__':
    unittest.main()
