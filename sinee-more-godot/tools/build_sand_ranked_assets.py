"""Deterministic source-derived ranked Egyptian pyramids for Sand Sea.

Two opposite material masters are cut from the exact user-approved 05 Sand
Sea PNG. The reference is preserved byte-for-byte. Transparent alpha silhouettes
are independently rank-scaled; numbers are live Godot labels, not baked art.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import hashlib, json, numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets'/'a5_sand_ranked'
SOURCE=OUT/'05_sand_sea_canon_source.png'
EXPECTED='01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED, 'Sand Sea visual canon changed'
assert Image.open(SOURCE).size==(1672,941)
# Outer contours trace actual shrine/pyramid silhouette, including flanking
# statues. No background, board grid, reserve text or controls are intentional.
MASTERS={
  1: {
   'box': (692,536,966,748),
   'outline': [(140,18),(155,36),(176,61),(198,86),(221,113),
     (230,120),(230,92),(235,82),(244,80),(252,89),(256,111),
     (257,164),(263,186),(262,194),(241,196),(234,192),
     (222,192),(218,197),(209,198),(208,203),(164,203),
     (146,208),(98,206),(85,203),(68,202),(65,195),
     (49,194),(45,198),(21,196),(17,192),(23,165),
     (23,108),(24,89),(29,83),(40,82),(47,90),(50,121),
     (60,118),(78,93),(102,63),(122,37)]
  },
  2: {
   'box': (1025,539,1328,742),
   'outline': [(180,7),(195,24),(220,50),(247,78),(266,103),
     (272,122),(275,101),(278,85),(285,80),(292,84),
     (298,95),(299,164),(303,184),(302,194),(278,194),
     (274,186),(260,184),(251,184),(250,194),(229,195),
     (221,201),(176,202),(165,198),(133,198),(131,190),
     (103,190),(102,197),(82,196),(77,192),(56,190),
     (51,184),(53,163),(53,104),(55,91),(61,84),(70,85),
     (75,93),(77,135),(88,115),(107,94),(129,68),(152,39)]
  }
}
WIDTHS=[50,58,66,74,82,90,98,107,117]
source=Image.open(SOURCE).convert('RGB')
manifest=[]
for player,config in MASTERS.items():
 box=config['box']; crop=source.crop(box)
 mask=Image.new('L',crop.size,0)
 ImageDraw.Draw(mask).polygon(config['outline'],fill=255)
 mask=mask.filter(ImageFilter.GaussianBlur(.55))
 matte=Image.new('RGBA',crop.size)
 matte.paste(crop,(0,0));matte.putalpha(mask)
 bbox=mask.getbbox(); assert bbox is not None
 cut=matte.crop(bbox)
 for rank,width in enumerate(WIDTHS,1):
  height=round(cut.height*width/cut.width)
  assert height<121, (rank,width,height)
  scaled=cut.resize((width,height),Image.Resampling.LANCZOS)
  canvas=Image.new('RGBA',(128,128),(0,0,0,0))
  canvas.alpha_composite(scaled,((128-width)//2,124-height))
  name=f'sand_rank_{rank:02d}_p{player}.png'
  path=OUT/name
  canvas.save(path,optimize=True)
  alpha=np.asarray(canvas.getchannel('A'))
  yy,xx=np.where(alpha>100)
  bounds=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
  manifest.append({'rank':rank,'player':player,'file':name,
    'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'alpha_bounds':bounds,'visible_width':bounds[2]-bounds[0],
    'visible_height':bounds[3]-bounds[1]})
manifest.sort(key=lambda m:(m['rank'],m['player']))
for player in (1,2):
 widths=[m['visible_width'] for m in manifest if m['player']==player]
 assert all(a<b for a,b in zip(widths,widths[1:])),widths
(OUT/'asset_manifest.json').write_text(json.dumps({'source':'05_sand_sea.png','source_sha256':EXPECTED,
 'method':'two board-sourced original pyramid masters, silhouette alpha, rank-dependent scaling, live rank overlay',
 'assets':manifest},indent=2,ensure_ascii=False)+'\n',encoding='utf8')
preview=Image.new('RGBA',(9*128,2*128),(41,26,18,255))
for m in manifest:
 preview.alpha_composite(Image.open(OUT/m['file']).convert('RGBA'),((m['rank']-1)*128,(m['player']-1)*128))
preview.convert('RGB').save(OUT/'sand_ranked_preview.jpg',quality=95)
print('A5_SAND_CANONICAL_PYRAMIDS_PASS textures=18')
