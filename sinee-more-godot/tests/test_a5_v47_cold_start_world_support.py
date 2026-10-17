"""A5 v47: structural cold-start dependency tests, NOT a Godot engine execution."""
import hashlib
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'scripts/main.gd').read_text(encoding='utf-8')
VISUALS=(ROOT/'scripts/world_visuals.gd').read_text(encoding='utf-8')
SCENE=(ROOT/'main.tscn').read_text(encoding='utf-8')


def body(source, name):
    m=re.search(rf'^func {re.escape(name)}\([^\n]*\) -> [^\n]+:\n',source,re.M)
    if not m: raise AssertionError(f'Missing function {name}')
    start=m.end()
    nxt=re.search(r'^func |^static func ',source[start:],re.M)
    return source[start:start+nxt.start()] if nxt else source[start:]

class ColdStartSupport(unittest.TestCase):
    def test_scene_does_not_precreate_material_node(self):
        self.assertNotIn('[node name="PhysicalSupport"',SCENE)
        self.assertNotIn('[node name="NorthernStonePlinth"',SCENE)

    def test_cold_start_has_one_world_initialization_before_any_surface_refresh(self):
        ready=body(MAIN,'_ready')
        self.assertEqual(ready.count('\t_set_world(current_world)'),1)
        self.assertNotIn('\t_refresh_surface()',ready)
        self.assertLess(ready.index('_prepare_world_shell()'),ready.index('_set_world(current_world)'))
        self.assertLess(ready.index('_create_perspective_layer()'),ready.index('_set_world(current_world)'))
        self.assertLess(ready.index('_set_world(current_world)'),ready.index('_update_status("ready")'))

    def test_world_switch_constructs_support_before_live_refresh(self):
        switch=body(MAIN,'_set_world')
        self.assertLess(switch.index('world_visuals.apply_world(self, current_world)'),switch.index('_refresh_surface()'))
        self.assertLess(switch.index('_refresh_surface()'),switch.index('_refresh_perspective_layer()'))

    def test_world_visuals_constructs_support_and_texture(self):
        apply=body(VISUALS,'apply_world')
        self.assertLess(apply.index('support = Panel.new()'),apply.index('foundation = TextureRect.new()'))
        self.assertIn('foundation.texture = pirate_plinth',apply)
        self.assertIn('foundation.texture = atlantis_plinth',apply)
        self.assertIn('foundation.texture = gods_plinth',apply)
        self.assertIn('foundation.texture = _canonical_cell_texture(4, 4)',apply)
        self.assertIn('foundation.texture = night_plinth',apply)
        self.assertIn('foundation.texture = northern_plinth',apply)
        self.assertIn('foundation.visible = world >= 1 and world <= 6',apply)

    def test_perspective_reader_requires_material_and_is_reached_by_refresh(self):
        refresh=body(MAIN,'_refresh_surface')
        reader=body(MAIN,'_refresh_perspective_layer')
        self.assertIn('_refresh_perspective_layer()',refresh)
        self.assertIn('PhysicalSupport/NorthernStonePlinth',reader)
        self.assertIn('assert(material != null',reader)

    def test_deferred_first_render_remains_after_world_application(self):
        layer=body(MAIN,'_create_perspective_layer')
        self.assertIn('call_deferred("_refresh_perspective_layer")',layer)
        ready=body(MAIN,'_ready')
        self.assertLess(ready.index('_create_perspective_layer()'),ready.index('_set_world(current_world)'))

    def test_seven_worlds_and_shared_renderer_unchanged(self):
        self.assertIn('for i in range(WorldVisuals.WORLDS.size()):',MAIN)
        self.assertIn('"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep"',VISUALS)
        self.assertIn('"Sand Sea", "Night Sea", "Northern Sea"',VISUALS)
        self.assertIn('const AIOpponent = preload(',MAIN)
        self.assertIn('const PerspectiveGeometry = preload(',MAIN)

if __name__=='__main__':unittest.main()
