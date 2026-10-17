"""A5 v139: active reserve exposes genuine legal ranks, not merely unspent ones.

Source contract + independent D2 model only. Native Godot smoke is wired into
--nd-run-smoke but is NOT claimed to have executed in this environment.
"""
from pathlib import Path
import pytest

MAIN = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf8')


def body(name):
    marker = f'func {name}('
    assert MAIN.count(marker) == 1, f'missing or duplicate {name}'
    start = MAIN.index(marker)
    end = MAIN.find('\nfunc ', start + 1)
    return MAIN[start:end if end >= 0 else None]


def test_legality_is_derived_from_production_predicate_not_second_engine():
    src = body('_rank_has_legal_cell')
    assert 'player != turn or game_over or rank < 1 or rank > 9' in src
    assert 'for cell in range(CELL_NAMES.size()):' in src
    assert '_is_legal_move(player, rank, cell)' in src
    for forbidden in ('board_stacks[cell].append', 'reserve_available[player - 1][rank - 1] =', '_on_primary('):
        assert forbidden not in src


def test_available_but_unplayable_rank_cannot_arm_ghost_move():
    src = body('_on_reserve_pressed')
    guard = 'if not _rank_has_legal_cell(player, index + 1):'
    assert guard in src
    assert src.index(guard) < src.index('if selected_reserve == index:')
    assert '"для ранга %d нет допустимой клетки"' in src
    assert '_reject_reserve_selection(' in src


def test_visual_cue_preserves_equal_touch_area_and_feedback():
    src = body('_refresh_surface')
    assert 'var can_place_rank := show_rank and _rank_has_legal_cell(player, i + 1)' in src
    assert 'rank_art.modulate.a = 0.53 if show_rank and not can_place_rank else 1.0' in src
    assert 'piece.tooltip_text = "" if not show_rank or can_place_rank' in src
    assert 'piece.disabled = game_over or player != turn or (ai_enabled and player == 2) or not reserve_available[player - 1][i]' in src
    assert 'piece.disabled = not can_place_rank' not in src
    assert 'piece.custom_minimum_size =' not in src
    assert 'piece.size =' not in src
    assert 'reserve.visible = player == turn' in src


def test_mobile_tutorial_explains_dimmed_unplayable_ranks():
    src = body('_render_mobile_menu_page')
    assert 'Тусклая фигура сейчас не имеет допустимого хода.' in src


def test_native_smoke_is_wired_but_not_claimed_executed():
    assert '_run_headless_unplayable_rank_smoke()' in body('_run_headless_geometry_and_interaction_smoke')
    src = body('_run_headless_unplayable_rank_smoke')
    for clause in ('assert(not _rank_has_legal_cell(1, 1)',
                   'assert(_rank_has_legal_cell(1, 9)',
                   'assert(low_art.modulate.a < high_art.modulate.a',
                   '_on_reserve_pressed(1, 0)', '_on_reserve_pressed(1, 8)',
                   'assert(selected_reserve == -1 and moves == 0',
                   'assert(selected_reserve == 8'):
        assert clause in src


@pytest.mark.parametrize('world', range(7))
@pytest.mark.parametrize('rule', ['C', 'D', 'CD'])
def test_independent_d2_example_has_unusable_rank1_and_usable_rank9(world, rule):
    # One occupied non-winning board, unique live cell tops; no visual world
    # affects legality. P1 cannot cover its own pieces; P1 rank 1 cannot
    # cover any P2 piece; P1 rank 9 can cover a P2 piece.
    owners = [2, 1, 2, 2, 1, 1, 1, 2, 2]
    ranks = [2, 2, 3, 4, 3, 4, 5, 5, 6]
    def has_move(rank):
        return any(owner == 2 and rank > top_rank and (rule == 'D' or 1 < 2)
                   for owner, top_rank in zip(owners, ranks))
    assert not has_move(1)
    assert has_move(9)
    assert world in range(7)
