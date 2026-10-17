"""A5 v141: three tactically distinct personas on one shared D2 AI.

Offline oracle is NOT Godot native/real touch evidence. Native self_test
uses the same fixture and is invoked by the existing headless smoke route.
"""
from pathlib import Path
import random
import pytest
from a5_v141_persona_oracle import legal, after, win, choose, match_variant, match

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts/ai_opponent.gd').read_text()


def test_integrated_godot_scoring_and_native_selftest():
    assert 'if persona == 1 and covered:' in SOURCE
    assert 'score += 18.0 + float(rank) * 0.9' in SOURCE
    assert 'elif persona == 2:' in SOURCE
    assert 'score += float(CELL_WEIGHTS[cell] * (rank - 1)) * 0.15' in SOURCE
    assert 'score += 3.0 if covered else 0.0' not in SOURCE
    assert 'score += 2.0 * CELL_WEIGHTS[cell]' not in SOURCE
    assert 'var persona_board: Array' in SOURCE
    assert 'persona_moves[0] == {"rank": 1, "cell": 4}' in SOURCE
    assert 'persona_moves[1] == {"rank": 9, "cell": 1}' in SOURCE
    assert 'persona_moves[2] == {"rank": 7, "cell": 1}' in SOURCE
    assert 'if difficulty >= 2:' in SOURCE
    assert 'if _wins_after_legal_move(board, player, rule, move):' in SOURCE
    assert 'score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)' in SOURCE


def test_native_fixture_matches_independent_oracle():
    board = [[(2, 6)], [(1, 6)], [], [(1, 7)], [], [], [], [], []]
    reserves = [[True]*5 + [False, False, True, True], [True]*5 + [False, True, True, True]]
    before = [list(stack) for stack in board]
    assert [choose(board, reserves, 2, 'C', 3, p) for p in range(3)] == [(1, 4), (9, 1), (7, 1)]
    assert board == before


@pytest.mark.parametrize('rule', ('C', 'D', 'CD'))
def test_personas_differ_in_meaningful_share_of_nonterminal_positions(rule):
    rng = random.Random(321 + {'C': 0, 'D': 1, 'CD': 2}[rule])
    positions = []
    for _ in range(190):
        board = [[] for _ in range(9)]
        reserves = [[True]*9 for _ in range(2)]
        turn = 1
        for _ in range(rng.randint(1, 12)):
            moves = legal(board, reserves, turn, rule)
            if not moves:
                turn = 3-turn
                moves = legal(board, reserves, turn, rule)
                if not moves:
                    break
            board, reserves = after(board, reserves, turn, rng.choice(moves))
            if win(board, turn, rule):
                break
            turn = 3-turn
        if not win(board, 1, rule) and not win(board, 2, rule) and legal(board, reserves, 2, rule):
            positions.append((board, reserves))
    assert len(positions) >= 100
    moves_by_persona = [tuple(choose(b, r, 2, rule, 3, p) for p in range(3)) for b, r in positions]
    # More than just three differently named menu settings: actual move choices.
    aggressive = sum(m[0] != m[1] for m in moves_by_persona)
    defensive = sum(m[0] != m[2] for m in moves_by_persona)
    assert aggressive >= len(positions) * .15, (rule, len(positions), aggressive)
    assert defensive >= len(positions) * .12, (rule, len(positions), defensive)
    for (b, r), choices in zip(positions, moves_by_persona):
        assert all(move in legal(b, r, 2, rule) for move in choices)


@pytest.mark.parametrize('rule', ('C', 'D', 'CD'))
@pytest.mark.parametrize('difficulty', (1, 2, 3))
@pytest.mark.parametrize('persona', (0, 1, 2))
def test_216_seeded_matches_no_illegal_or_unresolved(rule, difficulty, persona):
    outcomes = [match_variant(rule, difficulty, persona, seed) for seed in range(8)]
    assert all(max(score) == 3 and rounds <= 12 and moves > 0 for score, rounds, moves in outcomes)
    if difficulty == 3:
        assert all(score[1] == 3 for score, _, _ in outcomes)


def test_existing_21_case_native_full_match_oracle_unaffected():
    assert all(match(rule, world)[0] == [0, 3] for rule in ('C', 'D', 'CD') for world in range(7))
