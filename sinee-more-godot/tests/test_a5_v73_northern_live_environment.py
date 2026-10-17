"""A5 v73: Northern Sea original environment integrated into the LIVE seven-world game.
Offline checks are NOT Godot compilation, rendered screenshot or real-phone evidence.
"""
import hashlib, json, re, unittest
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
VISUAL=(ROOT/"scripts/world_visuals.gd").read_text(encoding="utf-8")
MAIN=(ROOT/"scripts/main.gd").read_bytes()
ASSETS=ROOT/"assets/a5_northern_environment"
MAN=json.loads((ASSETS/"asset_manifest.json").read_text(encoding="utf-8"))

class NorthernV73(unittest.TestCase):
    def test_01_original_environment_is_actually_loaded_into_live_scene(self):
        self.assertIn('if world == 6:\n\t\t\t# Prebaked original fjord/aurora scenery',VISUAL)
        self.assertIn('load(NORTHERN_ENV_ROOT + "/north_fjord_backdrop.png")',VISUAL)
        self.assertIn('backdrop.texture = backdrop_cache[world]',VISUAL)
        self.assertIn('scenery.visible = world != 0',VISUAL)

    def test_02_northern_board_has_physical_support(self):
        self.assertIn('load(NORTHERN_ENV_ROOT + "/north_frozen_runestone_plinth.png")',VISUAL)
        self.assertIn('foundation.texture = northern_plinth',VISUAL)
        self.assertIn('support.visible = world != 0',VISUAL)
        self.assertIn('foundation.visible = world >= 1 and world <= 6',VISUAL)
        self.assertIn('perspective_support_surface.texture = material',MAIN.decode())

    def test_03_original_assets_not_flattened_gameplay_screenshot(self):
        self.assertFalse(MAN['contains_board_cells_or_occupancy'])
        self.assertFalse(MAN['canonical_pngs_mutated'])
        self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)',VISUAL)
        self.assertIn('chart.mouse_filter = Control.MOUSE_FILTER_IGNORE',VISUAL)
        self.assertIn('world_visuals.piece_texture(current_world',MAIN.decode())
        self.assertIn('rank.text = str(int(top.rank))',MAIN.decode())

    def test_04_exact_original_asset_sizes_and_distinct_materials(self):
        self.assertEqual(len(MAN["assets"]),2)
        self.assertEqual({a["file"] for a in MAN["assets"]},
                         {"north_fjord_backdrop.png","north_frozen_runestone_plinth.png"})
        for item in MAN["assets"]:
            path=ASSETS/item["file"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item["sha256"])
            with Image.open(path) as im:
                self.assertEqual(list(im.size),item["size"])
                self.assertGreater(len(im.getcolors(2000000) or []),40 if "plinth" in item["file"] else 300)
        with Image.open(ASSETS/"north_fjord_backdrop.png") as im:
            self.assertEqual(im.size,(1024,576))
        with Image.open(ASSETS/"north_frozen_runestone_plinth.png") as im:
            self.assertEqual(im.size,(512,512))

    def test_05_prebuilt_backdrop_has_mountain_aurora_fjord_ship_quay(self):
        source=(ROOT/"tools/build_northern_environment.py").read_text()
        for expected in ["aurora", "mountain", "Fjord", "Longship", "frozen quay",
                         "sky=sky*(1-aurora", "im=Image.fromarray"]:
            self.assertIn(expected.lower(),source.lower())
        self.assertNotIn('07_northern_sea_canon_source.png',source)

    def test_06_plinth_is_not_repeated_board_cell(self):
        source=(ROOT/"tools/build_northern_environment.py").read_text()
        for expected in ["basalt", "Engraved circular", "Snow drifts", "Ice fractures"]:
            self.assertIn(expected,source)
        self.assertNotIn("board_stacks",source)
        self.assertNotIn("reserve_available",source)

    def test_07_all_seven_accepted_pngs_unchanged(self):
        manifest=json.loads((ROOT/"tools/approved_seven_world_manifest.json").read_text())
        self.assertEqual(len(manifest["images"]),7)
        for item in manifest["images"]:
            target=list((ROOT/"assets").rglob(item["file"].replace(".png","_canon_source.png")))
            self.assertEqual(len(target),1,item["file"])
            self.assertEqual(hashlib.sha256(target[0].read_bytes()).hexdigest(),item["sha256"])

    def test_08_world_catalog_shared_engine_and_pirate_preserved(self):
        self.assertIn('"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep"',VISUAL)
        self.assertIn('"Sand Sea", "Night Sea", "Northern Sea"',VISUAL)
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")',MAIN.decode())
        self.assertIn('const WorldVisuals = preload("res://scripts/world_visuals.gd")',MAIN.decode())
        self.assertTrue((ROOT/"scripts/pirate_opening_campaign.gd").exists())
        self.assertTrue((ROOT/"scripts/pirate_opening_choice_surface.gd").exists())

    def test_09_runtime_smoke_checks_nine_cells_and_state_without_claiming_pass(self):
        smoke=(ROOT/"tests/a5_v73_northern_runtime_smoke.gd").read_text()
        for required in ['game.call("_set_world", 6)','for i in range(9)',
                         'board_stacks','reserve_available','quit(1)',
                         'game.call("_set_world", 0)','A5_V73_NORTHERN_ENV_RUNTIME_PASS']:
            self.assertIn(required,smoke)

    def test_10_previous_worlds_and_live_scene_source_are_unchanged(self):
        # v73 edits world_visuals only, not the shared D2 engine, scene or Pirate.
        self.assertTrue((ROOT/"main.tscn").exists())
        self.assertIn('world >= 1 and world <= 6',VISUAL)
        for name in ['pirate','atlantis','gods','sand','night','north']:
            self.assertTrue((ROOT/"assets/a5_reference_cells"/name).is_dir())
        self.assertIn('var night_plinth: Texture2D',VISUAL)
        self.assertIn('sand_plinth = load(SAND_NIGHT_ENV_ROOT + "/sand_sandstone_support.png")',VISUAL)

if __name__=="__main__": unittest.main()
