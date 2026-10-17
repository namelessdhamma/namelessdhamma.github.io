"""A5 v95: closing a modal resumes a blocked real AI turn.

Static/source + small event-order model; not a Godot execution or touch PASS.
"""
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'scripts' / 'main.gd').read_text(encoding='utf-8')

def body(name):
    m = re.search(rf'^func {re.escape(name)}\([^\n]*\)[^\n]*:\n(.*?)(?=^func |^static func |\Z)', SRC, re.M | re.S)
    assert m, f'missing {name}'
    return m.group(1)

class DeferredAI:
    """Event ordering only, not a duplicate rules engine."""
    def __init__(self):
        self.ai = False
        self.turn = 2
        self.modal = True
        self.queued = False
        self.moves = 0
    def queue(self):
        if self.queued or not self.ai or self.modal or self.turn != 2:
            return
        self.queued = True
    def toggle(self):
        self.ai = not self.ai
        self.queue()
    def close(self, signal):
        self.modal = False
        if signal:
            self.queue()
    def tick(self):
        if self.queued:
            self.queued = False
            if self.ai and not self.modal and self.turn == 2:
                self.moves += 1
                self.turn = 1

class ModalResume(unittest.TestCase):
    def test_01_old_failure_reproduced(self):
        model = DeferredAI()
        model.toggle()
        model.close(signal=False)
        model.tick()
        self.assertEqual((model.moves, model.turn), (0, 2))

    def test_02_fixed_phone_close_moves_exactly_once(self):
        model = DeferredAI()
        model.toggle()
        model.tick()
        self.assertEqual(model.moves, 0)
        model.close(signal=True)
        model.close(signal=True)
        model.tick()
        model.tick()
        self.assertEqual((model.moves, model.turn), (1, 1))

    def test_03_resume_has_no_direct_board_mutation(self):
        b = body('_resume_ai_after_modal_close')
        self.assertIn('if not _modal_blocks_board_input():', b)
        self.assertIn('call_deferred("_queue_ai_turn_if_ready")', b)
        for forbidden in ('_on_primary()', 'board_stacks[', 'moves +=', 'turn ='):
            self.assertNotIn(forbidden, b)

    def test_04_phone_overlay_has_visibility_signal(self):
        b = body('_create_mobile_menu_panel')
        self.assertIn('mobile_menu_panel.visibility_changed.connect(_resume_ai_after_modal_close)', b)
        self.assertIn('mobile_menu_panel.hide()', b)

    def test_05_orientation_gate_has_visibility_signal(self):
        self.assertIn('orientation_overlay.visibility_changed.connect(_resume_ai_after_modal_close)', body('_create_orientation_overlay'))
        self.assertIn('orientation_overlay.visible = portrait', body('_sync_orientation_gate'))

    def test_06_native_popups_and_dialogs_are_covered(self):
        b = body('_prepare_world_shell')
        for snippet in ('game_popup.popup_hide.connect(_resume_ai_after_modal_close)',
                        'submenu.popup_hide.connect(_resume_ai_after_modal_close)',
                        'reset_dialog.visibility_changed.connect(_resume_ai_after_modal_close)',
                        'rules_dialog.visibility_changed.connect(_resume_ai_after_modal_close)'):
            self.assertIn(snippet, b)

    def test_07_pirate_overlay_close_is_covered(self):
        b = body('_ready')
        self.assertIn('PirateOpeningChoiceSurface/PirateOpeningChoice', b)
        self.assertIn('pirate_modal.visibility_changed.connect(_resume_ai_after_modal_close)', b)

    def test_08_deferred_ai_rechecks_modal_and_is_idempotent(self):
        self.assertIn('_ai_turn_queued or not ai_enabled or game_over or turn != 2 or _modal_blocks_board_input()', body('_queue_ai_turn_if_ready'))
        b = body('_play_ai_turn')
        self.assertIn('_ai_turn_queued = false', b)
        self.assertIn('_modal_blocks_board_input()', b)

    def test_09_production_smoke_covers_phone_and_portrait(self):
        b = body('_run_headless_ai_modal_resume_smoke')
        self.assertIn('_on_mobile_menu_action(106)', b)
        self.assertIn('mobile_menu_panel.hide()', b)
        self.assertIn('orientation_overlay.hide()', b)
        self.assertIn('assert(moves == 1 and turn == 1', b)
        self.assertIn('await _run_headless_ai_modal_resume_smoke()', body('_run_headless_geometry_and_interaction_smoke'))

    def test_10_existing_shared_gameplay_is_retained(self):
        for name in ('_is_legal_move', '_on_primary', '_on_cell_pressed', '_set_world', '_play_ai_turn'):
            self.assertIn(f'func {name}(', SRC)
        self.assertIn('const WorldVisuals = preload(', SRC)
        self.assertIn('const AIOpponent = preload(', SRC)

if __name__ == '__main__':
    unittest.main()
