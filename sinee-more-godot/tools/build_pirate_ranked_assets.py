"""Reproducibly derive LIVE naval-cap sprites from the exact user-approved Pirate Sea PNG.

The original PNG remains unmodified. Two visible canonical materials are isolated:
a dark anchor cap on the board and a brass cap in the active reserve. Their
baked numbers are replaced with a clean badge; Godot supplies the real rank.
No board, menu or game state is flattened into the runtime sprite assets.
"""
from pathlib import Path
from PIL import Image
from scipy.interpolate import PchipInterpolator
import cv2
import numpy as np
import hashlib, json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'a5_pirate_ranked'
SOURCE = OUT / '02_pirate_sea_canon_source.png'
CANON_SHA = '0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == CANON_SHA, 'Wrong approved Pirate reference'
OUT.mkdir(parents=True, exist_ok=True)
img = Image.open(SOURCE).convert('RGB')
# Board rank-7 dark naval cap, and reserve rank-9 brass naval cap.
# Coordinates are inspected silhouette bounds in the exact 1672x941 source.
masters = {
    1: dict(box=(1315,744,1478,907), ys=[14,20,30,45,65,85,105,130,145,153,159,162],
            left=[75,55,39,31,23,15,8,2,0,1,12,31],
            right=[91,113,127,138,146,154,161,162,162,158,148,128],
            badge_center=(89,40), badge_axes=(25,17), badge_color=(246,170,89)),
    2: dict(box=(1030,514,1214,690), ys=[13,20,30,45,65,90,110,130,145,157,168,175],
            left=[89,70,60,57,47,35,27,20,17,17,27,53],
            right=[112,133,145,154,162,169,176,180,179,174,160,133],
            badge_center=(98,40), badge_axes=(26,17), badge_color=(65,24,17)),
}
# Strictly increasing visible widths. Touch targets remain 44 physical px;
# numeric rank is a separate live label and not baked into these sprites.
widths = [54,62,70,78,86,94,102,110,118]
manifest=[]
for player, cfg in masters.items():
    crop = np.array(img.crop(cfg['box']), dtype=np.uint8)
    h,w = crop.shape[:2]
    yv=np.arange(h)
    left=PchipInterpolator(cfg['ys'],cfg['left'],extrapolate=False)(yv)
    right=PchipInterpolator(cfg['ys'],cfg['right'],extrapolate=False)(yv)
    mask=np.zeros((h,w),dtype=np.uint8)
    for y in range(h):
        if np.isfinite(left[y]) and np.isfinite(right[y]):
            cv2.line(mask,(max(0,int(left[y])),y),(min(w-1,int(right[y])),y),255,1)
    mask=cv2.GaussianBlur(mask,(3,3),0.7)
    # Clean the baked number from the inset top badge without modifying the
    # gold anchor emblem or outer cap. This avoids contradictory ranks in play.
    yy,xx=np.mgrid[:h,:w]
    cx,cy=cfg['badge_center'];rx,ry=cfg['badge_axes']
    d=((xx-cx)/rx)**2+((yy-cy)/ry)**2
    blend=np.clip((1.02-d)*9,0,1)[...,None]
    gloss=np.clip((cy-yy)/ry,-1,1)*5
    fill=np.clip(np.array(cfg['badge_color'])+gloss[...,None],0,255)
    rgb=np.uint8(crop*(1-blend)+fill*blend)
    rgba=np.dstack([rgb,mask])
    x,y,bw,bh=cv2.boundingRect(np.uint8(mask>20))
    master=Image.fromarray(rgba[y:y+bh,x:x+bw], 'RGBA')
    for rank,target in enumerate(widths,1):
        th=round(master.height*target/master.width)
        assert 0<th<125
        scaled=master.resize((target,th),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(128,128),(0,0,0,0))
        # Center horizontally, align all caps to the same lower baseline.
        canvas.alpha_composite(scaled,((128-target)//2,122-th))
        dest=OUT/f'pirate_rank_{rank:02d}_p{player}.png'
        canvas.save(dest,optimize=True)
        a=np.array(canvas.getchannel('A'))
        ys,xs=np.where(a>80)
        bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
        manifest.append({'rank':rank,'player':player,'file':dest.name,
                         'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                         'alpha_bounds':bbox,'visible_width':bbox[2]-bbox[0],
                         'visible_height':bbox[3]-bbox[1]})
manifest.sort(key=lambda x:(x['rank'],x['player']))
(OUT/'asset_manifest.json').write_text(json.dumps({
    'source':'02_pirate_sea.png','source_sha256':CANON_SHA,
    'source_kind':'USER_ACCEPTED_REFERENCE_UNMODIFIED',
    'method':'two exact-reference material masters, matte+number cleanup, rank-specific scaling; dynamic labels in Godot',
    'assets':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Audit-only contact sheet; NOT a gameplay screenshot.
sheet=Image.new('RGBA',(9*92,2*104),(30,49,65,255))
from PIL import ImageDraw, ImageFont
draw=ImageDraw.Draw(sheet)
for m in manifest:
    art=Image.open(OUT/m['file']).convert('RGBA')
    art.thumbnail((72,72),Image.Resampling.LANCZOS)
    x=(m['rank']-1)*92+(92-art.width)//2
    y=(m['player']-1)*104+2
    sheet.alpha_composite(art,(x,y))
    draw.text(((m['rank']-1)*92+43,(m['player']-1)*104+72),str(m['rank']),fill=(255,245,215,255),anchor='mt')
sheet.convert('RGB').save(OUT/'pirate_ranked_preview.jpg',quality=95)
print('A5_PIRATE_CANONICAL_ASSETS_PASS',len(manifest),'assets')
