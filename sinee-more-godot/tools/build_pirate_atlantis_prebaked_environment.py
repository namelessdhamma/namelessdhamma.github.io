"""Deterministic Pirate/Atlantis scenery-only and supported-table materials.

Precompute the four unchanged world_visuals.gd RGB8 formulas. No board cells,
reserve, rank, logo, state, or user-approved reference screenshot is baked.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/a5_pirate_atlantis_prebaked_environment'


def rgb(value):
    return np.array([int(value[i:i + 2], 16) / 255. for i in (1, 3, 5)], dtype=np.float64)


def mix(a, b, amount):
    t = np.asarray(amount)
    return a + (b - a) * t[..., None]


def where(mask, yes, no):
    return np.where(mask[..., None], yes, no)


def light(c, amount):
    return mix(c, np.ones(3), amount)


def dark(c, amount):
    return c * (1. - np.asarray(amount)[..., None])


def grid(w, h):
    x, y = np.meshgrid(np.arange(w, dtype=np.int32), np.arange(h, dtype=np.int32))
    return x, y, x / float(w - 1), y / float(h - 1)


def pirate_backdrop():
    x, y, u, v = grid(512, 288)
    horizon = .43
    sky = v < horizon
    c = mix(rgb('#17354c'), rgb('#eaa35b'), np.clip(v / horizon, 0., 1.))
    sun_dist = np.sqrt(((u - .83) * 1.5)**2 + ((v - .25) * 1.8)**2)
    c = where(sky & (sun_dist < .070), mix(c, rgb('#fff0bb'), np.clip((.070 - sun_dist) * 12., 0., 1.)), c)
    c = where(sky & (v > .34), mix(rgb('#19445d'), rgb('#b87545'), .2 + .3 * np.sin(v * 150. + u * 35.)), c)
    for mast in [.12, .36, .72, .93]:
        c = where(sky & (np.abs(u - mast) < .003) & (v > .11), rgb('#1b2024'), c)
        c = where(sky & (np.abs(v - .23) < .004) & (np.abs(u - mast) < .044), rgb('#1b2024'), c)
    c = where(sky & (v > .35) & (np.abs(np.sin(u * 41.)) > .87), mix(c, rgb('#161d25'), .9), c)
    plank = np.sin(v * 75. + np.sin(u * 15.) * .6)
    grain = np.sin(u * 160. + v * 13.)
    sea = mix(rgb('#2a170f'), rgb('#684027'), .30 + .20 * plank + .12 * grain)
    sea = where(np.abs(plank) > .985, rgb('#1b110e'), sea)
    sea = where((u < .07) | (u > .93), mix(sea, rgb('#a16a36'), .16), sea)
    sea = where(((x * 23 + y * 17) % 827) < 2, light(sea, .2), sea)
    return where(sky, c, sea)


def pirate_plinth():
    x, y, _, _ = grid(256, 256)
    edge = np.minimum.reduce([x, 255 - x, y, 255 - y])
    grain = .5 + .5 * np.sin(x * .13 + y * .019)
    c = mix(rgb('#4b2515'), rgb('#9b5730'), grain * .45)
    border = edge < 18
    b = mix(rgb('#1a100e'), rgb('#63341b'), edge / 18.)
    b = where((edge == 4) | (edge == 13), rgb('#d7a24b'), b)
    b = where((edge != 4) & (edge != 13) & (edge < 12) & ((x % 24 < 3) | (y % 24 < 3)), rgb('#b47a38'), b)
    c = where(border, b, c)
    c = where(~border & ((x % 82 < 2) | (y % 83 < 2)), light(c, .12), c)
    return c


def atlantis_backdrop():
    x, y, u, v = grid(512, 288)
    c = mix(rgb('#02182c'), rgb('#067e99'), np.clip(v * 1.25, 0., 1.))
    ray = np.abs(np.sin(u * 19. + v * 3.))
    c = where(v < .72, mix(c, rgb('#50c8e9'), .17 * ray**8 * (1. - v)), c)
    for column_u in [.065, .18, .82, .935]:
        dx = np.abs(u - column_u)
        mask = (dx < .018) & (v > .06) & (v < .88)
        column = mix(rgb('#134957'), rgb('#498b92'), .5 + .3 * np.sin(u * 260.))
        c = where(mask, column, c)
        c = where(~mask & (dx < .033) & (np.abs(v - .11) < .025), rgb('#a3a079'), c)
        c = where((dx < .023) & (y % 42 < 2) & (v > .1), light(c, .2), c)
    c = where(((u < .035) | (u > .965)) & (v > .15), mix(c, rgb('#5beaff'), .63 + .16 * np.sin(y * .28)), c)
    ground = mix(rgb('#092d39'), rgb('#246171'), .4 + .22 * np.sin(u * 110.))
    ground = where((y % 28 < 2) | (x % 64 < 2), mix(ground, rgb('#d4b86c'), .5), ground)
    c = where(v > .72, ground, c)
    c = where(((x * 73 + y * 37 + x * y * 3) % 1777 < 2) & (v < .72), rgb('#a5f1f4'), c)
    return c


def atlantis_plinth():
    x, y, _, _ = grid(256, 256)
    edge = np.minimum.reduce([x, 255 - x, y, 255 - y])
    grain = ((x * 43 + y * 71 + x * y * 7) % 109) / 109.
    c = mix(rgb('#163c4a'), rgb('#316471'), grain * .45)
    border = edge < 18
    b = mix(rgb('#081e2d'), rgb('#305f69'), edge / 18.)
    b = where((edge == 5) | (edge == 14), rgb('#16c7e2'), b)
    b = where(edge == 9, rgb('#d9b96a'), b)
    c = where(border, b, c)
    seam = ~border & ((x % 83 < 2) | (y % 83 < 2))
    c = where(seam, mix(rgb('#8ed7d7'), c, .4), c)
    fleck = ~border & ~seam & (((x * 17 + y * 31) % 211) < 3)
    c = where(fleck, light(c, .17), c)
    c = where(y > 235, dark(c, .24), c)
    return c


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assets = []
    for name, values in [
        ('pirate_chart_backdrop.png', pirate_backdrop()),
        ('pirate_chart_support.png', pirate_plinth()),
        ('atlantis_underwater_backdrop.png', atlantis_backdrop()),
        ('atlantis_stone_support.png', atlantis_plinth()),
    ]:
        p = OUT / name
        Image.fromarray(np.clip(np.rint(values * 255.), 0, 255).astype(np.uint8), 'RGB').save(p, optimize=True)
        assets.append({'file': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': list(Image.open(p).size)})
    manifest = {
        'generator': 'tools/build_pirate_atlantis_prebaked_environment.py',
        'kind': 'original_scenery_and_physical_support_ONLY',
        'contains_game_state_or_board_cells': False,
        'canonical_reference_images_changed': False,
        'source_math': 'scripts/world_visuals.gd Pirate/Atlantis RGB8 formulas',
        'assets': assets,
    }
    (OUT / 'asset_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
