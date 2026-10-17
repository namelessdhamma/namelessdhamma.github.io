"""OFFLINE source-art-only comparison; explicitly NOT a Godot screenshot."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'assets/a5_reference_cells/void'
BG=ROOT/'assets/a5_void_prebaked_environment/void_split_light_backdrop.png'
W,H=746,280
raw=np.asarray(Image.open(BG).convert('RGB'))
bg=cv2.resize(raw,(W,H),interpolation=cv2.INTER_LINEAR)
ref=np.array([(368,264),(1300,262),(1474,738),(195,741)],dtype=float)
center=ref.mean(axis=0)
q=center+(ref-center)*1.12
q[:,0]=q[:,0]/1672*W
q[:,1]=q[:,1]/941*235-10.6

def bilin(u,v):
 return q[0]*(1-u)*(1-v)+q[1]*u*(1-v)+q[2]*u*v+q[3]*(1-u)*v

def render(with_atlas):
 out=bg.copy()
 for i in range(9):
  r,c=divmod(i,3)
  pts=np.array([bilin(c/3,r/3),bilin((c+1)/3,r/3),bilin((c+1)/3,(r+1)/3),bilin(c/3,(r+1)/3)],dtype=np.float32)
  if with_atlas:
   tile=np.asarray(Image.open(ART/f'cell_{i:02d}.png').convert('RGB'))
  else:
   tile=np.full((192,192,3),(9,24,38),dtype=np.uint8)
  src=np.float32([[0,0],[191,0],[191,191],[0,191]])
  matrix=cv2.getPerspectiveTransform(src,pts)
  warped=cv2.warpPerspective(tile,matrix,(W,H),flags=cv2.INTER_LINEAR)
  mask=np.zeros((H,W),np.uint8);cv2.fillConvexPoly(mask,np.rint(pts).astype(np.int32),255)
  out[mask>0]=warped[mask>0]
 return Image.fromarray(out)

canvas=Image.new('RGB',(W*2,H+48),(12,15,21))
canvas.paste(render(False),(0,48));canvas.paste(render(True),(W,48))
d=ImageDraw.Draw(canvas)
d.text((12,10),'v110  |  flat Void live cells',fill=(245,245,245))
d.text((W+12,10),'v111  |  source-derived live cell atlas',fill=(245,245,245))
d.text((W-260,H+28),'OFFLINE ASSET PROJECTION - NOT GODOT',fill=(248,210,140))
canvas.save(ROOT/'A5_V111_VOID_BOARD_OFFLINE_BEFORE_AFTER_NOT_GODOT.jpg',quality=92)
