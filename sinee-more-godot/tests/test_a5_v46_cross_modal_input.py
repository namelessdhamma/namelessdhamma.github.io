"""A5 v46 source integrity + deterministic cross-modal input models (not engine proof)."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text()
INPUT = MAIN.split("func _input(event:", 1)[1].split("func _process(", 1)[0]
SMOKE = MAIN.split("func _run_headless_touch_emulation_smoke()", 1)[1].split("func _run_headless_reference_menu_smoke()", 1)[0]
BASE = json.loads((ROOT / "tests/a5_v45_complete_baseline_hashes.json").read_text())


def accept_events(events):
    """Independent state-machine model for the exact intended guard; no Godot runtime claim."""
    last_kind, last_frame, last_position = "none", -100, (-10000, -10000)
    accepted = []
    for kind, frame, position, index in events:
        if kind == "touch" and index != 0:
            continue
        dist2 = sum((a-b)**2 for a,b in zip(position, last_position))
        if kind != last_kind and frame >= last_frame and frame-last_frame <= 2 and dist2 <= 16:
            continue
        accepted.append((kind, position))
        last_kind, last_frame, last_position = kind, frame, position
    return accepted


class CrossModalInput(unittest.TestCase):
    def test_cross_modal_guard_is_before_board_move(self):
        self.assertLess(INPUT.index("PerspectiveGeometry.cell_at("), INPUT.index("press_kind != _last_board_press_kind"))
        self.assertLess(INPUT.index("press_kind != _last_board_press_kind"), INPUT.index("_on_cell_pressed(index)"))
        self.assertIn("frame - _last_board_press_frame <= 2", INPUT)
        self.assertIn("position.distance_squared_to(_last_board_press_position) <= 16.0", INPUT)

    def test_source_discriminates_touch_from_mouse(self):
        self.assertIn('press_kind = "touch"', INPUT)
        self.assertIn('press_kind = "mouse"', INPUT)
        self.assertIn("_last_board_press_kind = press_kind", INPUT)
        self.assertIn('var _last_board_press_kind := "none"', MAIN)

    def test_secondary_finger_is_excluded(self):
        self.assertIn("if touch_event.index != 0:", INPUT)
        self.assertIn("second_finger.index = 1", SMOKE)
        self.assertIn("Secondary finger must not change board selection", SMOKE)

    def test_rapid_same_kind_mouse_clicks_survive(self):
        e=[("mouse",120,(100,100),0),("mouse",120,(100,100),0)]
        self.assertEqual(len(accept_events(e)),2)
        self.assertIn("Second same-kind click must remain a distinct valid P2",SMOKE)

    def test_rapid_same_kind_touch_taps_survive(self):
        e=[("touch",120,(100,100),0),("touch",120,(100,100),0)]
        self.assertEqual(len(accept_events(e)),2)

    def test_touch_then_emulated_mouse_suppressed(self):
        e=[("touch",120,(100,100),0),("mouse",121,(102,101),0)]
        self.assertEqual(len(accept_events(e)),1)

    def test_mouse_then_touch_echo_suppressed(self):
        e=[("mouse",120,(100,100),0),("touch",121,(101,102),0)]
        self.assertEqual(len(accept_events(e)),1)

    def test_distinct_position_is_not_suppressed(self):
        e=[("touch",120,(100,100),0),("mouse",120,(140,100),0)]
        self.assertEqual(len(accept_events(e)),2)

    def test_echo_window_expires(self):
        e=[("touch",120,(100,100),0),("mouse",123,(100,100),0)]
        self.assertEqual(len(accept_events(e)),2)

    def test_multitouch_secondary_is_ignored(self):
        e=[("touch",120,(100,100),0),("touch",120,(150,100),1)]
        self.assertEqual(len(accept_events(e)),1)

    def test_board_ui_and_ai_guards_retained(self):
        for token in ["_modal_blocks_board_input()", "topbar.get_global_rect().has_point(position)", "dock.get_global_rect().has_point(position)", "ai_enabled and turn == 2", "get_viewport().set_input_as_handled()"]:
            self.assertIn(token, INPUT)

    def test_previous_archive_preserved_except_main(self):
        for rel,digest in BASE['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),digest,rel)

    def test_seven_canon_pngs_still_match_manifest(self):
        manifest=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        folders=['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked','a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
        for i,folder in enumerate(folders):
            (src,)=list((ROOT/'assets'/folder).glob('*canon_source.png'))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),manifest['images'][i]['sha256'])

    def test_headless_smoke_still_wired(self):
        pipeline=MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1].split('func _run_headless_piece_visual_scale_smoke()',1)[0]
        self.assertIn('_run_headless_touch_emulation_smoke()',pipeline)

if __name__ == '__main__':
    unittest.main()
