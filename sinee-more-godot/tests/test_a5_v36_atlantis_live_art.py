"""A5 v36 source-level Atlantis integration tests; NOT Godot or real-touch proof."""
import hashlib,json,subprocess,sys,unittest,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets'/'a5_atlantis_ranked'
MAIN=(ROOT/'scripts/main.gd').read_text()
WORLD=(ROOT/'scripts/world_visuals.gd').read_text()
MANIFEST=json.loads((ART/'asset_manifest.json').read_text())
BASE=Path('/mnt/data/A5_v35_Gods_Nine_Distinct_Canonical_Creatures_Integrated_Staging.zip')
SHA='2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'
class AtlantisArt(unittest.TestCase):
 def test_exact_accepted_reference(self):
  source=ART/'03_atlantis_canon_source.png'
  self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),SHA)
  self.assertEqual(MANIFEST['source_sha256'],SHA)
  with Image.open(source) as im:self.assertEqual(im.size,(1672,941))
 def test_two_materials_nine_ranks(self):
  self.assertEqual(len(MANIFEST['assets']),18)
  self.assertEqual({(m['rank'],m['player']) for m in MANIFEST['assets']},{(r,p) for r in range(1,10) for p in (1,2)})
 def test_sprite_checksums_alpha_and_bounds(self):
  for m in MANIFEST['assets']:
   path=ART/m['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),m['sha256'])
   rgba=np.asarray(Image.open(path).convert('RGBA'))
   self.assertEqual(rgba.shape,(128,128,4))
   self.assertEqual(int(rgba[0,0,3]),0)
   self.assertGreater(int((rgba[:,:,3]>100).sum()),80)
   y,x=np.where(rgba[:,:,3]>100)
   self.assertEqual([int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],m['alpha_bounds'])
 def test_monotonic_size(self):
  for player in (1,2):
   w=[m['visible_width'] for m in MANIFEST['assets'] if m['player']==player]
   self.assertTrue(all(a<b for a,b in zip(w,w[1:])),w)
 def test_opposing_materials_preserve_original_pixels(self):
  p1=np.asarray(Image.open(ART/'atlantis_rank_09_p1.png').convert('RGBA'))
  p2=np.asarray(Image.open(ART/'atlantis_rank_09_p2.png').convert('RGBA'))
  both=(p1[:,:,3]>100)&(p2[:,:,3]>100)
  self.assertGreater(np.linalg.norm(p1[:,:,:3][both].mean(0)-p2[:,:,:3][both].mean(0)),20)
 def test_source_derivation_deterministic(self):
  before={m['file']:m['sha256'] for m in MANIFEST['assets']}
  r=subprocess.run([sys.executable,str(ROOT/'tools/build_atlantis_ranked_assets.py')],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('A5_ATLANTIS_SOURCE_SHRINES_PASS',r.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_live_binding_both_game_and_reserve(self):
  self.assertIn('if world == 2:',WORLD.split('func piece_texture(',1)[1])
  self.assertIn('res://assets/a5_atlantis_ranked/atlantis_rank_%02d_p%d.png',WORLD)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('_run_headless_atlantis_ranked_art_smoke()',MAIN)
  self.assertIn('var rank_band := _atlantis_rank_band(rank)',MAIN)
  self.assertIn('var rank_band := _atlantis_rank_band(int(top.rank))',MAIN)
 def test_live_rank_bands_follow_silhouette(self):
  # Exact arithmetic mirrors Godot _atlantis_rank_band() and source bounds.
  last_y=1
  for r in range(1,10):
   center=.70-.049*(r-1)
   bounds=next(m['alpha_bounds'] for m in MANIFEST['assets'] if m['rank']==r and m['player']==1)
   self.assertLess(center,last_y);last_y=center
   self.assertGreaterEqual(center*128,bounds[1]);self.assertLessEqual(center*128,bounds[3])
 def test_unmodified_gameplay_and_seven_world_shell(self):
  with zipfile.ZipFile(BASE) as z:
   old_main=z.read('sinee-more-godot/scripts/main.gd').decode()
   old_world=z.read('sinee-more-godot/scripts/world_visuals.gd').decode()
  def body(s,frag):return s.split(frag,1)[1].split('\nfunc ',1)[0]
  for f in ['func _is_legal_move(', 'func _winning_line(', 'func _play_ai_turn(', 'func _reset_round(', 'func _refresh_surface(', 'func _modal_blocks_board_input(']:
   self.assertEqual(body(old_main,f),body(MAIN,f),f)
  for f in ['func apply_world(', 'func _canonical_cell_texture(']:
   self.assertEqual(body(old_world,f),body(WORLD,f),f)
  for w in ['a5_gods_ranked','a5_pirate_ranked','a5_northern_ranked']:
   self.assertIn(w,WORLD)
  self.assertEqual(len(list((ROOT/'assets/a5_scenery_perimeter').glob('world_*.png'))),7)
 def test_exact_change_scope(self):
  with zipfile.ZipFile(BASE) as z:
   old={n.removeprefix('sinee-more-godot/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('sinee-more-godot/') and not n.endswith('/')}
  new={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
  self.assertEqual({k for k in old if old[k]!=new.get(k)},{'scripts/main.gd','scripts/world_visuals.gd'})
  self.assertTrue(all(k.startswith('assets/a5_atlantis_ranked/') or k in ('tools/build_atlantis_ranked_assets.py','tests/test_a5_v36_atlantis_live_art.py') for k in new.keys()-old.keys()))
 def test_acceptance_stays_open(self):
  self.assertIn('next_round_button.visible = game_over',MAIN)
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('PerspectiveGeometry.cell_at(',MAIN)
if __name__=='__main__':unittest.main(verbosity=2)
