"""A5 v146: easy AI scores the actual board without allocating hypothetical states.

Offline source guard plus independent old-vs-new tactical oracle. This is NOT
Godot native compilation, rendering, or physical-phone qualification.
"""
from pathlib import Path
import random
from a5_v141_persona_oracle import legal, after, win, win_place, choose, WEIGHTS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/ai_opponent.gd').read_text(encoding='utf-8')


def easy_fast(board, reserves, player, rule, persona):
    """Independent allocation-free easy scoring model; no call to after()."""
    options = legal(board, reserves, player, rule)
    if not options:
        return None
    spent = sum(not flag for row in reserves for flag in row)
    already_won = win(board, player, rule)
    best, best_score = None, float('-inf')
    for rank, cell in options:
        covered = bool(board[cell])
        score = WEIGHTS[cell] * .4 + (10-rank) * .5 - (3 if covered else 0)
        score += ((cell * 7 + rank * 3 + spent * 5) % 17) * 2
        if persona == 1 and covered:
            score += 2.0 + rank * .2
        elif persona == 2:
            score += WEIGHTS[cell] * (rank - 1) * .04
        if already_won or win_place(board, player, rule, (rank, cell)):
            score += 2.0
        if score > best_score:
            best, best_score = (rank, cell), score
    return best


def test_live_easy_branch_does_not_allocate_hypothetical_state():
    method = SOURCE.split('func choose_move(', 1)[1].split('\nfunc self_test(', 1)[0]
    easy_branch = method.split('\n\t\tif difficulty == 1:', 2)[-1].split('\n\t\telse:', 1)[0]
    normal_branch = method.split('\n\t\telse:', 1)[1]
    assert 'easy_already_won' in method
    assert 'win = easy_already_won or _wins_after_legal_move(' in easy_branch
    assert '_after_move(' not in easy_branch
    assert '_after_move(board, reserves, player, move)' in normal_branch
    assert 'var enemy_wins := _winning_replies' in normal_branch
    assert 'score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)' in normal_branch


def test_optimized_win_check_equals_old_full_board_evaluation():
    rng = random.Random(14601)
    cases = 0
    for rule in ('C', 'D', 'CD'):
        for _ in range(110):
            board = [[] for _ in range(9)]
            reserves = [[True] * 9 for _ in range(2)]
            turn = 1
            for _ in range(rng.randrange(0, 15)):
                options = legal(board, reserves, turn, rule)
                if not options:
                    turn = 3 - turn
                    options = legal(board, reserves, turn, rule)
                    if not options:
                        break
                board, reserves = after(board, reserves, turn, rng.choice(options))
                if win(board, turn, rule):
                    break
                turn = 3 - turn
            for player in (1, 2):
                for move in legal(board, reserves, player, rule):
                    new_win = win(board, player, rule) or win_place(board, player, rule, move)
                    old_win = win(after(board, reserves, player, move)[0], player, rule)
                    assert new_win == old_win
                    cases += 1
    assert cases >= 12000


def test_all_easy_personas_choose_identical_moves_to_v145_oracle():
    rng = random.Random(14602)
    states = 0
    for rule in ('C', 'D', 'CD'):
        for _ in range(140):
            board = [[] for _ in range(9)]
            reserves = [[True] * 9 for _ in range(2)]
            turn = 1
            for _ in range(rng.randrange(0, 17)):
                options = legal(board, reserves, turn, rule)
                if not options:
                    turn = 3 - turn
                    options = legal(board, reserves, turn, rule)
                    if not options:
                        break
                board, reserves = after(board, reserves, turn, rng.choice(options))
                if win(board, turn, rule):
                    break
                turn = 3 - turn
            old_board = [stack.copy() for stack in board]
            old_reserves = [row.copy() for row in reserves]
            for persona in range(3):
                assert easy_fast(board, reserves, 2, rule, persona) == choose(board, reserves, 2, rule, 1, persona)
                states += 1
            assert board == old_board and reserves == old_reserves
    assert states == 1260


def test_easy_start_position_avoids_81_hypothetical_copies():
    board = [[] for _ in range(9)]
    reserves = [[True] * 9 for _ in range(2)]
    assert len(legal(board, reserves, 2, 'CD')) == 81
    for persona in range(3):
        assert easy_fast(board, reserves, 2, 'CD', persona) == choose(board, reserves, 2, 'CD', 1, persona)
    # v145 called _after_move once per candidate: 81 board/reserve clones;
    # v146's Easy branch calls it zero times. Normal/Hard unchanged.
