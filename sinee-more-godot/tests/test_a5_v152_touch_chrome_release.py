"""A5 v152: a release/drag onto the active reserve cannot spend a board rank.

These are independent source and reference-derived geometry tests, NOT native
Godot execution or real touch evidence. The native scene smoke is registered
separately and must be executed by a qualified Godot 4.7.2 runner.
"""
from __future__ import annotations

from pathlib import Path
import math
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts/main.gd").read_text()
GEOMETRY = (ROOT / "scripts/perspective_board_geometry.gd").read_text()


def _body(name: str) -> str:
    match = re.search(r"^(?:static )?func " + re.escape(name) + r"\([^\n]*", MAIN, re.M)
    assert match, f"missing {name}"
    next_func = re.search(r"\n(?:static )?func ", MAIN[match.end():])
    end = match.end() + next_func.start() if next_func else len(MAIN)
    return MAIN[match.start():end]


def _reference_quads():
    rows = []
    for line in GEOMETRY.splitlines():
        if "PackedVector2Array([" in line and "# " in line:
            corners = [(float(x), float(y)) for x, y in re.findall(r"Vector2\(([-\d.]+), ([-\d.]+)\)", line)]
            if len(corners) == 4:
                rows.append(corners)
    assert len(rows) == 7
    return rows


def _board_quad(world: int, viewport_h: float):
    quad = _reference_quads()[world]
    center = (sum(x for x, _ in quad) / 4, sum(y for _, y in quad) / 4)
    shift = -min(viewport_h * 0.045, 13)
    return [((center[0] + (x - center[0]) * 1.12) / 1672 * 746,
             (center[1] + (y - center[1]) * 1.12) / 941 * viewport_h + shift)
            for x, y in quad]


def _visual_bottom(world: int, height: float):
    bottom = max(y for _, y in _board_quad(world, height))
    lip = 9 if world == 0 else max(9, 13 * max(.35, min(height / 720, 1)))
    return bottom + lip


def _safe_height(world: int, reserve_top: float):
    proposed = min(280, max(100, (reserve_top - 5) / .8))
    if _visual_bottom(world, proposed) <= reserve_top - 6:
        return proposed
    lo, hi = 0.0, proposed
    for _ in range(16):
        mid = (lo + hi) / 2
        if _visual_bottom(world, mid) <= reserve_top - 6:
            lo = mid
        else:
            hi = mid
    return max(1, lo)


def _bilinear(q, u, v):
    top = tuple(q[0][i] * (1-u) + q[1][i] * u for i in range(2))
    bottom = tuple(q[3][i] * (1-u) + q[2][i] * u for i in range(2))
    return tuple(top[i] * (1-v) + bottom[i] * v for i in range(2))


def _cell_quad(world, cell, height):
    q = _board_quad(world, height)
    col, row = cell % 3, cell // 3
    return [_bilinear(q, col/3, row/3), _bilinear(q, (col+1)/3, row/3),
            _bilinear(q, (col+1)/3, (row+1)/3), _bilinear(q, col/3, (row+1)/3)]


def _inside_convex(q, point):
    sign = 0
    for i in range(4):
        x0,y0 = q[i]; x1,y1 = q[(i+1)%4]
        cross = (x1-x0)*(point[1]-y0)-(y1-y0)*(point[0]-x0)
        if abs(cross)<1e-4:
            continue
        s = 1 if cross>0 else -1
        if sign and sign!=s:
            return False
        sign=s
    return True


def _edge_dist2(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/max(1e-9,dx*dx+dy*dy)))
    return (point[0]-a[0]-dx*t)**2+(point[1]-a[1]-dy*t)**2


