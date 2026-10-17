"""A5 v109: nine upright, unoccupied, reference-derived live Night Sea board cells.

The accepted reference is an immutable INPUT. Occupied cells are never donors;
stateful pieces, ranks and touch targets remain Godot nodes.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_night_ranked/06_night_sea_canon_source.png'
DEST = ROOT / 'assets/a5_reference_cells/night'
SOURCE_SHA = 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'
SIZE = 192
# Two genuinely unoccupied compass cells in the user-approved screenshot.
# Quadrilaterals are (TL, TR, BR, BL), pixel coordinates of the 1672x941 art.
DONORS = {
    1: [[710,282],[969,282],[967,365],[704,365]],  # upper center
    6: [[365,563],[644,563],[645,702],[318,703]],   # lower left
}
# Retain all compasses upright. Two donor regions and varied safe zoom levels
# yield nine genuinely distinct backgrounds, without duplicating figures.
ASSIGN = [(1,0.87),(1,0.93),(1,0.99),
          (6,0.88),(1,0.96),(6,0.95),
          (6,0.91),(6,0.98),(1,0.90)]

def extract(source: np.ndarray, donor: int, inset: float) -> np.ndarray:
    quad = np.float32(DONORS[donor]); center = quad.mean(axis=0)
    quad = center + (quad-center)*inset
    dst = np.float32([[0,0],[SIZE-1,0],[SIZE-1,SIZE-1],[0,SIZE-1]])
    transform = cv2.getPerspectiveTransform(quad,dst)
    return cv2.warpPerspective(source,transform,(SIZE,SIZE),flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)

def build() -> list[dict]:
    digest=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert digest == SOURCE_SHA, 'Accepted Night Sea reference changed'
    with Image.open(SOURCE) as img:
        assert img.size == (1672,941)
        source=np.asarray(img.convert('RGB'))
    DEST.mkdir(parents=True,exist_ok=True)
    preview=Image.new('RGB',(SIZE*3,SIZE*3))
    records=[]
    for i,(donor,inset) in enumerate(ASSIGN):
        tile=Image.fromarray(extract(source,donor,inset),'RGB')
        name=f'cell_{i:02d}.png'
        path=DEST/name
        tile.save(path,optimize=False)
        preview.paste(tile,((i%3)*SIZE,(i//3)*SIZE))
        records.append({'cell':i,'file':name,'donor_empty_cell':donor,
                        'inset':inset,'turns_ccw':0,
                        'occupied_reference_cell_baked':False,
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    preview.save(DEST/'night_empty_cells_preview.jpg',quality=94)
    manifest={'version':'A5-v109','world':'night_sea','source_file':SOURCE.name,
              'source_sha256':digest,'source_size':[1672,941],
              'donor_cells':[1,6],'donor_quads':DONORS,
              'output_size':[SIZE,SIZE],
              'use':'Nine LIVE Godot board backgrounds; dynamic occupancy, ranks, reserve and input',
              'cells':records}
    (DEST/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SOURCE_SHA
    return records

if __name__=='__main__':
    print('A5_V109_NIGHT_EMPTY_CELLS_PASS',len(build()))
