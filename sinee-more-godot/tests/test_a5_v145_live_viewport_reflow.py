"""A5 v145: live phone viewport/profile changes must reflow UI at constant DPR.

Offline source-contract + independent geometry oracle. Native Godot and real-phone
acceptance remain explicitly unexecuted.
"""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    start = MAIN.index('func ' + name + '(')
    end = MAIN.find('\nfunc ', start + 1)
    return MAIN[start:end if end >= 0 else None]


def source_band(world, rank):
    if world == 1:
        return 0., .48
    if world == 2:
        c = .70 - .049 * (rank - 1)
        return c - .15, c + .15
    if world == 3:
        return .59, 1.
    if world == 4:
        c = .68 - .047 * (rank - 1)
        return c - .14, c + .14
    if world == 5:
        c = .803 - .0063 * (rank - 1)
        return c - .13, c + .13
    if world == 6:
        return .68, 1.
    return 0., 1.


def fit_band(world, rank, height, font):
    start, end = source_band(world, rank)
    needed = min(1., 1.25 * font / height)
    band_height = max(end - start, needed)
    center = (start + end) / 2
    top = min(1. - band_height, max(0., center - band_height / 2))
    return top, top + band_height


def test_reproduces_pre_v145_same_dpr_shrink_clipping():
    # Old fit at 88px looked valid. A later browser/rotation resize to 44px
    # without DPR/font change retained anchors and clipped the live number.
    for world in (2, 4, 5):
        for rank in range(1, 10):
            old = fit_band(world, rank, 88., 16.)
            assert (old[1] - old[0]) * 88. >= 20.
            assert (old[1] - old[0]) * 44. < 20.
            new = fit_band(world, rank, 44., 16.)
            assert (new[1] - new[0]) * 44. >= 20. - 1e-7


def test_viewport_and_phone_profile_are_independent_layout_cache_keys():
    src = body('_ensure_physical_touch_targets')
    assert 'var viewport_size := get_viewport_rect().size' in src
    assert 'var phone_profile := _use_mobile_menu()' in src
    assert 'viewport_size != _last_touch_viewport_size' in src
    assert 'phone_profile != _last_touch_mobile_profile' in src
    assert 'if not geometry_changed and absf(scale - _last_touch_scale)' in src
    assert '_last_touch_viewport_size = viewport_size' in src
    assert '_last_touch_mobile_profile = phone_profile' in src
    # A resize with the SAME DPR/density still invalidates cached HUD geometry.
    def refresh(old_size, new_size, old_phone, new_phone, scale=1., density=1.):
        return (old_size != new_size or old_phone != new_phone
                or not math.isclose(scale, 1.) or not math.isclose(density, 1.))
    assert refresh((844, 390), (746, 280), True, True)
    assert refresh((844, 390), (844, 390), False, True)
    assert not refresh((844, 390), (844, 390), True, True)


def test_deferred_refit_uses_settled_geometry_and_stale_resize_guard():
    caller = body('_ensure_physical_touch_targets')
    assert 'call_deferred("_refit_live_reserve_badges_after_layout", viewport_size, current_world)' in caller
    src = body('_refit_live_reserve_badges_after_layout')
    assert 'await get_tree().process_frame' in src
    assert 'get_viewport_rect().size != expected_size or current_world != expected_world' in src
    assert '_fit_reserve_rank_label(button, number, button.get_index() + 1, font_px)' in src
    assert 'number != null and number.visible' in src
    for forbidden in ('_save_match(', '_on_primary(', '_refresh_surface(', '_reset_round(',
                      'board_stacks =', 'scroll_horizontal =', 'ResourceLoader.load(',
                      'world_visuals.apply_world(', '_queue_ai_turn_if_ready('):
        assert forbidden not in src


def test_all_worlds_preserve_readable_rank_bounds_after_same_dpr_resize():
    # Seven worlds * nine ranks * four 44/88/132/56px profiles.
    for world in range(7):
        for rank in range(1, 10):
            for height in (44., 56., 88., 132.):
                top, bottom = fit_band(world, rank, height, 16.)
                assert 0. <= top < bottom <= 1.
                assert (bottom - top) * height + 1e-7 >= min(height, 20.)


def test_source_preserves_canon_and_live_gameplay_during_reflow():
    src = body('_refit_live_reserve_badges_after_layout')
    assert 'for player in [1, 2]:' in src
    assert 'var reserve := _reserve_node(player)' in src
    assert 'var font_px := _live_rank_font_px()' in src
    assert 'number := button.get_node_or_null("RankNumber") as Label' in src
    assert 'number.visible' in src
    assert 'number.anchor_top' not in src  # Canonical anchor logic is centralized.
    assert 'func _fit_reserve_rank_label(' in MAIN
    assert 'func _on_primary()' in MAIN
    assert 'func _run_headless_full_match_smoke()' in MAIN
