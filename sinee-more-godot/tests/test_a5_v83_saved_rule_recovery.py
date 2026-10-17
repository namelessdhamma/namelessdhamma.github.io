"""A5 v83: source-integrated saved-rule recovery. Native Godot smoke still required."""
from pathlib import Path
import re
import copy
import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')


def fn(name):
    match = re.search(rf'^func {re.escape(name)}\(.*?(?=^func |\Z)', MAIN, re.M | re.S)
    assert match, name
    return match.group(0)


def sample(rule='CD'):
    return {'schema': 1, 'rule': rule, 'board': [[] for _ in range(9)],
            'reserves': [[True] * 9 for _ in range(2)], 'turn': 1,
            'moves': 0, 'round': 1, 'score': [0, 0], 'winner': 0,
            'win_line': [], 'game_over': False, 'draw': False,
            'match_winner': 0, 'blocked_player': 0}


def oracle(snapshot):
    """Independent small oracle for rule-specific structural cases, not a Godot substitute."""
    rule = snapshot['rule']
    if rule not in {'C', 'D', 'CD'}:
        return False
    used = [set(), set()]
    for stack in snapshot['board']:
        if rule != 'D' and len(stack) > 2:
            return False
        prev_rank, prev_owner = 0, 0
        for piece in stack:
            owner, rank = piece['player'], piece['rank']
            if not 1 <= owner <= 2 or not 1 <= rank <= 9 or rank <= prev_rank or owner == prev_owner or rank in used[owner - 1]:
                return False
            used[owner - 1].add(rank)
            prev_rank, prev_owner = rank, owner
    if sum(len(s) for s in snapshot['board']) != snapshot['moves']:
        return False
    for p in range(2):
        for rank in range(1, 10):
            if snapshot['reserves'][p][rank - 1] == (rank in used[p]):
                return False
    if snapshot['winner']:
        line = snapshot['win_line']
        if line not in [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]:
            return False
        tops = [snapshot['board'][c][-1] for c in line]
        if any(piece['player'] != snapshot['winner'] for piece in tops):
            return False
        ranks = [piece['rank'] for piece in tops]
        if rule != 'C' and not (ranks[0] < ranks[1] < ranks[2] or ranks[0] > ranks[1] > ranks[2]):
            return False
    return True


def test_source_validator_uses_saved_rule_not_preference():
    source = fn('_match_snapshot_valid')
    assert 'var snapshot_rule: String = state["rule"]' in source
    assert 'snapshot_rule != "D"' in source
    assert 'snapshot_rule != "C"' in source
    assert 'str(state["rule"]) != current_rule' not in source
    assert 'typeof(state["rule"]) != TYPE_STRING' in source


def test_source_restore_reconciles_settings_after_applying_match():
    loader = fn('_load_match')
    assert loader.index('var recovered_rule_differs') < loader.index('_apply_match_snapshot(restored)')
    assert loader.index('_apply_match_snapshot(restored)') < loader.index('_save_preferences()')
    assert 'current_rule = str(state["rule"])' in fn('_apply_match_snapshot')
    assert 'DisplayServer.get_name() == "headless"' in loader


def test_in_project_native_smoke_is_wired_without_user_file_access():
    smoke = fn('_run_headless_cross_rule_resume_smoke')
    assert 'for rule in ["C", "D", "CD"]' in smoke
    assert 'D deep stack rejected' in smoke
    assert 'C non-ladder victory rejected' in smoke
    assert '_apply_match_snapshot(previous)' in smoke
    assert 'user://' not in smoke.replace('# Simulate lost/stale preferences without ever touching user:// files.', '')
    assert '_run_headless_cross_rule_resume_smoke()' in fn('_run_headless_match_snapshot_smoke')
    assert '_run_headless_match_snapshot_smoke()' in fn('_run_headless_geometry_and_interaction_smoke')


def test_valid_empty_round_for_each_rule_independent_of_preferences():
    for rule in ('C', 'D', 'CD'):
        assert oracle(sample(rule))


def test_deep_stack_legal_only_in_D():
    for rule in ('C', 'D', 'CD'):
        s = sample(rule)
        s['board'][4] = [{'player': 1, 'rank': 1}, {'player': 2, 'rank': 2}, {'player': 1, 'rank': 3}]
        s['reserves'][0][0] = s['reserves'][0][2] = s['reserves'][1][1] = False
        s['moves'], s['turn'] = 3, 2
        assert oracle(s) == (rule == 'D')


def test_non_ladder_win_legal_only_in_C():
    for rule in ('C', 'D', 'CD'):
        s = sample(rule)
        for cell, rank in enumerate([3, 1, 2]):
            s['board'][cell] = [{'player': 1, 'rank': rank}]
            s['reserves'][0][rank - 1] = False
        s.update(moves=3, turn=1, score=[1, 0], winner=1, win_line=[0, 1, 2], game_over=True)
        assert oracle(s) == (rule == 'C')


def test_corrupt_rule_never_accepted():
    for rule in ('', 'X', 'D ', 'CDx', None):
        assert not oracle(sample(rule))


def test_existing_gameplay_pirate_and_seven_world_assets_preserved():
    assert MAIN.count('func _on_primary()') == 1
    assert MAIN.count('func _winning_line(') == 1
    assert 'PirateOpeningCampaign' in (ROOT / 'project.godot').read_text()
    assert 'call_deferred("_play_ai_turn")' in fn('_queue_ai_turn_if_ready')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in fn('_run_headless_full_match_smoke')
