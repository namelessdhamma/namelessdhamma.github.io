"""Reproducible nine-rank Gothic beacons from USER-APPROVED Night Sea.

The source image is read-only and checked against its SHA-256. Each warm
lantern is isolated from its own numbered reserve position, rather than
replacing the canonical art with a generic drawn icon. Opponent blue/cool
family is a material transform of those source silhouettes. Numerals from
the concept screenshot are covered with neutral badges; actual numbers
are rendered from the live Godot game state.
"""
from pathlib import Path
import hashlib, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'a5_night_ranked'
SOURCE = OUT / '06_night_sea_canon_source.png'
EXPECTED = 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED, 'Approved Night Sea reference changed'
source = Image.open(SOURCE).convert('RGB')
assert source.size == (1672, 941)

# Individual centers and roof heights of the nine ACCEPTED Gothic lanterns.
CENTERS = [320, 448, 574, 691, 816, 946, 1076, 1205, 1337]
ROOFS = [811, 793, 784, 780, 772, 767, 763, 758, 750]
# Rank 1..9: strictly growing original-source silhouettes on identical 128px
# canvases; same safe touch target is assigned independently by the game.
WIDTHS = [49, 56, 63, 70, 77, 84, 91, 100, 111]
manifest = []
for rank, (cx, roof, width) in enumerate(zip(CENTERS, ROOFS, WIDTHS), 1):
    half = 76
    left, top = cx-half, roof-4
    crop = source.crop((left, top, cx+half, 911))
    w,h = crop.size
    local_roof = 4
    # Soft, source-aligned Gothic spire/tower outline. The separate lower
    # elliptical glow/base is not a baked UI control; it is piece artwork.
    tower_half = 15 + rank * 1.5
    body_half = 20 + rank * 2.0
    mask = Image.new('L', (w,h), 0)
    d = ImageDraw.Draw(mask)
    d.polygon([
        (half, local_roof), (half+5,local_roof+9),
        (half+11,local_roof+16), (half+tower_half,local_roof+24),
        (half+body_half,local_roof+43), (half+body_half, 868-top),
        (half+body_half+9,879-top), (half-body_half-9,879-top),
        (half-body_half,868-top), (half-body_half,local_roof+43),
        (half-tower_half,local_roof+24), (half-11,local_roof+16),
        (half-5,local_roof+9)], fill=255)
    base_rx = 37 + rank*3.5
    d.ellipse((half-base_rx, 871-top, half+base_rx, 906-top), fill=240)
    # Keep the source-derived glow, but remove neighboring background.
    mask = mask.filter(ImageFilter.GaussianBlur(.7))
    rgb = np.asarray(crop).copy()
    alpha = np.asarray(mask).copy()
    # Cover baked numerals on original reserve medallions; gameplay supplies
    # the actual rank label at the bottom of the sprite, in both contexts.
    yy,xx = np.mgrid[:h,:w]
    badge_y = 872-top
    neutral = ((xx-half)/15.5)**2 + ((yy-badge_y)/13.0)**2 <= 1
    ring = ((xx-half)/17.5)**2 + ((yy-badge_y)/15.0)**2 <= 1
    rgb[ring] = [88, 63, 35]
    rgb[neutral] = [13, 24, 38]
    alpha[ring] = 255
    for player in (1,2):
        colored = rgb.copy()
        if player == 2:
            f = colored.astype(np.float32)
            r,g,b = f[:,:,0],f[:,:,1],f[:,:,2]
            warm = (r > 94) & (r > g*1.13) & (r > b*1.20)
            bright = np.maximum(r,g)
            colored[warm,0] = np.uint8(np.clip(bright[warm]*.20,0,255))
            colored[warm,1] = np.uint8(np.clip(bright[warm]*.74,0,255))
            colored[warm,2] = np.uint8(np.clip(bright[warm]*1.04,0,255))
            # Badge stays dark and neutral; numbers are separate labels.
            colored[ring] = [33, 85, 112]
            colored[neutral] = [9, 25, 44]
        rgba = Image.fromarray(np.dstack([colored,alpha]),'RGBA')
        used = rgba.getchannel('A').getbbox()
        assert used is not None
        rgba = rgba.crop(used)
        scaled_h = min(117,round(rgba.height*width/rgba.width))
        scaled = rgba.resize((width,scaled_h),Image.Resampling.LANCZOS)
        tile = Image.new('RGBA',(128,128),(0,0,0,0))
        tile.alpha_composite(scaled,((128-width)//2,124-scaled_h))
        name = f'night_rank_{rank:02d}_p{player}.png'
        path = OUT/name
        tile.save(path,optimize=True)
        a = np.asarray(tile.getchannel('A'))
        ys,xs = np.where(a>100)
        assert len(xs)>80, (rank,player)
        bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
        manifest.append({'rank':rank,'player':player,'file':name,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'alpha_bounds':bounds,'visible_width':bounds[2]-bounds[0],
            'visible_height':bounds[3]-bounds[1]})
manifest.sort(key=lambda x:(x['rank'],x['player']))
for player in (1,2):
    sizes=[m['visible_width'] for m in manifest if m['player']==player]
    assert all(a<b for a,b in zip(sizes,sizes[1:])),sizes
(OUT/'asset_manifest.json').write_text(json.dumps({
    'source':'06_night_sea.png','source_sha256':EXPECTED,
    'method':'nine distinct original reserve lanterns; source-shaped transparent matte; cool-material transform; live numeric rank',
    'assets':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
preview=Image.new('RGBA',(9*128,2*128),(11,21,40,255))
for m in manifest:
    preview.alpha_composite(Image.open(OUT/m['file']).convert('RGBA'),((m['rank']-1)*128,(m['player']-1)*128))
preview.convert('RGB').save(OUT/'night_ranked_preview.jpg',quality=94)
print('A5_NIGHT_NINE_SOURCE_GOTHIC_BEACONS_PASS textures=18')
