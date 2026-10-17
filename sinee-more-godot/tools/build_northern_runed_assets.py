"""Deterministic Northern Sea rune engravings on approved-source-derived stone sprites.

Does not modify the seven approved reference PNGs or their extracted original
stone sprites. Numeric ranks remain dynamic Godot labels, not baked in artwork.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/a5_northern_ranked"
OUTPUT = ROOT / "assets/a5_northern_runed"
UPSCALE = 4

# Elder Futhark: Fehu, Uruz, Thurisaz, Ansuz, Raidho, Kenaz, Gebo,
# Wunjo, Hagalaz. Paths are strokes in a 1x1 unit square; they are NOT text
# glyphs, so the art is independent of device fonts or Unicode fallback.
RUNES = {
    1: [[(.26,.06),(.26,.94)],[(.26,.15),(.78,.30)],[(.26,.45),(.70,.58)]],
    2: [[(.24,.06),(.24,.90),(.72,.08),(.72,.93)]],
    3: [[(.26,.04),(.26,.96)],[(.26,.20),(.76,.50),(.26,.78)]],
    4: [[(.22,.96),(.22,.08),(.76,.34),(.22,.62)],[(.22,.43),(.73,.71)]],
    5: [[(.24,.95),(.24,.06),(.70,.06),(.78,.31),(.24,.50)],[(.24,.50),(.79,.96)]],
    6: [[(.77,.08),(.24,.51),(.77,.94)]],
    7: [[(.18,.08),(.82,.93)],[(.82,.08),(.18,.93)]],
    8: [[(.25,.95),(.25,.06),(.78,.27),(.25,.57)]],
    9: [[(.22,.05),(.22,.95)],[(.78,.05),(.78,.95)],[(.22,.67),(.78,.32)]],
}


def build_sprite(rank: int, player: int) -> tuple[Image.Image, dict]:
    path = SOURCE / f"north_rank_{rank:02d}_p{player}.png"
    original = Image.open(path).convert("RGBA")
    assert original.size == (128, 128)
    bbox = original.getbbox()
    assert bbox is not None
    left, top, right, bottom = bbox
    width, height = right-left, bottom-top
    # Engraving sits in the upper face. The lower portion is reserved for
    # the dynamic numeric label in the shared Godot reserve and board.
    glyph_w = width * 0.37
    glyph_h = height * 0.37
    cx = (left + right) / 2
    cy = top + height * 0.39
    x0, y0 = cx - glyph_w/2, cy - glyph_h/2
    s = UPSCALE
    base = original.resize((128*s,128*s), Image.Resampling.NEAREST)
    ink = Image.new("RGBA", base.size, (0,0,0,0))
    glow = Image.new("RGBA", base.size, (0,0,0,0))
    shadow = Image.new("RGBA", base.size, (0,0,0,0))
    d_ink, d_glow, d_shadow = ImageDraw.Draw(ink), ImageDraw.Draw(glow), ImageDraw.Draw(shadow)
    warm = player == 1
    core = (255, 198, 107, 235) if warm else (155, 225, 255, 235)
    halo = (247, 135, 52, 150) if warm else (65, 171, 255, 150)
    dark = (30, 17, 11, 215) if warm else (8, 30, 43, 215)
    stroke = max(1.3, min(width,height)*0.075)*s
    for path_unit in RUNES[rank]:
        pts = [(round((x0+x*glyph_w)*s),round((y0+y*glyph_h)*s)) for x,y in path_unit]
        pts_shadow = [(x+round(.8*s),y+round(1.0*s)) for x,y in pts]
        d_shadow.line(pts_shadow, fill=dark, width=round(stroke*1.6), joint="curve")
        d_glow.line(pts, fill=halo, width=round(stroke*2.4), joint="curve")
        d_ink.line(pts, fill=core, width=round(stroke), joint="curve")
        for x,y in pts:
            r=stroke/2
            d_ink.ellipse((x-r,y-r,x+r,y+r), fill=core)
    glow = glow.filter(ImageFilter.GaussianBlur(1.0*s))
    # Keep the engraving INSIDE the original stone alpha. Do not grow the
    # sprite silhouette, rank hit box, or transparent area around the stone.
    mask = base.getchannel("A")
    for layer in (shadow, glow, ink):
        layer.putalpha(ImageChops.darker(layer.getchannel('A'), mask))
        base = Image.alpha_composite(base, layer)
    base.putalpha(mask)
    result = base.resize((128,128), Image.Resampling.LANCZOS)
    # Exact original alpha is authoritative: prevent resampling halo pixels
    # outside the approved-source silhouette and retain monotonic rank size.
    result.putalpha(original.getchannel("A"))
    return result, {
        "rank":rank,"player":player,"rune_index":rank,
        "original_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "original_bbox":list(bbox),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries=[]
    for player in (1,2):
        for rank in range(1,10):
            im,meta=build_sprite(rank,player)
            dest=OUTPUT/f"north_runed_rank_{rank:02d}_p{player}.png"
            im.save(dest, optimize=False)
            meta.update(file=dest.name,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
            entries.append(meta)
    (OUTPUT/'asset_manifest.json').write_text(json.dumps({
        'source':'a5_northern_ranked (immutable approved-source derivatives)',
        'method':'deterministic Elder Futhark upper-face etch; dynamic numeric rank remains Godot UI',
        'assets':entries},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('NORTHERN_RUNED_ASSETS_PASS',len(entries))

if __name__=='__main__':main()
