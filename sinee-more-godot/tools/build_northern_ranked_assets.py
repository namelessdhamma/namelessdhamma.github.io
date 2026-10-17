from PIL import Image, ImageDraw, ImageFilter
import numpy as np, cv2, colorsys, hashlib, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC=ROOT/'assets/a5_northern_ranked/07_northern_sea_canon_source.png'
OUT=ROOT/'assets/a5_northern_ranked'
OUT.mkdir(parents=True,exist_ok=True)
boxes=[(250,811,331,907),(340,797,457,910),(465,795,577,910),(584,792,708,917),(713,787,837,918),(838,785,976,921),(974,777,1124,929),(1113,774,1274,928),(1264,761,1450,936)]
widths=[49,58,67,76,85,94,103,112,122]
img=Image.open(SRC).convert('RGB')
if hashlib.sha256(SRC.read_bytes()).hexdigest()!='3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775': raise SystemExit('canon hash mismatch')
manifest=[]
for rank,(box,target) in enumerate(zip(boxes,widths),1):
    crop=np.array(img.crop(box))
    h,w=crop.shape[:2]
    # Eliminate the baked, potentially inconsistent rank glyph. The gameplay
    # draws its own authoritative number with a font sized for touch.
    hsv=cv2.cvtColor(crop,cv2.COLOR_RGB2HSV)
    yy,xx=np.mgrid[:h,:w]
    # central numeral within the upper oval; restrict to glowing orange text
    # to preserve bronze edge and background carving.
    cx=w*0.50; cy=h*0.45
    central=((xx-cx)/(w*.24))**2+((yy-cy)/(h*.23))**2<1
    warm=(hsv[:,:,0]<28)&(hsv[:,:,1]>95)&(hsv[:,:,2]>105)
    glowing=central&warm
    m=np.uint8(glowing)*255
    m=cv2.dilate(m,np.ones((5,5),np.uint8),iterations=2)
    cleaned=cv2.inpaint(crop,m,5,cv2.INPAINT_TELEA)
    # Tight source-derived silhouette with soft edges, excluding surrounding
    # snowy wood and UI. Keep the base's warm rim and a little reflected glow.
    top=[.255,.195,.175,.155,.135,.125,.13,.13,.13][rank-1]
    poly=np.array([(.5,top),(.70,top+.035),(.84,top+.12),(.94,top+.26),(.95,.65),(.83,.81),(.67,.885),(.43,.90),(.21,.855),(.07,.72),(.06,.46),(.13,top+.23),(.30,top+.05)],dtype=float)
    pts=np.round(poly*np.array([w-1,h-1])).astype(np.int32)
    mask=np.zeros((h,w),np.uint8)
    cv2.fillPoly(mask,[pts],255)
    mask=cv2.GaussianBlur(mask,(0,0),1.6)
    # Work from the exact source pixels except where baked glyph removal is
    # necessary for dynamic authoritative numeric overlays.
    alpha=mask
    rgba=np.dstack([cleaned,alpha])
    bounds=cv2.boundingRect(np.uint8(alpha>20))
    x,y,bw,bh=bounds
    rgba=rgba[y:y+bh,x:x+bw]
    newh=int(round(rgba.shape[0]*target/rgba.shape[1]))
    assert newh<=124
    resized=cv2.resize(rgba,(target,newh),interpolation=cv2.INTER_AREA)
    # Consistent 128x128 transparent source plane, variable silhouette width.
    for player in (1,2):
        item=resized.copy()
        if player==2:
            pix=item[:,:,:3].astype(np.float32)/255
            rgb8=item[:,:,:3].copy()
            hsv2=cv2.cvtColor(rgb8,cv2.COLOR_RGB2HSV)
            # Recolour warm red/orange emissive details into blue/ice light;
            # keep near-neutral stone and carved shadows unchanged.
            hue=hsv2[:,:,0].astype(np.float32)
            sat=hsv2[:,:,1].astype(np.float32)
            val=hsv2[:,:,2].astype(np.float32)
            tint=(hue<26)&(sat>58)&(val>68)
            hue[tint]=np.interp(hue[tint],[0,26],[104,97])
            sat[tint]=np.clip(sat[tint]*1.1,0,255)
            hsv2[:,:,0]=hue.astype(np.uint8)
            hsv2[:,:,1]=sat.astype(np.uint8)
            item[:,:,:3]=cv2.cvtColor(hsv2,cv2.COLOR_HSV2RGB)
        canvas=np.zeros((128,128,4),np.uint8)
        ox=(128-target)//2
        oy=(128-newh)//2
        canvas[oy:oy+newh,ox:ox+target]=item
        dest=OUT/f'north_rank_{rank:02d}_p{player}.png'
        Image.fromarray(canvas,'RGBA').save(dest,optimize=True)
        a=canvas[:,:,3]
        yy2,xx2=np.where(a>80)
        bounds=[int(xx2.min()),int(yy2.min()),int(xx2.max()+1),int(yy2.max()+1)]
        manifest.append({'rank':rank,'player':player,'file':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bounds':bounds,'width':bounds[2]-bounds[0],'height':bounds[3]-bounds[1]})
(OUT/'asset_manifest.json').write_text(json.dumps({'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'source':'07_northern_sea.png','assets':manifest},indent=2),encoding='utf8')
# contact sheet at 44px and enlarged for review
sheet=Image.new('RGBA',(9*128,2*128),(28,41,55,255))
for m in manifest:
    im=Image.open(OUT/m['file'])
    x=(m['rank']-1)*128;y=(m['player']-1)*128
    sheet.alpha_composite(im,(x,y))
sheet.convert('RGB').save(str(OUT/'northern_ranked_preview.jpg'),quality=95)
print('created',len(manifest),'assets')
for p in (1,2):print('player',p,[(m['rank'],m['width']) for m in manifest if m['player']==p])
