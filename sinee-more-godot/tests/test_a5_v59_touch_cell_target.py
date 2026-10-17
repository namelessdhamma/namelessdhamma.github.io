"""Seven-world low-height touch hit-target model; NOT engine or real-phone PASS."""
import hashlib
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO = (ROOT / 'scripts/perspective_board_geometry.gd').read_text()
MAIN = (ROOT / 'scripts/main.gd').read_text()
CORNER_BLOCK = GEO.split('const GRID_CORNERS := [', 1)[1].split('\n]', 1)[0]
QUADS = []
for line in CORNER_BLOCK.splitlines():
    pts = [(float(x), float(y)) for x,y in re.findall(r'Vector2\((\d+\.\d+), (\d+\.\d+)\)', line)]
    if len(pts) == 4:
        QUADS.append(pts)
assert len(QUADS) == 7


def board_quad(world, width=746, height=210):
    p = QUADS[world]
    cx = sum(x for x,y in p)/4
    cy = sum(y for x,y in p)/4
    shift = -min(height*0.045,13)
    return [((cx+(x-cx)*1.12)/1672*width, (cy+(y-cy)*1.12)/941*height+shift) for x,y in p]


def bilinear(q,u,v):
    return tuple(((q[0][i]*(1-u)+q[1][i]*u)*(1-v)+(q[3][i]*(1-u)+q[2][i]*u)*v) for i in (0,1))


def cell_quad(world,cell,width=746,height=210):
    q=board_quad(world,width,height)
    c=cell%3;r=cell//3
    return [bilinear(q,c/3,r/3),bilinear(q,(c+1)/3,r/3),bilinear(q,(c+1)/3,(r+1)/3),bilinear(q,c/3,(r+1)/3)]


def inside(q,p):
    sign=0
    for i in range(4):
        a=q[i];b=q[(i+1)%4]
        cross=(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        if abs(cross)<1e-4:continue
        n=1 if cross>0 else -1
        if sign and sign!=n:return False
        sign=n
    return True


def exact(world,p):
    return next((i for i in range(9) if inside(cell_quad(world,i),p)), -1)


def touch(world,p,minimum=44):
    i=exact(world,p)
    if i>=0:return i
    if minimum<=0:return -1
    candidates=[]
    for i in range(9):
        q=cell_quad(world,i)
        c=(sum(x for x,y in q)/4,sum(y for x,y in q)/4)
        if abs(p[0]-c[0])<=minimum/2 and abs(p[1]-c[1])<=minimum/2:
            candidates.append(((p[0]-c[0])**2+(p[1]-c[1])**2,i))
    return min(candidates)[1] if candidates else -1


class TestA5V59(unittest.TestCase):
    def test_01_shared_touch_geometry_and_pointer_unchanged(self):
        self.assertIn('static func cell_at_touch(',GEO)
        self.assertIn('var exact := cell_at(world, point, viewport)',GEO)
        self.assertIn('var best_distance := INF',GEO)
        self.assertIn('press_kind == "touch" else PerspectiveGeometry.cell_at',MAIN)
        self.assertIn('ceilf(_minimum_touch_physical_px() / _physical_pixel_scale())',MAIN)

    def test_02_seven_worlds_nine_centers_hit_exact_cell(self):
        for world in range(7):
            for i in range(9):
                q=cell_quad(world,i)
                center=(sum(x for x,y in q)/4,sum(y for x,y in q)/4)
                self.assertEqual(touch(world,center),i,(world,i))

    def test_03_real_low_height_rows_below_44_trigger_fallback_need(self):
        for world in range(7):
            heights=[]
            for i in range(9):
                q=cell_quad(world,i)
                heights.append(math.dist(q[0],q[3]))
            self.assertLess(min(heights),44,(world,min(heights)))

    def test_04_expansion_around_top_row_center_reaches_outside_polygon(self):
        for world in range(7):
            for i in range(3):
                q=cell_quad(world,i)
                center=(sum(x for x,y in q)/4,sum(y for x,y in q)/4)
                outside=(center[0],center[1]-22)
                self.assertEqual(exact(world,outside),-1,(world,i,outside))
                self.assertEqual(touch(world,outside),i,(world,i))
                self.assertEqual(touch(world,outside,0),-1)

    def test_05_no_far_offboard_hits(self):
        for world in range(7):
            for p in [(0,0),(745,0),(0,209),(745,209),(-500,-500)]:
                self.assertEqual(touch(world,p),-1,(world,p))

    def test_06_every_cell_center_44px_square_maps_to_some_live_cell(self):
        for world in range(7):
            for i in range(9):
                q=cell_quad(world,i)
                cx=sum(x for x,y in q)/4;cy=sum(y for x,y in q)/4
                for dx in (-21.9,0,21.9):
                    for dy in (-21.9,0,21.9):
                        self.assertIn(touch(world,(cx+dx,cy+dy)),range(9),(world,i,dx,dy))

    def test_07_reference_pngs_unchanged(self):
        checks={
            '01_nd_premium_void_canon_source.png':'00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
            '02_pirate_sea_canon_source.png':'0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
            '03_atlantis_canon_source.png':'2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
            '04_gods_of_the_deep_canon_source.png':'10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
            '05_sand_sea_canon_source.png':'01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
            '06_night_sea_canon_source.png':'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
            '07_northern_sea_canon_source.png':'3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775',
        }
        for name,h in checks.items():
            matches=list((ROOT/'assets').rglob(name))
            self.assertEqual(len(matches),1,name)
            self.assertEqual(hashlib.sha256(matches[0].read_bytes()).hexdigest(),h)

if __name__=='__main__': unittest.main()
