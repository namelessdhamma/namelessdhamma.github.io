"""A5 v39 offline source/art regression; engine and touch require Godot."""
from pathlib import Path
import hashlib, json, subprocess, sys, unittest, zipfile
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_void_ranked'
MAN=json.loads((ART/'asset_manifest.json').read_text())
MAIN=(ROOT/'scripts/main.gd').read_text()
WORLD=(ROOT/'scripts/world_visuals.gd').read_text()
SHA='00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'
SOURCE_NAMES={
 'assets/a5_void_ranked/01_nd_premium_void_canon_source.png':SHA,
 'assets/a5_pirate_ranked/02_pirate_sea_canon_source.png':'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
 'assets/a5_atlantis_ranked/03_atlantis_canon_source.png':'2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
 'assets/a5_gods_ranked/04_gods_of_the_deep_canon_source.png':'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
 'assets/a5_sand_ranked/05_sand_sea_canon_source.png':'01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
 'assets/a5_night_ranked/06_night_sea_canon_source.png':'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
 'assets/a5_northern_ranked/07_northern_sea_canon_source.png':'3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775',
}

class VoidArt(unittest.TestCase):
 def test_canonical_seven_exact_hashes(self):
  for path,sha in SOURCE_NAMES.items():
   self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha,path)
 def test_original_void_source_untouched(self):
  self.assertEqual(MAN['source_sha256'],SHA)
  with Image.open(ART/'01_nd_premium_void_canon_source.png') as im:
   self.assertEqual(im.size,(1672,941))
 def test_exact_18_rank_side_pairs(self):
  self.assertEqual({(m['rank'],m['player']) for m in MAN['assets']},{(r,p) for r in range(1,10) for p in (1,2)})
 def test_transparent_sprites_and_hashes(self):
  for m in MAN['assets']:
   path=ART/m['file']; self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),m['sha256'])
   arr=np.asarray(Image.open(path).convert('RGBA'));self.assertEqual(arr.shape,(128,128,4))
   self.assertEqual(int(arr[0,0,3]),0)
   y,x=np.where(arr[:,:,3]>100);self.assertGreater(len(x),100)
   self.assertEqual([int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],m['alpha_bounds'])
 def test_strict_rank_size_growth(self):
  for player in (1,2):
   widths=[m['visible_width'] for m in MAN['assets'] if m['player']==player]
   self.assertTrue(all(a<b for a,b in zip(widths,widths[1:])),widths)
 def test_two_opposing_glass_light_families(self):
  a=np.asarray(Image.open(ART/'void_rank_09_p1.png').convert('RGBA')).astype('int16')
  b=np.asarray(Image.open(ART/'void_rank_09_p2.png').convert('RGBA')).astype('int16')
  lit_a=(a[:,:,3]>150)&(a[:,:,0]>150)
  lit_b=(b[:,:,3]>150)&(b[:,:,2]>150)
  self.assertGreater(lit_a.sum(),150);self.assertGreater(lit_b.sum(),150)
  self.assertGreater(np.median(a[:,:,0][lit_a]-a[:,:,2][lit_a]),30)
  self.assertGreater(np.median(b[:,:,2][lit_b]-b[:,:,0][lit_b]),30)
 def test_screenshot_digits_explicitly_removed(self):
  # Inpaint masks are confined to the original screenshot digits; actual
  # ranks are subsequently drawn by live Godot Labels, never image-baked.
  for player in ('1','2'):
   self.assertGreater(MAN['digit_inpaint_mask_pixels'][player],180)
  self.assertIn('number.text = str(rank) if rank > 0 else ""',MAIN)
 def test_builder_deterministic(self):
  before={m['file']:m['sha256'] for m in MAN['assets']}
  run=subprocess.run([sys.executable,str(ROOT/'tools/build_void_ranked_assets.py')],capture_output=True,text=True,timeout=25)
  self.assertEqual(run.returncode,0,run.stderr)
  self.assertIn('A5_VOID_GLASS_SOURCE_RANKED_PASS 18',run.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_live_shared_piece_binding(self):
  block=WORLD.split('func piece_texture(',1)[1].split('var image := Image.create(',1)[0]
  self.assertIn('if world == 0:',block)
  self.assertIn('res://assets/a5_void_ranked/void_rank_%02d_p%d.png',block)
  self.assertIn('piece_cache[key] = void_texture',block)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
 def test_game_state_not_screenshot(self):
  self.assertIn('number.text = str(rank) if rank > 0 else ""',MAIN)
  self.assertIn('rank.text = str(int(top.rank))',MAIN)
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('next_round_button.visible = game_over',MAIN)
 def test_only_void_floats(self):
  self.assertIn('var has_support := current_world != 0',MAIN)
  self.assertIn('perspective_support_surface.visible = has_support',MAIN)
  self.assertIn('assert(not perspective_support_surface.visible',MAIN)
 def test_headless_engine_smoke_is_wired(self):
  self.assertIn('func _run_headless_void_ranked_art_smoke() -> void:',MAIN)
  self.assertIn('_run_headless_void_ranked_art_smoke()',MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1])
  self.assertIn('BLUE_SEA_VOID_SOURCE_GLASS_DOMES_PASS',MAIN)
 def test_prior_ranked_assets_preserved(self):
  for world,folder in [('pirate','a5_pirate_ranked'),('atlantis','a5_atlantis_ranked'),('gods','a5_gods_ranked'),('sand','a5_sand_ranked'),('night','a5_night_ranked'),('north','a5_northern_ranked')]:
   man=json.loads((ROOT/'assets'/folder/'asset_manifest.json').read_text())
   self.assertEqual(len(man['assets']),18,world)
   for m in man['assets']:
    self.assertEqual(hashlib.sha256((ROOT/'assets'/folder/m['file']).read_bytes()).hexdigest(),m['sha256'],world)
 def test_ai_modes_preserved(self):
  self.assertIn('func _play_ai_turn()',MAIN)
  self.assertIn('func _run_headless_even_round_ai_smoke()',MAIN)
  self.assertIn('func _run_headless_rule_modes_smoke()',MAIN)
  self.assertIn('func _run_headless_reference_menu_smoke()',MAIN)
  self.assertIn('func _run_headless_pirate_menu_smoke()',MAIN)
 def test_no_extra_engine_or_seven_forks(self):
  self.assertEqual(len(list((ROOT/'scripts').glob('main.gd'))),1)
  self.assertIn('const WORLDS := [',WORLD)
  self.assertEqual(WORLD.split('const WORLDS := [',1)[1].split(']',1)[0].count('Sea'),4)

if __name__=='__main__':unittest.main(verbosity=2)
