"""Derive layered Atlantis shrine pieces from the exact user-approved reference.

The source is never modified. Both master materials are original board pieces
(no baked rank glyphs), preserving their glowing tridents. Only alpha silhouettes
and rank-specific sizes are produced; gameplay/number overlays stay live in Godot.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import cv2, numpy as np, hashlib, json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets'/'a5_atlantis_ranked'
SOURCE=OUT/'03_atlantis_canon_source.png'
SHA='2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA, 'Noncanonical Atlantis reference'
# Each silhouette is traced along the OUTER source-art border; masks exclude
# the ancient-stone board behind the piece, not the shrine's internal shadows.
MASTERS={
 1:dict(box=(729,535,939,723), rows=[(0,85,125),(10,82,128),(24,79,132),(34,71,139),(47,64,146),(59,59,152),(75,43,167),(94,36,176),(110,28,182),(129,17,195),(149,7,205),(169,3,207),(183,14,199),(187,30,184)]),
 2:dict(box=(1081,501,1330,717), rows=[(0,100,146),(12,94,153),(29,88,160),(45,78,170),(63,67,182),(82,56,194),(102,42,207),(124,29,220),(145,17,235),(170,7,242),(193,3,246),(211,17,231),(215,27,221)])
}
WIDTHS=[50,58,66,74,82,90,98,107,117]
manifest=[]
for player,cfg in MASTERS.items():
 x0,y0,x1,y1=cfg['box']; crop=np.asarray(Image.open(SOURCE).convert('RGB'))[y0:y1,x0:x1].copy()
 h,w=crop.shape[:2]; mask=np.zeros((h,w),dtype=np.uint8)
 rows=cfg['rows']
 # Linear interpolation follows source tier edges without overshooting corners.
 for y in range(h):
  if y<rows[0][0] or y>rows[-1][0]:continue
  left=np.interp(y,[p[0] for p in rows],[p[1] for p in rows]);right=np.interp(y,[p[0] for p in rows],[p[2] for p in rows]);
  mask[y,max(0,int(round(left))):min(w,int(round(right))+1)]=255
 mask=cv2.GaussianBlur(mask,(3,3),.55)
 yy,xx=np.where(mask>80); assert len(xx)>1000, 'Invalid shrine matte'
 cut=Image.fromarray(np.dstack([crop,mask])[yy.min():yy.max()+1,xx.min():xx.max()+1], 'RGBA')
 for rank,target in enumerate(WIDTHS,1):
  scaled_height=round(cut.height*target/cut.width)
  assert scaled_height<=121
  scaled=cut.resize((target,scaled_height),Image.Resampling.LANCZOS)
  canvas=Image.new('RGBA',(128,128),(0,0,0,0))
  canvas.alpha_composite(scaled,((128-target)//2,124-scaled_height))
  name=f'atlantis_rank_{rank:02d}_p{player}.png'; dest=OUT/name
  canvas.save(dest,optimize=True)
  a=np.asarray(canvas.getchannel('A')); yv,xv=np.where(a>100)
  bounds=[int(xv.min()),int(yv.min()),int(xv.max()+1),int(yv.max()+1)]
  manifest.append({'rank':rank,'player':player,'file':name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'alpha_bounds':bounds,'visible_width':bounds[2]-bounds[0]})
manifest.sort(key=lambda x:(x['rank'],x['player']))
for player in (1,2):
 widths=[m['visible_width'] for m in manifest if m['player']==player]
 assert all(a<b for a,b in zip(widths,widths[1:])),widths
(OUT/'asset_manifest.json').write_text(json.dumps({'source':'03_atlantis.png','source_sha256':SHA,'method':'two original board shrine material masters, source-pixel silhouette mattes, rank scaling, live numeric overlay','assets':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
sheet=Image.new('RGBA',(9*128,2*128),(11,29,44,255));d=ImageDraw.Draw(sheet)
for m in manifest:
 sheet.alpha_composite(Image.open(OUT/m['file']).convert('RGBA'),((m['rank']-1)*128,(m['player']-1)*128))
sheet.convert('RGB').save(OUT/'atlantis_ranked_preview.jpg',quality=95)
print('A5_ATLANTIS_SOURCE_SHRINES_PASS',len(manifest))