def _touch_cell(world, point, height, min_target=44):
    for cell in range(9):
        if _inside_convex(_cell_quad(world,cell,height),point):
            return cell
    half=min_target*.5
    nearest=-1;best=(float('inf'),float('inf'))
    for cell in range(9):
        q=_cell_quad(world,cell,height)
        center=(sum(x for x,_ in q)/4,sum(y for _,y in q)/4)
        square=abs(point[0]-center[0])<=half and abs(point[1]-center[1])<=half
        shortest=min(math.dist(q[i],q[(i+1)%4]) for i in range(4))
        edge=min(_edge_dist2(point,q[i],q[(i+1)%4]) for i in range(4))
        margin=max(2,(min_target-shortest)/2)
        if not square and edge>margin*margin:
            continue
        cd=(point[0]-center[0])**2+(point[1]-center[1])**2
        if edge<best[0]-1e-4 or abs(edge-best[0])<=1e-4 and cd<best[1]:
            best=(edge,cd);nearest=cell
    return nearest


class TestChromeBoundary(unittest.TestCase):
    def test_shared_live_chrome_predicate_and_order(self):
        helper=_body("_touch_over_live_chrome")
        self.assertIn('get_node("SafeArea/Landscape/Center/TopBar")',helper)
        self.assertIn('get_node("SafeArea/Landscape/Center/ReserveDock")',helper)
        self.assertIn('topbar.get_global_rect(), dock.get_global_rect()',helper)
        pure=_body("_touch_over_chrome_rects")
        self.assertIn('topbar_rect.has_point(point) or dock_rect.has_point(point)',pure)
        event=_body("_input")
        release=event.split('if not touch.pressed:',1)[1].split('# Track ALL primary touches',1)[0]
        self.assertLess(release.index('if _touch_over_live_chrome(touch.position):'),release.index('var released_cell :='))
        self.assertLess(release.index('if _touch_over_live_chrome(touch.position):'),release.index('var max_drift :='))
        self.assertLess(release.index('_touch_board_pending = false'),release.index('if _touch_over_live_chrome(touch.position):'))
        drag=event.split('if event is InputEventScreenDrag:',1)[1].split('if not (event is InputEventMouseButton):',1)[0]
        self.assertLess(drag.index('if _touch_over_live_chrome(drag.position):'),drag.index('var max_drift :='))
        self.assertIn('_cancel_pending_board_touch()',drag)

    def test_seven_worlds_have_high_density_expanded_touch_overlap(self):
        # At native Android density 3x and 1:1 physical/logical scale, the
        # minimum safe target is 132 pixels. On 746x280, the bottom-row
        # expanded hit target crosses a live reserve dock at y=218.
        # This reproduces the old false-commit path: the same cell is hit at
        # y=216 (board side) and y=219 (reserve side), just 3px apart.
        # Actual device geometry remains a separate qualification gate.
        dock_y=218.
        start=(373.,216.)
        release=(373.,219.)
        for world in range(7):
            height=_safe_height(world,dock_y)
            down=_touch_cell(world,start,height,min_target=132)
            up=_touch_cell(world,release,height,min_target=132)
            self.assertEqual(down,7,(world,height))
            self.assertEqual(up,down,(world,height))
            self.assertLess(start[1],dock_y)
            self.assertGreaterEqual(release[1],dock_y)
            self.assertLess(math.dist(start,release),16)


    def test_native_smoke_is_wired_and_preserves_game(self):
        main=_body("_run_headless_geometry_and_interaction_smoke")
        self.assertIn('_run_headless_touch_chrome_release_smoke()',main)
        fixture=_body("_run_headless_touch_chrome_release_smoke")
        for part in ['for world in range(WorldVisuals.WORLDS.size())',
                     'touch.position = dock.get_global_rect().get_center()',
                     'assert(moves == 0 and turn == 1 and selected_reserve == 8',
                     'drag.position = dock.get_global_rect().get_center()',
                     'not perspective_touch_preview_icon.visible',
                     'BLUE_SEA_TOUCH_CHROME_RELEASE_PASS']:
            self.assertIn(part,fixture)

if __name__ == '__main__':
    unittest.main()
