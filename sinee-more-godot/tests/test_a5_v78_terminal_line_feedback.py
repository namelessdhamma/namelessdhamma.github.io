"""Seven-world terminal line regression for integrated Godot source.

Static/asset-level verification ONLY; engine-side fixture in main.gd must be
run with Godot to qualify native behavior. Not a phone or visual parity PASS.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
VISUALS = (ROOT / 'scripts/world_visuals.gd').read_text()
GEOMETRY = (ROOT / 'scripts/perspective_board_geometry.gd').read_text()


def _body(start, end):
    return MAIN.split(f'func {start}', 1)[1].split(f'func {end}', 1)[0]


def test_terminal_highlight_is_live_win_line_not_static_reference():
    section = _body('_refresh_selection_feedback()', '_modal_blocks_board_input()')
    assert 'if game_over:' in section
    assert 'winner != 0 and win_line.has(i)' in section
    assert 'Color("#ffda73")' in section
    assert 'outline.width = maxf(3.5, 4.0 / _physical_pixel_scale())' in section
    assert section.index('if game_over:') < section.index('var legal :=')
    assert 'continue' in section
    assert 'perspective_legal_outlines[i].visible = legal or chosen_cell' in section
    assert 'outline.width = maxf(2.0, 2.5 / _physical_pixel_scale())' in section


def test_win_line_is_computed_by_production_rules_and_resets_cleanly():
    primary = _body('_on_primary()', '_on_secondary()')
    assert 'win_line = _winning_line(moving_player)' in primary
    assert 'game_over = true' in primary
    assert '_refresh_surface()' in primary
    reset = _body('_reset_round()', '_on_menu()')
    assert 'win_line = []' in reset
    assert '_refresh_surface()' in reset
    surface = _body('_refresh_surface()', '_update_status(')
    assert '_refresh_perspective_layer()' in surface
    assert '_refresh_selection_feedback()' in surface


def test_seven_world_native_smoke_covers_win_draw_world_switch_and_reset():
    smoke = _body('_run_headless_terminal_line_smoke()', '_run_headless_reserve_invalid_guard_smoke()')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'win_line = _winning_line(1)' in smoke
    assert 'assert(win_line == [3,4,5]' in smoke
    assert 'outline.visible == win_line.has(cell)' in smoke
    assert 'winner = 0' in smoke and 'round_draw = true' in smoke
    assert 'Draw cannot display a winning line' in smoke
    assert 'New round must clear terminal outlines' in smoke
    assert '_set_world((world + 1) % WorldVisuals.WORLDS.size())' in smoke
    assert '_run_headless_terminal_line_smoke()' in _body('_run_headless_geometry_and_interaction_smoke()', '_run_headless_full_match_smoke()')
    full = _body('_run_headless_full_match_smoke()', '_run_headless_match_hud_smoke()')
    assert 'winner != 0 and win_line.has(cell)' in full
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in full
    assert 'for mode in ["C", "D", "CD"]:' in full


def test_7_exact_approved_reference_pngs_unmodified():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    assert len(manifest['images']) == 7
    expected = {
        'nd_premium_void': 'a5_void_ranked/01_nd_premium_void_canon_source.png',
        'pirate_sea': 'a5_pirate_ranked/02_pirate_sea_canon_source.png',
        'atlantis': 'a5_atlantis_ranked/03_atlantis_canon_source.png',
        'gods_of_the_deep': 'a5_gods_ranked/04_gods_of_the_deep_canon_source.png',
        'sand_sea': 'a5_sand_ranked/05_sand_sea_canon_source.png',
        'night_sea': 'a5_night_ranked/06_night_sea_canon_source.png',
        'northern_sea': 'a5_northern_ranked/07_northern_sea_canon_source.png',
    }
    assert set(expected) == {item['world'] for item in manifest['images']}
    for item in manifest['images']:
        path = ROOT / 'assets' / expected[item['world']]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']


def test_unchanged_shared_board_layers_and_rules():
    assert 'var perspective_legal_outlines: Array[Line2D] = []' in MAIN
    assert 'outline.z_index = 4' in MAIN
    assert 'outline.mouse_filter' not in MAIN  # Line2D cannot intercept taps.
    assert 'PerspectiveGeometry.cell_at_touch(' in MAIN
    assert 'world_visuals.piece_texture(current_world,' in MAIN
    assert 'const LINES: Array[Array]' in MAIN
    assert 'PirateOpeningCampaign' in (ROOT / 'project.godot').read_text()
    assert 'func cell_quad(' in GEOMETRY
    assert 'func piece_texture(' in VISUALS
