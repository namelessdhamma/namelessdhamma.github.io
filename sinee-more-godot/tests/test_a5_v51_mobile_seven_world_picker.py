"""A5 v51 source-contract checks; real Godot execution and touch are NOT claimed."""
from pathlib import Path
import hashlib, math, re, unittest
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'scripts/main.gd').read_text()

def body(name):
    m=re.search(r'^func '+re.escape(name)+r'\([^\n]*',MAIN,re.M)
    assert m,name
    n=re.search(r'^func ',MAIN[m.end():],re.M)
    return MAIN[m.start():m.end()+n.start() if n else len(MAIN)]

class SevenWorldPicker(unittest.TestCase):
    def test_native_popup_is_hidden_on_phone(self):
        b=body('_sync_mobile_menu_trigger')
        self.assertIn('world_picker.visible = not phone',b)
        self.assertIn('mobile_world_button.visible = phone',b)
    def test_desktop_selector_preserved(self):
        self.assertIn('popup.id_pressed.connect(_set_world)',body('_prepare_world_shell'))
        self.assertIn('world_picker.visible = not phone',body('_sync_mobile_menu_trigger'))
    def test_mobile_selector_is_real_button(self):
        b=body('_prepare_world_shell')
        self.assertIn('mobile_world_button = Button.new()',b)
        self.assertIn('mobile_world_button.pressed.connect(_open_mobile_worlds)',b)
        self.assertIn('topbar.add_child(mobile_world_button)',b)
    def test_mobile_selector_is_same_existing_modal(self):
        b=body('_open_mobile_worlds')
        for token in ['_modal_blocks_board_input()', '_render_mobile_menu_page("worlds")','mobile_menu_panel.show()']:
            self.assertIn(token,b)
        self.assertNotIn('PopupMenu.new()',b)
    def test_all_seven_dynamic_entries(self):
        b=body('_render_mobile_menu_page')
        self.assertIn('range(WorldVisuals.WORLDS.size())',b)
        self.assertIn('WorldVisuals.WORLDS[world_id]',b)
        self.assertIn('500 + world_id',b)
        self.assertIn('world_id == current_world',b)
    def test_world_choice_preserves_game_engine(self):
        b=body('_on_mobile_menu_action')
        self.assertIn('id >= 500 and id < 500 + WorldVisuals.WORLDS.size()',b)
        self.assertIn('_set_world(id - 500)',b)
        self.assertIn('mobile_menu_panel.hide()',b)
        for forbidden in ['_reset_round()', 'board_stacks =', 'reserve_available =', 'turn =', 'moves =']:
            self.assertNotIn(forbidden,b)
        self.assertEqual(MAIN.count('func _on_primary('),1)
        self.assertEqual(MAIN.count('func _play_ai_turn('),1)
    def test_seven_canon_pngs_present_and_sha256(self):
        expected={
            '01_nd_premium_void.png':'00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
            '02_pirate_sea.png':'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
            '03_atlantis.png':'2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
            '04_gods_of_the_deep.png':'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
            '05_sand_sea.png':'01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
            '06_night_sea.png':'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
            '07_northern_sea.png':'3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775'
        }
        files=list(ROOT.rglob('*.png'))
        for name,digest in expected.items():
            matches=[p for p in files if p.name in (name, name.removesuffix('.png')+'_canon_source.png')]
            self.assertGreaterEqual(len(matches),1,name)
            self.assertTrue(any(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p in matches),name)
    def test_mobile_choices_have_physical_44px_min(self):
        b=body('_mobile_menu_add')
        self.assertIn('ceilf(44.0 / _physical_pixel_scale())',b)
        for scale in [280/720,320/720,1.0]:
            self.assertGreaterEqual(math.ceil(44/scale)*scale,44)
    def test_modal_prevents_board_placement(self):
        self.assertIn('mobile_menu_panel != null and mobile_menu_panel.visible',body('_modal_blocks_board_input'))
        for fn in ['_input','_on_reserve_pressed','_on_cell_pressed']:
            self.assertIn('_modal_blocks_board_input()',body(fn))
    def test_headless_integration_smoke_wired(self):
        self.assertIn('_run_headless_mobile_world_selector_smoke()',body('_run_headless_geometry_and_interaction_smoke'))
        b=body('_run_headless_mobile_world_selector_smoke')
        for s in ['get_child_count() == 8','range(WorldVisuals.WORLDS.size())','_on_mobile_menu_action(500 + world_id)','board_stacks == saved_board','reserve_available == saved_reserve','turn == saved_turn','moves == saved_moves','match_score == saved_score','ai_enabled == saved_ai']:
            self.assertIn(s,b)
    def test_world_switch_reuses_canonical_live_scene(self):
        b=body('_set_world')
        for s in ['world_visuals.apply_world(self, current_world)','_refresh_surface()','_refresh_perspective_layer()']:
            self.assertIn(s,b)
    def test_no_new_campaign_or_engine(self):
        self.assertEqual(MAIN.count('func _set_world('),1)
        self.assertEqual(MAIN.count('func _on_primary('),1)
        self.assertEqual(MAIN.count('func _is_legal_move('),1)
        self.assertEqual(MAIN.count('func _on_menu('),1)

if __name__=='__main__':unittest.main()
