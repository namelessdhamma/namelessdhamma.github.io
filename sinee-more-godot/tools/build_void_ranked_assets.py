"""Build two families of glass light domes from the exact accepted ND Void art.

This script never modifies the approved source PNG. It isolates two original
large glass pieces, removes screenshot-only rank glyphs, and creates nine
progressively larger transparent sprites for each player. Numeric rank and
occupancy are drawn by the shared Godot gameplay layer at runtime.
"""
from pathlib import Path
import hashlib, json
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/a5_void_ranked'
SOURCE=OUT/'01_nd_premium_void_canon_source.png'
SHA='00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA, 'Wrong approved ND Void source'
image=np.asarray(Image.open(SOURCE).convert('RGB'))
# Outer ellipses are calibrated on the original approved source. The board and
# baked number are explicitly excluded, not flattened into an in-game button.
masters={
 1:dict(box=(429,217,640,359), dome=(101,64,74,57), ring=(101,112,94,22), glyph=(87,40,129,102)),
 2:dict(box=(1002,213,1210,360), dome=(106,69,73,58), ring=(106,118,94,22), glyph=(102,48,144,111)),
}
widths=[45,53,61,69,77,85,93,102,113]
entries=[]
digit_stats={}
for player,cfg in masters.items():
 x0,y0,x1,y1=cfg['box']; rgb=image[y0:y1,x0:x1].copy()
 h,w=rgb.shape[:2]
 # Digit matte only within the known white number bounding region. Keep all
 # glass rim, specular edge, light ring and other source details untouched.
 a,b,c,d=cfg['glyph']; region=rgb[b:d,a:c]
 hsv=cv2.cvtColor(region,cv2.COLOR_RGB2HSV)
 whiten=(hsv[:,:,2]>112)&(hsv[:,:,1]<152)
 digit=np.zeros((h,w),np.uint8)
 digit[b:d,a:c]=(whiten.astype('uint8')*255)
 digit=cv2.dilate(digit,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
 digit_stats[str(player)]=int(np.count_nonzero(digit))
 clean=cv2.inpaint(rgb,digit,9,cv2.INPAINT_TELEA)
 yy,xx=np.mgrid[:h,:w].astype(np.float32)
 cx,cy,rx,ry=cfg['dome']; ds=((xx-cx)/rx)**2+((yy-cy)/ry)**2
 # Dome glass itself has translucent dark centre and brilliant opaque edge.
 dome=np.clip((1.045-ds)/.065,0,1)
 # The luminous base is an elliptical annulus; no square board pixels.
 cx,cy,rx,ry=cfg['ring']; ring_d=((xx-cx)/rx)**2+((yy-cy)/ry)**2
 inner_d=((xx-cx)/(rx*.78))**2+((yy-cy)/(ry*.56))**2
 annulus=np.clip((1.055-ring_d)/.09,0,1)*np.clip((inner_d-.84)/.23,0,1)
 # Source-bright emission, bounded to the original ring, plus translucent rim.
 hsv_all=cv2.cvtColor(clean,cv2.COLOR_RGB2HSV)
 brightness=hsv_all[:,:,2].astype(np.float32)/255.0
 ring_alpha=annulus*np.clip((brightness-.18)*1.8,.12,1.0)
 alpha=np.maximum(dome*.96,ring_alpha)
 # Trim stray halo above the glass, preserving its full base glow.
 alpha=np.clip(alpha*255,0,255).astype(np.uint8)
 rgba=np.dstack([clean,alpha])
 yv,xv=np.where(alpha>10)
 crop=Image.fromarray(rgba[yv.min():yv.max()+1,xv.min():xv.max()+1],'RGBA')
 for rank,target in enumerate(widths,1):
  scaled_height=round(crop.height*target/crop.width)
  assert scaled_height<=120,(rank,scaled_height)
  sprite=crop.resize((target,scaled_height),Image.Resampling.LANCZOS)
  canvas=Image.new('RGBA',(128,128),(0,0,0,0))
  canvas.alpha_composite(sprite,((128-target)//2,123-scaled_height))
  name=f'void_rank_{rank:02d}_p{player}.png'
  path=OUT/name;canvas.save(path,optimize=True)
  ar=np.asarray(canvas.getchannel('A')); yy,xx=np.where(ar>100)
  bounds=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
  entries.append(dict(rank=rank,player=player,file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),alpha_bounds=bounds,visible_width=bounds[2]-bounds[0],visible_height=bounds[3]-bounds[1]))
entries.sort(key=lambda e:(e['rank'],e['player']))
for player in (1,2):
 seq=[e['visible_width'] for e in entries if e['player']==player]
 assert all(a<b for a,b in zip(seq,seq[1:])),seq
(OUT/'asset_manifest.json').write_text(json.dumps({'source':'01_nd_premium_void.png','source_sha256':SHA,'method':'two source-derived glass light domes, white screenshot numerals inpainted, source-ellipse mattes, nine ranked sizes, live Godot numeric overlays','digit_inpaint_mask_pixels':digit_stats,'assets':entries},indent=2)+'\n')
preview=Image.new('RGBA',(9*128,2*128),(9,19,32,255))
for e in entries:
 preview.alpha_composite(Image.open(OUT/e['file']).convert('RGBA'),((e['rank']-1)*128,(e['player']-1)*128))
preview.convert('RGB').save(OUT/'void_ranked_preview.jpg',quality=95)
print('A5_VOID_GLASS_SOURCE_RANKED_PASS',len(entries))
