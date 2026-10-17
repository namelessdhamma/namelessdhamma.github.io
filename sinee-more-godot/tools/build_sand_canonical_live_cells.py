"""A5 v107: reconstruct Sand Sea's nine interactive, EMPTY stone cells.

The accepted Sand screenshot has exactly three unoccupied cells: sun at 2,
ankh at 4, Eye of Horus at 6. All art is sampled exclusively from those
empty cells; no pyramids, ranks, or screenshot occupancy are copied.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_sand_ranked/05_sand_sea_canon_source.png'
DEST = ROOT / 'assets/a5_reference_cells/sand'
EXPECTED_SHA = '01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'
SIZE = 192
# Bilinear perspective footprint of the real sandstone game surface, in
# 1672x941 source pixels, not a flattened live board screenshot overlay.
CORNERS = np.float32([[407, 228], [1281, 226], [1470, 751], [246, 751]])
EMPTY = {2: 'sun', 4: 'ankh', 6: 'eye_of_horus'}
# Preserve canonical motifs at their EXACT cells. Occupied cells borrow
# source-derived stone only from genuinely empty cells; unique insets avoid
# identical tiling while keeping hieroglyphs upright (no 90-degree rotations).
DESIGN = [
    (6, .76), (4, .78), (2, .82),
    (2, .76), (4, .82), (6, .79),
    (6, .82), (2, .78), (4, .76),
]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def quad(index: int) -> np.ndarray:
    col, row = index % 3, index // 3
    a, b, c, d = CORNERS
    def p(u: float, v: float) -> np.ndarray:
        return (1-v)*((1-u)*a+u*b)+v*((1-u)*d+u*c)
    return np.float32([p(col/3,row/3),p((col+1)/3,row/3),
                       p((col+1)/3,(row+1)/3),p(col/3,(row+1)/3)])

def extract(source: np.ndarray, donor: int, inset: float) -> np.ndarray:
    assert donor in EMPTY
    q = quad(donor)
    q = q.mean(axis=0) + (q-q.mean(axis=0))*inset
    target = np.float32([[0,0],[SIZE-1,0],[SIZE-1,SIZE-1],[0,SIZE-1]])
    matrix = cv2.getPerspectiveTransform(q,target)
    return cv2.warpPerspective(source,matrix,(SIZE,SIZE),
                               flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)

def build() -> list[dict]:
    assert sha(SOURCE) == EXPECTED_SHA, 'Accepted Sand PNG changed'
    with Image.open(SOURCE) as original:
        assert original.size == (1672,941)
        source = np.asarray(original.convert('RGB'))
    DEST.mkdir(parents=True,exist_ok=True)
    contact = Image.new('RGB',(SIZE*3,SIZE*3))
    records=[]
    for index,(donor,inset) in enumerate(DESIGN):
        assert index not in EMPTY or donor == index, 'Canonical symbol misplaced'
        pixels = extract(source,donor,inset)
        path = DEST/f'cell_{index:02d}.png'
        image = Image.fromarray(pixels,'RGB')
        image.save(path,optimize=False)
        contact.paste(image,((index%3)*SIZE,(index//3)*SIZE))
        records.append({'cell':index,'file':path.name,'sha256':sha(path),
                        'donor_empty_cell':donor,'donor_symbol':EMPTY[donor],
                        'inset':inset,'turns_ccw':0,
                        'reference_cell_is_empty':index in EMPTY,
                        'occupied_reference_cell_baked':False})
    assert len({r['sha256'] for r in records}) == 9
    contact.save(DEST/'sand_empty_cells_preview.jpg',quality=94)
    manifest={'version':'A5-v107','world':'sand_sea',
              'source_file':SOURCE.name,'source_sha256':EXPECTED_SHA,
              'source_size':[1672,941],
              'source_board_corners':CORNERS.astype(int).tolist(),
              'donor_cells':[2,4,6],
              'canonical_empty_motifs':{'2':'sun','4':'ankh','6':'eye_of_horus'},
              'output_size':[SIZE,SIZE],
              'use':'Nine live Godot stone cells; ranks/pyramids/occupancy dynamic',
              'cells':records}
    (DEST/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    assert sha(SOURCE) == EXPECTED_SHA
    return records

if __name__=='__main__':
    print('A5_V107_SAND_CANONICAL_CELLS',len(build()))
