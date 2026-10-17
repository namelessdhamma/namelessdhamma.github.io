"""A5 v84: blocked opponent -> winning move must persist as a valid terminal round.

Offline rule oracle + exact source wiring. Native Godot smoke is integrated but
must not be reported as executed unless Godot 4.7.2 runs successfully.
"""
from pathlib import Path

SOURCE = (Path(__file__).parents[1] / 'scripts' / 'main.gd').read_text()
LINES = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))


def function(name):
    start = SOURCE.index('func ' + name + '(')
    end = SOURCE.find('\nfunc ', start + 5)
    return SOURCE[start:end if end >= 0 else None]


def fixture():
    board = [
        [(1,1)], [(1,2)], [],
        [(2,1),(1,4),(2,7)], [(2,2),(1,5),(2,9)],
        [(2,3),(1,6),(2,8)], [(2,4)], [(2,6)], [(2,5)],
    ]
    reserves = [[False,False,True,False,False,False,True,True,True], [False]*9]
    return board, reserves


def wins(board, player, rule='D'):
    for line in LINES:
        tops = [board[i][-1] if board[i] else None for i in line]
        if all(piece and piece[0] == player for piece in tops):
            ranks = [piece[1] for piece in tops]
            if rule == 'C' or ranks[0] < ranks[1] < ranks[2] or ranks[0] > ranks[1] > ranks[2]:
                return line
    return None


def test_fixture_is_legal_d_stacks_and_exhausted_opponent():
    board, reserves = fixture()
    assert len(board) == 9 and sum(map(len,board)) == 14
    for player in (1,2):
        used = [rank for stack in board for owner,rank in stack if owner == player]
        assert len(used) == len(set(used))
        assert all(reserves[player-1][rank-1] == (rank not in used) for rank in range(1,10))
    for stack in board:
        assert all(stack[i][1] < stack[i+1][1] and stack[i][0] != stack[i+1][0]
                   for i in range(len(stack)-1))
    assert not any(reserves[1])
    assert wins(board,1) is None and wins(board,2) is None


def test_actual_next_placement_is_terminal_and_requires_unblocked_save():
    board, reserves = fixture()
    assert reserves[0][2] and not board[2]
    board[2].append((1,3))
    reserves[0][2] = False
    assert wins(board,1) == (0,1,2)
    assert sum(map(len,board)) == 15
    assert all(not reserves[1][i] for i in range(9))
    # v83's terminal save validator explicitly rejects game_over+blocked_player.
    assert 'blocked == active or bool(state["game_over"])' in function('_match_snapshot_valid')


def test_production_commit_clears_blocked_marker_before_terminal_branch():
    commit = function('_on_primary')
    assert commit.index('blocked_player = 0') < commit.index('win_line = _winning_line(moving_player)')
    assert commit.index('blocked_player = 0') < commit.index('if not win_line.is_empty():')
    assert '_save_match()' in commit


def test_native_smoke_integrated_into_explicit_headless_suite():
    smoke = function('_run_headless_blocked_to_win_resume_smoke')
    assert 'assert(_match_snapshot_valid(_match_snapshot())' in smoke
    assert '_on_reserve_pressed(1, 2)' in smoke
    assert '_on_cell_pressed(2)' in smoke
    assert 'assert(_match_snapshot_valid(winning_snapshot)' in smoke
    assert '_apply_match_snapshot(previous)' in smoke
    assert '_run_headless_blocked_to_win_resume_smoke()' in function('_run_headless_match_snapshot_smoke')
    assert '_run_headless_match_snapshot_smoke()' in function('_run_headless_geometry_and_interaction_smoke')
