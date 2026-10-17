"""A5 v41/v105/v106: extract empty playable board cells from three SHA-256-locked
user-approved reference PNGs. Never copy screenshot occupancy or UI.

This tool only writes the three new assets/a5_reference_cells/{pirate,atlantis,gods}
subfolders; the seven canonical source images are read-only inputs.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import runpy
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
OUTPUT = ASSETS / 'a5_reference_cells'
SIZE = 192
# Reference board corners (TL, TR, BR, BL), 1672x941 pixels, from the
# shared perspective geometry; no old five-world placeholder art.
SOURCES = {
 'pirate': {
  'world':'pirate_sea',
  'source':'a5_pirate_ranked/02_pirate_sea_canon_source.png',
  'sha256':'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
  'corners':[[500,254],[1190,254],[1300,706],[387,706]],
  'empty_cells':[0,4],
  'assignment':[0,4,0,4,0,4,0,4,0],
  'inset_by_donor':{0:0.95,4:0.70},
 },
 'atlantis': {
  'world':'atlantis',
  'source':'a5_atlantis_ranked/03_atlantis_canon_source.png',
  'sha256':'2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
  'corners':[[398,278],[1288,275],[1400,739],[283,744]],
  'empty_cells':[6],
  'assignment':[6,6,6,6,6,6,6,6,6],
  'inset_by_donor':{6:0.95},
 },
 'gods': {
  'world':'gods_of_the_deep',
  'source':'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
  'sha256':'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
  'corners':[[385,278],[1280,279],[1410,730],[265,730]],
  'empty_cells':[5,6],
  'assignment':[5,6,5,6,5,6,5,6,5],
  'inset_by_donor':{5:0.87,6:0.94},
 },
}

def interpolate(corners: np.ndarray, u: float, v: float) -> np.ndarray:
    return (1-v)*((1-u)*corners[0]+u*corners[1])+v*((1-u)*corners[3]+u*corners[2])

def cell_quad(corners: np.ndarray, cell: int) -> np.ndarray:
    col,row = cell%3,cell//3
    u0,v0 = col/3,row/3
    u1,v1 = (col+1)/3,(row+1)/3
    return np.float32([interpolate(corners,u0,v0),interpolate(corners,u1,v0),
                       interpolate(corners,u1,v1),interpolate(corners,u0,v1)])

def build() -> dict:
    result = {}
    for name, spec in SOURCES.items():
        if name == 'atlantis':
            # v108: preserve three safe source-derived border variants;
            # never overwrite with the obsolete rotated one-donor tiles.
            helper = runpy.run_path(str(ROOT / 'tools/build_atlantis_canonical_live_cells.py'))
            result[name] = helper['build']()
            continue
        if name == 'gods':
            # v106: canonical spiral/trident/eye are three separate empty
            # reference cells. Never regress to the old 2-donor rotation.
            helper = runpy.run_path(str(ROOT / 'tools/build_gods_canonical_live_cells.py'))
            result[name] = helper['build']()
            continue
        if name == 'pirate':
            # v105: distinct source-art chart motifs and unrotated empty cells.
            # The previous v41 donor rotation produced identical mountains in
            # six cells and even inverted the center mountain. Delegate to the
            # SHA-locked builder rather than silently regenerating old art.
            helper = runpy.run_path(str(ROOT / 'tools/build_pirate_unique_chart_cells.py'))
            result[name] = helper['build']()
            continue
        source = ASSETS / spec['source']
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        assert before == spec['sha256'], f'CANONICAL SOURCE CHANGED: {name}'
        with Image.open(source) as im:
            assert im.size == (1672,941), f'Unexpected approved reference size: {name}'
            pixels = np.array(im.convert('RGB'))
        dest = OUTPUT / name
        dest.mkdir(parents=True, exist_ok=True)
        corners = np.float32(spec['corners'])
        dst = np.float32([[0,0],[SIZE-1,0],[SIZE-1,SIZE-1],[0,SIZE-1]])
        donors = {}
        for index in spec['empty_cells']:
            # Inset by 2.5% to avoid neighboring PIECE spill while retaining
            # characteristic borders and carvings from the approved surface.
            quad = cell_quad(corners,index)
            center = quad.mean(axis=0)
            quad = center + (quad-center)*spec['inset_by_donor'][index]
            matrix = cv2.getPerspectiveTransform(quad.astype(np.float32),dst)
            donors[index] = cv2.warpPerspective(pixels,matrix,(SIZE,SIZE),
                flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
        records = []
        contact = Image.new('RGB',(SIZE*3,SIZE*3))
        for i, donor in enumerate(spec['assignment']):
            assert donor in donors
            # Only right-angle rotations of EMPTY donor cells, no generated
            # screenshot figure/rank. Deterministic variation in tile texture.
            turns = (i//3 + (i%3))%4
            image = Image.fromarray(np.ascontiguousarray(np.rot90(donors[donor],turns)),'RGB')
            path = dest/f'cell_{i:02d}.png'
            image.save(path,optimize=False)
            contact.paste(image,((i%3)*SIZE,(i//3)*SIZE))
            records.append({'cell':i,'donor_empty_cell':donor,'turns_ccw':turns,
                'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        contact.save(dest/f'{name}_empty_cells_preview.jpg',quality=94)
        manifest = {
            'version':'A5-v41','world':spec['world'],
            'source_file':source.name,'source_sha256':before,
            'source_size':[1672,941],'donor_cells':spec['empty_cells'],
            'source_board_corners':spec['corners'],'output_size':[SIZE,SIZE],
            'use':'Nine LIVE 3x3 Godot cell backgrounds; occupancy/pieces/ranks/UI dynamic',
            'cells':records,
        }
        (dest/'asset_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        result[name] = records
    return result

if __name__=='__main__':
    result=build()
    print('A5_V41_REFERENCE_EMPTY_CELLS', {k:len(v) for k,v in result.items()})
