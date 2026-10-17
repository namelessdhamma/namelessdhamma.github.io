"""v89 source/asset verification, not a Godot runtime or visual-parity PASS."""
from pathlib import Path
import hashlib
import re
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'scripts/main.gd').read_text()
GROUND=(ROOT/'scripts/piece_grounding.gd').read_text()
WORLD_FOLDERS=('void','pirate','atlantis','gods','sand','night','northern')

def fn(name):
    m=re.search(r'^func '+re.escape(name)+r'\([^\n]*\).*?(?=^func |^static func |\Z)',MAIN,re.M|re.S)
    assert m,name
    return m.group()

class PieceGrounding(unittest.TestCase):
    def test_01_alpha_bottoms_match_all_126_real_rank_assets(self):
        rows=re.findall(r'^\s*\[([\d, ]+)\],?\s*#',GROUND,re.M)
        self.assertEqual(len(rows),7)
        for w,folder in enumerate(WORLD_FOLDERS):
            actual=[int(n) for n in rows[w].split(',')]
            self.assertEqual(len(actual),9)
            for player in (1,2):
                assets=sorted((ROOT/f'assets/a5_{folder}_ranked').glob(f'*_p{player}.png'))
                self.assertEqual(len(assets),9)
                for rank,path in enumerate(assets,1):
                    im=Image.open(path).convert('RGBA')
                    self.assertEqual(im.size,(128,128))
                    self.assertEqual(im.getchannel('A').getbbox()[3],actual[rank-1],(w,player,rank))

    def test_02_north_rank_one_receives_real_downshift_while_rank_nine_is_nearly_grounded(self):
        # From the exact approved alpha bounds: 85/128 and 114/128.
        rank1=44*(124-85)/128
        rank9=44*(124-114)/128
        self.assertGreater(rank1,13)
        self.assertLess(rank9,4)
        self.assertGreater(rank1-rank9,9)
        self.assertIn('return extent * (TARGET_BASE_PX / 128.0 - bottom_fraction(world, rank))',GROUND)

    def test_03_void_remains_floating_and_never_gets_ground_offset(self):
        self.assertIn('if world == 0:\n\t\treturn 0.0',GROUND)
        refresh=fn('_refresh_perspective_layer')
        self.assertIn('if current_world == 0:',refresh)
        self.assertIn('luminous glass-dome halo',refresh)
        self.assertIn('contact.color = Color(0.015, 0.02, 0.035, 0.43)',refresh)

    def test_04_contacts_are_drawn_below_live_art_without_intercepting_touches(self):
        create=fn('_create_perspective_layer')
        self.assertLess(create.index('add_child(contact)'),create.index('add_child(icon)'))
        self.assertIn('contact.z_index = 3',create)
        self.assertIn('icon.z_index = 3',create)
        self.assertIn('PerspectiveGeometry.cell_at_touch(',fn('_input'))
        self.assertIn('_on_cell_pressed(index)',fn('_input'))

    def test_05_no_ghost_contacts_on_empty_cells_or_world_switch(self):
        refresh=fn('_refresh_perspective_layer')
        self.assertIn('contact.visible = not top.is_empty()',refresh)
        self.assertIn('contact.polygon = PackedVector2Array()',refresh)
        self.assertIn('var active_rank := int(top.rank)',refresh)
        self.assertIn('var active_player := int(top.player)',refresh)
        self.assertIn('contact_center := Vector2(center.x, base_y)',refresh)
        self.assertIn('contact.polygon = PieceGrounding.ellipse(',refresh)

    def test_06_native_smoke_is_connected_but_not_claimed_passed(self):
        self.assertIn('_run_headless_piece_grounding_smoke()',fn('_run_headless_geometry_and_interaction_smoke'))
        smoke=fn('_run_headless_piece_grounding_smoke')
        for marker in ('for world in range(WorldVisuals.WORLDS.size()):',
                       'for rank in [1, 5, 9]:',
                       'perspective_icons[4].position.y',
                       'perspective_ranks[4].text == str(rank)',
                       'board_stacks == saved_board and reserve_available == saved_reserves'):
            self.assertIn(marker,smoke)

    def test_07_shared_rules_ai_and_pirate_controller_not_replaced(self):
        self.assertEqual(MAIN.count('func _on_primary()'),1)
        self.assertEqual(MAIN.count('func _is_legal_move('),1)
        self.assertIn('const AIOpponent = preload(',MAIN)
        self.assertIn('PirateOpeningCampaign', (ROOT/'project.godot').read_text())
        self.assertIn('const WorldVisuals = preload(',MAIN)

    def test_08_all_seven_canon_hashes_unchanged(self):
        import json
        manifest=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(manifest['images']),7)
        for ref in manifest['images']:
            candidates=list((ROOT/'assets').rglob(ref['file'].replace('.png','_canon_source.png')))
            self.assertEqual(len(candidates),1,ref['world'])
            self.assertEqual(hashlib.sha256(candidates[0].read_bytes()).hexdigest(),ref['sha256'])

    def test_10_contact_footprint_stays_inside_cell_at_746x280(self):
        # Conservative affine approximation of the exact 3x3 perspective
        # grid. The contact is never an extra invisible touch region.
        geom=(ROOT/'scripts/perspective_board_geometry.gd').read_text()
        corners=re.findall(r'PackedVector2Array\(\[Vector2\(([^)]+)\), Vector2\(([^)]+)\), Vector2\(([^)]+)\), Vector2\(([^)]+)\)\]\)',geom)
        self.assertEqual(len(corners),7)
        rows=re.findall(r'^\s*\[([\d, ]+)\],?\s*#',GROUND,re.M)
        for w,quad in enumerate(corners):
            points=[tuple(float(x) for x in pair.split(',')) for pair in quad]
            cx=sum(x for x,y in points)/4
            cy=sum(y for x,y in points)/4
            p=[((cx+(x-cx)*1.12)*746/1672, (cy+(y-cy)*1.12)*280/941-12.6) for x,y in points]
            # The middle cell is safely away from the board edge.
            top=(sum(p[0][1]+p[1][1] for _ in [0])/2)*2/3 + (p[3][1]+p[2][1])/2/3
            bottom=(p[0][1]+p[1][1])/2/3 + (p[3][1]+p[2][1])/2*2/3
            center=(top+bottom)/2
            cell_h=bottom-top
            for rank in range(1,10):
                extent=min(44,cell_h*.88)
                alpha=int(rows[w].split(',')[rank-1])/128
                shift=0 if w==0 else extent*(124/128-alpha)
                base=center-extent/2+shift+extent*alpha
                if w:
                    self.assertLessEqual(base+extent*.065,bottom+0.8,(w,rank))
                    self.assertGreaterEqual(base-extent*.065,top,(w,rank))

    def test_09_footprint_ellipse_is_finite_and_never_a_hit_control(self):
        self.assertIn('for i in range(16):',GROUND)
        self.assertIn('PackedVector2Array()',GROUND)
        self.assertIn('points.append(center + Vector2(cos(angle) * radius_x, sin(angle) * radius_y))',GROUND)
        self.assertNotIn('Control.new()',GROUND)

if __name__=='__main__':unittest.main()
