"""A5 v90: actual shared Godot source + deterministic model checks.

This verifies the turn/visibility state machine but is NOT physical Android
scrolling, native Godot execution, or visual parity acceptance.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()


def fn(name):
    m = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\).*?(?=^func |^static func |\Z)', SOURCE, re.M | re.S)
    assert m, name
    return m.group()


class ScrollModel:
    """Model old-visibility capture and new-visibility deferred restore."""
    def __init__(self, max_scroll=(700, 400)):
        self.saved = [0, 0]
        self.last = 1
        self.turn = 1
        self.visible = True
        self.offset = 0
        self.max_scroll = max_scroll

    def refresh(self, turn, visible):
        was_visible = self.visible
        if was_visible and self.last in (1, 2):
            self.saved[self.last - 1] = self.offset
        changed = self.last != turn or (not was_visible and visible)
        self.turn = turn
        self.visible = visible
        if changed:
            self.last = turn
            if visible:
                self.offset = min(self.saved[turn - 1], self.max_scroll[turn - 1])
        return changed and visible

    def reset(self):
        self.saved = [0, 0]
        self.last = 0
        self.offset = 0


def test_01_source_captures_before_visibility_change():
    s = fn('_refresh_surface')
    assert s.index('_reserve_scroll_by_player[_last_reserve_scroll_player - 1] = reserve_scroller.scroll_horizontal') < s.index('reserve.visible = player == turn')
    assert s.index('var reserve_was_visible :=') < s.index('reserve_scroller.visible = not game_over')
    assert 'call_deferred("_restore_active_reserve_scroll", turn)' in s
    assert 'if game_over:\n\t\t\t# Terminal UI replaces the reserve with Next; no stale offset is shown.\n\t\t\treserve_scroller.scroll_horizontal = 0' in s


def test_02_source_uses_per_player_storage_and_deferred_clamped_restore():
    assert 'var _reserve_scroll_by_player: Array[int] = [0, 0]' in SOURCE
    s = fn('_restore_active_reserve_scroll')
    for token in ('await get_tree().process_frame',
                  'not reserve_scroller.visible or turn != player',
                  '_last_reserve_scroll_player != player',
                  'bar.max_value - bar.page',
                  'clampi(_reserve_scroll_by_player[player - 1], 0, max_scroll)'):
        assert token in s
    assert 'call_deferred("_restore_active_reserve_scroll", turn)' in fn('_refresh_surface')


def test_03_ai_turn_hides_reserve_and_restores_human_scroll():
    m = ScrollModel()
    m.offset = 600  # human swiped to high ranks on a dense Android phone
    assert not m.refresh(2, False)
    assert m.saved == [600, 0]
    m.offset = 0  # hidden row may be clamped by engine layout
    assert m.refresh(1, True)
    assert m.offset == 600


def test_04_local_pvp_remembers_both_positions_independently():
    m = ScrollModel()
    m.offset = 550
    assert m.refresh(2, True)
    assert m.offset == 0
    m.offset = 300
    assert m.refresh(1, True)
    assert m.offset == 550
    assert m.refresh(2, True)
    assert m.offset == 300
    assert m.saved == [550, 300]


def test_05_same_turn_world_switch_does_not_jump_scroller():
    m = ScrollModel()
    m.offset = 475
    assert not m.refresh(1, True)
    assert m.offset == 475
    assert m.saved[0] == 475


def test_06_deferred_restore_clamps_after_rotation_or_reserve_resize():
    m = ScrollModel(max_scroll=(250, 100))
    m.offset = 600
    m.refresh(2, False)
    m.offset = 0
    assert m.refresh(1, True)
    assert m.offset == 250


def test_07_reset_only_resets_at_new_round_not_every_move():
    s = fn('_reset_round')
    assert '_reserve_scroll_by_player = [0, 0]' in s
    assert '_last_reserve_scroll_player = 0' in s
    assert 'reserve_scroller.scroll_horizontal = 0' in s
    m = ScrollModel()
    m.offset = 500
    m.refresh(2, True)
    m.offset = 200
    m.reset()
    m.refresh(1, True)
    assert m.saved == [0, 0] and m.offset == 0


def test_08_gameplay_and_touch_hit_targets_unchanged():
    assert 'reserve.visible = player == turn and not game_over and (not ai_enabled or player == 1)' in fn('_refresh_surface')
    assert 'reserve_scroller.visible = not game_over and (not ai_enabled or turn == 1)' in fn('_refresh_surface')
    assert 'PerspectiveGeometry.cell_at_touch(' in fn('_input')
    assert 'board_stacks[selected_cell].append(' in fn('_on_primary')
    assert 'ai_engine.choose_move(' in fn('_play_ai_turn')
    assert 'PirateOpeningCampaign' in (ROOT / 'project.godot').read_text()


def test_09_exact_approved_canon_is_byte_unchanged():
    manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
    assert len(manifest['images']) == 7
    for entry in manifest['images']:
        matches = list((ROOT / 'assets').rglob(entry['file'].replace('.png', '_canon_source.png')))
        assert len(matches) == 1, entry['world']
        assert hashlib.sha256(matches[0].read_bytes()).hexdigest() == entry['sha256']
