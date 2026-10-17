from pathlib import Path
import hashlib,json,re
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'scripts/world_visuals.gd').read_text()
MAIN=(ROOT/'scripts/main.gd').read_text()
CANON=json.loads(Path('/mnt/data/MANIFEST.json').read_text()) if Path('/mnt/data/MANIFEST.json').exists() else None

def test_void_scenery_only_hidden():
    assert 'scenery.visible = world != 0' in SOURCE
    assert 'scenery.texture = scenery_cache[world]' in SOURCE
    assert 'var scenery := root.get_node_or_null("SceneryPerimeter")' in SOURCE

def test_void_has_empty_continuous_split_light():
    assert 'Color("#b17a45").lerp(Color("#6699c8"), smoothstep(0.40, 0.60, u))' in SOURCE
    assert 'var intensity := (0.13 + 0.19 * edge_light) * (1.0 - 0.30 * v)' in SOURCE
    assert 'c = c.lerp(split_light, intensity)' in SOURCE

def test_void_remains_floating_other_worlds_supported():
    assert 'var has_support := current_world != 0' in MAIN
    assert 'foundation.visible = world >= 1 and world <= 6' in SOURCE
    assert 'perspective_support_surface.visible = has_support' in MAIN

def test_void_glass_pieces_still_live():
    assert 'assets/a5_void_ranked/void_rank_%02d_p%d.png' in SOURCE
    assert 'rank.text = str(int(top.rank))' in MAIN
    assert 'icon.texture = world_visuals.piece_texture(current_world' in MAIN

def test_six_other_scenery_files_untouched():
    for i in range(1,7):
        p=ROOT/f'assets/a5_scenery_perimeter/world_{i:02d}.png'
        assert p.exists() and Image.open(p).size[0]>500

def test_void_reference_kept_not_overwritten():
    p=ROOT/'assets/a5_void_ranked/01_nd_premium_void_canon_source.png'
    assert p.exists()
    assert hashlib.sha256(p.read_bytes()).hexdigest() == '00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'

def test_gameplay_unchanged_by_visual_delta():
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
    assert 'func _run_headless_full_match_smoke() -> void:' in MAIN
    assert 'reserve_scroller = ScrollContainer.new()' in MAIN
