"""Build original Gods of the Deep LIVE scenery materials, not screenshot art.

Reproduces the procedural Gods backdrop/plinth formulas from world_visuals.gd
with vectorized arithmetic to avoid per-pixel GDScript allocations at runtime.
Only background and physical board support are baked. Game state, board cells,
creatures, ranks, logo, hit targets and controls remain independent live nodes.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/a5_gods_prebaked_environment'

def rgb(code):
    return np.array([int(code[i:i+2],16)/255 for i in (1,3,5)],dtype=np.float64)

def mix(a,b,t):
    return a*(1-np.asarray(t)[...,None])+b*np.asarray(t)[...,None]

def save(name,a):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    Image.fromarray(np.clip(np.rint(a*255),0,255).astype(np.uint8),'RGB').save(p,optimize=True)
    return {'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':[Image.open(p).width,Image.open(p).height]}

def backdrop():
    W,H=512,288
    x,y=np.meshgrid(np.arange(W,dtype=np.int32),np.arange(H,dtype=np.int32))
    u=x/511.0;v=y/287.0
    c=mix(rgb('#021225'),rgb('#073a5d'),v*.78)
    beam=np.abs(np.sin(u*17.0+v*3.0))
    c=mix(c,rgb('#11a9e3'),.15*beam**13*(1-v))
    for pillar in [.055,.14,.85,.94]:
        dx=np.abs(u-pillar)
        mask=(dx<.019)&(v>.12)&(v<.95)
        stone=mix(rgb('#05101d'),rgb('#25455a'),.25+.4*((x+y)%17)/17.)
        stone=mix(stone,rgb('#26b9e6'),np.where(dx>.014,.32,0.0))
        c=np.where(mask[...,None],stone,c)
    for j in range(4):
        cx=.1+j*.265;cy=.29+(j%2)*.18
        px=(u-cx)*11.;py=(v-cy)*11.
        bell=(px**2+(py+.05)**2<.13)&(py<.18)
        filament=(py>.12)&(py<.74)&(np.abs(np.sin(px*17.+py*3.))>.91)&(np.abs(px)<.28)
        c=np.where(bell[...,None],mix(c,rgb('#58d8ff'),.58),c)
        c=np.where((~bell&filament)[...,None],mix(c,rgb('#3e95c8'),.32),c)
    c=np.where((v>.89)[...,None],mix(c,rgb('#030b17'),.65),c)
    speck=((x*23+y*43)%941)<2
    c=np.where(speck[...,None],mix(c,np.ones(3),.37),c)
    return c

def plinth():
    W=H=256
    x,y=np.meshgrid(np.arange(W,dtype=np.int32),np.arange(H,dtype=np.int32))
    edge=np.minimum.reduce([x,255-x,y,255-y])
    grain=((x*43+y*71+x*y*3)%137)/137.
    c=mix(rgb('#071826'),rgb('#31536a'),grain*.43)
    border=edge<19
    b=mix(rgb('#020c16'),rgb('#315269'),edge/19.)
    b=np.where(((edge==6)|(edge==15))[...,None],rgb('#17c9ef'),b)
    b=np.where((edge==10)[...,None],rgb('#b58b55'),b)
    c=np.where(border[...,None],b,c)
    relief=(~border)&((x%79<2)|(y%83<2))
    c=np.where(relief[...,None],mix(c,np.ones(3),.13),c)
    engraving=(edge<25)&((x%46<3)|(y%46<3))
    c=np.where(engraving[...,None],mix(c,rgb('#bb8b4d'),.65),c)
    c=np.where((y>235)[...,None],c*.7,c)
    return c

def main():
    images=[save('gods_underwater_backdrop.png',backdrop()),save('gods_basalt_support.png',plinth())]
    manifest={'generator':'tools/build_gods_prebaked_environment.py',
              'kind':'original_scenery_and_physical_support_ONLY',
              'contains_game_state_or_board_cells':False,
              'canonical_reference_images_changed':False,
              'source_math':'scripts/world_visuals.gd Gods backdrop/plinth v73',
              'assets':images}
    (OUT/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__':print(json.dumps(main(),indent=2))
