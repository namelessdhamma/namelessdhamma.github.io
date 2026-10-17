"""A5 v53: structural and independent physical-viewport regression.

This cannot certify actual Godot rendering or real touch. Run in Godot to close
PLAYABLE/visual gates; these tests only establish source contract and model.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/main.gd").read_text()


def body(name):
    start = SOURCE.index(f"func {name}(")
    end = SOURCE.find("\nfunc ", start + 1)
    return SOURCE[start:end if end >= 0 else None]


def physical_model(width, height):
    mobile = min(width, height) <= 360
    portrait = width < height
    return {"mobile": mobile, "status_visible": not mobile,
            "rotate_visible": portrait, "board_input_allowed": not portrait}


class PhysicalViewportRotationGate(unittest.TestCase):
    def test_phone_landscape_compact(self):
        self.assertEqual(physical_model(746, 280), dict(mobile=True, status_visible=False,
                         rotate_visible=False, board_input_allowed=True))

    def test_phone_portrait_rotates_without_desktop_menu(self):
        self.assertEqual(physical_model(280, 746), dict(mobile=True, status_visible=False,
                         rotate_visible=True, board_input_allowed=False))

    def test_desktop_landscape_keeps_status(self):
        self.assertEqual(physical_model(1280, 720), dict(mobile=False, status_visible=True,
                         rotate_visible=False, board_input_allowed=True))

    def test_phone_threshold_both_orientations(self):
        self.assertTrue(physical_model(640, 360)["mobile"])
        self.assertTrue(physical_model(360, 640)["mobile"])

    def test_mobile_mode_uses_physical_short_edge(self):
        x = body("_use_mobile_menu")
        self.assertIn("get_window().size", x)
        self.assertIn("mini(physical.x, physical.y) <= 360", x)
        self.assertNotIn("get_viewport_rect", x)

    def test_initial_status_is_physical(self):
        x = body("_prepare_world_shell")
        self.assertIn('center.get_node("Status").visible = not _use_mobile_menu()', x)
        self.assertNotIn("get_viewport_rect().size.y >= 360", x)

    def test_resize_resynchronizes_status(self):
        x = body("_sync_mobile_menu_trigger")
        self.assertIn('status.visible = not phone', x)
        self.assertIn('mobile_menu_button.visible = phone', x)

    def test_rotation_gate_called_on_start_and_every_frame(self):
        self.assertIn("_sync_orientation_gate()", body("_ready"))
        self.assertIn("_sync_orientation_gate()", body("_process"))

    def test_orientation_message_and_live_overlay(self):
        x = body("_create_orientation_overlay")
        for token in ['CanvasLayer.new()', 'overlay_layer.layer = 100', 'ColorRect.new()', 'Control.MOUSE_FILTER_STOP',
                      'Поверните телефон горизонтально', 'Control.PRESET_FULL_RECT']:
            self.assertIn(token, x)

    def test_portrait_blocks_board_before_gui(self):
        x = body("_modal_blocks_board_input")
        self.assertIn("orientation_overlay != null and orientation_overlay.visible", x)
        self.assertIn("return true", x)
        self.assertIn("_modal_blocks_board_input()", body("_input"))

    def test_rotation_preserves_game_state(self):
        x = body("_sync_orientation_gate")
        for forbidden in ["_reset_round(", "board_stacks =", "reserve_available =", "match_score =", "_set_world("]:
            self.assertNotIn(forbidden, x)

    def test_portrait_closes_transient_menu_only(self):
        x = body("_sync_orientation_gate")
        self.assertIn("mobile_menu_panel.hide()", x)
        self.assertNotIn("_on_menu()", x)

if __name__ == '__main__':
    unittest.main()
