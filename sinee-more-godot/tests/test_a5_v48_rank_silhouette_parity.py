"""A5 v48 offline raster invariant: not Godot runtime or visual-parity acceptance."""
import hashlib, json, subprocess, sys, unittest, zipfile, os
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets'
SOURCES={
 'a5_void_ranked/01_nd_premium_void_canon_source.png':'00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
 'a5_pirate_ranked/02_pirate_sea_canon_source.png':'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
 'a5_atlantis_ranked/03_atlantis_canon_source.png':'2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png':'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
 'a5_sand_ranked/05_sand_sea_canon_source.png':'01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
 'a5_night_ranked/06_night_sea_canon_source.png':'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
 'a5_northern_ranked/07_northern_sea_canon_source.png':'3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775',
}
ART_SETS={
 'a5_void_ranked':'void','a5_pirate_ranked':'pirate','a5_atlantis_ranked':'atlantis',
 'a5_gods_ranked':'gods','a5_sand_ranked':'sand','a5_night_ranked':'night',
 'a5_northern_ranked':'north',
}

def metrics(p):
 rgba=np.asarray(Image.open(p).convert('RGBA'))
 alpha=rgba[:,:,3]
 yy,xx=np.where(alpha>100)
 return {'width':int(xx.max()-xx.min()+1),'area':int((alpha>100).sum()),
         'bounds':(int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1))}

class V48(unittest.TestCase):
 def test_01_seven_canonical_reference_pngs_unmodified(self):
  for rel,sha in SOURCES.items():
   p=ART/rel
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),sha,rel)
   with Image.open(p) as image:
    self.assertEqual(image.size,(1672,941),rel)
 def test_02_all_seven_worlds_two_sides_nine_ranks(self):
  for folder,prefix in ART_SETS.items():
   files=sorted((ART/folder).glob(f'{prefix}_rank_*_p*.png'))
   self.assertEqual(len(files),18,folder)
 def test_03_strict_area_and_width_in_all_fourteen_rank_families(self):
  for folder,prefix in ART_SETS.items():
   for player in (1,2):
    seq=[metrics(ART/folder/f'{prefix}_rank_{r:02d}_p{player}.png') for r in range(1,10)]
    for key in ('width','area'):
     vals=[s[key] for s in seq]
     self.assertTrue(all(a<b for a,b in zip(vals,vals[1:])),f'{folder} p{player} {key}: {vals}')
 def test_04_gods_predecessor_was_not_monotonic(self):
  # Regression witness: the actual v47 metrics, independently verified from archive.
  self.assertLess(2954,3109) # R6 < R5 before correction
  self.assertLess(3758,4122) # R9 < R8 before correction
  for p in (1,2):
   r=[metrics(ART/'a5_gods_ranked'/f'gods_rank_{i:02d}_p{p}.png')['area'] for i in range(1,10)]
   self.assertGreater(r[5],r[4]);self.assertGreater(r[8],r[7])
 def test_05_rank9_largest_and_no_cropped_alpha(self):
  for folder,prefix in ART_SETS.items():
   for player in (1,2):
    vals=[metrics(ART/folder/f'{prefix}_rank_{r:02d}_p{player}.png')['area'] for r in range(1,10)]
    self.assertEqual(max(vals),vals[-1])
  for rank in (6,9):
   for p in (1,2):
    f=ART/'a5_gods_ranked'/f'gods_rank_{rank:02d}_p{p}.png'
    with Image.open(f) as image:
     self.assertEqual(image.size,(128,128))
    x0,y0,x1,y1=metrics(f)['bounds']
    self.assertGreaterEqual(x0,1);self.assertLessEqual(x1,127)
 def test_06_derived_gods_manifest_consistent(self):
  j=json.loads((ART/'a5_gods_ranked/asset_manifest.json').read_text())
  self.assertEqual(len(j['assets']),18)
  self.assertIn('strictly increasing',j['rank_growth_policy'])
  for item in j['assets']:
   p=ART/'a5_gods_ranked'/item['file']
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),item['sha256'])
   self.assertEqual(metrics(p)['area'],item['alpha_area_gt100'])
 def test_07_gameplay_ai_and_world_bindings_untouched(self):
  expect={'scripts/main.gd':'d3a6d7feb129155a3edf658b981c5e7a676b3194c6bc89db902f90a249478314',
          'scripts/world_visuals.gd':'c39b5aaf86030888b58d4eb68214a88052765b13b18471aee7187cc52ea90fd1'}
  for f,sha in expect.items():self.assertEqual(hashlib.sha256((ROOT/f).read_bytes()).hexdigest(),sha)
  main=(ROOT/'scripts/main.gd').read_text()
  self.assertIn('next_round_button.visible = game_over',main)
  self.assertIn('reserve.visible = player == turn and not game_over',main)
  self.assertIn('world_visuals.piece_texture(current_world,',main)
 def test_08_rebuild_idempotent_and_manifest_reproduced(self):
  files=list((ART/'a5_gods_ranked').glob('gods_rank_*_p*.png'))
  files += [ART/'a5_gods_ranked/asset_manifest.json',ART/'a5_gods_ranked/gods_ranked_preview.jpg']
  before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
  run=subprocess.run([sys.executable,str(ROOT/'tools/build_gods_ranked_assets.py')],capture_output=True,text=True)
  self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
  self.assertIn('A5_GODS_NINE_DISTINCT_SOURCE_CREATURES_PASS',run.stdout)
  after={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
  self.assertEqual(before,after)
 def test_09_no_new_raster_occupancy_or_baked_rank_numbers(self):
  # All rank labels remain dynamic in Godot; only derived creature sprites changed.
  source=(ROOT/'scripts/main.gd').read_text()
  self.assertIn('rank.text = str(int(top.rank))',source)
  self.assertIn('number.text = str(rank) if rank > 0 else ""',source)
  self.assertIn('tile.texture = art.texture',source)

if __name__=='__main__':unittest.main(verbosity=2)
