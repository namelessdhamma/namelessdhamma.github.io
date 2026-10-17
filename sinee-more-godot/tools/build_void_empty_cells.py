"""A5 v111: source-locked, empty ND Premium Void board atlas.

Only the two visibly UNoccupied cells of the user-approved Void PNG supply
board art. Never extract a figure, numeric rank, UI, or frozen occupancy.
This build-time tool does not replace the shared live Godot board.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_void_ranked/01_nd_premium_void_canon_source.png'
OUTPUT = ROOT / 'assets/a5_reference_cells/void'
SOURCE_SHA256 = '00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'
GRID = np.array([(368,264),(1300,262),(1474,738),(195,741)], dtype=np.float64)
SIZE = 192

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bilinear(q: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return ((1-u)*(1-v))[...,None]*q[0] + (u*(1-v))[...,None]*q[1] + (u*v)[...,None]*q[2] + ((1-u)*v)[...,None]*q[3]

def donor_quad(row: int, col: int) -> np.ndarray:
    uv = [(col/3,row/3),((col+1)/3,row/3),((col+1)/3,(row+1)/3),(col/3,(row+1)/3)]
    return np.stack([bilinear(GRID, np.array(u), np.array(v)) for u,v in uv])

def sample(src: np.ndarray, xy: np.ndarray) -> np.ndarray:
    x = np.clip(xy[...,0],0,src.shape[1]-2)
    y = np.clip(xy[...,1],0,src.shape[0]-2)
    x0 = np.floor(x).astype(np.int32); y0 = np.floor(y).astype(np.int32)
    fx = (x-x0)[...,None]; fy = (y-y0)[...,None]
    return ((1-fx)*(1-fy)*src[y0,x0] + fx*(1-fy)*src[y0,x0+1]
            + (1-fx)*fy*src[y0+1,x0] + fx*fy*src[y0+1,x0+1])

def build_tile(src: np.ndarray, index: int) -> np.ndarray:
    # A perspective-correct warp of the *empty* top-middle cell. Deliberate
    # small subpixel offsets distinguish tiles without rotating its rings.
    inset = 0.055 + 0.004*(index % 3) + 0.003*(index // 3)
    ys,xs = np.mgrid[0:SIZE,0:SIZE]
    u = inset+(1-2*inset)*(xs+0.5)/SIZE
    v = inset+(1-2*inset)*(ys+0.5)/SIZE
    q = donor_quad(0,1)
    img = sample(src,bilinear(q,u,v))
    # The reference has a warm left / cool right lighting split. Keep its
    # original chromatic material, with a restrained world-position tint.
    col = index % 3; row = index // 3
    tone = [(1.065,1.025,0.955),(1.0,1.0,1.0),(0.945,1.015,1.075)][col]
    img *= np.array(tone)[None,None,:]*(1.0+0.008*(row-1))
    if index == 4:
        # A source-only compass from the OTHER empty reference cell.
        # Crop excludes the bottom-row rank-5 dome beginning at y>522.
        compass = src[388:511,710:938]
        ch,cw = compass.shape[:2]
        # No rank, glass dome, board occupancy or HUD enters this crop.
        cx = (xs+0.5-SIZE/2)/SIZE
        cy = (ys+0.5-SIZE/2)/SIZE
        radius = np.sqrt((cx/0.38)**2+(cy/0.38)**2)
        alpha = np.clip((1.0-radius)/0.18,0,1)[...,None]*0.93
        uvx = np.clip((cx/0.38+1)/2,0,1)*(cw-1)
        uvy = np.clip((cy/0.38+1)/2,0,1)*(ch-1)
        yyxx = np.stack([uvx,uvy],axis=-1)
        img = img*(1-alpha)+sample(compass,yyxx)*alpha
    return np.clip(np.rint(img),0,255).astype(np.uint8)

def build() -> dict:
    assert sha256(SOURCE)==SOURCE_SHA256, 'Approved Void PNG changed: abort'
    OUTPUT.mkdir(parents=True,exist_ok=True)
    src = np.asarray(Image.open(SOURCE).convert('RGB'),dtype=np.float64)
    assert src.shape==(941,1672,3)
    records=[]
    previews=[]
    for i in range(9):
        rgb=build_tile(src,i)
        path=OUTPUT/f'cell_{i:02d}.png'
        Image.fromarray(rgb,'RGB').save(path,optimize=False)
        previews.append(Image.fromarray(rgb,'RGB'))
        records.append({'cell':i,'file':path.name,'sha256':sha256(path),
                        'empty_donors':['top_middle']+(['middle_middle_compass'] if i==4 else []),
                        'occupied_reference_cell_baked':False,'rotation_ccw_quarters':0})
    sheet=Image.new('RGB',(3*SIZE,3*SIZE))
    for i,im in enumerate(previews):sheet.paste(im,((i%3)*SIZE,(i//3)*SIZE))
    sheet.save(OUTPUT/'void_empty_cells_preview.jpg',quality=93,subsampling=0)
    manifest={'version':'A5-v111','world':'nd_premium_void','source_file':SOURCE.name,
              'source_sha256':SOURCE_SHA256,'source_size':[1672,941],
              'purpose':'source-derived empty cells, no figures, ranks, UI or occupancy; live Godot state only',
              'donors':['top_middle','middle_middle_compass'],'assets':records}
    (OUTPUT/'asset_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    assert sha256(SOURCE)==SOURCE_SHA256
    return manifest

if __name__=='__main__':
    m=build()
    print('A5_V111_VOID_EMPTY_CANONICAL_CELLS',len(m['assets']),SOURCE_SHA256)
