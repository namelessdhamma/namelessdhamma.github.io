"""A5 v120 independent numeric geometry oracle; NOT a native Godot render test."""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'scripts/main.gd').read_text()
GEOMETRY = (ROOT / 'scripts/perspective_board_geometry.gd').read_text()


def corners():
    block = GEOMETRY.split('const GRID_CORNERS := [', 1)[1].split('\n]', 1)[0]
    rows = re.findall(r'PackedVector2Array\(\[(.*?)\]\)', block)
    assert len(rows) == 7
    result = []
    for row in rows:
        points = [(float(x), float(y)) for x, y in re.findall(r'Vector2\(([\d.]+),\s*([\d.]+)\)', row)]
        assert len(points) == 4
        result.append(points)
    return result


QUADS = corners()


def board_bottom(world, height):
    quad = QUADS[world]
    cy = sum(y for _, y in quad) / 4.0
    shift = -min(height * 0.045, 13.0)
    return max((cy + (y - cy) * 1.12) / 941.0 * height + shift for _, y in quad)


def visual_bottom(world, height):
    margin = 9.0 if world == 0 else max(9.0, 13.0 * min(1.0, max(0.35, height / 720.0)))
    return board_bottom(world, height) + margin


def legacy_height(viewport_height, dock_top):
    return min(viewport_height, max(100.0, (dock_top - 5.0) / 0.80))


def safe_height(world, viewport_height, dock_top):
    proposed = legacy_height(viewport_height, dock_top)
    allowed = dock_top - 6.0
    if visual_bottom(world, proposed) <= allowed:
        return proposed
    low, high = 0.0, proposed
    for _ in range(16):
        mid = (low + high) * 0.5
        if visual_bottom(world, mid) <= allowed:
            low = mid
        else:
            high = mid
    return max(1.0, low)


class TestBoardReserveClearance(unittest.TestCase):
    def test_01_predecessor_has_real_support_collision(self):
        # This is a reproducible source-model defect, not a claimed screenshot.
        old = legacy_height(720, 540)
        overlaps = [visual_bottom(w, old) - 540 for w in range(7)]
        self.assertGreater(overlaps[6], 8.0)  # Northern support overlaps reserve.
        self.assertGreater(overlaps[2], 7.0)  # Atlantis support overlaps reserve.

    def test_02_seven_worlds_twelve_reserve_profiles_each(self):
        for w in range(7):
            for height in (280, 390, 430, 720):
                for fraction in (0.72, 0.78, 0.84):
                    dock = height * fraction
                    h = safe_height(w, height, dock)
                    with self.subTest(world=w, height=height, dock=dock):
                        self.assertLessEqual(visual_bottom(w, h), dock - 5.8)
                        self.assertLessEqual(h, legacy_height(height, dock))
                        self.assertGreater(h, 0)

    def test_03_does_not_shrink_qualified_board_when_safe(self):
        for w in range(7):
            for height, dock in ((280, 260), (390, 350), (720, 620)):
                old = legacy_height(height, dock)
                if visual_bottom(w, old) <= dock - 6:
                    self.assertEqual(safe_height(w, height, dock), old)

    def test_04_larger_dock_gap_does_not_reduce_board_height(self):
        for w in range(7):
            for height in (280, 390, 430, 720):
                prev = 0.0
                for fraction in (0.72, 0.78, 0.84):
                    h = safe_height(w, height, height * fraction)
                    self.assertGreaterEqual(h, prev)
                    prev = h

    def test_05_solver_matches_real_world_geometry_contract(self):
        for token in ('_perspective_visual_bottom(world, Vector2(viewport_size.x, proposed))',
                      'for _iteration in range(16):',
                      'overhang = maxf(overhang, 13.0 * clampf(viewport_size.y / 720.0, 0.35, 1.0))',
                      'return maxf(1.0, low)',
                      '_safe_board_height_for_reserve(current_world, size, reserve_top)',
                      '_board_height_cache_world != current_world',
                      '_board_height_cache_dock_top != reserve_top',
                      '_run_headless_board_reserve_clearance_smoke()',
                      'BLUE_SEA_SEVEN_WORLD_RESERVE_CLEARANCE_PASS 84 profiles'):
            self.assertIn(token, MAIN)
        self.assertEqual(MAIN.count('func _perspective_board_rect()'), 1)

    def test_06_canonical_sources_untouched(self):
        hashes = ['00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8',
                  '0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1',
                  '2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f',
                  '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d',
                  '01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3',
                  'ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da',
                  '3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775']
        source = list((ROOT / 'assets').rglob('*canon_source.png'))
        self.assertEqual(len(source), 7)
        self.assertEqual({hashlib.sha256(p.read_bytes()).hexdigest() for p in source}, set(hashes))


if __name__ == '__main__':
    unittest.main()
