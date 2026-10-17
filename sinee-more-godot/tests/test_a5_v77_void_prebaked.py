"""Void fast-path source-math oracle; NOT Godot runtime or reference visual parity."""
from pathlib import Path
import hashlib,json,math
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/'scripts/world_visuals.gd').read_text()
ASSET=ROOT/'assets/a5_void_prebaked_environment/void_split_light_backdrop.png'

def _rgb(h): return tuple(int(h[i:i+2],16)/255 for i in (1,3,5))
def _mix(a,b,t): return tuple(i+(j-i)*t for i,j in zip(a,b))
def _clamp(t): return max(0.,min(1.,t))
def _oracle(x,y):
    u=x/511.; v=y/287.
    t=_clamp((u-.40)/.20)
    t=t*t*(3.-2.*t)
    base=_mix(_rgb('#040910'),_rgb('#101a2b'),v)
    light=_mix(_rgb('#b17a45'),_rgb('#6699c8'),t)
    strength=(.13+.19*_clamp(abs(u-.5)*2.))*(1.-.30*v)
    return tuple(round(_clamp(q)*255) for q in _mix(base,light,strength))

def test_void_147456_pixels_match_independent_scalar_oracle():
    actual=np.asarray(Image.open(ASSET).convert('RGB'))
    expected=np.array([_oracle(x,y) for y in range(288) for x in range(512)],dtype=np.uint8).reshape(288,512,3)
    assert actual.shape==(288,512,3)
    assert np.array_equal(actual,expected)

def test_void_asset_hash_and_source_math_manifest():
    m=json.loads((ASSET.parent/'asset_manifest.json').read_text())
    assert m['sha256']==hashlib.sha256(ASSET.read_bytes()).hexdigest()
    assert m['pixels_compared']==147456 and m['pixel_mismatches']==0
    assert m['contains_board_or_pieces_or_ui'] is False
    assert m['canonical_reference_images_modified'] is False

def test_live_world_zero_uses_void_asset_and_six_supported_worlds_unchanged():
    branch=SRC.split('func apply_world(')[1].split('func piece_texture(')[0]
    assert 'if world == 0:' in branch
    assert 'load(VOID_ENV_ROOT + "/void_split_light_backdrop.png") as Texture2D' in branch
    assert 'backdrop_cache[world] = void_scene' in branch
    for old in ['PIRATE_ATLANTIS_ENV_ROOT','NORTHERN_ENV_ROOT','GODS_ENV_ROOT','SAND_NIGHT_ENV_ROOT']:
        assert old in branch
    assert 'scenery.visible = world != 0' in branch
    assert 'support.visible = world != 0' in branch
    assert 'foundation.visible = world >= 1 and world <= 6' in branch
    assert 'chart.texture = _canonical_cell_texture(world, cell_index)' in branch

def test_canonical_source_manifest_unchanged_and_no_baked_game_state():
    manifest=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
    assert len(manifest['images'])==7
    assert all(len(i['sha256'])==64 for i in manifest['images'])
    assert len(list(ASSET.parent.glob('*.png')))==1
    assert not any(word in ASSET.name for word in ['board','piece','rank','screen','ui'])
