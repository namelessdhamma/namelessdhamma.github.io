"""A5 v119: independent offline gesture-state model and source wiring tests.

These are NOT native Godot or physical-phone results.
"""
from pathlib import Path
import re
import pytest

SOURCE = (Path(__file__).resolve().parents[1] / 'scripts/main.gd').read_text(encoding='utf-8')


def body(name):
    match = re.search(r'^func ' + re.escape(name) + r'\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)', SOURCE, re.M | re.S)
    assert match, name
    return match.group(1)


class GestureModel:
    """Independent event-level oracle for the intended primary/secondary ordering."""
    def __init__(self):
        self.secondary = set()
        self.primary = False
        self.armed = False
        self.moves = 0

    def touch(self, index, pressed):
        if index != 0:
            if pressed:
                self.secondary.add(index)
                self.armed = False
            else:
                self.secondary.discard(index)
            return
        if pressed:
            self.primary = True
            self.armed = not self.secondary
        else:
            if self.primary and self.armed:
                self.moves += 1
            self.primary = False
            self.armed = False

    def focus_lost(self):
        self.secondary.clear()
        self.primary = False
        self.armed = False


@pytest.mark.parametrize('world', range(7))
@pytest.mark.parametrize('secondary_first', [True, False])
def test_multitouch_orders_never_commit(world, secondary_first):
    m = GestureModel()
    if secondary_first:
        m.touch(1, True)
        m.touch(0, True)
    else:
        m.touch(0, True)
        m.touch(1, True)
    assert not m.armed
    m.touch(1, False)
    m.touch(0, False)
    assert m.moves == 0 and not m.secondary
    m.touch(0, True)
    m.touch(0, False)
    assert m.moves == 1


@pytest.mark.parametrize('second_index', [1, 2, 3, 5])
def test_secondary_index_set_does_not_depend_on_finger_number(second_index):
    m = GestureModel()
    m.touch(second_index, True)
    m.touch(0, True)
    m.touch(second_index, False)
    m.touch(0, False)
    assert m.moves == 0


def test_secondary_tracking_is_live_not_a_one_time_boolean():
    m = GestureModel()
    m.touch(1, True)
    m.touch(2, True)
    m.touch(1, False)
    m.touch(0, True)
    assert not m.armed and m.secondary == {2}
    m.touch(2, False)
    m.touch(0, False)
    assert m.moves == 0


def test_focus_loss_clears_orphaned_finger():
    m = GestureModel()
    m.touch(2, True)
    m.focus_lost()
    m.touch(0, True)
    m.touch(0, False)
    assert m.moves == 1 and not m.secondary


def test_source_secondary_index_state_and_echo_suppression():
    src = body('_input')
    secondary = src.split('if touch.index != 0:', 1)[1].split('if not touch.pressed:', 1)[0]
    assert '_touch_secondary_indices[touch.index] = true' in secondary
    assert '_touch_secondary_indices.erase(touch.index)' in secondary
    assert '_cancel_pending_board_touch()' in secondary
    assert '_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS' in secondary
    primary_press = src.split('# Track ALL primary touches', 1)[1].split('if event is InputEventScreenDrag:', 1)[0]
    assert primary_press.index('if not _touch_secondary_indices.is_empty():') < primary_press.index('_touch_board_pending = true')


def test_focus_and_native_fixture_wired():
    assert '_touch_secondary_indices.clear()' in body('_notification')
    smoke = body('_run_headless_multitouch_order_smoke')
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'for secondary_first in [true, false]:' in smoke
    assert '_notification(NOTIFICATION_APPLICATION_FOCUS_OUT)' in smoke
    assert 'BLUE_SEA_MULTITOUCH_ORDER_PASS' in smoke
    assert '_run_headless_multitouch_order_smoke()' in body('_run_headless_geometry_and_interaction_smoke')


def test_no_parallel_rules_or_world_engine():
    assert SOURCE.count('func _on_primary() -> void:') == 1
    assert SOURCE.count('func _input(event: InputEvent) -> void:') == 1
    assert 'var _touch_secondary_indices: Dictionary = {}' in SOURCE
