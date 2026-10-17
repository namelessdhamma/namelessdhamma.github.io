"""Static + source-asset preflight; NOT native Godot or real-touch evidence."""
from pathlib import Path
import re
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
ASSETS = ROOT / 'assets'
WORLDS = [
    ('a5_void_ranked', 'void'), ('a5_pirate_ranked', 'pirate'),
    ('a5_atlantis_ranked', 'atlantis'), ('a5_gods_ranked', 'gods'),
    ('a5_sand_ranked', 'sand'), ('a5_night_ranked', 'night'),
    ('a5_northern_ranked', 'north'),
]

class HeldTouchPreview(unittest.TestCase):
    def test_one_noninteractive_shared_overlay(self):
        self.assertEqual(MAIN.count('TextureRect.new()\n\tperspective_touch_preview_icon.name'), 1)
        self.assertEqual(MAIN.count('Label.new()\n\tperspective_touch_preview_rank.name'), 1)
        self.assertIn('perspective_touch_preview_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE', MAIN)
        self.assertIn('perspective_touch_preview_rank.mouse_filter = Control.MOUSE_FILTER_IGNORE', MAIN)
        self.assertIn('perspective_touch_preview_icon.modulate.a = 0.57', MAIN)
        self.assertIn('perspective_touch_preview_icon.visible = false', MAIN)

    def test_preview_cannot_authorize_or_mutate_gameplay(self):
        body = MAIN.split('func _refresh_touch_preview() -> void:\n', 1)[1].split('\nfunc _refresh_selection_feedback()', 1)[0]
        for condition in [
            '_touch_board_pending', '_touch_board_state_at_press != _touch_board_state_token()',
            '_modal_blocks_board_input()', '_is_legal_move(turn, rank, _touch_board_cell)',
            '_reserve_rank_label_band(rank)',
        ]:
            self.assertIn(condition, body)
        for forbidden in ['_on_primary(', '_on_cell_pressed(', 'board_stacks.append(', '_save_match(', 'reserve_available[', 'moves +=', 'turn =']:
            self.assertNotIn(forbidden, body)
        self.assertIn('world_visuals.piece_texture(current_world, turn, rank)', body)
        self.assertIn('perspective_touch_preview_rank.text = str(rank)', body)

    def test_all_termination_paths_hide_preview(self):
        cancel = MAIN.split('func _cancel_pending_board_touch() -> void:\n', 1)[1].split('\nfunc _input(', 1)[0]
        self.assertIn('_refresh_touch_preview()', cancel)
        self.assertIn('_touch_board_pending = false\n\t\t\t_touch_board_cell = -1\n\t\t\t_touch_board_state_at_press.clear()\n\t\t\t_refresh_touch_preview()', MAIN)
        self.assertIn('_touch_board_state_at_press = _touch_board_state_token()\n\t\t_refresh_touch_preview()', MAIN)
        self.assertIn('"Canceled returning swipe must not leave a ghost piece"', MAIN)
        self.assertIn('"Released touch must remove the preview before rendering committed occupancy"', MAIN)

    def test_all_seven_worlds_have_ranked_preview_textures(self):
        for folder, prefix in WORLDS:
            for player in (1, 2):
                widths = []
                heights = []
                for rank in range(1, 10):
                    path = ASSETS / folder / f'{prefix}_rank_{rank:02d}_p{player}.png'
                    with self.subTest(world=prefix, player=player, rank=rank):
                        self.assertTrue(path.is_file())
                        with Image.open(path) as image:
                            self.assertEqual(image.size, (128, 128))
                            self.assertEqual(image.mode, 'RGBA')
                            bbox = image.getchannel('A').point(lambda a: 255 if a > 20 else 0).getbbox()
                            self.assertIsNotNone(bbox)
                            widths.append(bbox[2] - bbox[0]); heights.append(bbox[3] - bbox[1])
                self.assertTrue(all(b > a for a, b in zip(widths, widths[1:])), (prefix, player, widths))
                self.assertTrue(all(b > a for a, b in zip(heights, heights[1:])), (prefix, player, heights))

if __name__ == '__main__':
    unittest.main()
