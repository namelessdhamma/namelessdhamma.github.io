"""A5 v147: persistent selected rank on low-height phones and safe AI takeover.

Source and independent state-model regression only. Native Godot/real touch
remain separate, unpassed acceptance gates.
"""
from pathlib import Path
import re
import pytest

MAIN = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(rf'^(?:static )?func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^(?:static )?func |\Z)', MAIN, re.M | re.S)
    assert match, name
    return match.group(1)


def selected_line(base, selected, turn, mobile, terminal, ai):
    if not mobile or terminal or ai and turn == 2 or turn not in (1, 2) or not 0 <= selected <= 8:
        return base
    return f'P{turn} · №{selected + 1}'


def notice_line(base, notice, deadline, now, mobile, terminal):
    return notice if mobile and not terminal and notice and deadline > now else base


@pytest.mark.parametrize('selected', range(9))
@pytest.mark.parametrize('player', (1, 2))
def test_rank_persists_after_notice_expiry_even_if_reserve_scrolled(selected, player):
    rank = selected_line(f'ХОД P{player}', selected, player, True, False, False)
    assert rank == f'P{player} · №{selected + 1}'
    assert notice_line(rank, f'РАНГ {selected+1}', 1700, 1699, True, False) == f'РАНГ {selected+1}'
    assert notice_line(rank, f'РАНГ {selected+1}', 1700, 1700, True, False) == rank


@pytest.mark.parametrize('selected', (-1, 0, 4, 8, 9))
def test_ai_terminal_desktop_and_empty_selection_precedence(selected):
    assert selected_line('ХОД ИИ', selected, 2, True, False, True) == 'ХОД ИИ'
    assert selected_line('РАУНД P1', selected, 1, True, True, False) == 'РАУНД P1'
    assert selected_line('ХОД P1', selected, 1, False, False, False) == 'ХОД P1'
    if selected not in range(9):
        assert selected_line('ХОД P1', selected, 1, True, False, False) == 'ХОД P1'


def test_actual_live_hud_uses_rank_fallback_then_notice_then_storage_warning():
    selected = body('_hud_selected_rank_line')
    assert 'not mobile or terminal or ai_turn' in selected
    assert 'rank_index < 0 or rank_index > 8' in selected
    assert 'return "P%d · №%d" % [player, rank_index + 1]' in selected
    hud = body('_refresh_match_hud')
    assert hud.index('state = _hud_selected_rank_line(') < hud.index('state = _hud_secondary_line(')
    assert hud.index('state = _hud_secondary_line(') < hud.index('if _match_save_dirty:')
    assert 'match_hud_label.text = score + "\\n" + state' in hud
    assert 'selected_reserve, turn, mobile, game_over' in hud
    assert 'ai_enabled and turn == 2' in hud
    assert 'match_hud.tooltip_text' in hud


def test_takeover_clears_only_human_p2_pending_selection_and_keeps_ai_queue():
    toggle = body('_toggle_ai')
    assert 'if ai_enabled and turn == 2:' in toggle
    assert toggle.index('_cancel_pending_board_touch()') < toggle.index('selected_reserve = -1')
    assert toggle.index('selected_reserve = -1') < toggle.index('_refresh_surface()')
    assert '_queue_ai_turn_if_ready()' in toggle
    assert '_save_preferences()' in toggle
    assert 'board_stacks =' not in toggle
    assert 'reserve_available =' not in toggle


def test_actual_rank_clear_commit_undo_and_terminal_refresh_existing_hud():
    assert 'selected_reserve = -1' in body('_on_secondary')
    assert '_update_status("selection cleared")' in body('_on_secondary')
    assert 'selected_reserve = -1' in body('_on_primary')
    assert '_refresh_surface()' in body('_on_primary')
    assert '_refresh_surface()' in body('_undo_last_move')
    assert 'selected_reserve = -1' in body('_reset_round')
    assert '_refresh_match_hud()' in body('_refresh_surface')
    assert 'Time.get_ticks_msec() >= _hud_notice_deadline_msec' in body('_process')


def test_native_hud_smoke_covers_rank_expiry_and_priority_without_claiming_execution():
    smoke = body('_run_headless_hud_notice_smoke')
    assert '"P1 · №9"' in smoke
    assert '"ХОД ИИ"' in smoke
    assert '"РАУНД P1"' in smoke
    assert '"НЕЛЬЗЯ"' in smoke
    assert '_run_headless_hud_notice_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_hud_is_presentation_only_and_does_not_duplicate_gameplay_or_input():
    for fn in ('_hud_selected_rank_line', '_hud_secondary_line', '_refresh_match_hud'):
        fn_body = body(fn)
        for forbidden in ('board_stacks.append', '_on_primary(', '_save_match(', '_is_legal_move(', 'add_child(', 'PopupMenu.new('):
            assert forbidden not in fn_body, (fn, forbidden)
