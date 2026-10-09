extends RefCounted
# A5 seven-world source-derived perspective grid geometry, candidate only.
# Art source: approved 1672x941 PNGs, verified against SHA-256 MANIFEST.json.
# Four corners per world: TL, TR, BR, BL of the interactive 3x3 grid.
# Physical supporting surfaces and live state remain separate layers.
const REFERENCE_SIZE := Vector2(1672.0, 941.0)
const ENLARGE := 1.12
const MAX_UPSHIFT_PX := 13.0
const WORLD_IDS := [
    "nd_premium_void", "pirate_sea", "atlantis", "gods_of_the_deep",
    "sand_sea", "night_sea", "northern_sea"
]
const GRID_CORNERS := [
    PackedVector2Array([Vector2(368.0, 264.0), Vector2(1300.0, 262.0), Vector2(1474.0, 738.0), Vector2(195.0, 741.0)]), # nd_premium_void
    PackedVector2Array([Vector2(500.0, 254.0), Vector2(1190.0, 254.0), Vector2(1300.0, 706.0), Vector2(387.0, 706.0)]), # pirate_sea
    PackedVector2Array([Vector2(398.0, 278.0), Vector2(1288.0, 275.0), Vector2(1400.0, 739.0), Vector2(283.0, 744.0)]), # atlantis
    PackedVector2Array([Vector2(385.0, 278.0), Vector2(1280.0, 279.0), Vector2(1410.0, 730.0), Vector2(265.0, 730.0)]), # gods_of_the_deep
    PackedVector2Array([Vector2(402.0, 288.0), Vector2(1265.0, 287.0), Vector2(1388.0, 742.0), Vector2(270.0, 739.0)]), # sand_sea
    PackedVector2Array([Vector2(402.0, 282.0), Vector2(1278.0, 282.0), Vector2(1410.0, 740.0), Vector2(258.0, 739.0)]), # night_sea
    PackedVector2Array([Vector2(407.0, 300.0), Vector2(1264.0, 299.0), Vector2(1396.0, 744.0), Vector2(281.0, 747.0)]), # northern_sea
]

static func board_quad(world: int, viewport: Rect2) -> PackedVector2Array:
    assert(world >= 0 and world < GRID_CORNERS.size())
    var ref_quad: PackedVector2Array = GRID_CORNERS[world]
    var center := Vector2.ZERO
    for point in ref_quad:
        center += point
    center /= 4.0
    var result := PackedVector2Array()
    var vertical_shift := -minf(viewport.size.y * 0.045, MAX_UPSHIFT_PX)
    for point in ref_quad:
        var enlarged: Vector2 = center + (point - center) * ENLARGE
        result.append(viewport.position + Vector2(
            enlarged.x / REFERENCE_SIZE.x * viewport.size.x,
            enlarged.y / REFERENCE_SIZE.y * viewport.size.y + vertical_shift
        ))
    return result

static func _bilinear(quad: PackedVector2Array, u: float, v: float) -> Vector2:
    var top: Vector2 = quad[0].lerp(quad[1], u)
    var bottom: Vector2 = quad[3].lerp(quad[2], u)
    return top.lerp(bottom, v)

static func cell_quad(world: int, cell: int, viewport: Rect2) -> PackedVector2Array:
    assert(cell >= 0 and cell < 9)
    var q := board_quad(world, viewport)
    var col: int = cell % 3
    var row: int = cell / 3
    var u0 := float(col) / 3.0
    var u1 := float(col + 1) / 3.0
    var v0 := float(row) / 3.0
    var v1 := float(row + 1) / 3.0
    return PackedVector2Array([
        _bilinear(q, u0, v0), _bilinear(q, u1, v0),
        _bilinear(q, u1, v1), _bilinear(q, u0, v1)
    ])

static func _inside_convex_quad(q: PackedVector2Array, point: Vector2) -> bool:
    var sign := 0
    for i in range(4):
        var edge: Vector2 = q[(i + 1) % 4] - q[i]
        var rel: Vector2 = point - q[i]
        var cross := edge.cross(rel)
        if absf(cross) <= 0.0001:
            continue
        var this_sign := 1 if cross > 0.0 else -1
        if sign != 0 and sign != this_sign:
            return false
        sign = this_sign
    return true

static func cell_at(world: int, point: Vector2, viewport: Rect2) -> int:
    for cell in range(9):
        if _inside_convex_quad(cell_quad(world, cell, viewport), point):
            return cell
    return -1

static func cell_center(world: int, cell: int, viewport: Rect2) -> Vector2:
    var q := cell_quad(world, cell, viewport)
    return (q[0] + q[1] + q[2] + q[3]) / 4.0
