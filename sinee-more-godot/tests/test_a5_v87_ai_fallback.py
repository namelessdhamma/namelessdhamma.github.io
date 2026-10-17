"""A5 v87 offline contract checks; native Godot execution remains a separate gate."""
from pathlib import Path
import pytest

SOURCE = (Path(__file__).parents[1] / 'scripts/main.gd').read_text()


def function(name):
    start = SOURCE.index('func ' + name + '(')
    end = SOURCE.find('\nfunc ', start + 1)
    return SOURCE[start:end if end >= 0 else None]


def legal(board, reserves, player, rule, rank, cell):
    if not (1 <= rank <= 9 and 0 <= cell <= 8 and reserves[player-1][rank-1]):
        return False
    stack = board[cell]
    return not stack or (stack[-1]['player'] != player and rank > stack[-1]['rank']
                         and not (rule in ('C','CD') and len(stack) >= 2))


def fallback(board, reserves, rule, proposed):
    if type(proposed.get('rank')) is int and type(proposed.get('cell')) is int:
        rank, cell = proposed['rank'], proposed['cell']
        if legal(board, reserves, 2, rule, rank, cell):
            return {'rank': rank, 'cell': cell}
    for rank in range(1, 10):
        for cell in range(9):
            if legal(board, reserves, 2, rule, rank, cell):
                return {'rank': rank, 'cell': cell}
    return {}


def test_production_ai_reaches_commit_without_error_return():
    body = function('_play_ai_turn')
    assert 'var move: Dictionary = _resolve_ai_move(proposed)' in body
    assert 'push_error("Blue Sea AI returned no move despite legal choices")' not in body
    assert 'selected_reserve = int(move["rank"]) - 1' in body
    assert '_on_primary()' in body
    helper = function('_resolve_ai_move')
    assert '_is_legal_move(2, rank, cell)' in helper
    assert 'typeof(raw_rank) == TYPE_INT and typeof(raw_cell) == TYPE_INT' in helper
    assert 'for rank in range(1, 10):' in helper
    assert 'for cell in range(9):' in helper
    assert '_run_headless_ai_fallback_smoke()' in function('_run_headless_geometry_and_interaction_smoke')


@pytest.mark.parametrize('rule', ['C', 'D', 'CD'])
@pytest.mark.parametrize('world', range(7))
def test_emergency_move_never_violates_shared_rules(world, rule):
    # World is deliberately irrelevant: one shared rules engine for seven skins.
    board = [[] for _ in range(9)]
    board[0] = [{'player': 1, 'rank': 1}, {'player': 2, 'rank': 3}]
    board[1] = [{'player': 1, 'rank': 2}]
    reserves = [[True]*9, [True]*9]
    reserves[1][2] = False
    for proposal in [{}, {'rank': 3, 'cell': 0}, {'rank': 99, 'cell': 1},
                     {'rank': '9', 'cell': 4}, {'rank': 9, 'cell': 4}]:
        choice = fallback(board, reserves, rule, proposal)
        assert legal(board, reserves, 2, rule, choice['rank'], choice['cell'])
        if proposal == {'rank': 9, 'cell': 4}:
            assert choice == proposal
        else:
            assert choice == {'rank': 1, 'cell': 2}


@pytest.mark.parametrize('rule', ['C', 'D', 'CD'])
def test_no_legal_ai_piece_returns_empty(rule):
    assert fallback([[] for _ in range(9)], [[True]*9, [False]*9], rule, {}) == {}


def test_rank_9_cover_only_in_unlimited_depth_rule():
    board = [[{'player': 1, 'rank': 1}, {'player': 2, 'rank': 3}] ] + [[] for _ in range(8)]
    reserves = [[True]*9, [True]*9]
    assert not legal(board, reserves, 1, 'CD', 9, 0)
    assert legal(board, reserves, 1, 'D', 9, 0)
