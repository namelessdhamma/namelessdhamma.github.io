"""A5 v166: Normal/Hard skip redundant full-board win scans after early-win check.

This independent Python oracle verifies the EXACT pre-v166 decision ordering and
scores on reachable D2 positions, plus synthetic already-won states. It does
not claim native Godot execution, actual touch or visual parity.
"""
from __future__ import annotations

import random
from pathlib import Path
from a5_v141_persona_oracle import legal, after, win, win_place, replies, choose, WEIGHTS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/ai_opponent.gd').read_text(encoding='utf-8')


def tactical_fast(board, reserves, player, rule, difficulty, persona):
    """Independent v166 normal/hard score model; never call win(next_board)."""
    assert difficulty in (2, 3)
    candidates = legal(board, reserves, player, rule)
    if not candidates:
        return None
    for move in candidates:
        if win_place(board, player, rule, move):
            return move
    preexisting_win = win(board, player, rule)
    enemy = 3 - player
    best, best_score = None, float('-inf')
    for rank, cell in candidates:
        covered = bool(board[cell])
        next_board, next_reserves = after(board, reserves, player, (rank, cell))
        score = WEIGHTS[cell] * 3 + (10 - rank) * .65 + (9 if covered else 0)
        if persona == 1 and covered:
            score += 18.0 + rank * .9
        elif persona == 2:
            score += WEIGHTS[cell] * (rank - 1) * .15
        enemy_wins = replies(next_board, next_reserves, enemy, rule)
        score -= enemy_wins * (22000 if difficulty == 3 else 12000)
        if difficulty == 3:
            score += replies(next_board, next_reserves, player, rule) * (90 if persona == 2 else 200)
            if persona == 2:
                score -= enemy_wins * 6000
        if preexisting_win:
            score += 1000000
        if score > best_score:
            best, best_score = (rank, cell), score
    return best


def test_source_uses_one_normal_hard_preexisting_win_scan_and_no_candidate_win_scan():
    method = SOURCE.split('func choose_move(', 1)[1].split('\nfunc self_test(', 1)[0]
    assert 'var tactical_already_won := is_win(board, player, rule) if difficulty >= 2 else false' in method
    assert 'win = tactical_already_won' in method
    assert 'win = is_win(next_board, player, rule)' not in method
    assert method.index('if difficulty >= 2:\n\t\tfor move in candidates:') < method.index('var tactical_already_won')
    assert 'var next: Dictionary = _after_move(board, reserves, player, move)' in method
    assert 'score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)' in method
    assert 'if score > best_score:' in method


def test_exact_full_board_win_equivalence_on_reachable_and_synthetic_states():
    rng = random.Random(16601)
    checked = 0
    for rule in ('C', 'D', 'CD'):
        for _ in range(85):
            board = [[] for _ in range(9)]
            reserves = [[True] * 9 for _ in range(2)]
            player = 1
            for _ in range(rng.randrange(0, 16)):
                options = legal(board, reserves, player, rule)
                if not options:
                    player = 3 - player
                    options = legal(board, reserves, player, rule)
                    if not options:
                        break
                board, reserves = after(board, reserves, player, rng.choice(options))
                if win(board, player, rule):
                    break
                player = 3 - player
            for player in (1, 2):
                preexisting_win = win(board, player, rule)
                for move in legal(board, reserves, player, rule):
                    old = win(after(board, reserves, player, move)[0], player, rule)
                    new = preexisting_win or win_place(board, player, rule, move)
                    assert old == new
                    checked += 1
    assert checked > 10000


def test_normal_and_hard_ai_moves_match_exact_predecessor_oracle():
    rng = random.Random(16602)
    cases = 0
    for rule in ('C', 'D', 'CD'):
        for _ in range(40):
            board = [[] for _ in range(9)]
            reserves = [[True] * 9 for _ in range(2)]
            player = 1
            for _ in range(rng.randrange(0, 17)):
                options = legal(board, reserves, player, rule)
                if not options:
                    player = 3 - player
                    options = legal(board, reserves, player, rule)
                    if not options:
                        break
                board, reserves = after(board, reserves, player, rng.choice(options))
                if win(board, player, rule):
                    break
                player = 3 - player
            before_board = [stack.copy() for stack in board]
            before_reserves = [row.copy() for row in reserves]
            for difficulty in (2, 3):
                for persona in (0, 1, 2):
                    assert tactical_fast(board, reserves, 2, rule, difficulty, persona) == choose(board, reserves, 2, rule, difficulty, persona)
                    cases += 1
            assert board == before_board and reserves == before_reserves
    assert cases == 720


def test_21_qualified_world_rule_fixture_outcomes_are_unchanged():
    # This is a source-only oracle; worlds share one gameplay/AI engine.
    from tools.a5_v134_offline_ai_oracle import simulate
    for world in range(7):
        for rule in ('C', 'D', 'CD'):
            rounds = simulate(rule)
            assert rounds and rounds[-1]['score'] == [0, 3]
            assert all(item['winner'] == 2 for item in rounds)
