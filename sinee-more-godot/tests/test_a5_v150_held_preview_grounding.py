"""v150 source/geometry preflight; engine and physical-touch evidence remain OPEN."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
GROUNDING = (ROOT / 'scripts/piece_grounding.gd').read_text(encoding='utf-8')


class GroundedPreview(unittest.TestCase):
    def test_shared_rank_geometry_is_used_by_live_piece_and_preview(self):
        self.assertEqual(MAIN.count('func _perspective_piece_rect('), 1)
        helper = MAIN.split('func _perspective_piece_rect(', 1)[1].split('\nfunc _refresh_perspective_layer(', 1)[0]
        self.assertIn('PieceGrounding.baseline_shift(world, rank, extent)', helper)
        self.assertIn('if rank > 0:', helper)
        live = MAIN.split('func _refresh_perspective_layer() -> void:', 1)[1].split('\nfunc _refresh_touch_preview()', 1)[0]
        preview = MAIN.split('func _refresh_touch_preview() -> void:', 1)[1].split('\nfunc _refresh_selection_feedback()', 1)[0]
        self.assertIn('var rect := _perspective_piece_rect(current_world, i,', live)
        self.assertIn('var preview_rect := _perspective_piece_rect(current_world, cell, rank, extent)', preview)
        self.assertNotIn('perspective_touch_preview_icon.position = reference_icon.position', preview)
        self.assertIn('perspective_touch_preview_icon.position = preview_rect.position', preview)
        self.assertIn('perspective_touch_preview_icon.size = preview_rect.size', preview)

    def test_rank_9_over_rank_1_old_offset_mismatch_and_fixed_all_worlds(self):
        block = GROUNDING.split('const BOTTOM_PX := [', 1)[1].split(']\nconst TARGET_BASE_PX', 1)[0]
        bottoms = [[int(x) for x in re.findall(r'\d+', row.split(']')[0])]
                   for row in block.splitlines() if row.lstrip().startswith('[')]
        self.assertEqual(len(bottoms), 7)
        for world, row in enumerate(bottoms):
            self.assertEqual(len(row), 9)
            for extent in (22, 44, 88):
                for covered_rank in range(1, 10):
                    for preview_rank in range(1, 10):
                        shift = lambda rank: 0 if world == 0 else extent * (124 - row[rank - 1]) / 128
                        eventual = shift(preview_rank)
                        preview = shift(preview_rank)  # same helper as committed render
                        self.assertAlmostEqual(preview, eventual)
                        if world == 6 and covered_rank == 1 and preview_rank == 9:
                            self.assertGreater(abs(shift(covered_rank) - eventual), 4.0)
        self.assertEqual(bottoms[6][0], 85)
        self.assertEqual(bottoms[6][-1], 114)

    def test_board_rank_badge_center_matches_preview(self):
        preview = MAIN.split('func _refresh_touch_preview() -> void:', 1)[1].split('\nfunc _refresh_selection_feedback()', 1)[0]
        self.assertIn('var band := _reserve_rank_label_band(rank)', preview)
        self.assertIn('if current_world == 1:\n\t\tband.x = 0.03', preview)
        self.assertIn('preview_rect.position.y + preview_rect.size.y', preview)
        self.assertIn('perspective_touch_preview_rank.position = Vector2(preview_rect.position.x,', preview)
        self.assertIn('clampf(center_y - number_height * 0.5, cell_top + 1.0, cell_bottom - number_height - 1.0)', preview)

    def test_native_smoke_covers_seven_real_scene_worlds_and_cover(self):
        self.assertIn('_run_headless_held_preview_grounding_smoke()', MAIN)
        smoke = MAIN.split('func _run_headless_held_preview_grounding_smoke() -> void:', 1)[1].split('\n# Engine-level geometry assertion', 1)[0]
        for fragment in ('for world in range(WorldVisuals.WORLDS.size())',
                         '_on_cell_pressed(4)', '_on_reserve_pressed(2, 8)',
                         '_input(touch)', 'int(_top_piece(4).rank) == 9',
                         'perspective_icons[4].position.is_equal_approx(preview_position)',
                         'perspective_ranks[4].position.is_equal_approx(preview_label_position)',
                         'BLUE_SEA_HELD_PREVIEW_GROUNDING_PASS'):
            self.assertIn(fragment, smoke)
        self.assertNotIn('board_stacks.append(', smoke)


if __name__ == '__main__':
    unittest.main()
