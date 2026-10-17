"""Independent rules oracle for the v80 shared Godot AI tactical count.

Python is NOT a Godot runtime. These property tests verify the exact tactical
mathematics and source wiring; native parse/full-match evidence remains OPEN.
"""
from pathlib import Path
import random

AI = Path(__file__).resolve().parents[1] / "scripts" / "ai_opponent.gd"
LINES = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))


def legal_destination(board, player, rank, cell, rule):
    stack = board[cell]
    if not stack:
        return True
    top = stack[-1]
    return top[0] != player and rank > top[1] and not (rule in ('C','CD') and len(stack) >= 2)


def legal_moves(board, reserves, player, rule):
    return [(rank,cell) for rank in range(1,10) if reserves[player-1][rank-1]
            for cell in range(9) if legal_destination(board,player,rank,cell,rule)]


def is_win(board, player, rule):
    for line in LINES:
        if all(board[cell] and board[cell][-1][0] == player for cell in line):
            ranks = [board[cell][-1][1] for cell in line]
            if rule == 'C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:
                return True
    return False


def after(board, player, rank, cell):
    b=[stack[:] for stack in board]
    b[cell].append((player,rank))
    return b


def slow_count(board, reserves, player, rule):
    return sum(is_win(after(board,player,rank,cell),player,rule)
               for rank,cell in legal_moves(board,reserves,player,rule))


def destination_win(board, player, rule, cell, rank):
    for line in LINES:
        if cell not in line:
            continue
        if all(c == cell or (board[c] and board[c][-1][0] == player) for c in line):
            ranks=[rank if c==cell else board[c][-1][1] for c in line]
            if rule == 'C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:
                return True
    return False


def fast_count(board, reserves, player, rule):
    won=is_win(board,player,rule)
    n=0
    for rank in range(1,10):
        if not reserves[player-1][rank-1]:
            continue
        for cell in range(9):
            if legal_destination(board,player,rank,cell,rule) and (won or destination_win(board,player,rule,cell,rank)):
                n+=1
    return n


def random_position(rng):
    board=[[] for _ in range(9)]
    reserves=[[True]*9 for _ in range(2)]
    for _ in range(rng.randrange(0,15)):
        player=rng.choice((1,2))
        unused=[rank for rank in range(1,10) if reserves[player-1][rank-1]]
        if not unused: continue
        rank=rng.choice(unused)
        choices=[c for c in range(9) if legal_destination(board,player,rank,c,'D')]
        if not choices: continue
        cell=rng.choice(choices)
        board[cell].append((player,rank))
        reserves[player-1][rank-1]=False
    return board,reserves


def test_v80_shared_ai_uses_one_legal_predicate_and_allocation_free_count():
    src=AI.read_text()
    assert 'func _legal_destination(' in src
    assert 'func _wins_after_placement(' in src
    count=src.split('func _winning_replies(',1)[1].split('func _reference_winning_replies(',1)[0]
    assert 'legal_moves(' not in count and '_after_move(' not in count
    assert '_legal_destination(' in count and '_wins_after_placement(' in count
    assert 'var already_won := is_win(' in count
    assert '_reference_winning_replies(' in src.split('func self_test()',1)[1]


def test_v80_randomized_threat_equivalence_1200_cases():
    rng=random.Random(20261013)
    for _ in range(200):
        board,reserves=random_position(rng)
        for rule in ('C','D','CD'):
            for player in (1,2):
                assert fast_count(board,reserves,player,rule)==slow_count(board,reserves,player,rule)


def test_v80_preexisting_win_and_no_legal_replies():
    board=[[] for _ in range(9)]
    for i,rank in enumerate((1,2,3)):
        board[i].append((1,rank))
    reserves=[[True]*9 for _ in range(2)]
    for rule in ('C','D','CD'):
        assert fast_count(board,reserves,1,rule)==slow_count(board,reserves,1,rule)
    reserves[0]=[False]*9
    for rule in ('C','D','CD'):
        assert fast_count(board,reserves,1,rule)==slow_count(board,reserves,1,rule)==0


def test_v80_stack_two_ceiling_and_deep_stacks():
    board=[[] for _ in range(9)]
    board[0]=[(1,1),(2,4)]
    reserves=[[True]*9 for _ in range(2)]
    assert (9,0) not in legal_moves(board,reserves,1,'C')
    assert (9,0) not in legal_moves(board,reserves,1,'CD')
    assert (9,0) in legal_moves(board,reserves,1,'D')
    for rule in ('C','D','CD'):
        for player in (1,2):
            assert fast_count(board,reserves,player,rule)==slow_count(board,reserves,player,rule)
