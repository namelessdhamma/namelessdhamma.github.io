extends RefCounted
# Exact alpha bounding-box bottoms (pixels of 128px transparent source PNGs).
# All 126 approved-source ranked assets were inspected. P1 and P2 share the
# same geometric silhouettes; only their material/color differs.
# Rank-1 Northern rune ends at 85/128, rank-9 at 114/128; the previous fixed
# icon rectangle made the smaller stones visibly hover above the frozen board.
const BOTTOM_PX := [
	[123,123,123,123,123,123,123,123,123], # Void: floating light domes
	[122,122,122,122,122,122,122,122,122], # Pirate naval caps
	[124,124,124,124,124,124,124,124,124], # Atlantis shrines
	[123,123,124,123,123,124,124,124,124], # Gods sea creatures
	[124,124,124,124,124,124,124,124,124], # Sand pyramids
	[124,124,124,124,124,124,124,124,124], # Night beacons
	[85,86,92,96,102,104,109,111,114] # Northern rune stones
]
const TARGET_BASE_PX := 124.0

static func bottom_fraction(world: int, rank: int) -> float:
	assert(world >= 0 and world < BOTTOM_PX.size())
	assert(rank >= 1 and rank <= 9)
	return float(BOTTOM_PX[world][rank - 1]) / 128.0

static func baseline_shift(world: int, rank: int, extent: float) -> float:
	# The sole floating world must not be grounded. For the other six,
	# align the actual opaque sprite bottom, not the 128px transparent box.
	if world == 0:
		return 0.0
	return extent * (TARGET_BASE_PX / 128.0 - bottom_fraction(world, rank))

static func ellipse(center: Vector2, radius_x: float, radius_y: float) -> PackedVector2Array:
	# Geometry only; Polygon2D does not intercept mouse or touch events.
	var points := PackedVector2Array()
	for i in range(16):
		var angle := TAU * float(i) / 16.0
		points.append(center + Vector2(cos(angle) * radius_x, sin(angle) * radius_y))
	return points
