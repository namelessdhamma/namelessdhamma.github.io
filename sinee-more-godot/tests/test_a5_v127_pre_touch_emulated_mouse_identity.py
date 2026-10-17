"""A5 v127: prevent touch-generated mouse press BEFORE ScreenTouch down.

Static integration tests only. Native engine smoke is integrated in main.gd but
requires Godot 4.7.2; no physical touch or release acceptance is claimed.
"""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()


def body(name):
    start = MAIN.index('func ' + name + '(')
    end = MAIN.find('\nfunc ', start + 5)
    return MAIN[start:end if end >= 0 else None]


class TestPreTouchEmulatedMouseIdentity(unittest.TestCase):
    def test_emulated_mouse_device_guard_precedes_time_and_touch_guards(self):
        input_body = body('_input')
        mouse = input_body.split('if not (event is InputEventMouseButton):', 1)[1]
        guard = 'if mouse.device == InputEvent.DEVICE_ID_EMULATION:'
        self.assertIn(guard, mouse)
        self.assertLess(mouse.index(guard), mouse.index('if _touch_primary_active or not _touch_secondary_indices.is_empty():'))
        self.assertLess(mouse.index(guard), mouse.index('if _touch_multifinger_mouse_echo_deadline_msec > 0'))
        self.assertLess(mouse.index(guard), mouse.index('var frame := Engine.get_process_frames()'))
        self.assertIn('get_viewport().set_input_as_handled()\n\t\treturn', mouse[mouse.index(guard):mouse.index(guard)+140])

    def test_only_board_mouse_events_filtered_gui_controls_preserved(self):
        mouse = body('_input').split('if not (event is InputEventMouseButton):', 1)[1]
        self.assertLess(mouse.index('if topbar.get_global_rect().has_point('), mouse.index('if mouse.device == InputEvent.DEVICE_ID_EMULATION:'))
        self.assertLess(mouse.index('or dock.get_global_rect().has_point('), mouse.index('if mouse.device == InputEvent.DEVICE_ID_EMULATION:'))
        self.assertLess(mouse.index('var index := PerspectiveGeometry.cell_at('), mouse.index('if mouse.device == InputEvent.DEVICE_ID_EMULATION:'))
        self.assertNotIn('Input.emulate_mouse_from_touch = false', MAIN)
        self.assertIn('_on_cell_pressed(index)', mouse)

    def test_native_seven_world_smoke_covers_both_input_orders_and_physical_mouse(self):
        native = body('_run_headless_emulated_mouse_identity_smoke')
        self.assertIn('for world in range(WorldVisuals.WORLDS.size()):', native)
        self.assertIn('ghost.device = InputEvent.DEVICE_ID_EMULATION', native)
        self.assertIn('physical.device = InputEvent.DEVICE_ID_MOUSE', native)
        self.assertLess(native.index('_input(ghost)'), native.index('touch.pressed = true'))
        self.assertIn('assert(moves == 0 and selected_reserve == 0', native)
        self.assertIn('assert(moves == 0 and _touch_board_pending', native)
        self.assertIn('assert(moves == 1 and turn == 2 and not reserve_available[0][0]', native)
        self.assertIn('assert(moves == 1 and turn == 2,', native)
        self.assertIn('BLUE_SEA_EMULATED_MOUSE_PRE_TOUCH_PASS', native)
        self.assertIn('_run_headless_emulated_mouse_identity_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_gameplay_ai_pirate_and_all_worlds_still_shared(self):
        for name in ('_on_primary', '_is_legal_move', '_play_ai_turn', '_on_reserve_pressed', '_set_world'):
            self.assertIn('func ' + name + '(', MAIN)
        self.assertIn('const AIOpponent = preload(', MAIN)
        self.assertIn('PirateOpeningChoiceSurface', MAIN)
        self.assertIn('world_visuals.apply_world(self, current_world)', MAIN)
        self.assertIn('rank.text = str(int(top.rank))', MAIN)

    def test_approved_reference_images_are_unchanged(self):
        manifest = json.loads((ROOT / 'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 7)
        for item in manifest['images']:
            found = list((ROOT / 'assets').rglob(item['file'].replace('.png', '_canon_source.png')))
            self.assertEqual(len(found), 1, item['file'])
            self.assertEqual(hashlib.sha256(found[0].read_bytes()).hexdigest(), item['sha256'])

if __name__ == '__main__':
    unittest.main()
