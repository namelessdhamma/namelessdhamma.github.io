"""A5 v108: reconstruct live Atlantis cells without screenshot pyramids.

The only fully unobstructed approved-source cell is bottom-left (6).
The top-middle (1) and middle-right (5) have characteristic empty ring
art, but perspective crop overlaps pieces in the NEXT row. To preserve
those canonical motifs, retain their piece-free TOP EDGE and
feather all lower regions into empty cell 6. All source pixels come
from the SHA-locked user-approved Atlantis PNG; no rendered screenshot,
pyramid, rank, or board occupancy is embedded in live cell textures.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_atlantis_ranked/03_atlantis_canon_source.png'
DEST = ROOT / 'assets/a5_reference_cells/atlantis'
EXPECTED_SHA = '2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'
SIZE = 192
CORNERS = np.float32([[398,278],[1288,275],[1400,739],[283,744]])
# Top-center and mid-right have only their upper portion usable.
# The center ring and lower image region always come from empty source cell 6.
SAFE_UPPER_END = {1: 22, 5: 22}
FEATHER_END = 48
# Exact unoccupied positions are assigned their own donor identity.
# Vary inset slightly rather than rotating directional lighting or carvings.
DESIGN = [
    (6,.85), (1,.70), (6,.92),
    (5,.81), (6,.89), (5,.87),
    (6,.97), (1,.78), (6,.94),
]

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def quad(index:int)->np.ndarray:
    col,row=index%3,index//3
    a,b,c,d=CORNERS
    def p(u:float,v:float)->np.ndarray:
        return (1-v)*((1-u)*a+u*b)+v*((1-u)*d+u*c)
    return np.float32([p(col/3,row/3),p((col+1)/3,row/3),
                       p((col+1)/3,(row+1)/3),p(col/3,(row+1)/3)])

def extract(pixels:np.ndarray, donor:int, inset:float)->np.ndarray:
    assert donor in {1,5,6}
    q=quad(donor)
    q=q.mean(axis=0)+(q-q.mean(axis=0))*inset
    target=np.float32([[0,0],[191,0],[191,191],[0,191]])
    m=cv2.getPerspectiveTransform(q,target)
    return cv2.warpPerspective(pixels,m,(SIZE,SIZE),flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)

def empty_tile(pixels:np.ndarray,donor:int,inset:float)->np.ndarray:
    base=extract(pixels,6,inset)
    if donor==6:
        return base
    upper=extract(pixels,donor,inset)
    end=SAFE_UPPER_END[donor]
    # Exactly zero upper-donor contribution below FEATHER_END.
    # No pyramid silhouette from the occupied neighboring row survives.
    alpha=np.clip((FEATHER_END-np.arange(SIZE,dtype=np.float32))/(FEATHER_END-end),0,1)
    alpha=alpha[:,None,None]
    return np.clip(np.rint(upper*alpha+base*(1-alpha)),0,255).astype(np.uint8)

def build()->list[dict]:
    assert sha(SOURCE)==EXPECTED_SHA,'Accepted Atlantis PNG changed'
    with Image.open(SOURCE) as image:
        assert image.size==(1672,941)
        pixels=np.asarray(image.convert('RGB'))
    DEST.mkdir(parents=True,exist_ok=True)
    contact=Image.new('RGB',(SIZE*3,SIZE*3))
    records=[]
    for index,(donor,inset) in enumerate(DESIGN):
        if index in (1,5,6):
            assert donor==index,'Unoccupied source motif misplaced'
        art=empty_tile(pixels,donor,inset)
        path=DEST/f'cell_{index:02d}.png'
        Image.fromarray(art,'RGB').save(path,optimize=False)
        contact.paste(Image.fromarray(art,'RGB'),((index%3)*SIZE,(index//3)*SIZE))
        records.append({'cell':index,'file':path.name,'sha256':sha(path),
                        'donor_empty_cell':donor,'inset':inset,
                        'source_upper_only':donor in (1,5),
                        'safe_upper_end':SAFE_UPPER_END.get(donor),
                        'lower_blend_end':FEATHER_END if donor in (1,5) else None,
                        'turns_ccw':0,'reference_cell_is_empty':index in (1,5,6),
                        'occupied_reference_cell_baked':False})
    assert len({r['sha256'] for r in records})==9
    contact.save(DEST/'atlantis_empty_cells_preview.jpg',quality=94)
    manifest={'version':'A5-v108','world':'atlantis',
              'source_file':SOURCE.name,'source_sha256':EXPECTED_SHA,
              'source_size':[1672,941],
              'source_board_corners':CORNERS.astype(int).tolist(),
              'donor_cells':[1,5,6],
              'upper_donor_safety':{'1':SAFE_UPPER_END[1],'5':SAFE_UPPER_END[5]},
              'lower_donor_empty_cell':6,
              'output_size':[SIZE,SIZE],
              'use':'Nine LIVE Godot cells; pyramids/ranks/occupancy dynamic',
              'cells':records}
    (DEST/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    assert sha(SOURCE)==EXPECTED_SHA
    return records

if __name__=='__main__':
    print('A5_V108_ATLANTIS_CANONICAL_LIVE_CELLS',len(build()))
