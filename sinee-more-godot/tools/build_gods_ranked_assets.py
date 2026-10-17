"""Deterministic, layered creature sprites from the exact accepted Gods of the Deep reference.

Nine different lower-dock silhouettes are isolated (not nine resizes of one creature).
The dark opponent family uses the same reference silhouettes with a dark abyssal/cyan
material treatment. Numeric medallions are neutralized: Godot renders actual rank.
No source PNG is altered, and no screenshot is used as an interactive surface.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import cv2
import hashlib, json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets'/'a5_gods_ranked'
SOURCE=OUT/'04_gods_of_the_deep_canon_source.png'
SHA='10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA,'Noncanonical Gods reference'
OUT.mkdir(parents=True,exist_ok=True)
source=np.asarray(Image.open(SOURCE).convert('RGB'))
# Canonical lower reserve: nine *distinct* ranked beings, left to right.
# Per-piece source bounding rectangles intentionally avoid the upper board/UI.
BOXES=[(176,807,308,932),(310,797,439,932),(424,786,572,932),
       (576,799,714,932),(711,806,872,932),(865,809,1040,932),
       (1023,802,1164,932),(1170,786,1354,932),(1341,781,1583,932)]
WIDTHS=[48,56,64,72,80,88,96,104,112]
BADGE_CENTERS=[(240,889),(376,891),(508,891),(641,889),(789,890),(951,892),(1120,893),(1256,892),(1414,891)]
manifest=[]
last_visible_height={1:0,2:0}
last_visible_area={1:0,2:0}
for rank,(box,target) in enumerate(zip(BOXES,WIDTHS),1):
    x0,y0,x1,y1=box
    rgb=source[y0:y1,x0:x1].copy()
    h,w=rgb.shape[:2]
    yy,xx=np.mgrid[:h,:w]
    # Soft horizontally centered stencil excludes neighboring rank artwork.
    nx=(xx-(w-1)/2)/((w-1)/2)
    ny=(yy-(h-1)*.58)/((h-1)*.64)
    envelope=np.clip((1.20-nx*nx-ny*ny)*2.5,0,1)
    R,G,B=[rgb[:,:,i].astype(np.float32) for i in range(3)]
    # Warm pearlescent contours and electric-blue glows are foreground.
    warm=np.clip((R-63)/140,0,1)*np.clip((G-48)/125,0,1)
    electric=np.clip((G-62)/145,0,1)*np.clip((B-105)/120,0,1)
    strength=np.maximum(warm,electric)
    # Bright fragments connect across faint inner body details.
    fg=np.uint8(strength>.22)*255
    fg=cv2.morphologyEx(fg,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    fg=cv2.dilate(fg,np.ones((3,3),np.uint8),iterations=1)
    # Retain brighter artwork and gentle edge glows; eliminate dark background.
    alpha=np.maximum(strength*.90,fg.astype(np.float32)/255*.57)*envelope
    alpha=np.uint8(np.clip(alpha*255,0,255))
    alpha=cv2.GaussianBlur(alpha,(3,3),.65)
    # Neutral dark medallion covers inconsistent baked screenshot numerals.
    # The gameplay overlay is the sole rank source.
    # Badge is near the lower central line of each source crop.
    cx=BADGE_CENTERS[rank-1][0]-x0
    cy=BADGE_CENTERS[rank-1][1]-y0
    rad=25.0
    disc=((xx-cx)**2+(yy-cy)**2)<=rad**2
    ring=((xx-cx)**2+(yy-cy)**2)<=(rad+2.5)**2
    rgb[ring]=np.array([68,131,155],np.uint8)
    rgb[disc]=np.array([5,19,31],np.uint8)
    alpha[ring]=255
    # Remove blank outer space and center each sprite in the common 128px tile.
    inds=np.where(alpha>45)
    assert len(inds[0])>300, f'Rank {rank} source extraction failed'
    by0,by1=int(inds[0].min()),int(inds[0].max()+1)
    bx0,bx1=int(inds[1].min()),int(inds[1].max()+1)
    cropped_rgb=rgb[by0:by1,bx0:bx1]
    cropped_a=alpha[by0:by1,bx0:bx1]
    for player in (1,2):
        colored=cropped_rgb.copy()
        if player==2:
            c=colored.astype(np.float32)
            luminance=(c[:,:,0]*.3+c[:,:,1]*.59+c[:,:,2]*.11)/255
            # Deep cobalt body with electric-cyan contour lighting.
            colored[:,:,0]=np.uint8(np.clip(5+25*luminance,0,255))
            colored[:,:,1]=np.uint8(np.clip(17+100*luminance,0,255))
            colored[:,:,2]=np.uint8(np.clip(36+183*luminance,0,255))
            # Keep neutral dark rank badge for contrast with live white number.
            dy,dx=np.mgrid[by0:by1,bx0:bx1]
            circle=(dx-cx)**2+(dy-cy)**2<=rad**2
            colored[circle]=[5,19,31]
        rgba=np.dstack([colored,cropped_a])
        sprite=Image.fromarray(rgba,'RGBA')
        height=min(116,round(sprite.height*target/sprite.width))
        sprite=sprite.resize((target,height),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(128,128),(0,0,0,0))
        canvas.alpha_composite(sprite,((128-target)//2,123-height))
        # v48: preserve the original distinct creatures, but correct their
        # nonmonotonic *visible area*. R6 was smaller than R5; R9 smaller
        # than R8 even though the source widths grew. Uniform scaling about
        # the lower medallion/baseline retains the canon creature anatomy.
        rank_scale = {6: 1.07, 9: 1.11}.get(rank, 1.0)
        if rank_scale != 1.0:
            inv = 1.0 / rank_scale
            canvas = canvas.transform(
                (128,128), Image.Transform.AFFINE,
                (inv,0,64*(1-inv),0,inv,123*(1-inv)),
                resample=Image.Resampling.BICUBIC)
        # v63: the previous area-only fix left several higher ranks visibly
        # SHORTER than their predecessor (R3/R6/R8/R9). Preserve each unique
        # canonical creature and its horizontal silhouette; gently extend only
        # the vertical display dimension, anchored to the same bottom baseline.
        # Numeric rank remains a live Godot overlay, not a baked screenshot.
        original_canvas=canvas
        factor=1.0
        for attempt in range(12):
            if factor > 1.0:
                inv_y=1.0/factor
                canvas=original_canvas.transform((128,128), Image.Transform.AFFINE,
                    (1,0,0,0,inv_y,123*(1-inv_y)),
                    resample=Image.Resampling.BICUBIC)
            alpha_view=np.asarray(canvas.getchannel('A'))
            ys=np.where(alpha_view>100)[0]
            visible_height=int(ys.max()-ys.min()+1)
            visible_area=int((alpha_view>100).sum())
            if visible_height>last_visible_height[player] and visible_area>last_visible_area[player]:
                break
            # A larger rank must grow in *both* dimensions and visible area.
            # Grow only enough to clear the predecessor, never switch creature.
            factor*=max(1.03,
                (last_visible_height[player]+3)/float(visible_height),
                (last_visible_area[player]+15)/float(visible_area))*1.01
            assert factor <= 1.50, f'Excessive vertical correction rank {rank}: {factor}'
        else:
            raise AssertionError(f'Rank {rank} could not achieve monotonic silhouette')
        last_visible_height[player]=visible_height
        last_visible_area[player]=visible_area
        name=f'gods_rank_{rank:02d}_p{player}.png'
        path=OUT/name
        canvas.save(path,optimize=True)
        a=np.array(canvas.getchannel('A'))
        sy,sx=np.where(a>100)
        area_gt100=int((a>100).sum())
        bounds=[int(sx.min()),int(sy.min()),int(sx.max()+1),int(sy.max()+1)]
        manifest.append({'rank':rank,'player':player,'file':name,
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'alpha_bounds':bounds,'visible_width':bounds[2]-bounds[0],
                         'visible_height':int(np.where(a>100)[0].max()-np.where(a>100)[0].min()+1),
                         'alpha_area_gt100':area_gt100})
# v124: At 22px, Gods rank 7 had only 114 alpha-visible pixels versus
# rank 6's 113 (0.9% increase). Enlarging the entire silhouette would make
# rank 7 WIDER than rank 8, breaking the stronger canonical rank ordering.
# Instead, strengthen existing source-derived translucent detail inside the
# same silhouette: no geometry change, no new figure, no baked numeral, no
# different touch target. At 22px the rank-7/6 separation is now >10%.
for player in (1, 2):
    path=OUT/f'gods_rank_07_p{player}.png'
    canvas=Image.open(path).convert('RGBA')
    scale=1.03
    inv=1.0/scale
    canvas=canvas.transform((128,128), Image.Transform.AFFINE,
        (inv,0,64*(1-inv),0,inv,123*(1-inv)),
        resample=Image.Resampling.BICUBIC)
    # Strengthen only already present translucent creature details. A fully
    # opaque badge stays unchanged and the alpha-visible footprint remains
    # strictly smaller than rank 8 at both native and 22px board scales.
    rgba=np.asarray(canvas).copy()
    old_alpha=rgba[:,:,3].copy()
    native_visible=np.where(old_alpha>100)
    x_min,x_max=int(native_visible[1].min()),int(native_visible[1].max())
    y_min,y_max=int(native_visible[0].min()),int(native_visible[0].max())
    yy,xx=np.indices(old_alpha.shape)
    within_original_bounds=(xx>=x_min)&(xx<=x_max)&(yy>=y_min)&(yy<=y_max)
    stronger=np.uint8(np.minimum(255.0, np.rint(old_alpha.astype(np.float32)*1.50)))
    # Never extend the 128px alpha>100 silhouette beyond its predecessor
    # bounds: rank 8 must remain strictly wider AND taller than rank 7.
    rgba[:,:,3]=np.where(within_original_bounds,stronger,old_alpha)
    canvas=Image.fromarray(rgba,'RGBA')
    canvas.save(path,optimize=True)
    alpha=np.asarray(canvas.getchannel('A'))
    sy,sx=np.where(alpha>100)
    bounds=[int(sx.min()),int(sy.min()),int(sx.max()+1),int(sy.max()+1)]
    record=next(m for m in manifest if m['rank']==7 and m['player']==player)
    record.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  alpha_bounds=bounds,
                  visible_width=bounds[2]-bounds[0],
                  visible_height=bounds[3]-bounds[1],
                  alpha_area_gt100=int((alpha>100).sum()))
# v130: At ultra-small actual sprite rasters, the distinct Gods creatures
# can alias into a false size reversal even though their 128px silhouettes
# and 22px presentation grow correctly. The accepted rank order must remain
# legible at 12px and 18px as well, for both sides, without changing creature
# identity, badge positions, touch targets, or the immutable reference PNG.
# Boost only existing translucent details INSIDE the original >100 alpha bbox.
for rank, alpha_gain in ((5, 1.10), (8, 1.20)):
    for player in (1, 2):
        path=OUT/f'gods_rank_{rank:02d}_p{player}.png'
        canvas=Image.open(path).convert('RGBA')
        rgba=np.asarray(canvas).copy()
        old_alpha=rgba[:,:,3].copy()
        sy,sx=np.where(old_alpha>100)
        yy,xx=np.indices(old_alpha.shape)
        within_original_bounds=(xx>=sx.min())&(xx<=sx.max())&(yy>=sy.min())&(yy<=sy.max())
        stronger=np.uint8(np.minimum(255.0, np.rint(old_alpha.astype(np.float32)*alpha_gain)))
        rgba[:,:,3]=np.where(within_original_bounds,stronger,old_alpha)
        canvas=Image.fromarray(rgba,'RGBA')
        canvas.save(path,optimize=True)
        alpha=np.asarray(canvas.getchannel('A'))
        ys,xs=np.where(alpha>100)
        bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
        record=next(m for m in manifest if m['rank']==rank and m['player']==player)
        record.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      alpha_bounds=bounds,
                      visible_width=bounds[2]-bounds[0],
                      visible_height=bounds[3]-bounds[1],
                      alpha_area_gt100=int((alpha>100).sum()))

# All 126 live sprites must preserve rank progression even at 12px: the
# four corrected Gods sprites are not a separate rendering/gameplay path.
for player in (1,2):
    for raster_size in (12,14,16,18,20,22,24,28,32):
        areas=[]
        for rank in range(1,10):
            alpha=Image.open(OUT/f'gods_rank_{rank:02d}_p{player}.png').getchannel('A')
            scaled=alpha.resize((raster_size,raster_size),Image.Resampling.LANCZOS)
            areas.append(int((np.asarray(scaled)>100).sum()))
        assert all(a<b for a,b in zip(areas,areas[1:])), (player,raster_size,areas)
manifest.sort(key=lambda m:(m['rank'],m['player']))
assert len(manifest)==18
for player in (1,2):
    sizes=[m['visible_width'] for m in manifest if m['player']==player]
    assert all(a<b for a,b in zip(sizes,sizes[1:])),sizes
    areas=[m['alpha_area_gt100'] for m in manifest if m['player']==player]
    assert all(a<b for a,b in zip(areas,areas[1:])),areas
    heights=[m['visible_height'] for m in manifest if m['player']==player]
    assert all(a<b for a,b in zip(heights,heights[1:])),heights
(OUT/'asset_manifest.json').write_text(json.dumps({
    'source':'04_gods_of_the_deep.png','source_sha256':SHA,
    'method':'nine unique canonical reserve creatures; source brightness matte; dark opponent recolor; live ranks; v48 area correction retained; v63 baseline-anchored vertical normalization; v124 3% rank-7 correction; v130 translucent-detail strengthening of ranks 5 and 8 for strict 12-32px progression',
    'rank_growth_policy':'strictly increasing alpha-visible width, height and area for both sides at 128px and 12-32px raster sizes; source-derived creature shapes and live numeric labels retained',
    'assets':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
contact=Image.new('RGBA',(9*128,2*128),(10,25,42,255))
for m in manifest:
    tile=Image.open(OUT/m['file']).convert('RGBA')
    contact.alpha_composite(tile,((m['rank']-1)*128,(m['player']-1)*128))
contact.convert('RGB').save(OUT/'gods_ranked_preview.jpg',quality=93)
print('A5_GODS_NINE_DISTINCT_SOURCE_CREATURES_PASS',len(manifest))
