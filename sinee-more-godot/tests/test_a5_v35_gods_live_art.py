"""A5 v35 source/asset tests. NOT Godot runtime, touch, or visual parity proof."""
import hashlib,json,unittest,zipfile,os,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_gods_ranked'
BASE=Path(os.environ.get('A5_V34_ZIP','/mnt/data/A5_v34_Pirate_Canonical_Ranked_Naval_Caps_Integrated_Staging.zip'))
MAIN=(ROOT/'scripts/main.gd').read_text()
WORLD=(ROOT/'scripts/world_visuals.gd').read_text()
MANIFEST=json.loads((ART/'asset_manifest.json').read_text())
class GodsArt(unittest.TestCase):
 def test_canonical_reference_exact(self):
  src=ART/'04_gods_of_the_deep_canon_source.png'
  self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d')
  with Image.open(src) as im:self.assertEqual(im.size,(1672,941))
 def test_nine_distinct_beings_two_families(self):
  self.assertEqual(len(MANIFEST['assets']),18)
  self.assertEqual({(m['rank'],m['player']) for m in MANIFEST['assets']},{(r,p) for r in range(1,10) for p in (1,2)})
  # Unlike earlier repeated procedural silhouettes, nine source regions differ.
  self.assertEqual(len(set(hashlib.sha256((ART/f'gods_rank_{r:02d}_p1.png').read_bytes()).hexdigest() for r in range(1,10))),9)
 def test_sha_transparency_and_alpha_bounds(self):
  for m in MANIFEST['assets']:
   path=ART/m['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),m['sha256'])
   a=np.array(Image.open(path).convert('RGBA'))
   self.assertEqual(a.shape,(128,128,4));self.assertEqual(int(a[0,0,3]),0)
   self.assertGreater((a[:,:,3]>65).sum(),80)
 def test_strictly_growing_both_families(self):
  for p in (1,2):
   w=[m['visible_width'] for m in MANIFEST['assets'] if m['player']==p]
   self.assertTrue(all(a<b for a,b in zip(w,w[1:])),w)
 def test_materials_differ(self):
  a=np.array(Image.open(ART/'gods_rank_09_p1.png').convert('RGBA'))
  b=np.array(Image.open(ART/'gods_rank_09_p2.png').convert('RGBA'))
  mask=(a[:,:,3]>100)&(b[:,:,3]>100)
  self.assertGreater(np.linalg.norm(a[:,:,:3][mask].mean(0)-b[:,:,:3][mask].mean(0)),35)
 def test_source_reproducibility(self):
  before={m['file']:m['sha256'] for m in MANIFEST['assets']}
  r=subprocess.run([sys.executable,str(ROOT/'tools/build_gods_ranked_assets.py')],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('A5_GODS_NINE_DISTINCT_SOURCE_CREATURES_PASS',r.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_live_godot_board_and_reserve_binding(self):
  self.assertIn('if world == 3:',WORLD.split('func piece_texture(',1)[1])
  self.assertIn('res://assets/a5_gods_ranked/gods_rank_%02d_p%d.png',WORLD)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('number.anchor_top = 0.59 if current_world == 3 else 0.0',MAIN)
  self.assertIn('rank.position = rect.position + Vector2(0.0, rect.size.y * 0.59)',MAIN)
  self.assertIn('_run_headless_gods_ranked_art_smoke()',MAIN)
 def test_preserved_gameplay_and_pirate(self):
  with zipfile.ZipFile(BASE) as z:
   old_main=z.read('sinee-more-godot/scripts/main.gd').decode()
   old_world=z.read('sinee-more-godot/scripts/world_visuals.gd').decode()
  for fragment in ['func _is_legal_move(', 'func _winning_line(', 'func _play_ai_turn(', 'func _on_primary(', 'func _reset_round(', 'func _refresh_surface(', 'func _modal_blocks_board_input(']:
   def body(s):return s.split(fragment,1)[1].split('\nfunc ',1)[0]
   self.assertEqual(body(old_main),body(MAIN),fragment)
  for fragment in ['func _canonical_cell_texture(', 'func apply_world(']:
   def body(s):return s.split(fragment,1)[1].split('\nfunc ',1)[0]
   self.assertEqual(body(old_world),body(WORLD),fragment)
  self.assertIn('res://assets/a5_pirate_ranked/',WORLD)
  self.assertIn('res://assets/a5_northern_ranked/',WORLD)
 def test_only_intended_files_changed(self):
  with zipfile.ZipFile(BASE) as z:
   old={n.removeprefix('sinee-more-godot/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('sinee-more-godot/') and not n.endswith('/')}
  new={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
  self.assertEqual(set(k for k in old if old[k]!=new.get(k)),{'scripts/main.gd','scripts/world_visuals.gd'})
  self.assertTrue(all(k.startswith('assets/a5_gods_ranked/') or k in ('tools/build_gods_ranked_assets.py','tests/test_a5_v35_gods_live_art.py') for k in new.keys()-old.keys()))
 def test_seven_world_resources_preserved(self):
  self.assertEqual(len(list((ROOT/'assets/a5_scenery_perimeter').glob('world_*.png'))),7)
  self.assertEqual(len(list((ROOT/'assets/a5_reference_cells').glob('**/cell_*.png'))),18)
  self.assertEqual(len(list((ROOT/'assets/a5_northern_ranked').glob('north_rank_*_p*.png'))),18)
  self.assertEqual(len(list((ROOT/'assets/a5_pirate_ranked').glob('pirate_rank_*_p*.png'))),18)
 def test_no_false_acceptance(self):
  self.assertIn('next_round_button.visible = game_over',MAIN)
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('PerspectiveGeometry.cell_at(',MAIN)
if __name__=='__main__':unittest.main(verbosity=2)
