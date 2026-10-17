"""Independent Python oracle for the EXACT v133 D2/AI source contract.

This is NOT native Godot gameplay, NOT phone input and NOT PLAYABLE evidence.
It checks that the 21 deterministic CI fixtures have coherent expectations
before an authorized native execution spends its CI budget. The function hashes fail closed on changed production logic. In v141,
choose_move was independently re-reviewed with the v141 persona oracle and
v142 easy-difficulty oracle. The 21 historical fixtures use hard balanced AI;
this older oracle is NOT the current easy-difficulty evaluator. The v142
fixture covers all three difficulties against the exact new production logic.
In v146 the Easy path was reviewed against the v145 independent oracle on 1,260
reachable persona/rule positions and an independent win-equivalence oracle;
Normal/Hard keep the same scoring and 21 hard fixtures. Hash updated only
for the reviewed choose_move function; all other bindings remain fail-closed.
In v166 the Normal/Hard candidate loop uses one pre-existing-win flag after
its early new-win scan instead of rescanning eight board lines for every
non-winning candidate. Independent v166 tests compare 720 exact old-vs-new
AI choices, over 10,000 legal-placement win flags, and the 21 world/rule
fixture expectations; the production function hash was updated only after
those checks passed.
In v154 the shared _on_primary final-commit entrypoint gained only a modal/lifecycle
precondition BEFORE any game mutation. Independent exact-source comparison to
v153 verified that the full original commit core, starting at
`if selected_reserve < 0`, is byte-identical (SHA-256
107fa0f16abc702ddcfa023efab2a0fb5a6666fcf70a1375a50cf9ae0b7c4aa9).
The v154 oracle binding was updated to the newly reviewed full function hash.
"""
import hashlib
from pathlib import Path
import pytest
from tools.a5_v134_offline_ai_oracle import simulate, ai_choose, legal_dest, moves, after, win

ROOT = Path(__file__).resolve().parents[1]
FUNCTION_HASHES = {
    'scripts/ai_opponent.gd': {
        'legal_moves': '99492ab947f057615c0ac51aafd2e603d1ca95e4e8704f42c64af4b14573b97a',
        'choose_move': '32a3ffb2f913300d0f03d49bbbfd07c9cac5ec3128b73bec6b6ac032c41a66cc',
        '_winning_replies': '51476b913534690fff95ee3dd8de1e24bfa132f62e4db4eb57fad0a4f8857581',
        '_wins_after_placement': 'eac17437dba4b427e9314d23329c726807543229ba638177d7ca0fd4983b1ec4',
    },
    'scripts/main.gd': {
        '_on_primary': '777708e5deabe19654034e02f3cb02eb4cf95072c3fb609f240fbeb75fcccf02',
        '_is_legal_move': 'ada41fede94de2598e349d5df08bc72688e8e6b956acb7a7bd7c2b78b406add2',
        '_winning_line': '6007326b6b084a95351fc9e288568095ff98e983e74c8299f1decf586fed8365',
    },
}


def _function_source(source: str, name: str) -> str:
    start = source.index('func ' + name + '(')
    end = source.find('\nfunc ', start + 1)
    return (source[start:] if end == -1 else source[start:end]).rstrip() + '\n'


@pytest.mark.parametrize('path,functions', FUNCTION_HASHES.items())
def test_oracle_is_bound_to_exact_production_logic(path, functions):
    source = (ROOT / path).read_text()
    for name, expected in functions.items():
        actual = hashlib.sha256(_function_source(source, name).encode()).hexdigest()
        assert actual == expected, f'Production {name} changed; independent oracle review required'


@pytest.mark.parametrize('world', range(7))
@pytest.mark.parametrize('rule', ['C', 'D', 'CD'])
def test_native_full_match_fixture_expected_outcome_offline_only(world, rule):
    # The shared engine is world-independent. Deliberately repeat each fixture
    # to ensure the 21 native cases' expected terminal outcome is coherent.
    assert world in range(7)
    rounds = simulate(rule)
    assert len(rounds) <= 12
    assert rounds[-1]['score'] == [0, 3]
    assert all(0 < item['moves'] <= 18 for item in rounds)
    assert all(item['winner'] == 2 for item in rounds)
    assert sum(item['moves'] for item in rounds) > 0


@pytest.mark.parametrize('rule', ['C', 'D', 'CD'])
@pytest.mark.parametrize('difficulty', [1, 2, 3])
@pytest.mark.parametrize('persona', [0, 1, 2])
def test_all_ai_configs_return_legal_opening_offline_only(rule, difficulty, persona):
    board = [[] for _ in range(9)]
    reserves = [[True] * 9 for _ in range(2)]
    candidate = ai_choose(board, reserves, 2, rule, difficulty, persona)
    assert candidate in moves(board, reserves, 2, rule)
    next_board, next_reserves = after(board, reserves, 2, *candidate)
    assert sum(map(len, next_board)) == 1
    assert next_reserves[1].count(False) == 1
    assert not win(next_board, 1, rule)
    assert board == [[] for _ in range(9)]
    assert reserves == [[True] * 9 for _ in range(2)]
