"""Independent Python model of the deterministic v52 AI match fixture.
This does NOT replace running Godot's actual game or real touch tests.
"""
import unittest
try:
    from .a5_v52_ai_model import legal, win, apply, choose
except ImportError:  # unittest discover -s tests
    from a5_v52_ai_model import legal, win, apply, choose


def one_round(rule, round_number):
    board = [[] for _ in range(9)]
    reserves = [[True] * 9 for _ in range(2)]
    turn = 1 if round_number % 2 == 1 else 2
    for moves in range(18):
        options = legal(board, reserves, turn, rule)
        if not options:
            turn = 3 - turn
            options = legal(board, reserves, turn, rule)
            if not options:
                return 0, moves
        if turn == 2:
            move = choose(board, reserves, 2, rule, 3, 0)
        else:
            move = options[(round_number * 17 + moves * 7) % len(options)]
        assert move in options
        board, reserves = apply(board, reserves, turn, move)
        if win(board, turn, rule):
            return turn, moves + 1
        turn = 3 - turn
    return 0, 18


class A5V52Model(unittest.TestCase):
    def test_full_match_terminates_for_C_D_CD(self):
        for rule in ('C', 'D', 'CD'):
            with self.subTest(rule=rule):
                score = [0, 0]
                total = 0
                for round_number in range(1, 13):
                    winner, moves = one_round(rule, round_number)
                    self.assertLessEqual(moves, 18)
                    total += moves
                    if winner:
                        score[winner - 1] += 1
                    if max(score) >= 3:
                        break
                self.assertEqual(score, [0, 3])
                self.assertEqual(round_number, 3)
                self.assertGreater(total, 0)


if __name__ == '__main__':
    unittest.main()
