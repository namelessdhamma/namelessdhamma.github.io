"""A5 v86 source and independent rule oracle; not a Godot runtime certification."""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text()


def fn(name):
    start = SRC.index('func ' + name + '(')
    end = SRC.find('\nfunc ', start + 5)
    return SRC[start:end if end != -1 else None]


def swapped_v85_fixture():
    board = [
        [(2, 1)], [(2, 2)], [],
        [(1, 1), (2, 4), (1, 7)],
        [(1, 2), (2, 5), (1, 9)],
        [(1, 3), (2, 6), (1, 8)],
        [(1, 4)], [(1, 6)], [(1, 5)]
    ]
    reserves = [[False] * 9, [False, False, True, False, False, False, True, True, True]]
    return board, reserves


def legal(board, reserves, player, rule='D'):
    for rank in range(1, 10):
        if not reserves[player - 1][rank - 1]:
            continue
        for stack in board:
            if not stack or (stack[-1][0] != player and rank > stack[-1][1]
                             and (rule == 'D' or len(stack) < 2)):
                return True
    return False


def test_oracle_p1_blocked_p2_can_finish():
    board, reserves = swapped_v85_fixture()
    assert sum(map(len, board)) == 14
    assert not legal(board, reserves, 1)
    assert legal(board, reserves, 2)
    board[2].append((2, 3))
    reserves[1][2] = False
    assert [board[i][-1] for i in (0, 1, 2)] == [(2, 1), (2, 2), (2, 3)]


def test_fixture_uses_each_rank_once_and_increasing_cover():
    board, reserves = swapped_v85_fixture()
    for stack in board:
        assert all(a[0] != b[0] and a[1] < b[1] for a, b in zip(stack, stack[1:]))
    for player in (1, 2):
        used = [rank for stack in board for owner, rank in stack if owner == player]
        assert len(used) == len(set(used))
        assert all(reserves[player-1][r-1] == (r not in used) for r in range(1, 10))


def test_restored_turn_normalizes_both_players_and_terminal_draw():
    f = fn('_reconcile_restored_turn')
    for snippet in ('if game_over or _has_legal_move(turn):',
                    'var exhausted := turn',
                    'var other := 2 if turn == 1 else 1',
                    'if _has_legal_move(other):',
                    'blocked_player = exhausted', 'turn = other',
                    'game_over = true', 'round_draw = true',
                    'blocked_player = 0', 'selected_reserve = -1',
                    'selected_cell = -1', 'return true'):
        assert snippet in f
    assert 'ai_enabled' not in f  # symmetric: both human and AI can be exhausted


def test_recovery_precedes_first_render_and_persists():
    f = fn('_load_match')
    assert f.index('_apply_match_snapshot(restored)') < f.index('_reconcile_restored_turn()')
    assert f.index('_reconcile_restored_turn()') < f.index('_save_match()')
    assert 'if repaired_turn or recovered_from_backup:' in f
    assert 'assert(_match_snapshot_valid(_match_snapshot())' in f
    assert fn('_ready').index('var resumed_match := _load_match()') < fn('_ready').index('_prepare_world_shell()')


def test_recovery_is_idempotent_and_never_overwrites_terminal_round():
    f = fn('_reconcile_restored_turn')
    assert f.index('if game_over or _has_legal_move(turn):') < f.index('var exhausted := turn')
    assert 'return false' in f
    assert 'winner = ' not in f and 'match_score' not in f and 'round_number' not in f


def test_native_fixture_uses_live_input_and_persistence_validation():
    f = fn('_run_headless_restored_human_turn_smoke')
    for snippet in ('_match_snapshot_valid(_match_snapshot())',
                    'not _has_legal_move(1) and _has_legal_move(2)',
                    '_reconcile_restored_turn()',
                    'turn == 2 and blocked_player == 1',
                    'not _reconcile_restored_turn()',
                    '_reserve_node(2).visible and not _reserve_node(1).visible',
                    '_on_reserve_pressed(2, 2)', '_on_cell_pressed(2)',
                    'game_over and winner == 2 and blocked_player == 0',
                    '_apply_match_snapshot(previous)'):
        assert snippet in f
    assert '_run_headless_restored_human_turn_smoke()' in fn('_run_headless_match_snapshot_smoke')


def test_no_change_to_existing_ai_guard_or_full_match_suite():
    assert 'if move.is_empty():' in fn('_play_ai_turn')
    assert 'for world in range(WorldVisuals.WORLDS.size())' in fn('_run_headless_full_match_smoke')
    assert 'for mode in ["C", "D", "CD"]' in fn('_run_headless_full_match_smoke')
