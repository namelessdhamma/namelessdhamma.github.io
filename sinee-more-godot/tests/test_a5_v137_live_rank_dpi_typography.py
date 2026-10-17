"""v137 shared mobile rank-label refresh, offline checks only.

These checks do not execute Godot or certify physical touch/visual parity.
"""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    start = MAIN.index('func ' + name + '(')
    end = MAIN.find('\nfunc ', start + 1)
    return MAIN[start:end if end >= 0 else None]


def font(density, scale):
    return max(16, math.ceil(14.0 * density / scale))


def outline(density, scale):
    return max(4, math.ceil(3.0 * density / scale))


def test_live_font_and_outline_scale_together_and_never_drop_below_safe_minimum():
    assert 'maxi(16, ceili(14.0 * _native_touch_density() / _physical_pixel_scale()))' in body('_live_rank_font_px')
    assert 'maxi(4, ceili(3.0 * _native_touch_density() / _physical_pixel_scale()))' in body('_live_rank_outline_px')
    for density, scale in ((1, 1), (2, 2), (3, 3), (3, 1), (3, 1.5), (2, 0.8), (1, 2)):
        assert font(density, scale) >= 16
        assert outline(density, scale) >= 4
    assert font(3, 1) > font(3, 3)
    assert outline(3, 0.8) > outline(3, 3)


def test_existing_badges_are_refreshed_not_only_new_labels():
    b = body('_set_piece_badge')
    assert b.index('if number == null:') < b.index('number.add_theme_font_size_override("font_size", _live_rank_font_px())')
    assert b.index('if number == null:') < b.index('number.add_theme_constant_override("outline_size", _live_rank_outline_px())')
    assert 'number.visible = rank > 0' in b
    assert 'number.mouse_filter = Control.MOUSE_FILTER_IGNORE' in b


def test_dpr_change_updates_only_existing_labels_and_preserves_scroll_and_gameplay():
    b = body('_sync_live_reserve_rank_typography')
    assert 'if font_px == _last_reserve_rank_font_px and outline_px == _last_reserve_rank_outline_px:' in b
    assert 'for player in [1, 2]:' in b
    assert 'for piece in reserve.get_children():' in b
    assert 'get_node_or_null("RankNumber")' in b
    assert 'number.add_theme_font_size_override("font_size", font_px)' in b
    assert 'number.add_theme_constant_override("outline_size", outline_px)' in b
    live_lines = '\n'.join(line for line in b.splitlines() if not line.lstrip().startswith('#'))
    assert all(forbidden not in live_lines for forbidden in (
        '_refresh_surface(', '_set_world(', '_on_primary(', '_save_match(',
        'scroll_horizontal =', 'selected_reserve =', 'button.custom_minimum_size =',
        'piece.texture =', 'board_stacks =', 'reserve_available =',
    ))
    assert '_sync_live_reserve_rank_typography()' in body('_process')


def test_perspective_board_rank_labels_share_live_scaling():
    b = body('_refresh_perspective_layer')
    assert 'var logical_rank_font := maxi(16, ceili(14.0 * _last_perspective_density / _last_perspective_pixel_scale))' in b
    assert 'var logical_rank_outline := _live_rank_outline_px()' in b
    assert 'rank.add_theme_font_size_override("font_size", logical_rank_font)' in b
    assert 'rank.add_theme_constant_override("outline_size", logical_rank_outline)' in b
    assert 'icon.visible = not top.is_empty()' in b


def test_opt_in_native_smoke_covers_all_seven_and_does_not_spend_a_piece():
    b = body('_run_headless_live_rank_dpi_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in b
    assert 'for player in [1, 2]:' in b
    assert 'for label in perspective_ranks:' in b
    assert 'assert(_match_snapshot() == before' in b
    assert 'BLUE_SEA_LIVE_RANK_DPI_SMOKE_PASS worlds=7 labels=189' in b
    assert '_run_headless_live_rank_dpi_smoke()' in body('_run_headless_geometry_and_interaction_smoke')
