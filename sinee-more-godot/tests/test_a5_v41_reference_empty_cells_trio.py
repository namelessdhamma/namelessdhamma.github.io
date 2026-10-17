"""A5 v41 offline gates for canonical EMPTY board tiles in 3 more worlds.
These tests do NOT certify a Godot compile, gameplay, or visual parity.
"""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
CANON=json.loads((Path('/mnt/data/MANIFEST.json') if Path('/mnt/data/MANIFEST.json').exists() else ROOT/'tools/approved_seven_world_manifest.json').read_text())
CANON_SHA={item['world']:item['sha256'] for item in CANON['images']}
WORLDS={
 'pirate':('pirate_sea','a5_pirate_ranked/02_pirate_sea_canon_source.png'),
 'atlantis':('atlantis','a5_atlantis_ranked/03_atlantis_canon_source.png'),
 'gods':('gods_of_the_deep','a5_gods_ranked/04_gods_of_the_deep_canon_source.png'),
}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class TestCanonicalEmptyCellTrio(unittest.TestCase):
 def test_source_integrity(self):
  for folder,(world,source) in WORLDS.items():
   with self.subTest(world=world):self.assertEqual(sha(ASSETS/source),CANON_SHA[world])
 def test_manifest_matches_source_and_assets(self):
  for folder,(world,source) in WORLDS.items():
   with self.subTest(world=world):
    path=ASSETS/'a5_reference_cells'/folder
    m=json.loads((path/'asset_manifest.json').read_text())
    self.assertEqual(m['world'],world)
    self.assertEqual(m['source_sha256'],CANON_SHA[world])
    self.assertEqual(m['output_size'],[192,192])
    self.assertEqual(len(m['cells']),9)
    self.assertEqual([x['cell'] for x in m['cells']],list(range(9)))
    for rec in m['cells']:
     file=path/rec['file'];self.assertTrue(file.is_file())
     self.assertEqual(sha(file),rec['sha256'])
     with Image.open(file) as im:
      self.assertEqual(im.size,(192,192));self.assertEqual(im.mode,'RGB')
 def test_no_occupied_donors(self):
  # Reviewed against the approved source (2026-10-11):
  # Pirate chart donors are empty; Atlantis 6 is fully empty while
  # 1 and 5 supply only their demonstrably piece-free TOP EDGES;
  # Gods 1/5/6 supply spiral/trident/eye motifs.
  accepted={'pirate':{0,4},'atlantis':{1,5,6},'gods':{1,5,6}}
  for folder in WORLDS:
   m=json.loads((ASSETS/'a5_reference_cells'/folder/'asset_manifest.json').read_text())
   self.assertEqual(set(m['donor_cells']),accepted[folder])
   self.assertTrue(all(x['donor_empty_cell'] in accepted[folder] for x in m['cells']))
 def test_distinct_source_art(self):
  for folder in WORLDS:
   p=ASSETS/'a5_reference_cells'/folder
   images=[np.asarray(Image.open(p/f'cell_{i:02d}.png')) for i in range(9)]
   self.assertGreater(len({sha(p/f'cell_{i:02d}.png') for i in range(9)}),3)
   self.assertGreater(float(np.mean(np.std(images[0].astype(float),axis=(0,1)))),12)
 def test_reference_assets_have_no_alpha_overlay(self):
  for folder in WORLDS:
   p=ASSETS/'a5_reference_cells'/folder
   for i in range(9):
    with Image.open(p/f'cell_{i:02d}.png') as im:
     self.assertEqual(im.mode,'RGB')
 def test_six_worlds_share_one_live_cell_loader(self):
  text=(ROOT/'scripts/world_visuals.gd').read_text()
  self.assertIn('if world >= 1 and world <= 6:',text)
  self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)',text)
  self.assertIn('"pirate", "atlantis", "gods", "sand", "night", "north"',text)
  self.assertNotIn('chart.texture = pirate_cell_cache[cell_index]',text)
  self.assertNotIn('chart.texture = atlantis_cell_cache[cell_index]',text)
  self.assertNotIn('chart.texture = gods_cell_cache[cell_index]',text)
 def test_perspective_uses_live_tiles(self):
  text=(ROOT/'scripts/main.gd').read_text()
  self.assertIn('tile.texture = art.texture',text)
  self.assertIn('PerspectiveGeometry.cell_at(current_world, position, perspective_rect)',text)
  self.assertIn('_on_cell_pressed(index)',text)
  self.assertIn('world_visuals.piece_texture(current_world, int(top.player), int(top.rank))',text)
 def test_engine_smoke_wired(self):
  text=(ROOT/'scripts/main.gd').read_text()
  self.assertIn('_run_headless_six_supported_world_cells_smoke()',text)
  self.assertIn('BLUE_SEA_SIX_SUPPORTED_CANONICAL_EMPTY_CELLS_PASS',text)
  self.assertIn('assert(board_stacks == saved_stacks and reserve_available == saved_reserves',text)
 def test_no_flattened_reference_background(self):
  text=(ROOT/'scripts/world_visuals.gd').read_text()
  self.assertIn('SceneryPerimeter',text)
  self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)',text)
  self.assertNotIn('canon_source.png") as Texture2D',text)
 def test_regenerate_deterministically(self):
  paths=[ASSETS/'a5_reference_cells'/folder/f'cell_{i:02d}.png' for folder in WORLDS for i in range(9)]
  before=[sha(p) for p in paths]
  cmd=[sys.executable,str(ROOT/'tools/build_reference_empty_cells_trio.py')]
  subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertEqual(before,[sha(p) for p in paths])

if __name__=='__main__':unittest.main(verbosity=2)
