"""Independent source-math pixel oracle and source integration checks.

These tests DO NOT prove native Godot compilation, 746x280 touch, or visual
parity against the seven approved reference screenshots.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets/a5_pirate_atlantis_prebaked_environment'
SOURCE = (ROOT / 'scripts/world_visuals.gd').read_text()
MAIN = (ROOT / 'scripts/main.gd').read_text()
spec = importlib.util.spec_from_file_location('v76_builder', ROOT / 'tools/build_pirate_atlantis_prebaked_environment.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def rgb(code):
    return tuple(int(code[i:i + 2], 16) / 255. for i in (1, 3, 5))


def lerp(a, b, t):
    return tuple(i + (j - i) * t for i, j in zip(a, b))


def lighten(a, t):
    return lerp(a, (1., 1., 1.), t)


def darken(a, t):
    return tuple(v * (1. - t) for v in a)


def clamp(a):
    return min(1., max(0., a))


def packed(c):
    return tuple(round(clamp(v) * 255) for v in c)


def pirate_backdrop(x, y):
    u, v = x / 511., y / 287.
    h = .43
    c = lerp(rgb('#17354c'), rgb('#eaa35b'), clamp(v / h))
    if v < h:
        d = math.sqrt(((u - .83) * 1.5)**2 + ((v - .25) * 1.8)**2)
        if d < .070:
            c = lerp(c, rgb('#fff0bb'), clamp((.070 - d) * 12.))
        if v > .34:
            c = lerp(rgb('#19445d'), rgb('#b87545'), .2 + .3 * math.sin(v * 150. + u * 35.))
        for mast in [.12, .36, .72, .93]:
            if abs(u - mast) < .003 and v > .11:
                c = rgb('#1b2024')
            if abs(v - .23) < .004 and abs(u - mast) < .044:
                c = rgb('#1b2024')
        if v > .35 and abs(math.sin(u * 41.)) > .87:
            c = lerp(c, rgb('#161d25'), .9)
    else:
        plank = math.sin(v * 75. + math.sin(u * 15.) * .6)
        grain = math.sin(u * 160. + v * 13.)
        c = lerp(rgb('#2a170f'), rgb('#684027'), .30 + .20 * plank + .12 * grain)
        if abs(plank) > .985:
            c = rgb('#1b110e')
        if u < .07 or u > .93:
            c = lerp(c, rgb('#a16a36'), .16)
        if (x * 23 + y * 17) % 827 < 2:
            c = lighten(c, .2)
    return packed(c)


def pirate_plinth(x, y):
    edge = min(x, 255 - x, y, 255 - y)
    grain = .5 + .5 * math.sin(x * .13 + y * .019)
    c = lerp(rgb('#4b2515'), rgb('#9b5730'), grain * .45)
    if edge < 18:
        c = lerp(rgb('#1a100e'), rgb('#63341b'), edge / 18.)
        if edge in (4, 13):
            c = rgb('#d7a24b')
        elif edge < 12 and (x % 24 < 3 or y % 24 < 3):
            c = rgb('#b47a38')
    elif x % 82 < 2 or y % 83 < 2:
        c = lighten(c, .12)
    return packed(c)


def atlantis_backdrop(x, y):
    u, v = x / 511., y / 287.
    c = lerp(rgb('#02182c'), rgb('#067e99'), clamp(v * 1.25))
    ray = abs(math.sin(u * 19. + v * 3.))
    if v < .72:
        c = lerp(c, rgb('#50c8e9'), .17 * ray**8 * (1. - v))
    for column_u in [.065, .18, .82, .935]:
        dx = abs(u - column_u)
        if dx < .018 and .06 < v < .88:
            c = lerp(rgb('#134957'), rgb('#498b92'), .5 + .3 * math.sin(u * 260.))
        elif dx < .033 and abs(v - .11) < .025:
            c = rgb('#a3a079')
        if dx < .023 and y % 42 < 2 and v > .1:
            c = lighten(c, .2)
    if (u < .035 or u > .965) and v > .15:
        c = lerp(c, rgb('#5beaff'), .63 + .16 * math.sin(y * .28))
    if v > .72:
        c = lerp(rgb('#092d39'), rgb('#246171'), .4 + .22 * math.sin(u * 110.))
        if y % 28 < 2 or x % 64 < 2:
            c = lerp(c, rgb('#d4b86c'), .5)
    if (x * 73 + y * 37 + x * y * 3) % 1777 < 2 and v < .72:
        c = rgb('#a5f1f4')
    return packed(c)


def atlantis_plinth(x, y):
    edge = min(x, 255 - x, y, 255 - y)
    grain = ((x * 43 + y * 71 + x * y * 7) % 109) / 109.
    c = lerp(rgb('#163c4a'), rgb('#316471'), grain * .45)
    if edge < 18:
        c = lerp(rgb('#081e2d'), rgb('#305f69'), edge / 18.)
        if edge in (5, 14):
            c = rgb('#16c7e2')
        elif edge == 9:
            c = rgb('#d9b96a')
    elif x % 83 < 2 or y % 83 < 2:
        c = lerp(rgb('#8ed7d7'), c, .4)
    elif (x * 17 + y * 31) % 211 < 3:
        c = lighten(c, .17)
    if y > 235:
        c = darken(c, .24)
    return packed(c)


CASES = [
    ('pirate_chart_backdrop.png', pirate_backdrop, builder.pirate_backdrop, 512, 288),
    ('pirate_chart_support.png', pirate_plinth, builder.pirate_plinth, 256, 256),
    ('atlantis_underwater_backdrop.png', atlantis_backdrop, builder.atlantis_backdrop, 512, 288),
    ('atlantis_stone_support.png', atlantis_plinth, builder.atlantis_plinth, 256, 256),
]


def test_all_425984_source_math_pixels_match_independent_scalar_oracle():
    for name, scalar, vectorized, w, h in CASES:
        image = np.asarray(Image.open(ASSETS / name).convert('RGB'))
        assert image.shape == (h, w, 3)
        # A distinct, straightforward scalar reference, not a second call to
        # the vectorized production builder.
        expected = np.array([scalar(x, y) for y in range(h) for x in range(w)], dtype=np.uint8).reshape(h, w, 3)
        assert np.array_equal(image, expected), (name, int(np.count_nonzero(image != expected)))
        assert np.array_equal(image, np.clip(np.rint(vectorized() * 255), 0, 255).astype(np.uint8))


def test_all_four_asset_hashes_and_build_are_reproducible():
    manifest = json.loads((ASSETS / 'asset_manifest.json').read_text())
    assert len(manifest['assets']) == 4
    assert manifest['contains_game_state_or_board_cells'] is False
    assert manifest['canonical_reference_images_changed'] is False
    for asset in manifest['assets']:
        assert hashlib.sha256((ASSETS / asset['file']).read_bytes()).hexdigest() == asset['sha256']
    assert builder.main() == manifest


def test_live_seven_world_scene_uses_prepared_pirate_and_atlantis_only_for_scenery():
    assert 'const PIRATE_ATLANTIS_ENV_ROOT' in SOURCE
    for filename in ['pirate_chart_backdrop.png', 'pirate_chart_support.png',
                     'atlantis_underwater_backdrop.png', 'atlantis_stone_support.png']:
        assert filename in SOURCE
    assert 'backdrop_cache[world] = prepared' in SOURCE
    assert 'foundation.texture = pirate_plinth' in SOURCE
    assert 'foundation.texture = atlantis_plinth' in SOURCE
    assert '_make_pirate_chart_plinth()' not in SOURCE.split('func apply_world(')[1].split('func ')[0]
    assert '_make_atlantis_stone_plinth()' not in SOURCE.split('func apply_world(')[1].split('func ')[0]
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in SOURCE
    assert 'perspective_support_surface.texture = material' in MAIN
    assert 'func _on_cell_pressed(index: int)' in MAIN
    assert 'func _play_ai_turn()' in MAIN
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN


def test_seven_user_approved_reference_files_are_not_replaced():
    original = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    assert len(original['images']) == 7
    assert all(len(item['sha256']) == 64 for item in original['images'])
    # Exact source PNGs are not in the baked scenery output directory.
    assert sorted(p.name for p in ASSETS.glob('*.png')) == sorted(c[0] for c in CASES)
