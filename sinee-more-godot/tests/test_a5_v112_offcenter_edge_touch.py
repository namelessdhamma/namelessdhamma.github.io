"""A5 v112 offline geometry oracle, not native Godot/physical touch evidence."""
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO = (ROOT / 'scripts/perspective_board_geometry.gd').read_text(encoding='utf-8')
MAIN = (ROOT / 'scripts/main.gd').read_text(encoding='utf-8')
SPEC = importlib.util.spec_from_file_location('touch_v59', ROOT / 'tests/test_a5_v59_touch_cell_target.py')
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


def dist2_segment(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    d = vx * vx + vy * vy
    t = max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / d)) if d else 0
    return (p[0] - a[0] - t * vx) ** 2 + (p[1] - a[1] - t * vy) ** 2


def revised_touch(world, p, minimum=44, height=210):
    exact = next((i for i in range(9) if BASE.inside(BASE.cell_quad(world, i, height=height), p)), -1)
    if exact >= 0 or minimum <= 0:
        return exact
    candidates = []
    for i in range(9):
        q = BASE.cell_quad(world, i, height=height)
        center = (sum(x for x, _ in q) / 4, sum(y for _, y in q) / 4)
        square = abs(p[0] - center[0]) <= minimum / 2 and abs(p[1] - center[1]) <= minimum / 2
        short = min(math.dist(q[k], q[(k + 1) % 4]) for k in range(4))
        edge2 = min(dist2_segment(p, q[k], q[(k + 1) % 4]) for k in range(4))
        margin = max(2, (minimum - short) / 2)
        if square or edge2 <= margin * margin:
            center2 = (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2
            candidates.append((round(edge2, 6), center2, i))
    return min(candidates)[2] if candidates else -1


def off_center_top(world, cell, height=210, outward=0.75):
    q = BASE.cell_quad(world, cell, height=height)
    a, b = q[0], q[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(ex, ey)
    return (a[0] * 0.82 + b[0] * 0.18 + ey / norm * outward,
            a[1] * 0.82 + b[1] * 0.18 - ex / norm * outward)


def test_previous_real_missed_offcenter_taps_seven_worlds():
    for world in range(7):
        p = off_center_top(world, 0)
        assert BASE.exact(world, p) == -1, (world, p)
        assert BASE.touch(world, p) == -1, f'previous v111 fallback unexpectedly covered world {world}'
        assert revised_touch(world, p) == 0, (world, p)


def test_all_27_top_border_positions_across_worlds():
    for world in range(7):
        for cell in range(3):
            for offset in (0.25, 0.75, 1.5):
                p = off_center_top(world, cell, outward=offset)
                assert revised_touch(world, p) == cell, (world, cell, offset)


def test_no_distant_false_board_hits_and_exact_mouse_unchanged():
    for world in range(7):
        for p in [(0, 0), (745, 0), (0, 209), (745, 209), (-100, -100)]:
            assert revised_touch(world, p) == -1
        for cell in range(9):
            q = BASE.cell_quad(world, cell)
            center = (sum(x for x, _ in q) / 4, sum(y for _, y in q) / 4)
            assert revised_touch(world, center) == cell
            assert revised_touch(world, center, minimum=0) == cell
        p = off_center_top(world, 0)
        assert revised_touch(world, p, minimum=0) == -1


def test_44px_center_fallback_remains_for_legacy_touch_behavior():
    for world in range(7):
        for cell in range(9):
            q = BASE.cell_quad(world, cell)
            cx, cy = (sum(x for x, _ in q) / 4, sum(y for _, y in q) / 4)
            for dx in (-21.9, 0, 21.9):
                for dy in (-21.9, 0, 21.9):
                    assert revised_touch(world, (cx + dx, cy + dy)) in range(9)


def test_shared_live_source_uses_segment_distance_and_native_smoke():
    assert 'static func _segment_distance_squared(' in GEO
    assert 'var center_square :=' in GEO
    assert 'var edge_margin := maxf(2.0, (minimum_target - shortest_edge) * 0.5)' in GEO
    assert 'if not center_square and edge_distance > edge_margin * edge_margin:' in GEO
    assert 'var exact := cell_at(world, point, viewport)' in GEO
    assert 'PerspectiveGeometry.cell_at_touch(' in MAIN and 'PerspectiveGeometry.cell_at(current_world, mouse.position, perspective_rect)' in MAIN
    assert '_run_headless_edge_touch_smoke()' in MAIN
    assert 'BLUE_SEA_EDGE_TOUCH_PASS worlds=7' in MAIN


def test_no_rule_or_visual_canon_mutation():
    for token in ('func _is_legal_move(', 'func _on_primary(', 'func _play_ai_turn(',
                  'func _set_world(', 'func _run_headless_full_match_smoke('):
        assert token in MAIN
    from hashlib import sha256
    known = [
        ('a5_void_ranked/01_nd_premium_void_canon_source.png','00ffb7f48345b493cbd2cb986a3fb21fac345db50f0f8f20c679cdff58b421b8'),
        ('a5_pirate_ranked/02_pirate_sea_canon_source.png','0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1'),
        ('a5_atlantis_ranked/03_atlantis_canon_source.png','2cd5c4188ee1f21bb3aa74eec0ca933affd6d9af0982b27433c2689acf8d219f'),
        ('a5_gods_ranked/04_gods_of_the_deep_canon_source.png','10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'),
        ('a5_sand_ranked/05_sand_sea_canon_source.png','01d5b202cd9451520652f67c4ccdbd6d636e59e16c056b050aa10663c73fb6b3'),
        ('a5_night_ranked/06_night_sea_canon_source.png','ecdb9072a004b264eb768d98caaceb63857329dcbb8cb5bf5c6a86424c8b66da'),
        ('a5_northern_ranked/07_northern_sea_canon_source.png','3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775'),
    ]
    for name, expected in known:
        assert sha256((ROOT / 'assets' / name).read_bytes()).hexdigest() == expected
