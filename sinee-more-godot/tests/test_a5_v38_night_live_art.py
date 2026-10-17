"""Offline v38 Night Sea integration checks. Does not certify Godot runtime/touch."""
import hashlib, json, subprocess, sys, unittest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_night_ranked'
WORLD=(ROOT/'scripts/world_visuals.gd').read_text(encoding='utf8')
MAIN=(ROOT/'scripts/main.gd').read_text(encoding='utf8')
MANIFEST=json.loads((ART/'asset_manifest.json').read_text(encoding='utf8'))
BASE_DATA=json.loads((ROOT/'tests/a5_v37_baseline_hashes.json').read_text())
BASE_HASHES=BASE_DATA['sha256_by_path']
SHA='ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'

class NightSea(unittest.TestCase):
 def test_approved_reference_exact_and_unmodified(self):
  self.assertEqual(hashlib.sha256((ART/'06_night_sea_canon_source.png').read_bytes()).hexdigest(),SHA)
  self.assertEqual(MANIFEST['source_sha256'],SHA)
  with Image.open(ART/'06_night_sea_canon_source.png') as image:
   self.assertEqual(image.size,(1672,941))
 def test_18_rank_player_pairs(self):
  self.assertEqual(len(MANIFEST['assets']),18)
  self.assertEqual({(m['rank'],m['player']) for m in MANIFEST['assets']},{(r,p) for r in range(1,10) for p in (1,2)})
 def test_asset_hash_and_transparency(self):
  for m in MANIFEST['assets']:
   path=ART/m['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),m['sha256'])
   rgba=np.asarray(Image.open(path).convert('RGBA'))
   self.assertEqual(rgba.shape,(128,128,4));self.assertEqual(int(rgba[0,0,3]),0)
   y,x=np.where(rgba[:,:,3]>100)
   self.assertGreater(len(x),80)
   self.assertEqual([int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],m['alpha_bounds'])
 def test_visible_silhouettes_strictly_grow(self):
  for p in (1,2):
   sizes=[m['visible_width'] for m in MANIFEST['assets'] if m['player']==p]
   self.assertTrue(all(a<b for a,b in zip(sizes,sizes[1:])),sizes)
 def test_two_opposing_lantern_light_materials(self):
  warm=np.asarray(Image.open(ART/'night_rank_09_p1.png').convert('RGBA'))
  cool=np.asarray(Image.open(ART/'night_rank_09_p2.png').convert('RGBA'))
  bright=(warm[:,:,0]>160)&(warm[:,:,3]>160)
  self.assertGreater(bright.sum(),100)
  self.assertGreater(float((warm[:,:,0]-warm[:,:,2])[bright].mean()),40)
  self.assertGreater(float((cool[:,:,2]-cool[:,:,0])[bright].mean()),45)
 def test_distinct_source_silhouettes_not_reused_master(self):
  # Distinct original lanterns produce distinct sprite textures, not a clone.
  hashes=[hashlib.sha256((ART/f'night_rank_{r:02d}_p1.png').read_bytes()).hexdigest() for r in range(1,10)]
  self.assertEqual(len(set(hashes)),9)
  self.assertIn('nine distinct original reserve lanterns',MANIFEST['method'])
 def test_reproducible_builder(self):
  before={m['file']:m['sha256'] for m in MANIFEST['assets']}
  p=subprocess.run([sys.executable,str(ROOT/'tools/build_night_ranked_assets.py')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  self.assertIn('A5_NIGHT_NINE_SOURCE_GOTHIC_BEACONS_PASS',p.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_live_world_5_sprite_binding(self):
  self.assertIn('if world == 5:',WORLD.split('func piece_texture(',1)[1])
  self.assertIn('res://assets/a5_night_ranked/night_rank_%02d_p%d.png',WORLD)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('func _run_headless_night_ranked_art_smoke()',MAIN)
  self.assertIn('_run_headless_night_ranked_art_smoke()',MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1])
 def test_live_badges_on_reserve_and_board(self):
  self.assertIn('var night_band := _night_rank_band(rank)',MAIN)
  self.assertIn('var night_band := _night_rank_band(int(top.rank))',MAIN)
  self.assertIn('number.anchor_top = night_band.x',MAIN)
  self.assertIn('rank.position = rect.position + Vector2(0.0, rect.size.y * night_band.x)',MAIN)
  self.assertIn('rank_label.text == str(rank)',MAIN)
 def test_badge_within_each_ranked_silhouette(self):
  for rank in range(1,10):
   center=.803-.0063*(rank-1)
   bounds=next(m['alpha_bounds'] for m in MANIFEST['assets'] if m['rank']==rank and m['player']==1)
   self.assertGreater(center*128,bounds[1]);self.assertLess(center*128,bounds[3])
 def test_night_physically_supported_and_board_cells(self):
  self.assertIn('foundation.visible = world == 1 or world == 2 or world == 3 or world == 5 or world == 6',WORLD)
  self.assertIn('res://assets/a5_reference_cells/night/cell_04.png',WORLD)
  self.assertIn('chart.visible = world >= 1 and world <= 5',WORLD)
  self.assertIn('var has_support := current_world != 0',MAIN)
 def test_previous_assets_preserved(self):
  old={name:sha for name,sha in BASE_HASHES.items() if name.startswith('assets/')}
  for name,sha in old.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),sha,name)
 def test_gameplay_and_ai_logic_unchanged(self):
  def body(s,f):return s.split(f,1)[1].split('\nfunc ',1)[0]
  for f,old_sha in BASE_DATA['protected_gameplay_function_sha256'].items():
   self.assertEqual(hashlib.sha256(body(MAIN,f).encode()).hexdigest(),old_sha,f)
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('next_round_button.visible = game_over',MAIN)
 def test_source_change_scope(self):
  old=BASE_HASHES
  new={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
  self.assertEqual({k for k in old if old[k]!=new.get(k)},{'scripts/main.gd','scripts/world_visuals.gd'})
  self.assertTrue(all(k.startswith('assets/a5_night_ranked/') or k in ('tools/build_night_ranked_assets.py','tests/test_a5_v38_night_live_art.py','tests/a5_v37_baseline_hashes.json') for k in new.keys()-old.keys()))

if __name__=='__main__':unittest.main(verbosity=2)
