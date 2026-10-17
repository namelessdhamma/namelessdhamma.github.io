"""Offline independent scalar checks for the v75 integrated Sand/Night fast path.

These are NOT Godot compilation, visual acceptance or physical-touch tests.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import zipfile
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
BUILDER=ROOT/'tools/build_sand_night_prebaked_environment.py'
ASSETS=ROOT/'assets/a5_sand_night_prebaked_environment'
SOURCE=ROOT/'scripts/world_visuals.gd'
spec=importlib.util.spec_from_file_location('v75builder',BUILDER)
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

def color(s): return tuple(int(s[i:i+2],16)/255 for i in (1,3,5))
def lerp(a,b,t): return tuple(i+(j-i)*t for i,j in zip(a,b))
def dark(a,t): return tuple(i*(1-t) for i in a)
def light(a,t): return lerp(a,(1.,1.,1.),t)
def clamp(x,a=0.,b=1.): return max(a,min(b,x))
def pack(a): return tuple(round(clamp(v)*255) for v in a)

def scalar_sand_backdrop(x,y):
    u=x/511.;v=y/287.;h=.54
    c=lerp(color('#522b38'),color('#f7a354'),clamp(v/h))
    if v<h:
        d=math.sqrt(((u-.858)*1.45)**2+((v-.17)*2.5)**2)
        if d<.13:c=lerp(c,color('#ffd581'),(.13-d)/.13*.63)
        if d<.04:c=color('#fff8d6')
        for px,py,pw in [(.665,.035,.18),(.805,.085,.17),(.925,.21,.09)]:
            half=pw*clamp((v-py)/(.47-py))
            if py<=v<=.47 and abs(u-px)<half:
                c=color('#9d6042') if u<px else color('#d28b54')
                if abs(math.sin((v-py)*420.+u*7.))>.95:c=dark(c,.16)
        if .34<v<h:
            band=int(u*91.)
            height=.38+.055*((band*7)%5)/4.
            if v>=height and band%7<4:c=lerp(c,color('#8b4c39'),.63)
            for o in [.12,.24,.48,.95]:
                dx=abs(u-o)
                if (dx<.006 and v>.25) or (.22<v<.25 and dx<(v-.22)*.20):c=color('#75443b')
    else:
        dune=math.sin(u*21.+v*9.)*.5+math.sin(u*54.-v*14.)*.25
        grain=((x*37+y*61+x*y)%113)/113.
        c=lerp(color('#96633f'),color('#d9a866'),clamp(.52+dune*.13+grain*.18))
        if abs(math.sin(v*160.+u*19.))>.988:c=dark(c,.12)
    return pack(c)

def scalar_sand_plinth(x,y):
    edge=min(x,255-x,y,255-y)
    grain=((x*41+y*67+x*y*3)%137)/137.
    c=lerp(color('#ad7945'),color('#e4b773'),grain*.66)
    if edge<20:
        c=color('#12364d')
        if edge<3 or edge==18:c=color('#d6a347')
        elif 5<edge<16:
            glyph=(x+y*3)%27
            if glyph<3 or glyph>23:c=color('#efb75c')
    elif x%83<2 or y%83<2:c=dark(c,.16)
    elif (x*13+y*29)%421<3:c=light(c,.18)
    return pack(c)

def scalar_night_backdrop(x,y):
    u=x/511.;v=y/287.;h=.51
    c=lerp(color('#03091b'),color('#16355a'),clamp(v/h))
    if v<h:
        cloud=math.sin(u*29.+v*17.+math.sin(u*9.)*2.2)
        cloud+=.58*math.sin(u*61.-v*26.)+.31*math.sin(u*103.+v*71.)
        bank=.32+.18*math.sin(u*16.+.7)
        if v<bank and cloud>.42:c=lerp(c,color('#08132b'),clamp((cloud-.42)*.43,0.,.62))
        elif cloud<-.67:c=lerp(c,color('#3261a1'),clamp((-cloud-.67)*.24,0.,.29))
        mx=(u-.744)*1.79;my=v-.118;moon=math.sqrt(mx*mx+my*my)
        if moon<.175:c=lerp(c,color('#6d9fe0'),(.175-moon)/.175*.33)
        if moon<.058:
            c=lerp(color('#d8eaff'),color('#a7c9f4'),clamp(moon/.058)*.27)
            if math.sin(u*251.+v*123.)>.92:c=dark(c,.11)
        for tx,ty,tz in [(.085,.20,.027),(.18,.30,.022),(.90,.16,.030),(.955,.25,.024)]:
            dx=abs(u-tx)
            if dx<tz and v>ty:c=color('#071021')
            elif ty-.055<v<ty and dx<tz*(v-(ty-.055))/.055:c=color('#071021')
            if dx<tz*.65 and ty+.10<v<h and y%21<5:c=lerp(c,color('#ff9e46'),.72)
        for sx,sy,sw in [(.30,.36,.075),(.53,.31,.095),(.68,.37,.068)]:
            dx=abs(u-sx)
            if dx<.003 and sy-.09<v<.49:c=color('#060c1c')
            if sy<v<.465 and dx<sw*(.465-v)/(.465-sy):c=lerp(c,color('#142943'),.94)
            if .463<v<.49 and dx<sw:c=color('#060d1c')
    else:
        wave=math.sin(v*310.+math.sin(u*33.)*5.)
        ripple=math.sin(u*143.-v*61.)
        c=lerp(color('#06162e'),color('#22528a'),clamp(.29+.17*wave+.11*ripple,.04,.61))
        reflect=math.exp(-((u-.744)/(.065+.19*(v-h)))**2)
        if wave>.54:c=lerp(c,color('#8fb9f0'),reflect*(wave-.54)*.65)
        if v>.82:
            grain=((x*41+y*67+x*y)%127)/127.
            c=lerp(color('#111a2d'),color('#30445a'),grain*.48)
            if y%23<2 or (x+(y//23%2)*35)%79<2:c=dark(c,.34)
    for lx,ly in [(.13,.43),(.39,.47),(.59,.46),(.88,.42)]:
        glow=math.sqrt(((u-lx)*1.79)**2+(v-ly)**2)
        if glow<.035:c=lerp(c,color('#ff9c42'),(.035-glow)/.035*.65)
        if glow<.005:c=color('#ffe7a4')
    return pack(c)

def scalar_night_plinth(x,y):
    edge=min(x,255-x,y,255-y)
    grain=((x*31+y*71+x*y*5)%149)/149.
    c=lerp(color('#111d30'),color('#354962'),grain*.51)
    if edge<17:
        c=color('#101326')
        if edge in (3,14):c=color('#c78c49')
        elif 5<edge<13 and (x+y*3)%19<3:c=color('#7b563a')
    elif y%48<2 or (x+(y//48%2)*37)%73<2:c=dark(c,.35)
    dx=x-127.5;dy=y-127.5;radius=math.sqrt(dx*dx+dy*dy)
    if edge>=18 and (abs(radius-85.)<.8 or abs(radius-61.)<.8):c=lerp(c,color('#b9814d'),.67)
    if edge>=18 and radius<86. and (abs(dx)<.8 or abs(dy)<.8):c=lerp(c,color('#c28a50'),.55)
    return pack(c)

SPECS=[('sand_sunset_backdrop.png',512,288,scalar_sand_backdrop),
       ('sand_sandstone_support.png',256,256,scalar_sand_plinth),
       ('night_gothic_harbor_backdrop.png',512,288,scalar_night_backdrop),
       ('night_masonry_support.png',256,256,scalar_night_plinth)]

def test_independent_scalar_samples_exact():
    rng=random.Random(750021)
    for name,w,h,scalar in SPECS:
        im=np.asarray(Image.open(ASSETS/name).convert('RGB'))
        points={(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,h//2)}
        points.update((rng.randrange(w),rng.randrange(h)) for _ in range(2500))
        for x,y in points:
            actual=tuple(int(v) for v in im[y,x])
            expected=scalar(x,y)
            assert actual==expected,(name,x,y,actual,expected)

def test_manifest_hashes_and_dimensions():
    manifest=json.loads((ASSETS/'asset_manifest.json').read_text())
    assert len(manifest['assets'])==4
    assert not manifest['contains_game_state_or_board_cells']
    for entry in manifest['assets']:
        p=ASSETS/entry['file']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256']
        assert list(Image.open(p).size)==entry['size']

def test_live_world_source_integration_and_isolation():
    src=SOURCE.read_text()
    assert 'world == 4 or world == 5' in src
    assert 'prepared_scene := load(SAND_NIGHT_ENV_ROOT + backdrop_file)' in src
    assert 'sand_plinth = load(SAND_NIGHT_ENV_ROOT + "/sand_sandstone_support.png")' in src
    assert 'night_plinth = load(SAND_NIGHT_ENV_ROOT + "/night_masonry_support.png")' in src
    assert 'scenery.visible = world != 0' in src
    assert 'support.visible = world != 0' in src
    assert 'chart.visible = world >= 1 and world <= 6' in src
    assert '_make_backdrop(world)' in src  # remaining worlds retain fallback

def test_approved_seven_canon_unchanged_against_provider_manifest():
    m=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
    assert len(m['images'])==7
    for entry in m['images']:
        candidates=list((ROOT/'assets').glob('*/'+entry['file'].replace('.png','_canon_source.png')))
        # The source PNGs are intentionally stored with their original canonical basename.
        candidates+=list((ROOT/'assets').glob('*/'+entry['file']))
        assert len(candidates)>=1,entry['file']
        assert hashlib.sha256(candidates[0].read_bytes()).hexdigest()==entry['sha256']
