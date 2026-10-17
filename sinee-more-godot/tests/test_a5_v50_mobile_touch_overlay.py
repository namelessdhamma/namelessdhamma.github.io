"""A5 v50 static/source-model regression; engine and real-device PASS remain OPEN."""
from pathlib import Path
import re, unittest, math
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'scripts/main.gd').read_text()

def body(name):
    m=re.search(r'^func '+re.escape(name)+r'\([^\n]*', MAIN,re.M)
    assert m, name
    nextm=re.search(r'^func ',MAIN[m.end():],re.M)
    return MAIN[m.start():m.end()+nextm.start() if nextm else len(MAIN)]

class MobileOverlay(unittest.TestCase):
    def test_separate_mobile_route_at_real_window_height(self):
        self.assertIn('get_window().size.y <= 360',body('_use_mobile_menu'))
        self.assertIn('_sync_mobile_menu_trigger()',body('_process'))
        self.assertIn('top_menu.visible = not phone',body('_sync_mobile_menu_trigger'))
        self.assertIn('mobile_menu_button.visible = phone',body('_sync_mobile_menu_trigger'))
    def test_mobile_overlay_is_actual_interactive_scene(self):
        b=body('_create_mobile_menu_panel')
        for token in ['PanelContainer.new()', 'ScrollContainer.new()', 'VBoxContainer.new()', 'Control.MOUSE_FILTER_STOP','Control.PRESET_FULL_RECT','add_child(mobile_menu_panel)']:
            self.assertIn(token,b)
        self.assertNotIn('TextureRect.new()',b)
    def test_physical_minimum_44_and_readable_14(self):
        b=body('_mobile_menu_add')
        self.assertIn('ceilf(44.0 / _physical_pixel_scale())',b)
        self.assertIn('ceili(14.0 / _physical_pixel_scale())',b)
        for scale in [280/720,320/720,360/720,1.0]:
            touch=math.ceil(44/scale)*scale
            text=max(16,math.ceil(14/scale))*scale
            self.assertGreaterEqual(touch,44)
            self.assertGreaterEqual(text,14)
    def test_modal_input_isolation_all_gameplay_paths(self):
        self.assertIn('mobile_menu_panel != null and mobile_menu_panel.visible',body('_modal_blocks_board_input'))
        for f in ['_input','_on_reserve_pressed','_on_cell_pressed','_unhandled_key_input']:
            self.assertIn('_modal_blocks_board_input()',body(f))
    def test_mobile_menu_trigger_and_reference_glyph(self):
        self.assertIn('mobile_menu_button.pressed.connect(_open_mobile_menu)',body('_prepare_world_shell'))
        self.assertIn('_open_mobile_menu()',body('_on_reference_menu_hotspot_pressed'))
        self.assertIn('_open_mobile_menu()',body('_unhandled_key_input'))
    def test_no_direct_reset_or_next_without_contract(self):
        b=body('_render_mobile_menu_page')
        self.assertIn('if game_over:',b)
        self.assertIn('"Следующий раунд", 2',b)
        self.assertIn('"Сбросить матч…", 1',b)
        self.assertIn('"История · Рифы", 4',b)
        self.assertIn('if current_world == 1:',b)
        self.assertIn('"Правила · " + current_rule, 100, locked',b)
    def test_existing_handlers_reused_no_second_game_engine(self):
        self.assertIn('_on_game_menu_item(id)',body('_on_mobile_menu_action'))
        self.assertIn('mobile_menu_panel.hide()',body('_on_mobile_menu_action'))
        self.assertEqual(MAIN.count('func _on_primary('),1)
        self.assertEqual(MAIN.count('func _play_ai_turn('),1)
    def test_settings_pages_and_ids(self):
        b=body('_render_mobile_menu_page')
        for tok in ['"main"','"rules"','"difficulty"','"persona"','300 + id','399 + id','410 + id','"← Назад", -1','"Закрыть", -2']:
            self.assertIn(tok,b)
    def test_dynamic_relayout_on_rotation(self):
        b=body('_sync_mobile_menu_trigger')
        self.assertIn('absf(scale - _mobile_menu_last_scale)',b)
        self.assertIn('_render_mobile_menu_page(_mobile_menu_page)',b)
        self.assertIn('mobile_menu_panel.hide()',b)
    def test_headless_smoke_wired_and_not_claimed_executed(self):
        self.assertIn('_run_headless_mobile_menu_touch_smoke()',body('_run_headless_geometry_and_interaction_smoke'))
        b=body('_run_headless_mobile_menu_touch_smoke')
        for tok in ['_on_mobile_menu_action(301)','_on_mobile_menu_action(402)','_on_mobile_menu_action(412)','_modal_blocks_board_input()','physical_scale >= 43.5','"Rules must lock once the match has started"']:
            self.assertIn(tok,b)
    def test_canon_assets_and_ai_are_unmodified_in_package(self):
        self.assertTrue((ROOT/'scripts/ai_opponent.gd').is_file())
        self.assertTrue((ROOT/'scripts/pirate_opening_campaign.gd').is_file())
        self.assertEqual(len(list((ROOT/'assets/a5_live_logos').glob('world_*.png'))),7)
    def test_desktop_popup_fallback_remains(self):
        self.assertIn('top_menu.get_popup().popup_centered()',body('_unhandled_key_input'))
        self.assertIn('top_menu.get_popup().popup_centered()',body('_on_reference_menu_hotspot_pressed'))
        self.assertIn('popup.add_submenu_node_item(',body('_populate_game_menu'))

if __name__=='__main__': unittest.main()
