"""A5 v74: Gods of the Deep prebuilt LIVE backdrop/support, source checks only.
Offline PASS is NOT Godot compilation, gameplay, rendered visual or touch PASS.
"""
import hashlib, json, unittest, math
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets/a5_gods_prebaked_environment'
VISUAL=(ROOT/'scripts/world_visuals.gd').read_text(encoding='utf-8')
MAIN=(ROOT/'scripts/main.gd').read_text(encoding='utf-8')
MAN=json.loads((ASSETS/'asset_manifest.json').read_text(encoding='utf-8'))

def col(s):return tuple(int(s[i:i+2],16)/255 for i in (1,3,5))
def lerp(a,b,t):return tuple(x*(1-t)+y*t for x,y in zip(a,b))
def sample_gods_backdrop(x,y):
    u=x/511;v=y/287
    c=lerp(col('#021225'),col('#073a5d'),v*.78)
    beam=abs(math.sin(u*17+v*3))
    c=lerp(c,col('#11a9e3'),.15*beam**13*(1-v))
    for pillar in [.055,.14,.85,.94]:
        dx=abs(u-pillar)
        if dx<.019 and .12<v<.95:
            c=lerp(col('#05101d'),col('#25455a'),.25+.4*((x+y)%17)/17)
            if dx>.014:c=lerp(c,col('#26b9e6'),.32)
    for j in range(4):
        cx=.1+j*.265;cy=.29+(j%2)*.18
        px=(u-cx)*11;py=(v-cy)*11
        if px*px+(py+.05)**2<.13 and py<.18:
            c=lerp(c,col('#58d8ff'),.58)
        elif .12<py<.74 and abs(math.sin(px*17+py*3))>.91 and abs(px)<.28:
            c=lerp(c,col('#3e95c8'),.32)
    if v>.89:c=lerp(c,col('#030b17'),.65)
    if (x*23+y*43)%941<2:c=lerp(c,(1,1,1),.37)
    return tuple(round(min(1,max(0,v))*255) for v in c)

def sample_gods_plinth(x,y):
    edge=min(x,255-x,y,255-y)
    grain=((x*43+y*71+x*y*3)%137)/137
    c=lerp(col('#071826'),col('#31536a'),grain*.43)
    if edge<19:
        c=lerp(col('#020c16'),col('#315269'),edge/19)
        if edge==6 or edge==15:c=col('#17c9ef')
        elif edge==10:c=col('#b58b55')
    elif x%79<2 or y%83<2:c=lerp(c,(1,1,1),.13)
    if edge<25 and (x%46<3 or y%46<3):c=lerp(c,col('#bb8b4d'),.65)
    if y>235:c=tuple(t*.7 for t in c)
    return tuple(round(min(1,max(0,v))*255) for v in c)

class GodsV74(unittest.TestCase):
    def test_01_live_scene_loads_both_prebuilt_assets(self):
        self.assertIn('elif world == 3:\n\t\t\t# Deep-sea ruins',VISUAL)
        self.assertIn('load(GODS_ENV_ROOT + "/gods_underwater_backdrop.png")',VISUAL)
        self.assertIn('load(GODS_ENV_ROOT + "/gods_basalt_support.png")',VISUAL)
        self.assertIn('backdrop.texture = backdrop_cache[world]',VISUAL)
        self.assertIn('foundation.texture = gods_plinth',VISUAL)
    def test_02_first_entry_bypasses_212992_pixel_gdscript_generation(self):
        # 512x288 + 256x256, no Image.set_pixel loops on the live Gods route.
        self.assertLess(VISUAL.index('elif world == 3:\n\t\t\t# Deep-sea ruins'),VISUAL.index('backdrop_cache[world] = _make_backdrop(world)'))
        self.assertNotIn('gods_plinth = _make_gods_stone_plinth()',VISUAL)
        self.assertEqual(512*288+256*256,212992)
    def test_03_prebaked_images_match_manifest(self):
        self.assertEqual(len(MAN['assets']),2)
        self.assertFalse(MAN['contains_game_state_or_board_cells'])
        self.assertFalse(MAN['canonical_reference_images_changed'])
        for a in MAN['assets']:
            p=ASSETS/a['file']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),a['sha256'])
            with Image.open(p) as im:self.assertEqual(list(im.size),a['size'])
    def test_04_scalar_independent_backdrop_samples_match_pixels(self):
        with Image.open(ASSETS/'gods_underwater_backdrop.png') as im:
            for x in [0,17,49,72,114,184,239,300,408,482,511]:
                for y in [0,28,51,88,119,144,172,211,256,287]:
                    got=im.getpixel((x,y));expected=sample_gods_backdrop(x,y)
                    self.assertTrue(all(abs(a-b)<=1 for a,b in zip(got,expected)),(x,y,got,expected))
    def test_05_scalar_independent_plinth_samples_match_pixels(self):
        with Image.open(ASSETS/'gods_basalt_support.png') as im:
            for x in [0,4,6,10,15,19,22,46,78,111,192,240,255]:
                for y in [0,6,10,15,18,23,79,128,235,237,255]:
                    got=im.getpixel((x,y));expected=sample_gods_plinth(x,y)
                    self.assertTrue(all(abs(a-b)<=1 for a,b in zip(got,expected)),(x,y,got,expected))
    def test_06_no_flat_reference_screenshot_or_game_state_baked(self):
        self.assertIn('chart.texture = _canonical_cell_texture(world, cell_index)',VISUAL)
        self.assertIn('world_visuals.piece_texture(current_world',MAIN)
        self.assertIn('rank.text = str(int(top.rank))',MAIN)
        self.assertIn('board_stacks[selected_cell].append',MAIN)
        self.assertIn('var gods_cell_cache: Dictionary',VISUAL)
    def test_07_seven_exact_accepted_references_unchanged(self):
        approved=json.loads((ROOT/'tools/approved_seven_world_manifest.json').read_text())
        self.assertEqual(len(approved['images']),7)
        for item in approved['images']:
            hits=list((ROOT/'assets').rglob(item['file'].replace('.png','_canon_source.png')))
            self.assertEqual(len(hits),1,item['file'])
            self.assertEqual(hashlib.sha256(hits[0].read_bytes()).hexdigest(),item['sha256'])
    def test_08_shared_ai_and_pirate_unchanged(self):
        self.assertIn('const AIOpponent = preload("res://scripts/ai_opponent.gd")',MAIN)
        self.assertTrue((ROOT/'scripts/pirate_opening_campaign.gd').exists())
        self.assertTrue((ROOT/'scripts/pirate_opening_choice_surface.gd').exists())
    def test_09_runtime_fixture_is_integrated_but_not_claimed_executed(self):
        src=(ROOT/'tests/a5_v74_gods_environment_runtime_smoke.gd').read_text()
        for token in ['_set_world", 3','gods_underwater','get("board_stacks")','for i in range(9)','quit(1)','A5_V74_GODS_ENV_RUNTIME_PASS']:
            self.assertIn(token,src)
    def test_10_northern_fast_path_and_six_worlds_remain(self):
        self.assertIn('load(NORTHERN_ENV_ROOT + "/north_fjord_backdrop.png")',VISUAL)
        self.assertIn('world >= 1 and world <= 6',VISUAL)
        self.assertIn('scenery.visible = world != 0',VISUAL)

if __name__=='__main__':unittest.main()
