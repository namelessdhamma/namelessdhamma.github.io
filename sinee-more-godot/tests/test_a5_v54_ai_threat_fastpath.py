"""A5 v54: exact AI lookahead equivalence, including already-terminal boards.

These are independent Python behavioral models of the previous and current
GDScript algorithms. They do NOT constitute a Godot runtime performance test.
"""
import importlib.util
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'scripts/ai_opponent.gd').read_text()
spec = importlib.util.spec_from_file_location('a5_old_model', Path(__file__).with_name('a5_v52_ai_model.py'))
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def hypothetical_win(board, player, rule, move):
    rank, dest = move
    for line in old.LINES:
        if dest not in line:
            continue
        tops = [((player, rank) if cell == dest else (board[cell][-1] if board[cell] else None)) for cell in line]
        if not all(piece is not None and piece[0] == player for piece in tops):
            continue
        a, b, c = [piece[1] for piece in tops]
        if rule == 'C' or a < b < c or a > b > c:
            return True
    return False


def slow_replies(board, reserves, player, rule):
    return sum(old.win(old.apply(board, reserves, player, move)[0], player, rule)
               for move in old.legal(board, reserves, player, rule))


def fast_replies(board, reserves, player, rule):
    options = old.legal(board, reserves, player, rule)
    if not options:
        return 0
    if old.win(board, player, rule):
        return len(options)
    return sum(hypothetical_win(board, player, rule, move) for move in options)


def fast_choose(board, reserves, player, rule, difficulty, persona):
    moves = old.legal(board, reserves, player, rule)
    if not moves:
        return None
    enemy = 3-player
    best = None
    best_score = float('-inf')
    for rank, cell in moves:
        covered = bool(board[cell])
        next_board, next_reserves = old.apply(board, reserves, player, (rank, cell))
        is_win = old.win(next_board, player, rule)
        score = old.WEIGHTS[cell]*3 + (10-rank)*.65
        if covered:
            score += 9
        if persona == 1 and covered:
            score += 3
        if persona == 2:
            score += 2*old.WEIGHTS[cell]
        if difficulty == 1:
            score += ((cell*7+rank*3)%11)*.4
        else:
            enemy_wins = fast_replies(next_board, next_reserves, enemy, rule)
            score -= enemy_wins*(22000 if difficulty == 3 else 12000)
            if difficulty == 3:
                score += fast_replies(next_board, next_reserves, player, rule)*(90 if persona == 2 else 200)
                if persona == 2:
                    score -= enemy_wins*6000
        if is_win and difficulty >= 2:
            score += 1000000
        if score > best_score:
            best_score = score
            best = (rank, cell)
    return best


def positions(rule, seed, count=100):
    rng = random.Random(seed)
    board = [[] for _ in range(9)]
    reserves = [[True]*9 for _ in range(2)]
    player = 1
    yield board, reserves
    for _ in range(count):
        options = old.legal(board, reserves, player, rule)
        if not options:
            player = 3-player
            options = old.legal(board, reserves, player, rule)
        if not options:
            board = [[] for _ in range(9)]
            reserves = [[True]*9 for _ in range(2)]
            player = 1
            yield board, reserves
            continue
        board, reserves = old.apply(board, reserves, player, rng.choice(options))
        yield board, reserves
        if old.win(board, player, rule):
            # Include terminal positions before resetting: old lookahead
            # counts preexisting wins for every legal reply.
            board = [[] for _ in range(9)]
            reserves = [[True]*9 for _ in range(2)]
        player = 3-player


class A5AIThreatFastpath(unittest.TestCase):
    def test_source_removes_deep_copies_per_hypothetical_reply(self):
        start = SCRIPT.index('func _winning_replies(')
        end = SCRIPT.index('\nfunc ', start+1)
        block = SCRIPT[start:end]
        self.assertNotIn('.duplicate(true)', block)
        self.assertTrue('_wins_after_legal_move(' in block or '_wins_after_placement(' in block)
        self.assertTrue('if is_win(board, player, rule):' in block or 'var already_won := is_win(board, player, rule)' in block)

    def test_hypothetical_win_matches_materialized_board(self):
        checked = 0
        for mode in ('C', 'D', 'CD'):
            for board, reserves in positions(mode, 111, 100):
                for player in (1, 2):
                    for move in old.legal(board, reserves, player, mode):
                        # The fast primitive checks only NEW lines; positions
                        # already won are handled by the caller's guard.
                        if old.win(board, player, mode):
                            continue
                        expected = old.win(old.apply(board, reserves, player, move)[0], player, mode)
                        self.assertEqual(expected, hypothetical_win(board, player, mode, move))
                        checked += 1
        self.assertGreater(checked, 10000)

    def test_all_reply_counts_match_prior_algorithm(self):
        checked = 0
        for mode in ('C', 'D', 'CD'):
            for board, reserves in positions(mode, 137, 160):
                for player in (1, 2):
                    self.assertEqual(slow_replies(board, reserves, player, mode),
                                     fast_replies(board, reserves, player, mode))
                    checked += 1
        self.assertEqual(checked, 966)

    def test_preexisting_win_preserved(self):
        board = [[] for _ in range(9)]
        board[0] = [(2, 1)]
        board[1] = [(2, 2)]
        board[2] = [(2, 3)]
        reserves = [[True]*9, [False, False, False] + [True]*6]
        for mode in ('C', 'D', 'CD'):
            self.assertTrue(old.win(board, 2, mode))
            self.assertEqual(slow_replies(board, reserves, 2, mode),
                             fast_replies(board, reserves, 2, mode))

    def test_all_difficulties_personas_choose_same_move(self):
        checked = 0
        for mode in ('C', 'D', 'CD'):
            states = list(positions(mode, 101, 30))
            for board, reserves in states[::3]:
                for player in (1, 2):
                    for difficulty in (1, 2, 3):
                        for persona in (0, 1, 2):
                            self.assertEqual(old.choose(board, reserves, player, mode, difficulty, persona),
                                             fast_choose(board, reserves, player, mode, difficulty, persona))
                            checked += 1
        self.assertEqual(checked, 594)


if __name__ == '__main__':
    unittest.main()
