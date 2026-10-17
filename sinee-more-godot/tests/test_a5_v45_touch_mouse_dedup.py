"""A5 v45: prevent one physical touch becoming two board actions.

These are source/behavior-model tests; they are NOT a Godot engine run.
The GDScript headless regression must be executed by a qualified runner.
"""
from __future__ import annotations
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
BASELINE = json.loads((ROOT / 'tests/a5_v44_project_baseline_hashes.json').read_text())

class TouchMouseDedup(unittest.TestCase):
    def test_both_touch_and_mouse_still_supported(self):
        block = MAIN.split('func _input(event:',1)[1].split('func _process(',1)[0]
        self.assertIn('event is InputEventScreenTouch and event.pressed',block)
        self.assertIn('event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT',block)

    def test_gui_areas_and_modal_still_protected(self):
        block = MAIN.split('func _input(event:',1)[1].split('func _process(',1)[0]
        self.assertIn('_modal_blocks_board_input()',block)
        self.assertIn('topbar.get_global_rect().has_point(position)',block)
        self.assertIn('dock.get_global_rect().has_point(position)',block)

    def test_dedup_occurs_after_board_hit_test_before_move(self):
        block = MAIN.split('func _input(event:',1)[1].split('func _process(',1)[0]
        self.assertLess(block.index('PerspectiveGeometry.cell_at('),block.index('frame - _last_board_press_frame'))
        self.assertLess(block.index('frame - _last_board_press_frame'),block.index('_on_cell_pressed(index)'))
        self.assertIn('position.distance_squared_to(_last_board_press_position) <= 16.0',block)
        self.assertIn('get_viewport().set_input_as_handled()\n\t\t\treturn',block)

    def test_dedup_window_bounded(self):
        self.assertIn('frame - _last_board_press_frame <= 2',MAIN)
        self.assertIn('var _last_board_press_frame := -100',MAIN)
        self.assertIn('var _last_board_press_position := Vector2(-10000.0, -10000.0)',MAIN)

    def test_independent_pointer_cell_allowed_in_headless_regression(self):
        block=MAIN.split('func _run_headless_touch_emulation_smoke()',1)[1].split('func _run_headless_reference_menu_smoke()',1)[0]
        self.assertIn('InputEventScreenTouch.new()',block)
        self.assertIn('InputEventMouseButton.new()',block)
        self.assertIn('assert(moves == 1 and selected_cell == -1,',block)
        self.assertIn('assert(selected_cell == 5 and moves == 1,',block)
        self.assertIn('round_number = saved_round',block)

    def test_headless_smoke_wired_into_existing_pipeline(self):
        block=MAIN.split('func _run_headless_geometry_and_interaction_smoke()',1)[1].split('func _run_headless_piece_visual_scale_smoke()',1)[0]
        self.assertIn('_run_headless_touch_emulation_smoke()',block)

    def test_no_legacy_rules_or_ai_source_mutation(self):
        for fn, expected_hash in BASELINE['protected_functions'].items():
            m=re.search(r'^func '+fn+r'\([^\n]*',MAIN,re.M)
            self.assertIsNotNone(m,fn)
            e=re.search(r'^(?:func |var |const )',MAIN[m.end():],re.M)
            text=MAIN[m.start():m.end()+e.start()] if e else MAIN[m.start():]
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),expected_hash,fn)
        self.assertEqual(hashlib.sha256((ROOT/'scripts/ai_opponent.gd').read_bytes()).hexdigest(),
                         BASELINE['files']['scripts/ai_opponent.gd'])

    def test_all_previous_project_files_except_main_identical(self):
        for rel, digest in BASELINE['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),digest,rel)

    def test_seven_approved_png_sources_unchanged(self):
        manifest=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        folders=['a5_void_ranked','a5_pirate_ranked','a5_atlantis_ranked','a5_gods_ranked','a5_sand_ranked','a5_night_ranked','a5_northern_ranked']
        for i,folder in enumerate(folders):
            (src,)=list((ROOT/'assets'/folder).glob('*canon_source.png'))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),manifest['images'][i]['sha256'])

    def test_deterministic_event_sequence_model(self):
        # Independent logic model: first tap commits, duplicate is suppressed,
        # distinct-cell tap is allowed. This is NOT evidence of Godot runtime.
        def play(dedup):
            frame, last_frame, last_pos = 120,-100,(-999,-999)
            moves, turn, selected_cell, selected_reserve=0,1,-1,0
            for pos in [(100,100),(100,100),(140,100)]:
                if dedup and frame-last_frame<=2 and sum((a-b)**2 for a,b in zip(pos,last_pos))<=16:
                    continue
                last_frame,last_pos=frame,pos
                cell=4 if pos==(100,100) else 5
                selected_cell=cell
                if selected_reserve>=0:
                    moves+=1;turn=2;selected_cell=-1;selected_reserve=-1
            return moves,turn,selected_cell
        self.assertEqual(play(False),(1,2,5))
        self.assertEqual(play(True),(1,2,5))
        # Compare the two-event prefix: the unfixed duplicate ghost-selects.
        def two_event_prefix(dedup):
            moves,selected_cell,selected_reserve,last_frame,last_pos=0,-1,0,-100,(-999,-999)
            for pos in [(100,100),(100,100)]:
                if dedup and 120-last_frame<=2 and pos==last_pos:continue
                last_frame,last_pos=120,pos
                selected_cell=4
                if selected_reserve>=0:
                    moves+=1;selected_reserve=-1;selected_cell=-1
            return moves,selected_cell
        self.assertEqual(two_event_prefix(False),(1,4))
        self.assertEqual(two_event_prefix(True),(1,-1))

if __name__ == '__main__':
    unittest.main()
