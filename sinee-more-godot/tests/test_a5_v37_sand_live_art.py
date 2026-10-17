"""A5 v37 offline/source tests only; no Godot/runtime or real-touch claims."""
import hashlib, json, subprocess, sys, unittest, zipfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_sand_ranked'
WORLD=(ROOT/'scripts/world_visuals.gd').read_text(encoding='utf8')
MAIN=(ROOT/'scripts/main.gd').read_text(encoding='utf8')
MANIFEST=json.loads((ART/'asset_manifest.json').read_text(encoding='utf8'))
BASE=Path('/mnt/data/A5_v36_Atlantis_Canonical_Shrines_Integrated_Staging.zip')
SHA='01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'

class SandArt(unittest.TestCase):
 def test_canon_unmodified(self):
  self.assertEqual(hashlib.sha256((ART/'05_sand_sea_canon_source.png').read_bytes()).hexdigest(),SHA)
  self.assertEqual(MANIFEST['source_sha256'],SHA)
  self.assertEqual(Image.open(ART/'05_sand_sea_canon_source.png').size,(1672,941))
 def test_exact_18_material_rank_pairs(self):
  self.assertEqual(len(MANIFEST['assets']),18)
  self.assertEqual({(m['rank'],m['player']) for m in MANIFEST['assets']}, {(r,p) for r in range(1,10) for p in (1,2)})
 def test_asset_sha_alpha_integrity(self):
  for m in MANIFEST['assets']:
   path=ART/m['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),m['sha256'])
   rgba=np.asarray(Image.open(path).convert('RGBA'))
   self.assertEqual(rgba.shape,(128,128,4))
   self.assertEqual(int(rgba[0,0,3]),0)
   yy,xx=np.where(rgba[:,:,3]>100)
   self.assertGreater(len(xx),90)
   self.assertEqual([int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],m['alpha_bounds'])
 def test_rank_silhouettes_strictly_increase(self):
  for p in (1,2):
   widths=[m['visible_width'] for m in MANIFEST['assets'] if m['player']==p]
   self.assertTrue(all(a<b for a,b in zip(widths,widths[1:])),widths)
 def test_distinct_source_materials(self):
  a=np.asarray(Image.open(ART/'sand_rank_09_p1.png').convert('RGBA'))
  b=np.asarray(Image.open(ART/'sand_rank_09_p2.png').convert('RGBA'))
  both=(a[:,:,3]>100)&(b[:,:,3]>100)
  self.assertGreater(np.linalg.norm(a[:,:,:3][both].mean(0)-b[:,:,:3][both].mean(0)),30)
 def test_deterministic_build(self):
  before={m['file']:m['sha256'] for m in MANIFEST['assets']}
  p=subprocess.run([sys.executable,str(ROOT/'tools/build_sand_ranked_assets.py')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  self.assertIn('A5_SAND_CANONICAL_PYRAMIDS_PASS',p.stdout)
  for name,sha in before.items():self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),sha)
 def test_live_world_4_binding(self):
  self.assertIn('if world == 4:',WORLD.split('func piece_texture(',1)[1])
  self.assertIn('res://assets/a5_sand_ranked/sand_rank_%02d_p%d.png',WORLD)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('func _run_headless_sand_ranked_art_smoke()',MAIN)
  self.assertIn('_run_headless_sand_ranked_art_smoke()',MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1])
 def test_live_rank_labels_both_board_and_reserve(self):
  self.assertIn('var sand_band := _sand_rank_band(rank)',MAIN)
  self.assertIn('var sand_band := _sand_rank_band(int(top.rank))',MAIN)
  self.assertIn('number.anchor_top = sand_band.x',MAIN)
  self.assertIn('rank.position = rect.position + Vector2(0.0, rect.size.y * sand_band.x)',MAIN)
  self.assertIn('rank_label.text == str(rank)',MAIN)
 def test_rank_band_within_silhouette(self):
  prev=2.0
  for rank in range(1,10):
   center=.68-.047*(rank-1)
   bounds=next(m['alpha_bounds'] for m in MANIFEST['assets'] if m['rank']==rank and m['player']==1)
   self.assertLess(center,prev);prev=center
   self.assertGreaterEqual(center*128,bounds[1]);self.assertLessEqual(center*128,bounds[3])
 def test_prior_four_world_assets_unchanged(self):
  with zipfile.ZipFile(BASE) as z:
   old={n.removeprefix('sinee-more-godot/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('sinee-more-godot/assets/') and not n.endswith('/')}
  for path,sha in old.items():
   self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha,path)
 def test_gameplay_and_world_shell_preserved(self):
  with zipfile.ZipFile(BASE) as z:
   prev_main=z.read('sinee-more-godot/scripts/main.gd').decode()
   prev_world=z.read('sinee-more-godot/scripts/world_visuals.gd').decode()
  def body(s,frag):return s.split(frag,1)[1].split('\nfunc ',1)[0]
  for f in ('func _is_legal_move(', 'func _winning_line(', 'func _play_ai_turn(', 'func _reset_round(', 'func _refresh_surface(', 'func _modal_blocks_board_input('):
   self.assertEqual(body(prev_main,f),body(MAIN,f),f)
  for f in ('func apply_world(', 'func _canonical_cell_texture('):
   self.assertEqual(body(prev_world,f),body(WORLD,f),f)
  self.assertEqual(len(list((ROOT/'assets/a5_scenery_perimeter').glob('world_*.png'))),7)
 def test_exact_source_delta_scope(self):
  with zipfile.ZipFile(BASE) as z:
   old={n.removeprefix('sinee-more-godot/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('sinee-more-godot/') and not n.endswith('/')}
  new={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
  self.assertEqual({k for k in old if old[k]!=new.get(k)},{'scripts/main.gd','scripts/world_visuals.gd'})
  self.assertTrue(all(k.startswith('assets/a5_sand_ranked/') or k in ('tools/build_sand_ranked_assets.py','tests/test_a5_v37_sand_live_art.py') for k in new.keys()-old.keys()))
 def test_gate_still_open(self):
  self.assertIn('next_round_button.visible = game_over',MAIN)
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('PerspectiveGeometry.cell_at(',MAIN)

if __name__=='__main__':unittest.main(verbosity=2)
