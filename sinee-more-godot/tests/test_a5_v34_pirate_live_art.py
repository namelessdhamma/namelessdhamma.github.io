"""A5 v34 offline artifact and source regression. Not a Godot runtime or real touch test."""
import hashlib,json,unittest,zipfile,os
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve()
ROOT=Path(os.environ.get('A5_PROJECT_ROOT', HERE.parents[1] if HERE.parent.name=='tests' else HERE.parent/'sinee-more-godot'))
ASSET=ROOT/'assets/a5_pirate_ranked'
SOURCE=ASSET/'02_pirate_sea_canon_source.png'
MANIFEST=json.loads((ASSET/'asset_manifest.json').read_text())
MAIN=(ROOT/'scripts/main.gd').read_text()
WORLD=(ROOT/'scripts/world_visuals.gd').read_text()
OLD=Path(os.environ.get('A5_V33_ZIP', HERE.parent/'A5_v33_Northern_Reference_Ranked_Stones_Integrated_Staging.zip'))
class A5V34PirateCanonical(unittest.TestCase):
 def test_exact_user_approved_source(self):
  self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1')
  with Image.open(SOURCE) as im:self.assertEqual(im.size,(1672,941))
 def test_all_eighteen_assets(self):
  self.assertEqual(len(MANIFEST['assets']),18)
  self.assertEqual(len(list(ASSET.glob('pirate_rank_*_p*.png'))),18)
  self.assertEqual({(m['rank'],m['player']) for m in MANIFEST['assets']},{(r,p) for r in range(1,10) for p in (1,2)})
 def test_every_png_sha_and_transparency(self):
  for m in MANIFEST['assets']:
   f=ASSET/m['file']; self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),m['sha256'])
   a=np.array(Image.open(f).convert('RGBA'))
   self.assertEqual(a.shape,(128,128,4))
   self.assertEqual(int(a[0,0,3]),0)
   self.assertGreater(int((a[:,:,3]>80).sum()),80)
 def test_visible_sizes_strictly_grow_for_both_players(self):
  for player in (1,2):
   rows=[m for m in MANIFEST['assets'] if m['player']==player]
   sizes=[m['visible_width'] for m in rows]
   self.assertTrue(all(a<b for a,b in zip(sizes,sizes[1:])),sizes)
   self.assertGreaterEqual(sizes[0],48)
   self.assertLessEqual(sizes[-1],125)
 def test_opposing_materials_visibly_different(self):
  imgs=[]
  for p in (1,2):
   im=np.array(Image.open(ASSET/f'pirate_rank_09_p{p}.png').convert('RGBA'))
   opaque=im[:,:,3]>100
   imgs.append(im[:,:,:3][opaque].mean(axis=0))
  self.assertGreater(np.linalg.norm(imgs[0]-imgs[1]),70)
 def test_shared_live_renderer_not_flattened(self):
  self.assertIn('if world == 1:',WORLD.split('func piece_texture(',1)[1])
  self.assertIn('res://assets/a5_pirate_ranked/pirate_rank_%02d_p%d.png',WORLD)
  self.assertIn('piece_cache[key] = pirate_texture',WORLD)
  self.assertIn('world_visuals.piece_texture(current_world,',MAIN)
  self.assertIn('PerspectiveGeometry.cell_at(',MAIN)
 def test_live_number_over_pirate_top_badge(self):
  self.assertIn('number.anchor_bottom = 0.48 if current_world == 1 else 1.0',MAIN)
  self.assertIn('rank.position = rect.position + Vector2(0.0, rect.size.y * 0.03)',MAIN)
  self.assertIn('rank.size = Vector2(rect.size.x, rect.size.y * 0.45)',MAIN)
  self.assertIn('number.text = str(rank) if rank > 0 else ""',MAIN)
 def test_godot_headless_asset_assertions_wired_but_not_executed(self):
  self.assertIn('_run_headless_pirate_ranked_art_smoke()',MAIN)
  self.assertIn('BLUE_SEA_PIRATE_RANKED_CANONICAL_PASS',MAIN)
  self.assertIn('image.get_used_rect()',MAIN)
 def test_gameplay_unchanged_from_v33(self):
  if not OLD.exists():self.skipTest("Optional v33 baseline archive not supplied")
  with zipfile.ZipFile(OLD) as z:
   old_main=z.read('sinee-more-godot/scripts/main.gd').decode()
   old_world=z.read('sinee-more-godot/scripts/world_visuals.gd').decode()
  for fragment in ['func _is_legal_move(', 'func _winning_line(', 'func _play_ai_turn(', 'func _on_primary(', 'func _reset_round(', 'func _refresh_surface(']:
   def body(s):return s.split(fragment,1)[1].split('\nfunc ',1)[0]
   self.assertEqual(body(old_main),body(MAIN),fragment)
  for fragment in ['func _canonical_cell_texture(', 'func apply_world(']:
   def body(s):return s.split(fragment,1)[1].split('\nfunc ',1)[0]
   self.assertEqual(body(old_world),body(WORLD),fragment)
 def test_only_intended_existing_files_changed(self):
  if not OLD.exists():self.skipTest("Optional v33 baseline archive not supplied")
  with zipfile.ZipFile(OLD) as z:
   old={x.filename.removeprefix('sinee-more-godot/'):hashlib.sha256(z.read(x)).hexdigest() for x in z.infolist() if x.filename.startswith('sinee-more-godot/') and not x.is_dir()}
  new={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file()}
  self.assertEqual([k for k in old if old[k]!=new.get(k)],['scripts/main.gd','scripts/world_visuals.gd'])
  self.assertTrue(all(k.startswith('assets/a5_pirate_ranked/') or k in ('tools/build_pirate_ranked_assets.py','tests/test_a5_v34_pirate_live_art.py') for k in new.keys()-old.keys()))
 def test_seven_worlds_and_legacy_assets_retained(self):
  self.assertEqual(len(list((ROOT/'assets/a5_scenery_perimeter').glob('world_*.png'))),7)
  self.assertEqual(len(list((ROOT/'assets/a5_reference_cells').glob('**/cell_*.png'))),18)
  self.assertEqual(len(list((ROOT/'assets/a5_northern_ranked').glob('north_rank_*_p*.png'))),18)
  self.assertIn('"История · Рифы"',MAIN)
  self.assertIn('ai_engine.choose_move(',MAIN)
 def test_no_false_gate_claim(self):
  self.assertIn('reserve.visible = player == turn and not game_over',MAIN)
  self.assertIn('next_round_button.visible = game_over',MAIN)
  self.assertIn('if _modal_blocks_board_input():',MAIN)
if __name__=='__main__':unittest.main(verbosity=2)
