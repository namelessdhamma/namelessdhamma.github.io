"""v144: exact-source rank badge layout for all seven playable worlds.

Pure math and source contract only. Native smoke is registered but unexecuted.
"""
from pathlib import Path
import math

MAIN = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    start = MAIN.index('func ' + name + '(')
    end = MAIN.find('\nfunc ', start + 1)
    return MAIN[start:end if end >= 0 else None]


def source_band(world, rank):
    if world == 1: return (0.0, 0.48)
    if world == 2:
        center = .70 - .049 * (rank - 1)
        return center - .15, center + .15
    if world == 3: return (.59, 1.0)
    if world == 4:
        center = .68 - .047 * (rank - 1)
        return center - .14, center + .14
    if world == 5:
        center = .803 - .0063 * (rank - 1)
        return center - .13, center + .13
    if world == 6: return (.68, 1.0)
    return (0., 1.)


def fitted(world, rank, button_height, font_px):
    start, end = source_band(world, rank)
    h = max(1., button_height)
    needed = min(1., 1.25 * font_px / h)
    height = max(end - start, needed)
    center = (start + end) / 2
    top = max(0., min(1. - height, center - height / 2))
    return top, top + height


def test_reference_medallions_are_shorter_than_live_font_before_repair():
    for world in (2, 4, 5):
        for rank in range(1, 10):
            start, end = source_band(world, rank)
            assert (end - start) * 44 < 16 * 1.25


def test_all_worlds_ranks_and_densities_fit_numbers_inside_their_own_button():
    # 7 worlds * 9 ranks * 2 physical profiles * 2 font sizes = 252 cases.
    for world in range(7):
        for rank in range(1, 10):
            for height, font in ((44, 16), (88, 28), (132, 42), (44, 22)):
                top, bottom = fitted(world, rank, height, font)
                assert -1e-8 <= top < bottom <= 1 + 1e-8
                assert (bottom - top) * height + 1e-6 >= min(height, 1.25 * font)


def test_badge_centers_are_preserved_when_not_near_a_button_edge():
    for world in range(7):
        for rank in range(1, 10):
            start, end = source_band(world, rank)
            center = (start + end) / 2
            top, bottom = fitted(world, rank, 88, 28)
            # Only legitimate edge clamping can move the center.
            if (bottom - top) / 2 <= min(center, 1 - center):
                assert math.isclose((top + bottom) / 2, center, abs_tol=1e-7)


def test_fit_restarts_from_canonical_band_after_any_density_change():
    for world in range(7):
        for rank in range(1, 10):
            initial = fitted(world, rank, 44, 22)
            restored = fitted(world, rank, 44, 16)
            assert restored == fitted(world, rank, 44, 16)
            assert initial[1] - initial[0] >= restored[1] - restored[0] - 1e-7


def test_live_fit_is_wired_into_new_badges_and_dpr_refresh_without_gameplay_changes():
    fit = body('_fit_reserve_rank_label')
    assert 'var source_band := _reserve_rank_label_band(rank)' in fit
    assert 'number.anchor_top = top_fraction' in fit
    assert 'number.anchor_bottom = top_fraction + height_fraction' in fit
    assert '1.25 * float(font_px) / button_height' in fit
    assert '_fit_reserve_rank_label(button, number, rank, _live_rank_font_px())' in body('_set_piece_badge')
    refresh = body('_sync_live_reserve_rank_typography')
    assert '_fit_reserve_rank_label(reserve_button, number, reserve_button.get_index() + 1, font_px)' in refresh
    refresh_code = '\n'.join(line for line in refresh.splitlines() if not line.lstrip().startswith('#'))
    fit_code = '\n'.join(line for line in fit.splitlines() if not line.lstrip().startswith('#'))
    for forbidden in ('_refresh_surface(', '_on_primary(', '_save_match(', 'scroll_horizontal =', 'board_stacks ='):
        assert forbidden not in refresh_code
        assert forbidden not in fit_code


def test_native_smoke_checks_126_reserve_labels_and_preserves_match_state():
    smoke = body('_run_headless_live_rank_dpi_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'for player in [1, 2]:' in smoke
    assert 'readable_height + 0.01 >= minf(piece_height, float(expected_font) * 1.25)' in smoke
    assert 'assert(_match_snapshot() == before' in smoke
