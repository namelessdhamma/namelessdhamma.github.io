"""A5 v142: genuinely approachable easy AI, not native Godot evidence."""
from pathlib import Path
from itertools import product
from a5_v141_persona_oracle import legal, after, win, choose, match_variant, match

AI=(Path(__file__).resolve().parents[1]/'scripts/ai_opponent.gd').read_text()


def test_easy_is_integrated_into_production_shared_ai():
    assert 'if difficulty == 1:' in AI
    assert 'spent_count * 5' in AI
    assert 'score += 2.0' in AI
    assert 'if win:' in AI
    assert 'var enemy_wins := _winning_replies' in AI
    assert 'score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)' in AI
    assert 'if difficulty >= 2:' in AI


def test_easy_is_approachable_and_all_three_levels_complete():
    counts={}
    for difficulty in (1,2,3):
        results=[match_variant(rule,difficulty,persona,seed) for rule,persona,seed in product(('C','D','CD'),range(3),range(8))]
        assert len(results)==72
        assert all(max(score)==3 and rounds<=12 and ai_moves>0 for score,rounds,ai_moves in results)
        counts[difficulty]=(sum(score[1]==3 for score,_,_ in results),sum(score[0]==3 for score,_,_ in results))
    # Same deterministic seeds and the same novice opponent as v141: 70/72
    # easy wins previously; new easy wins 44/72 while normal/hard retain 72.
    assert counts == {1:(44,28),2:(72,0),3:(72,0)}


def test_every_easy_move_legal_and_deterministic_across_seven_worlds():
    for rule in ('C','D','CD'):
        board=[[] for _ in range(9)]; reserves=[[True]*9 for _ in range(2)]
        for world in range(7):
            for persona in range(3):
                choice=choose(board,reserves,2,rule,1,persona)
                assert choice in legal(board,reserves,2,rule)
                assert choice==choose(board,reserves,2,rule,1,persona)
        # Cover ceiling and D/CD rank ladder are still governed by shared rules.
        board[0]=[(1,2),(2,5)]
        assert (9,0) not in legal(board,reserves,1,'C')
        assert (9,0) not in legal(board,reserves,1,'CD')


def test_hard_native_full_match_oracle_still_21_of_21():
    assert all(match(rule,world)[0]==[0,3] for rule,world in product(('C','D','CD'),range(7)))
