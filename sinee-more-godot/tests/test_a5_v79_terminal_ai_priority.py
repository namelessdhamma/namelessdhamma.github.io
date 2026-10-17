"""A5 v79 source and independent tactical model checks.

These checks do NOT execute Godot; the production native self_test is wired
into the explicit headless smoke and must still run in a qualified engine.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = (ROOT / 'scripts/ai_opponent.gd').read_text()
MAIN = (ROOT / 'scripts/main.gd').read_text()
LINES = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))


def model_win_after(board, player, rule, rank, cell):
    """Independent Python oracle of the destination-only winning rule."""
    for line in LINES:
        if cell not in line:
            continue
        values = []
        for idx in line:
            if idx == cell:
                values.append(rank)
            elif board[idx] and board[idx][-1][0] == player:
                values.append(board[idx][-1][1])
            else:
                break
        if len(values) == 3 and (rule == 'C' or values[0] < values[1] < values[2] or values[0] > values[1] > values[2]):
            return True
    return False


def test_native_terminal_priority_precedes_expensive_opponent_lookahead():
    f = AI.split('func choose_move(',1)[1].split('func self_test(',1)[0]
    assert 'if difficulty >= 2:' in f
    assert 'if _wins_after_legal_move(board, player, rule, move):' in f
    assert f.index('if _wins_after_legal_move(board, player, rule, move):') < f.index('var enemy :=')
    assert f.index('return move') < f.index('var enemy_wins :=')
    assert 'func _wins_after_legal_move(' in AI


def test_independent_tactical_oracle_all_modes_and_players():
    for player in (1,2):
        for rule in ('C','D','CD'):
            board = [[] for _ in range(9)]
            board[0] = [(player,1)]
            board[1] = [(player,2)]
            before = repr(board)
            assert model_win_after(board,player,rule,3,2)
            assert not model_win_after(board,player,rule,3,3)
            assert repr(board) == before


def test_strict_ladder_for_d_and_cd_but_not_c():
    board = [[] for _ in range(9)]
    board[0] = [(2,5)]
    board[1] = [(2,5)]
    assert model_win_after(board,2,'C',7,2)
    assert not model_win_after(board,2,'D',7,2)
    assert not model_win_after(board,2,'CD',7,2)


def test_native_selftest_checks_three_rules_two_difficulties_three_personas():
    f = AI.split('func self_test(',1)[1]
    assert 'for rule in ["C", "D", "CD"]:' in f
    assert 'for difficulty in [2,3]:' in f
    assert 'for persona in [0,1,2]:' in f
    assert 'assert(is_win(next["board"], 2, rule))' in f
    assert 'assert(ai_engine.self_test()' in MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1]


def test_no_change_to_canonical_world_or_rule_modules():
    assert 'func _is_legal_move(' in MAIN
    assert 'func _winning_line(' in MAIN
    assert 'func _queue_ai_turn_if_ready(' in MAIN
    assert 'func _play_ai_turn(' in MAIN
    assert 'const LINES: Array[Array]' in AI
