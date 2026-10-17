#!/usr/bin/env python3
"""Deterministic ORIGINAL layered Northern Sea environment assets.
The seven user-approved PNGs are read-only semantic references; no game state,
rank numerals, buttons, or reference screenshot pixels are included here.
The live Godot board, cells, pieces and input are rendered independently.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import math, random, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "a5_northern_environment"
W,H=1024,576
R=random.Random(7306)

def lerp(a,b,t): return int(a+(b-a)*max(0,min(1,t)))
def blend(a,b,t): return tuple(lerp(a[i],b[i],t) for i in range(3))
def line(draw,xy,fill,width=1): draw.line(xy,fill=fill,width=width)

def backdrop():
    im=Image.new("RGB",(W,H))
    px=im.load()
    top=(2,12,31); horizon=(21,66,94); water=(6,31,55)
    for y in range(H):
        for x in range(W):
            v=y/H
            c=blend(top,horizon,min(1,v/.53)) if v<.53 else blend(water,(17,45,63),min(1,(v-.53)/.47))
            # Luminous blue fjord reflection; no screenshot pixels.
            if .52<v<.83:
                ripple=(math.sin(y*.36+x*.035)+math.sin(x*.17-y*.07))*0.5
                strength=max(0,1-abs(x/W-.52)*2)*max(0,ripple)*.26
                c=blend(c,(89,167,199),strength)
            px[x,y]=c
    d=ImageDraw.Draw(im,"RGBA")
    for _ in range(130):
        x=R.randrange(W);y=R.randrange(3,218)
        r=R.choice((1,1,1,2))
        d.ellipse((x-r,y-r,x+r,y+r),fill=(185,228,255,R.randrange(75,190)))
    # Soft multi-band aurora, luminous atmospheric light rather than dotted stripes.
    import numpy as np
    sky=np.asarray(im.convert("RGB")).astype(np.float32).copy()
    yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
    t=xx/W
    aurora=np.zeros((H,W),dtype=np.float32)
    for offset,phase,width,power in [(73.0,0.0,42.0,.42),(105.0,1.6,35.0,.29),(142.0,3.1,52.0,.21)]:
        center=offset+21*np.sin(t*9+phase)+12*np.sin(t*23+phase*1.5)
        band=np.exp(-((yy-center)/width)**2)
        curtain=(.53+.47*np.sin(t*33+yy*.018+phase)**2)
        aurora+=power*band*curtain
    aurora*=np.clip((295-yy)/145,0,1)
    aurora=np.clip(aurora,0,.66)
    tint=np.zeros_like(sky)
    tint[:,:,0]=48+25*np.sin(t*4)
    tint[:,:,1]=201+26*np.sin(t*7)
    tint[:,:,2]=167+35*np.cos(t*5)
    sky=sky*(1-aurora[:,:,None])+tint*aurora[:,:,None]
    im=Image.fromarray(np.clip(sky,0,255).astype("uint8"),"RGB").convert("RGBA")
    d=ImageDraw.Draw(im,"RGBA")
    # Three overlapping natural mountain ridges with continuous snow lines.
    for layer,base,amplitude,color,snow in [
        (0,277,137,(5,24,44,255),(151,194,218,245)),
        (1,318,111,(12,40,61,255),(183,215,228,245)),
        (2,363,78,(19,53,70,255),(210,232,237,245)),
    ]:
        peaks=[]
        for x in range(-10,W+20,5):
            wave=(math.sin(x*.009+layer*1.4)*.42+
                  math.sin(x*.026+layer*.8)*.32+
                  math.sin(x*.071+layer*1.7)*.15+
                  math.sin(x*.12+layer*3.3)*.09)
            y=int(base-amplitude*(.55+.52*wave))
            peaks.append((x,y))
        d.polygon(peaks+[(W,H),(0,H)],fill=color)
        snowline=[]
        for x,y in peaks:
            depth=11+int((layer+1)*4)+int(11*abs(math.sin(x*.034+layer)))
            snowline.append((x,y+depth))
        d.polygon(peaks+list(reversed(snowline)),fill=snow)
        # Light follows slope breaks, giving ridges faceted relief.
        for j in range(2,len(peaks)-3,7):
            x,y=peaks[j]
            if peaks[j+1][1]>y:
                d.polygon([(x,y+17),(x+20,peaks[j+4][1]+23),
                           (x+42,peaks[j+4][1]+59)],fill=(51,89,109,80))
        for j in range(3,len(peaks)-4,11):
            x,y=peaks[j]
            d.line((x,y+29,x+17,y+72),fill=(3,19,37,110),width=2)
    # Fjord shore and small harbor settlement: behind live board.
    d.polygon([(0,326),(165,304),(274,323),(390,341),(390,359),(0,357)],fill=(12,35,50,255))
    d.polygon([(645,338),(789,315),(1024,292),(1024,366),(645,368)],fill=(12,36,50,255))
    for x,y in [(98,309),(140,306),(175,317),(785,322),(823,316),(882,307),(924,301)]:
        d.rectangle((x,y-19,x+22,y+4),fill=(26,37,48,255))
        d.polygon([(x-5,y-19),(x+11,y-31),(x+27,y-19)],fill=(8,24,39,255))
        for dx in (6,16):
            d.rectangle((x+dx,y-11,x+dx+3,y-4),fill=(255,160,76,230))
    # Far-water snow/ice floes and broken reflections.
    for i in range(100):
        y=R.randrange(338,473); x=R.randrange(W)
        width=int((y-300)/9)+R.randrange(5,21)
        d.polygon([(x,y),(x+width,y-1),(x+width+9,y+3),(x-7,y+4)],fill=(126,181,200,R.randrange(26,92)))
    # Longship on the right; the approved perimeter contains the detailed ship.
    # This interior silhouette creates coherent continuity without baking game pieces.
    cx=834;deck=380
    d.polygon([(cx-103,deck),(cx+112,deck-6),(cx+86,deck+25),(cx-70,deck+27)],fill=(13,23,34,255))
    d.arc((cx-111,deck-14,cx+112,deck+43),0,175,fill=(171,103,62,255),width=4)
    d.line((cx,deck-171,cx,deck+5),fill=(32,26,35,255),width=6)
    d.polygon([(cx-1,deck-166),(cx+70,deck-137),(cx+72,deck-30),(cx,deck-36)],fill=(121,57,65,215))
    for yy in range(deck-150,deck-41,23):
        d.line((cx+4,yy,cx+70,yy+7),fill=(214,193,171,140),width=5)
    for i in range(8):
        xx=cx-63+i*19
        d.ellipse((xx,deck-4,xx+16,deck+13),outline=(186,125,73,255),width=3)
    # Perspective frozen quay below the board, real ground plane.
    d.polygon([(0,464),(1024,464),(1024,576),(0,576)],fill=(14,27,39,255))
    for yy in (473,494,519,548):
        d.line((0,yy,1024,yy+2),fill=(79,107,124,170),width=3)
        d.line((0,yy+3,1024,yy+4),fill=(4,11,24,150),width=2)
    for yy in (472,496,520,549):
        for x in range((yy*7)%125,1024,118):
            d.line((x,yy,x+7,yy+25),fill=(5,13,22,200),width=3)
    for i in range(160):
        x=R.randrange(W); y=R.randrange(463,576)
        r=R.randrange(1,5)
        d.ellipse((x-r,y-1,x+r,y+1),fill=(177,218,228,R.randrange(20,110)))
    return im.convert("RGB")

def plinth():
    N=512
    im=Image.new("RGBA",(N,N),(0,0,0,0));d=ImageDraw.Draw(im,"RGBA")
    # Thick basalt stone slab with ice and bronze perimeter; corner snow belongs to material.
    d.rounded_rectangle((4,9,507,507),radius=22,fill=(11,28,45,255),outline=(5,13,24,255),width=8)
    d.rounded_rectangle((17,21,494,487),radius=18,fill=(23,49,66,255),outline=(144,102,56,255),width=7)
    d.rounded_rectangle((33,36,478,471),radius=12,fill=(24,49,69,255),outline=(89,163,185,255),width=4)
    d.rounded_rectangle((43,47,468,460),radius=10,outline=(201,172,104,220),width=2)
    # Stone mottling restricted to inset, keeping border readable.
    noise=Image.new("RGBA",(N,N),(0,0,0,0));np=noise.load()
    for y in range(49,460):
        for x in range(45,468):
            val=(x*71+y*37+(x*y)%137)%211
            np[x,y]=(65,110,126,int(8+val/9))
    im=Image.alpha_composite(im,noise);d=ImageDraw.Draw(im,"RGBA")
    # Engraved circular navigation chart, not an occupied game cell.
    cx=256;cy=249
    for rad,col,w in [(187,(184,135,76,130),3),(165,(110,193,215,125),3),
                      (147,(183,150,91,130),2),(104,(111,174,192,110),2)]:
        d.ellipse((cx-rad,cy-rad,cx+rad,cy+rad),outline=col,width=w)
    for deg in range(0,360,15):
        a=math.radians(deg)
        p0=(cx+173*math.cos(a),cy+173*math.sin(a))
        p1=(cx+(183 if deg%45 else 191)*math.cos(a),cy+(183 if deg%45 else 191)*math.sin(a))
        d.line([p0,p1],fill=(201,168,95,160),width=2)
    # Four cardinal runes are non-numeric decoration.
    for ox,oy,rot in [(256,73,0),(256,424,180),(80,250,270),(430,250,90)]:
        # three simple angular strokes; do not encode rank/occupancy.
        d.line([(ox-9,oy+10),(ox-9,oy-12),(ox+10,oy-12),(ox-9,oy+5)],fill=(165,221,229,220),width=3)
        d.line([(ox-7,oy-2),(ox+10,oy+10)],fill=(165,221,229,190),width=2)
    # Snow drifts along the far edge and frosted corners.
    snow=[(10,29),(47,21),(73,28),(95,24),(129,29),(159,23),(188,26),(218,19),
          (250,26),(283,19),(312,25),(342,20),(371,25),(401,22),(431,28),(462,22),(501,33),
          (501,9),(10,9)]
    d.polygon(snow,fill=(219,242,247,246))
    d.line(snow[:-2],fill=(129,190,213,240),width=3)
    for corner in [(19,25),(492,25),(20,487),(492,484)]:
        x,y=corner
        d.ellipse((x-17,y-10,x+16,y+13),fill=(194,232,242,220))
        d.arc((x-20,y-14,x+20,y+17),195,345,fill=(255,255,255,230),width=3)
    # Ice fractures, not numbers.
    cracks=[[(54,357),(77,341),(93,358),(110,349)],
            [(374,78),(385,94),(408,102),(414,120)],
            [(118,420),(128,407),(143,414)],
            [(411,358),(393,372),(397,388),(378,400)]]
    for pts in cracks:
        d.line(pts,fill=(147,213,228,175),width=2)
    # Braided Nordic bronze corner relief.
    for x0,y0 in [(31,31),(450,31),(31,445),(450,445)]:
        for j in range(3):
            d.arc((x0+j*3,y0+j*3,x0+30-j*3,y0+30-j*3),0,270,fill=(199,151,84,195),width=2)
    return im

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    paths=[OUT/"north_fjord_backdrop.png",OUT/"north_frozen_runestone_plinth.png"]
    backdrop().save(paths[0], optimize=True)
    plinth().save(paths[1], optimize=True)
    meta={"generator":"tools/build_northern_environment.py","canonical_pngs_mutated":False,
          "contains_board_cells_or_occupancy":False,
          "assets":[{"file":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                     "size":list(Image.open(p).size)} for p in paths]}
    (OUT/"asset_manifest.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(meta,indent=2))
if __name__=="__main__": main()
