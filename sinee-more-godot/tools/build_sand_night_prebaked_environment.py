"""Reproducible, source-math-derived live scenery for Sand and Night Sea.

Only background and physical support textures are baked. Interactive cells,
occupancy, ranks, UI, logo and touch targets remain live and shared.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/a5_sand_night_prebaked_environment'

def rgb(code):
    return np.array([int(code[i:i+2],16)/255 for i in (1,3,5)],dtype=np.float64)

def mix(a,b,t):
    t=np.asarray(t)
    return a*(1-t[...,None])+b*t[...,None]

def clip(a,lo=0.,hi=1.):
    return np.clip(a,lo,hi)

def where(mask,a,b):
    return np.where(mask[...,None],a,b)

def dark(c,t):
    return c*(1-np.asarray(t)[...,None])

def lighten(c,t):
    return mix(c,np.ones(3),t)

def grids(w,h):
    x,y=np.meshgrid(np.arange(w,dtype=np.int32),np.arange(h,dtype=np.int32))
    return x,y,x/(w-1.),y/(h-1.)

def sand_backdrop():
    x,y,u,v=grids(512,288)
    horizon=.54
    c=mix(rgb('#522b38'),rgb('#f7a354'),clip(v/horizon))
    sky=v<horizon
    d=np.sqrt(((u-.858)*1.45)**2+((v-.17)*2.5)**2)
    c=where(sky&(d<.13),mix(c,rgb('#ffd581'),(.13-d)/.13*.63),c)
    c=where(sky&(d<.040),rgb('#fff8d6'),c)
    for px,py,pw in [(0.665,.035,.18),(.805,.085,.17),(.925,.21,.09)]:
        foot=.47
        half=pw*clip((v-py)/(foot-py))
        mask=sky&(v>=py)&(v<=foot)&(np.abs(u-px)<half)
        face=where(u<px,rgb('#9d6042'),rgb('#d28b54'))
        course=np.abs(np.sin((v-py)*420.+u*7.))
        face=where(course>.95,dark(face,.16),face)
        c=where(mask,face,c)
    skyline=sky&(v>.34)
    band=(u*91.).astype(np.int32)
    height=.38+.055*((band*7)%5)/4.
    c=where(skyline&(v>=height)&(band%7<4),mix(c,rgb('#8b4c39'),.63),c)
    for obelisk in [.12,.24,.48,.95]:
        dx=np.abs(u-obelisk)
        mask=skyline&(((dx<.006)&(v>.25))|((v>.22)&(v<.25)&(dx<(v-.22)*.20)))
        c=where(mask,rgb('#75443b'),c)
    dune=np.sin(u*21.+v*9.)*.5+np.sin(u*54.-v*14.)*.25
    grain=((x*37+y*61+x*y)%113)/113.
    sand=mix(rgb('#96633f'),rgb('#d9a866'),clip(.52+dune*.13+grain*.18))
    sand=where(np.abs(np.sin(v*160.+u*19.))>.988,dark(sand,.12),sand)
    return where(sky,c,sand)

def sand_plinth():
    x,y,_,_=grids(256,256)
    edge=np.minimum.reduce([x,255-x,y,255-y])
    grain=((x*41+y*67+x*y*3)%137)/137.
    c=mix(rgb('#ad7945'),rgb('#e4b773'),grain*.66)
    border=edge<20
    b=np.broadcast_to(rgb('#12364d'),c.shape).copy()
    b=where((edge<3)|(edge==18),rgb('#d6a347'),b)
    glyph=(x+y*3)%27
    b=where((edge>5)&(edge<16)&((glyph<3)|(glyph>23)),rgb('#efb75c'),b)
    c=where(border,b,c)
    c=where((~border)&((x%83<2)|(y%83<2)),dark(c,.16),c)
    c=where((~border)&~((x%83<2)|(y%83<2))&(((x*13+y*29)%421)<3),lighten(c,.18),c)
    return c

def night_backdrop():
    x,y,u,v=grids(512,288)
    horizon=.51
    sky=v<horizon
    c=mix(rgb('#03091b'),rgb('#16355a'),clip(v/horizon))
    cloud=np.sin(u*29.+v*17.+np.sin(u*9.)*2.2)
    cloud+=.58*np.sin(u*61.-v*26.)
    cloud+=.31*np.sin(u*103.+v*71.)
    bank=.32+.18*np.sin(u*16.+.7)
    darkcloud=(v<bank)&(cloud>.42)
    c=where(sky&darkcloud,mix(c,rgb('#08132b'),clip((cloud-.42)*.43,0.,.62)),c)
    c=where(sky&~darkcloud&(cloud<-.67),mix(c,rgb('#3261a1'),clip((-cloud-.67)*.24,0.,.29)),c)
    mx=(u-.744)*1.79;my=v-.118
    moon=np.sqrt(mx*mx+my*my)
    c=where(sky&(moon<.175),mix(c,rgb('#6d9fe0'),(.175-moon)/.175*.33),c)
    inner=mix(rgb('#d8eaff'),rgb('#a7c9f4'),clip(moon/.058)*.27)
    inner=where(np.sin(u*251.+v*123.)>.92,dark(inner,.11),inner)
    c=where(sky&(moon<.058),inner,c)
    for tx,ty,tz in [(.085,.20,.027),(.18,.30,.022),(.90,.16,.030),(.955,.25,.024)]:
        dx=np.abs(u-tx)
        tower=(dx<tz)&(v>ty)
        roof=(v>ty-.055)&(v<ty)&(dx<tz*(v-(ty-.055))/.055)
        c=where(sky&(tower|roof),rgb('#071021'),c)
        window=(dx<tz*.65)&(v>ty+.10)&(v<horizon)&((y%21)<5)
        c=where(sky&window,mix(c,rgb('#ff9e46'),.72),c)
    for sx,sy,sw in [(.30,.36,.075),(.53,.31,.095),(.68,.37,.068)]:
        dx=np.abs(u-sx)
        mast=(dx<.003)&(v>sy-.09)&(v<.49)
        c=where(sky&mast,rgb('#060c1c'),c)
        sail=(v>sy)&(v<.465)&(dx<sw*(.465-v)/(.465-sy))
        c=where(sky&sail,mix(c,rgb('#142943'),.94),c)
        hull=(v>.463)&(v<.49)&(dx<sw)
        c=where(sky&hull,rgb('#060d1c'),c)
    wave=np.sin(v*310.+np.sin(u*33.)*5.)
    ripples=np.sin(u*143.-v*61.)
    water=mix(rgb('#06162e'),rgb('#22528a'),clip(.29+.17*wave+.11*ripples,.04,.61))
    reflection=np.exp(-((u-.744)/(.065+.19*(v-horizon)))**2)
    water=where(wave>.54,mix(water,rgb('#8fb9f0'),reflection*(wave-.54)*.65),water)
    grain=((x*41+y*67+x*y)%127)/127.
    quay=mix(rgb('#111a2d'),rgb('#30445a'),grain*.48)
    masonry=(y%23<2)|((x+((y//23)%2)*35)%79<2)
    quay=where(masonry,dark(quay,.34),quay)
    water=where(v>.82,quay,water)
    c=where(sky,c,water)
    for lx,ly in [(.13,.43),(.39,.47),(.59,.46),(.88,.42)]:
        glow=np.sqrt(((u-lx)*1.79)**2+(v-ly)**2)
        c=where(glow<.035,mix(c,rgb('#ff9c42'),(.035-glow)/.035*.65),c)
        c=where(glow<.005,rgb('#ffe7a4'),c)
    return c

def night_plinth():
    x,y,_,_=grids(256,256)
    edge=np.minimum.reduce([x,255-x,y,255-y])
    grain=((x*31+y*71+x*y*5)%149)/149.
    c=mix(rgb('#111d30'),rgb('#354962'),grain*.51)
    border=edge<17
    b=np.broadcast_to(rgb('#101326'),c.shape).copy()
    b=where((edge==3)|(edge==14),rgb('#c78c49'),b)
    b=where((edge>5)&(edge<13)&(((x+y*3)%19)<3),rgb('#7b563a'),b)
    c=where(border,b,c)
    joints=(y%48<2)|((x+((y//48)%2)*37)%73<2)
    c=where((~border)&joints,dark(c,.35),c)
    dx=x-127.5;dy=y-127.5
    radius=np.sqrt(dx*dx+dy*dy)
    rings=(np.abs(radius-85.)<.8)|(np.abs(radius-61.)<.8)
    c=where((edge>=18)&rings,mix(c,rgb('#b9814d'),.67),c)
    rays=(np.abs(dx)<.8)|(np.abs(dy)<.8)
    c=where((edge>=18)&(radius<86.)&rays,mix(c,rgb('#c28a50'),.55),c)
    return c

def save(name,a):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    Image.fromarray(np.clip(np.rint(a*255.),0,255).astype(np.uint8),'RGB').save(p,optimize=True)
    return {'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'size':[Image.open(p).width,Image.open(p).height]}

def main():
    assets=[save('sand_sunset_backdrop.png',sand_backdrop()),
            save('sand_sandstone_support.png',sand_plinth()),
            save('night_gothic_harbor_backdrop.png',night_backdrop()),
            save('night_masonry_support.png',night_plinth())]
    manifest={'generator':'tools/build_sand_night_prebaked_environment.py',
              'kind':'original_live_scenery_and_physical_support_ONLY',
              'contains_game_state_or_board_cells':False,
              'canonical_reference_images_changed':False,
              'source_math':'scripts/world_visuals.gd Sand and Night procedural formulas v74',
              'assets':assets}
    (OUT/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__': print(json.dumps(main(),indent=2))
