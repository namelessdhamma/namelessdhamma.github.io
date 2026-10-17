"""Offline structural acceptance for A5 v49; not a Godot runtime/touch PASS."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT/'scripts/main.gd').read_text()

def body(name):
    match = re.search(rf'^func {re.escape(name)}\([^\n]*', MAIN, re.M)
    assert match, name
    next_func = re.search(r'^func ', MAIN[match.end():], re.M)
    return MAIN[match.start():match.end()+next_func.start() if next_func else len(MAIN)]

class MobileSettingsMenu(unittest.TestCase):
    def test_one_compact_main_menu_with_three_stable_submenus(self):
        b = body('_populate_game_menu')
        self.assertIn('popup.clear() # Keep the three stable child PopupMenu nodes',b)
        self.assertEqual(b.count('popup.add_submenu_node_item('),3)
        self.assertIn('popup.add_submenu_node_item("Правила · " + current_rule, rule_submenu, 100)',b)
        self.assertIn('popup.add_submenu_node_item("ИИ сложность · "',b)
        self.assertIn('popup.add_submenu_node_item("ИИ характер · "',b)
        self.assertNotIn('popup.add_radio_check_item(',b)
    def test_each_submenu_keeps_old_settings_id_contract(self):
        b=body('_populate_game_menu')
        self.assertIn('rule_submenu.add_radio_check_item(mode, 300 + mode_id)',b)
        self.assertIn('difficulty_submenu.add_radio_check_item(difficulties[level - 1], 399 + level)',b)
        self.assertIn('persona_submenu.add_radio_check_item(personas[persona_id], 410 + persona_id)',b)
        self.assertIn('rule_submenu.set_item_checked(',b)
        self.assertIn('difficulty_submenu.set_item_checked(',b)
        self.assertIn('persona_submenu.set_item_checked(',b)
        for token in ['elif id >= 300 and id <= 302:', 'elif id >= 400 and id <= 402:', 'elif id >= 410 and id <= 412:']:
            self.assertIn(token,body('_on_game_menu_item'))
    def test_rule_lock_preserved_for_submenu_and_choices(self):
        b=body('_populate_game_menu')
        self.assertIn('popup.set_item_disabled(popup.item_count - 1, not can_change)',b)
        self.assertIn('rule_submenu.set_item_disabled(rule_submenu.item_count - 1, not can_change)',b)
        self.assertIn('moves == 0 and round_number == 1',b)
    def test_nested_submenus_block_hidden_gameplay(self):
        b=body('_modal_blocks_board_input')
        self.assertIn('for submenu in [rule_submenu, difficulty_submenu, persona_submenu]:',b)
        self.assertIn('if submenu != null and submenu.visible:',b)
        for name in ['_input','_on_reserve_pressed','_on_cell_pressed','_unhandled_key_input']:
            self.assertIn('_modal_blocks_board_input()',body(name))
    def test_menu_geometry_is_bounded_to_actual_window(self):
        b=body('_configure_mobile_popup')
        self.assertIn('get_window().size.y - 12',b)
        self.assertIn('menu.max_size = Vector2i(',b)
        self.assertIn('v_separation',b)
        self.assertIn('_configure_mobile_popup(menu)',body('_populate_game_menu'))
    def test_stable_children_not_recreated_on_each_popup(self):
        b=body('_prepare_world_shell')
        self.assertEqual(b.count('= PopupMenu.new()'),3)
        self.assertIn('game_popup.add_child(submenu)',b)
        self.assertIn('submenu.id_pressed.connect(_on_game_menu_item)',b)
        self.assertNotIn('PopupMenu.new()',body('_populate_game_menu'))
    def test_reset_and_pirate_opening_unchanged(self):
        b=body('_populate_game_menu')
        for t in ['popup.add_item("Сбросить матч…", 1)', 'popup.add_item("Как играть · правила C/D/CD", 3)', 'popup.add_item("История · Рифы", 4)', 'popup.add_item("Следующий раунд", 2)']:
            self.assertIn(t,b)
        self.assertIn('reset_dialog.popup_centered()',body('_on_game_menu_item'))
        self.assertIn('pirate_surface.call("show_opening_choice")',body('_on_game_menu_item'))
    def test_headless_assertions_are_wired_not_claimed_run(self):
        self.assertIn('_run_headless_mobile_settings_smoke()',body('_run_headless_geometry_and_interaction_smoke'))
        b=body('_run_headless_mobile_settings_smoke')
        self.assertIn('popup.item_count <= 6',b)
        self.assertIn('Rules must lock after first move',b)
        self.assertIn('get_item_submenu_node(',b)
        self.assertIn('saved_world',b)
    def test_no_other_game_engine_or_art_changes(self):
        self.assertTrue((ROOT/'project.godot').is_file())
        self.assertTrue((ROOT/'scripts/ai_opponent.gd').is_file())
        self.assertTrue((ROOT/'scripts/pirate_opening_campaign.gd').is_file())

if __name__ == '__main__': unittest.main()
