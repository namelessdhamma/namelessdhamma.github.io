"""A5 v85: no-frame-loop when restoring a structurally valid blocked AI turn.

The native Godot headless fixture is embedded in main.gd. These tests validate
source integration and the independent D-rule state oracle, not a Godot run.
"""
from pathlib import Path

SOURCE = (Path(__file__).parents[1] / 'scripts' / 'main.gd').read_text()


def function(name):
    start = SOURCE.index('func ' + name + '(')
    end = SOURCE.find('\nfunc ', start + 5)
    return SOURCE[start:end if end >= 0 else None]


def fixture():
    board = [
        [(1,1)], [(1,2)], [],
        [(2,1),(1,4),(2,7)], [(2,2),(1,5),(2,9)],
        [(2,3),(1,6),(2,8)], [(2,4)], [(2,6)], [(2,5)]
    ]
    reserves = [[False,False,True,False,False,False,True,True,True], [False]*9]
    return board, reserves


def legal(board, reserves, player):
    for rank in range(1, 10):
        if not reserves[player-1][rank-1]:
            continue
        for stack in board:
            if not stack or (stack[-1][0] != player and rank > stack[-1][1]):
                return True
    return False


def test_interrupted_snapshot_is_structurally_consistent():
    board, reserves = fixture()
    assert sum(map(len, board)) == 14
    assert not legal(board, reserves, 2)
    assert legal(board, reserves, 1)
    for player in (1,2):
        used = [rank for stack in board for owner,rank in stack if owner == player]
        assert len(used) == len(set(used))
        assert all(reserves[player-1][rank-1] == (rank not in used) for rank in range(1,10))


def test_empty_ai_result_advances_to_human_and_persists():
    handler = function('_play_ai_turn')
    branch = handler.split('if move.is_empty():', 1)[1].split('selected_reserve = int(move', 1)[0]
    assert 'if _has_legal_move(2):' in branch
    assert 'blocked_player = 2' in branch
    assert 'turn = 1' in branch
    assert 'if not _has_legal_move(1):' in branch
    assert 'round_draw = true' in branch
    assert 'blocked_player = 0' in branch
    assert '_refresh_surface()' in branch and '_save_match()' in branch
    assert branch.rstrip().endswith('return')


def test_no_per_frame_empty_ai_loop_after_skip():
    queue = function('_queue_ai_turn_if_ready')
    assert 'turn != 2' in queue
    assert '_ai_turn_queued' in queue
    process = function('_process')
    assert '_queue_ai_turn_if_ready()' in process
    # After the empty-result transition turn=1, so the queue guard rejects it.
    assert 'turn = 1' in function('_play_ai_turn')


def test_real_human_can_win_after_ai_yield():
    board, reserves = fixture()
    board[2].append((1,3))
    reserves[0][2] = False
    assert [board[i][-1] for i in (0,1,2)] == [(1,1),(1,2),(1,3)]
    assert not legal(board, reserves, 2)
    assert not reserves[0][2]


def test_native_fixture_integrated_into_existing_headless_suite():
    smoke = function('_run_headless_ai_empty_resume_smoke')
    for fragment in ('_match_snapshot_valid(_match_snapshot())', '_play_ai_turn()',
                     'turn == 1 and blocked_player == 2', '_queue_ai_turn_if_ready()',
                     'not _ai_turn_queued', '_on_reserve_pressed(1, 2)',
                     '_on_cell_pressed(2)', 'game_over and winner == 1',
                     '_apply_match_snapshot(previous)'):
        assert fragment in smoke
    assert '_run_headless_ai_empty_resume_smoke()' in function('_run_headless_match_snapshot_smoke')
    assert '_run_headless_match_snapshot_smoke()' in function('_run_headless_geometry_and_interaction_smoke')
