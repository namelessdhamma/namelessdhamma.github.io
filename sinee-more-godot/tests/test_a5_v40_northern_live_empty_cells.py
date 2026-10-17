"""Offline v40 Northern rune-circle art integration; Godot runtime still required."""
import hashlib, json, subprocess, sys, unittest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/north'
CANON=ROOT/'assets/a5_northern_ranked/07_northern_sea_canon_source.png'
MAN=json.loads((ART/'asset_manifest.json').read_text())
WORLD=(ROOT/'scripts/world_visuals.gd').read_text()
MAIN=(ROOT/'scripts/main.gd').read_text()
SHA='3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775'

class NorthernLiveCellArt(unittest.TestCase):
 def test_01_source_exact(self):
  self.assertEqual(hashlib.sha256(CANON.read_bytes()).hexdigest(),SHA)
  self.assertEqual(MAN['source_sha256'],SHA)
  with Image.open(CANON) as im:self.assertEqual(im.size,(1672,941))
 def test_02_nine_cells(self):
  self.assertEqual({x['cell'] for x in MAN['assets']},set(range(9)))
  self.assertEqual(len(MAN['assets']),9)
 def test_03_source_is_empty_cells_only(self):
  self.assertEqual(set(MAN['donors']),{'top_middle','bottom_left'})
  self.assertEqual({x['empty_source_cell'] for x in MAN['assets']},set(MAN['donors']))
  self.assertIn('no figures, ranks, UI or occupancy',MAN['purpose'])
 def test_04_sha_for_every_tile(self):
  for a in MAN['assets']:
   p=ART/a['file']
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),a['sha256'])
   with Image.open(p) as im:self.assertEqual(im.size,(192,192))
 def test_05_opaque_no_baked_piece(self):
  # An occupied concept cell has a large orange/blue luminous disk.
  # Donor empty tiles have dark central rune-circle stone, not luminous tokens.
  for a in MAN['assets']:
   arr=np.asarray(Image.open(ART/a['file']).convert('RGB'))
   center=arr[66:126,66:126]
   bright=((center.max(axis=2)>220)&((center.max(axis=2)-center.min(axis=2))>80)).mean()
   self.assertLess(bright,0.07,a['file'])
 def test_06_deterministic_rebuild(self):
  before={x['file']:x['sha256'] for x in MAN['assets']}
  p=subprocess.run([sys.executable,str(ROOT/'tools/build_northern_empty_cells.py')],capture_output=True,text=True,timeout=20)
  self.assertEqual(p.returncode,0,p.stderr)
  self.assertIn('A5_NORTHERN_EMPTY_CANONICAL_CELLS_PASS 9',p.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_07_native_world_cell_binding(self):
  self.assertIn('chart.visible = world >= 1 and world <= 6',WORLD)
  self.assertIn('elif world == 4 or world == 5 or world == 6:',WORLD)
  self.assertIn('("night" if world == 5 else "north")',WORLD)
 def test_08_same_live_perspective_grid(self):
  self.assertIn('tile.texture = art.texture',MAIN)
  self.assertIn('PerspectiveGeometry.cell_quad(current_world, i, perspective_rect)',MAIN)
  self.assertIn('PerspectiveGeometry.cell_at(current_world, position, perspective_rect)',MAIN)
 def test_09_no_flattened_board(self):
  self.assertIn('var top := _top_piece(i)',MAIN)
  self.assertIn('icon.texture = world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('rank.text = str(int(top.rank))',MAIN)
 def test_10_godot_smoke_wired(self):
  self.assertIn('func _run_headless_northern_cell_art_smoke()',MAIN)
  self.assertIn('_run_headless_northern_cell_art_smoke()',MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1])
  self.assertIn('perspective_tiles[i].texture == art.texture',MAIN)
 def test_11_support_retained(self):
  self.assertIn('var has_support := current_world != 0',MAIN)
  self.assertIn('perspective_support_surface.visible = has_support',MAIN)
 def test_12_ai_and_rules_retained(self):
  self.assertIn('func _play_ai_turn()',MAIN)
  self.assertIn('func _run_headless_even_round_ai_smoke()',MAIN)
  self.assertIn('func _run_headless_rule_modes_smoke()',MAIN)
 def test_13_pirate_campaign_retained(self):
  self.assertTrue((ROOT/'scripts/pirate_opening_campaign.gd').exists())
  self.assertTrue((ROOT/'scripts/pirate_opening_choice_surface.gd').exists())
 def test_14_other_world_assets_unchanged(self):
  for folder in ['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked','a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']:
   man=json.loads((ROOT/'assets'/folder/'asset_manifest.json').read_text())
   self.assertEqual(len(man['assets']),18)
   for a in man['assets']:
    self.assertEqual(hashlib.sha256((ROOT/'assets'/folder/a['file']).read_bytes()).hexdigest(),a['sha256'])
 def test_15_no_new_engine(self):
  self.assertEqual(len(list((ROOT/'scripts').glob('main.gd'))),1)
  self.assertEqual(len(list((ROOT/'scripts').glob('world_visuals.gd'))),1)

if __name__=='__main__':unittest.main(verbosity=2)
