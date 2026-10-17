"""Seven-world canonical menu is live and visible, including minimal Void."""
import hashlib
import json
import re
import unittest
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SRC = (ROOT / "scripts" / "main.gd").read_text()
MANIFEST = json.loads((ASSETS / "a5_menu_plates" / "manifest.json").read_text())
APPROVED = json.loads((ROOT / "tools" / "approved_seven_world_manifest.json").read_text())["images"]


def body(name):
    m = re.search(r"^func " + re.escape(name) + r"\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)", SRC, re.M | re.S)
    assert m, name
    return m.group(1)


class LiveCanonicalMenu(unittest.TestCase):
    def test_01_all_seven_exact_approved_sources_untouched(self):
        self.assertEqual(len(MANIFEST), 7)
        for i, record in enumerate(MANIFEST):
            matches = list(ASSETS.glob("a5_*_ranked/" + record["source"]))
            self.assertEqual(len(matches), 1)
            self.assertEqual(hashlib.sha256(matches[0].read_bytes()).hexdigest(), APPROVED[i]["sha256"])
            self.assertEqual(record["source_sha256"], APPROVED[i]["sha256"])

    def test_02_each_plate_is_original_source_pixels_with_rounded_alpha(self):
        for record in MANIFEST:
            source = Image.open(next(ASSETS.glob("a5_*_ranked/" + record["source"]))).convert("RGBA")
            plate = Image.open(ASSETS / "a5_menu_plates" / record["sprite"]).convert("RGBA")
            x0, y0, x1, y1 = record["bounds"]
            self.assertEqual(plate.size, (x1-x0, y1-y0))
            self.assertEqual(plate.getchannel("A").getpixel((0,0)), 0)
            self.assertEqual(plate.getchannel("A").getpixel(((x1-x0)//2, (y1-y0)//2)), 255)
            # All visible plate pixels must be verbatim from the accepted PNG.
            source_crop = source.crop((x0,y0,x1,y1))
            if record["world"] != 0:
                self.assertIsNone(ImageChops.difference(source_crop.convert("RGB"), plate.convert("RGB")).getbbox())
            else:
                # Minimal Void removes only cosmic contamination from its
                # derived button; all three approved glyph strokes survive.
                for yy in range(plate.height):
                    for xx in range(plate.width):
                        r,g,b,a = plate.getpixel((xx,yy))
                        if a and min(r,g,b) >= 175:
                            self.assertEqual((r,g,b), source_crop.getpixel((xx,yy))[:3])
                        if a:
                            self.assertFalse(r > 80 and r > g*1.4 and r > b*1.7)
            # Real three white glyph strokes are present in the source plate.
            bright = sum(1 for r,g,b,a in plate.get_flattened_data() if a and min(r,g,b) >= 175)
            self.assertGreater(bright, 80, record["sprite"])

    def test_03_supported_worlds_have_no_double_menu_plate(self):
        for record in MANIFEST[1:]:
            x0,y0,x1,y1 = record["bounds"]
            scene = Image.open(ASSETS / "a5_scenery_perimeter" / f"world_{record['world']:02d}.png").convert("RGBA")
            mask = Image.new("L", (x1-x0,y1-y0), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,x1-x0-1,y1-y0-1), radius=record["radius"], fill=255)
            a = scene.getchannel("A").crop((x0,y0,x1,y1))
            for aa, mm in zip(a.get_flattened_data(), mask.get_flattened_data()):
                if mm:
                    self.assertEqual(aa, 0)
            self.assertGreater(scene.getchannel("A").getpixel((140,70)), 0)

    def test_04_void_has_live_plate_despite_hidden_perimeter(self):
        self.assertIn('scenery.visible = world != 0', (ROOT / 'scripts/world_visuals.gd').read_text())
        # ResourceLoader.CACHE_MODE_IGNORE is the current bounded-memory path;
        # an old load() exact-string assertion no longer expresses the contract.
        self.assertIn('reference_menu_art.texture = ResourceLoader.load(menu_path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE) as Texture2D', body('_set_world'))
        self.assertIn('world_%02d.png', body('_set_world'))
        self.assertIn('CanonicalMenuPlate', body('_create_reference_menu_hotspot'))

    def test_05_menu_is_real_touch_button_not_flattened_screenshot(self):
        create = body('_create_reference_menu_hotspot')
        layout = body('_layout_reference_menu_hotspot')
        callback = body('_on_reference_menu_hotspot_pressed')
        self.assertIn('reference_menu_hotspot.pressed.connect(_on_reference_menu_hotspot_pressed)', create)
        self.assertIn('reference_menu_art.mouse_filter = Control.MOUSE_FILTER_IGNORE', create)
        self.assertIn('reference_menu_hotspot.mouse_filter = Control.MOUSE_FILTER_STOP', create)
        self.assertIn('ceilf(_minimum_touch_physical_px() / scale)', layout)
        self.assertIn('_open_mobile_menu()', callback)
        self.assertIn('top_menu.get_popup().popup_centered()', callback)
        self.assertIn('reference_menu_hotspot.z_index = 7', create)

    def test_06_board_and_rules_remain_separate_live_layers(self):
        self.assertIn('PerspectiveGeometry.cell_at_touch(', body('_input'))
        self.assertIn('board_stacks[selected_cell].append(', body('_on_primary'))
        self.assertIn('var art := source.get_node_or_null("WorldCellArt")', body('_refresh_perspective_layer'))
        self.assertIn('reserve.visible = player == turn', body('_refresh_surface'))
        self.assertIn('next_round_button.visible = game_over', body('_refresh_surface'))


if __name__ == '__main__':
    unittest.main()
