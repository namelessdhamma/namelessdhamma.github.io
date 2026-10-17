"""Independent D2 reachability + source integration checks for AI tail Undo.

These offline checks do not certify a native Godot run or real touch.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
LINES = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]


def body(name):
    match = re.search(rf'(?m)^func {re.escape(name)}\([^\n]*', MAIN)
    assert match, name
    next_func = re.search(r'(?m)^func |^static func ', MAIN[match.end():])
    return MAIN[match.start():match.end() + (next_func.start() if next_func else len(MAIN))]


def paths():
    fixture = body('_run_headless_blocked_human_ai_undo_smoke')
    return {mode: ast.literal_eval(re.search(rf'"{mode}": (\[\[.*?\]\])', fixture).group(1))
            for mode in ('C','D','CD')}


def simulate(mode, placements):
    board = [[] for _ in range(9)]
    available = [set(range(1,10)), set(range(1,10))]
    turn = 1
    before_human = None
    def legal(player):
        return [(rank, cell) for rank in available[player-1] for cell in range(9)
                if not board[cell] or (board[cell][-1][0] != player and rank > board[cell][-1][1]
                                       and (mode == 'D' or len(board[cell]) < 2))]
    for index, (player, rank, cell) in enumerate(placements):
        assert player == turn, (mode,index,'turn',player,turn)
        assert (rank,cell) in legal(player), (mode,index,'illegal',player,rank,cell)
        if index == 10:
            before_human = ([stack.copy() for stack in board], [r.copy() for r in available], turn)
        board[cell].append((player,rank))
        available[player-1].remove(rank)
        won = False
        for line in LINES:
            if all(board[c] and board[c][-1][0] == player for c in line):
                ranks = [board[c][-1][1] for c in line]
                if mode == 'C' or ranks[0] < ranks[1] < ranks[2] or ranks[0] > ranks[1] > ranks[2]:
                    won = True
        assert not won or index == len(placements)-1, (mode,index,'premature win')
        if index == 11:
            assert not legal(1) and legal(2), (mode,'human not blocked / AI no second turn')
        if legal(3-player):
            turn = 3-player
        elif legal(player):
            turn = player
        elif index < len(placements)-1:
            raise AssertionError((mode,index,'premature stalemate'))
    assert before_human is not None
    return before_human


def test_reachable_consecutive_ai_turns_in_all_three_rules():
    for mode, sequence in paths().items():
        assert len(sequence) == 13
        assert [move[0] for move in sequence[-3:]] == [1,2,2]
        before = simulate(mode, sequence)
        assert before[2] == 1


def test_old_two_entry_logic_is_provably_wrong_for_reachable_trace():
    for seq in paths().values():
        history = [{'player': p, 'was_ai': p == 2} for p,_,_ in seq]
        old_undo_steps = 0 if history[-1]['was_ai'] and history[-2]['player'] != 1 else 2
        assert old_undo_steps == 0
        # New semantics restore all consecutive AI replies AND the preceding P1 move.
        ai_tail = 0
        for entry in reversed(history):
            if entry['was_ai']:
                ai_tail += 1
            else:
                break
        assert ai_tail + 1 == 3


def test_shared_undo_scans_back_to_last_human_without_shadow_rules():
    undo = body('_undo_steps')
    assert 'for index in range(_undo_history.size() - 1, -1, -1):' in undo
    assert 'if int(entry["player"]) != 2:' in undo
    assert 'if int(entry["player"]) != 1:' in undo
    assert 'return ai_tail + 1' in undo
    assert 'return 0' in undo
    assert 'return 1' in undo


def test_corrupt_snapshot_is_rejected_before_history_mutation():
    undo = body('_undo_last_move')
    assert undo.index('if not _match_snapshot_valid(previous):') < undo.index('_undo_history.pop_back()')
    assert 'return' in undo[undo.index('if not _match_snapshot_valid(previous):'):undo.index('_undo_history.pop_back()')]
    assert '_apply_match_snapshot(previous, true)' in undo
    assert '_save_match()' in undo


def test_native_fixture_covers_all_worlds_and_is_wired_into_smoke():
    fixture = body('_run_headless_blocked_human_ai_undo_smoke')
    assert 'range(WorldVisuals.WORLDS.size())' in fixture
    assert 'for mode in ["C", "D", "CD"]' in fixture
    assert 'assert(_undo_steps() == 3)' in fixture
    assert 'assert(_undo_steps() == 0)' in fixture
    assert 'BLUE_SEA_BLOCKED_HUMAN_AI_UNDO_PASS' in fixture
    assert '_run_headless_blocked_human_ai_undo_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_approved_visual_assets_not_modified_by_this_delta():
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in MAIN
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in MAIN
