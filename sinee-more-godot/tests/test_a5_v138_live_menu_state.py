"""A5 v138 live shared menu state/terminal action source regressions.

Offline checks only. They do not certify Godot execution or real-phone UX.
"""
from pathlib import Path

MAIN = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    start = MAIN.index('func ' + name + '(')
    end = MAIN.find('\nfunc ', start + 1)
    return MAIN[start:end if end >= 0 else None]


def test_phone_main_menu_shows_live_world_selection_not_generic_count():
    src = body('_render_mobile_menu_page')
    assert '"Мир · " + WorldVisuals.WORLDS[current_world], 105' in src
    assert '"Выбрать мир · 7"' not in src
    assert 'for world_id in range(WorldVisuals.WORLDS.size()):' in src
    assert 'world_id == current_world' in src


def test_phone_menu_shows_current_ai_difficulty_and_persona():
    src = body('_render_mobile_menu_page')
    assert '["Лёгкая", "Обычная", "Сложная"][ai_difficulty - 1], 101' in src
    assert '["Баланс", "Атака", "Защита"][ai_persona], 102' in src
    assert '"Сложность ИИ", 101' not in src
    assert '"Характер ИИ", 102' not in src


def test_phone_selection_controls_still_route_to_existing_settings():
    src = body('_on_mobile_menu_action')
    for id_, page in ((105, 'worlds'), (101, 'difficulty'), (102, 'persona')):
        assert f'elif id == {id_}:' in src
        assert f'_render_mobile_menu_page("{page}")' in src
    assert '_set_world(id - 500)' in src
    assert '_on_game_menu_item(id)' in src


def test_desktop_terminal_menu_distinguishes_next_round_from_new_match():
    src = body('_populate_game_menu')
    assert 'popup.add_item("Новый матч" if match_winner != 0 else "Следующий раунд", 2)' in src
    assert 'popup.add_item("Следующий раунд", 2)' not in src
    handler = body('_on_game_menu_item')
    assert 'elif id == 2 and game_over:' in handler
    assert '_on_menu()' in handler


def test_terminal_action_matches_actual_shared_gameplay_transition():
    src = body('_on_menu')
    assert 'if not game_over:' in src
    assert 'if match_winner != 0:' in src
    assert 'match_score = [0, 0]' in src
    assert 'round_number = 1' in src
    assert 'round_number += 1' in src
    assert '_reset_round()' in src


def test_mobile_terminal_and_live_next_still_match_and_are_terminal_only():
    src = body('_render_mobile_menu_page')
    assert 'if game_over:' in src
    assert '"Новый матч" if match_winner != 0 else "Следующий раунд"' in src
    refresh = body('_refresh_surface')
    assert 'next_round_button.visible = game_over' in refresh
    assert 'next_round_button.text = "P%d ВЫИГРАЛ МАТЧ · НОВЫЙ"' in refresh


def test_changes_do_not_add_actions_beneath_live_reserve_or_a_second_engine():
    src = body('_render_mobile_menu_page')
    assert 'if page == "main":' in src
    assert '"Сбросить матч…"' in src
    assert '"Отменить ход"' in src
    assert '"Правила · " + current_rule' in src
    # The menu renderer must remain presentation-only; gameplay changes
    # stay in the existing actions, not in duplicated settings code.
    assert 'board_stacks =' not in src
    assert 'reserve_available =' not in src
    assert '_on_primary(' not in src
    assert '_save_match(' not in src
