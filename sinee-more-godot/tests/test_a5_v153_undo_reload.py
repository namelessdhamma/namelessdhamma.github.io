"""v153 optional Undo persistence: source checks and independent JSON edge cases.

No native Godot binary in this runner. Native production-handler fixture is
registered as BLUE_SEA_UNDO_RELOAD_PASS and remains unexecuted here.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text()


def body(name):
    m = re.search(rf"^(?:static )?func {re.escape(name)}\(", SOURCE, re.M)
    assert m, name
    next_m = re.search(r"\n(?:static )?func ", SOURCE[m.end():])
    return SOURCE[m.start():m.end() + next_m.start() if next_m else len(SOURCE)]


def fingerprint(state):
    board = [[[int(p["player"]), int(p["rank"])] for p in stack]
             for stack in state["board"]]
    fields = [state["rule"], board, state["reserves"], int(state["turn"]),
              int(state["moves"]), int(state["round"]), state["score"],
              int(state["winner"]), state["win_line"], state["game_over"],
              state["draw"], int(state["match_winner"]), int(state["blocked_player"])]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def snapshot(moves=0):
    board = [[] for _ in range(9)]
    reserves = [[True] * 9, [True] * 9]
    if moves:
        board[0].append({"player": 1, "rank": 1})
        reserves[0][0] = False
    return {"schema": 1, "rule": "CD", "board": board, "reserves": reserves,
            "turn": 2 if moves else 1, "moves": moves, "round": 1,
            "score": [0, 0], "winner": 0, "win_line": [], "game_over": False,
            "draw": False, "match_winner": 0, "blocked_player": 0,
            "reserve_scroll": [0, 0]}


class UndoReloadTests(unittest.TestCase):
    def test_sidecar_not_match_authority(self):
        save = body("_save_match")
        self.assertIn('_write_match_atomically(MATCH_STATE_PATH, _match_snapshot())', save)
        self.assertLess(save.index('_write_match_atomically('), save.index('_write_undo_journal('))
        self.assertIn('push_warning(', save)
        self.assertIn('_match_save_dirty = false', save)
        self.assertNotIn('_match_save_dirty = true', save.split('else:', 1)[0])

    def test_restore_only_after_valid_primary_or_backup(self):
        load = body("_load_match")
        self.assertLess(load.index('_read_valid_match_at(MATCH_STATE_PATH)'), load.index('_apply_match_snapshot(restored)'))
        self.assertLess(load.index('_apply_match_snapshot(restored)'), load.index('_restore_undo_journal('))
        self.assertLess(load.index('_reconcile_restored_turn()'), load.index('_restore_undo_journal('))
        self.assertIn('if DisplayServer.get_name() == "headless":', load)

    def test_bound_and_full_history_validation(self):
        v = body("_undo_journal_valid")
        for token in ('history.size() > 18', '_match_snapshot_valid(before)',
                      '_undo_single_placement_valid(before, after, player)',
                      'range(history.size() - 1, -1, -1)', 'after = before'):
            self.assertIn(token, v)
        transition = body('_undo_single_placement_valid')
        for token in ('int(before["moves"]) + 1', 'int(before["turn"]) != player',
                      'current.size() != prior.size() + 1', 'used_rank',
                      'prior_available != current_available', 'expected_score'):
            self.assertIn(token, transition)

    def test_fingerprint_ignores_scroll_and_dictionary_order(self):
        f = body("_undo_match_fingerprint")
        self.assertNotIn('reserve_scroll', f)
        self.assertIn('ranks.append([int(piece["player"]), int(piece["rank"])])', f)
        a = snapshot(1)
        b = json.loads(json.dumps(a))
        b['reserve_scroll'] = [500, 20]
        b['board'][0][0] = {'rank': 1, 'player': 1}
        self.assertEqual(fingerprint(a), fingerprint(b))
        b['board'][0][0]['rank'] = 2
        self.assertNotEqual(fingerprint(a), fingerprint(b))

    def test_different_game_rejects_stale_journal(self):
        before, after = snapshot(), snapshot(1)
        self.assertNotEqual(fingerprint(before), fingerprint(after))
        modified = json.loads(json.dumps(after))
        modified['turn'] = 1
        self.assertNotEqual(fingerprint(modified), fingerprint(after))
        modified = json.loads(json.dumps(after))
        modified['rule'] = 'C'
        self.assertNotEqual(fingerprint(modified), fingerprint(after))

    def test_atomic_temp_readback_and_version(self):
        writer, reader = body('_write_undo_journal'), body('_read_undo_journal')
        self.assertLess(writer.index('file.flush()'), writer.index('JSON.parse_string(check.get_as_text())'))
        self.assertLess(writer.index('JSON.parse_string(check.get_as_text())'), writer.index('DirAccess.rename_absolute('))
        self.assertIn('_read_undo_journal(path, state)', writer)
        self.assertIn('parsed["fingerprint"] != _undo_match_fingerprint(state)', reader)
        self.assertIn('_undo_journal_valid(parsed["history"], state)', reader)
        self.assertIn('TYPE_FLOAT', reader)
        self.assertIn('TYPE_FLOAT', body('_undo_journal_valid'))

    def test_all_mutations_keep_journal_in_sync(self):
        for name in ('_on_primary', '_undo_last_move', '_reset_round'):
            self.assertIn('_save_match()', body(name), name)
        self.assertIn('_undo_history.clear()', body('_reset_round'))
        self.assertIn('var original_history := _undo_history.duplicate(true)', body('_run_headless_undo_reload_smoke'))

    def test_native_fixture_registered_and_isolated(self):
        smoke = body('_run_headless_undo_reload_smoke')
        self.assertIn('user://a5_undo_reload_smoke_v153.json', smoke)
        self.assertIn('_undo_last_move()', smoke)
        self.assertIn('BLUE_SEA_UNDO_RELOAD_PASS', smoke)
        self.assertNotIn('MATCH_STATE_PATH', smoke)
        self.assertNotIn('UNDO_STATE_PATH', smoke)
        self.assertIn('_run_headless_undo_reload_smoke()', SOURCE)

    def test_existing_game_snapshot_schema_unchanged(self):
        snap = body('_match_snapshot')
        self.assertIn('"schema": 1', snap)
        self.assertNotIn('"undo"', snap)
        self.assertNotIn('UNDO_STATE_PATH', body('_write_match_atomically'))


if __name__ == '__main__':
    unittest.main()
