"""Source/asset checks for live Night Sea beacon light; NOT native rendering."""
from pathlib import Path
import hashlib
import json
import re
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
CANON = ROOT / 'assets/a5_night_ranked/06_night_sea_canon_source.png'
MANIFEST = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())


def test_approved_night_art_immutable():
    assert hashlib.sha256(CANON.read_bytes()).hexdigest() == 'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'
    assert Image.open(CANON).size == (1672, 941)


def test_reference_has_distinct_warm_cool_beacon_light():
    # Sample the reference's central orange and left blue beacon pools,
    # avoiding baked numerals/toolbar. No art is edited by this test.
    im = Image.open(CANON).convert('RGB')
    def avg(box):
        crop = im.crop(box)
        values = list(crop.getdata())
        return tuple(sum(px[i] for px in values) / len(values) for i in range(3))
    # Warm center lantern vs blue left lantern (coordinates in original PNG).
    warm = avg((813, 420, 850, 449))
    cool = avg((490, 450, 530, 485))
    assert warm[0] > warm[2] * 1.12, (warm, cool)
    assert cool[2] > cool[0] * 1.12, (warm, cool)


def test_exactly_nine_shared_live_ring_pairs_and_one_preview_pair():
    assert 'var perspective_night_beacon_blooms: Array[Line2D]' in MAIN
    assert 'var perspective_night_beacon_rims: Array[Line2D]' in MAIN
    assert MAIN.count('perspective_night_beacon_blooms.append(bloom)') == 1
    assert MAIN.count('perspective_night_beacon_rims.append(rim)') == 1
    assert 'for i in range(9):' in MAIN
    assert 'HeldNightBeaconBloom' in MAIN and 'HeldNightBeaconRim' in MAIN
    assert MAIN.count('_update_night_beacon_ring(') == 3  # definition, board, preview


def test_live_occupancy_only_and_non_night_cleanup():
    helper = MAIN.split('func _update_night_beacon_ring(', 1)[1].split('\nfunc _refresh_perspective_layer', 1)[0]
    assert 'world == 5 and rank >= 1 and rank <= 9' in helper
    assert 'bloom.visible = show' in helper and 'rim.visible = show' in helper
    assert 'bloom.clear_points()' in helper and 'rim.clear_points()' in helper
    assert 'PieceGrounding.bottom_fraction(world, rank)' in helper
    assert 'player == 1 else Color("#4cbcff")' in helper


def test_rank_growth_changes_light_contact_without_changing_hit_targets():
    for rank in range(1, 9):
        assert .28 + .015 * rank < .28 + .015 * (rank + 1)
    helper = MAIN.split('func _update_night_beacon_ring(', 1)[1].split('\nfunc _refresh_perspective_layer', 1)[0]
    assert 'radius_x := extent * (0.28 + 0.015 * rank)' in helper
    assert '_on_cell_pressed(' not in helper and '_is_legal_move(' not in helper
    assert 'Line2D.new()' in MAIN


def test_preview_uses_same_geometry_and_clears_on_release():
    assert '_update_night_beacon_ring(perspective_touch_preview_bloom,' in MAIN
    assert '_update_night_beacon_ring(perspective_night_beacon_blooms[i],' in MAIN
    section = MAIN.split('func _refresh_touch_preview()', 1)[1].split('func _refresh_selection_feedback()', 1)[0]
    assert 'perspective_touch_preview_bloom.clear_points()' in section
    assert 'perspective_touch_preview_rim.clear_points()' in section
    assert 'perspective_touch_preview_bloom.visible = true' not in section  # helper controls visibility


def test_21_native_full_matches_have_world_by_world_light_assertions():
    section = MAIN.split('func _run_headless_full_match_smoke()', 1)[1].split('func _run_headless_hud_notice_smoke()', 1)[0]
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in section
    assert 'for mode in ["C", "D", "CD"]:' in section
    assert 'light_expected := world == 5 and occupied' in section
    assert 'perspective_night_beacon_rims[light_cell].visible == light_expected' in section
    assert 'perspective_night_beacon_blooms[light_cell].visible == light_expected' in section
