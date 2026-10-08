extends RefCounted

# Seven interactive world treatments share the same D2 board and game state.
# The approved reference PNGs are art direction, never composited over gameplay.
const WORLDS := [
	"ND Premium Void", "Pirate Sea", "Atlantis", "Gods of the Deep",
	"Sand Sea", "Night Sea", "Northern Sea"
]
const BOARD_COLORS := [
	Color("#071320"), Color("#a9763c"), Color("#386b70"), Color("#243a50"),
	Color("#ba925e"), Color("#353449"), Color("#91b9c8")
]
const LINE_COLORS := [
	Color("#e4b56b"), Color("#4c2512"), Color("#a8e8df"), Color("#58a3b4"),
	Color("#6d4b2b"), Color("#a9a0dd"), Color("#e0f6fa")
]
var piece_cache: Dictionary = {}
var backdrop_cache: Dictionary = {}

func apply_world(root: Control, world: int) -> void:
	assert(world >= 0 and world < WORLDS.size())
	var background := root.get_node("Background") as ColorRect
	background.color = BOARD_COLORS[world].darkened(0.7)
	var backdrop := root.get_node_or_null("WorldBackdrop") as TextureRect
	if backdrop == null:
		backdrop = TextureRect.new()
		backdrop.name = "WorldBackdrop"
		backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
		backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		backdrop.stretch_mode = TextureRect.STRETCH_SCALE
		root.add_child(backdrop)
		root.move_child(backdrop, background.get_index() + 1)
		backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if not backdrop_cache.has(world):
		backdrop_cache[world] = _make_backdrop(world)
	backdrop.texture = backdrop_cache[world]
	var board_aspect := root.get_node("SafeArea/Landscape/Center/BoardAspect") as AspectRatioContainer
	var support := board_aspect.get_node_or_null("PhysicalSupport") as Panel
	if support == null:
		support = Panel.new()
		support.name = "PhysicalSupport"
		support.mouse_filter = Control.MOUSE_FILTER_IGNORE
		board_aspect.add_child(support)
		board_aspect.move_child(support, 0)
		support.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		support.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var backing := StyleBoxFlat.new()
	backing.bg_color = BOARD_COLORS[world].darkened(0.22)
	backing.border_color = LINE_COLORS[world].darkened(0.25)
	backing.set_border_width_all(5 if world != 0 else 2)
	backing.set_corner_radius_all(7)
	backing.shadow_color = Color(0.0, 0.0, 0.0, 0.72 if world != 0 else 0.28)
	backing.shadow_size = 9 if world != 0 else 3
	support.add_theme_stylebox_override("panel", backing)
	# Decorated physical stone support is behind the interactive board.
	var foundation := support.get_node_or_null("NorthernStonePlinth") as TextureRect
	if foundation == null:
		foundation = TextureRect.new()
		foundation.name = "NorthernStonePlinth"
		foundation.mouse_filter = Control.MOUSE_FILTER_IGNORE
		foundation.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		foundation.stretch_mode = TextureRect.STRETCH_SCALE
		support.add_child(foundation)
		foundation.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		foundation.offset_left = -14.0
		foundation.offset_top = -12.0
		foundation.offset_right = 14.0
		foundation.offset_bottom = 18.0
	foundation.visible = world == 6
	if world == 6 and foundation.texture == null:
		foundation.texture = _make_northern_stone_plinth()
	var board := root.get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	board.add_theme_constant_override("h_separation", 5)
	board.add_theme_constant_override("v_separation", 5)
	for child in board.get_children():
		if not (child is Button):
			continue
		var cell := child as Button
		var normal := StyleBoxFlat.new()
		normal.bg_color = Color("#182d43").lightened(0.025 * float(cell.get_index() % 3)) if world == 6 else BOARD_COLORS[world].lightened(0.06)
		normal.border_color = Color("#d5a668") if world == 6 else LINE_COLORS[world]
		normal.set_border_width_all(2)
		normal.set_corner_radius_all(3)
		var hover := normal.duplicate() as StyleBoxFlat
		hover.bg_color = BOARD_COLORS[world].lightened(0.23)
		var pressed := normal.duplicate() as StyleBoxFlat
		pressed.bg_color = BOARD_COLORS[world].darkened(0.2)
		cell.add_theme_stylebox_override("normal", normal)
		cell.add_theme_stylebox_override("hover", hover)
		cell.add_theme_stylebox_override("pressed", pressed)
		cell.add_theme_stylebox_override("disabled", normal)
		cell.add_theme_color_override("font_color", LINE_COLORS[world])
	var title := root.get_node("SafeArea/Landscape/Center/TopBar/Title") as Label
	title.text = "СИНЕЕ МОРЕ"
	title.add_theme_color_override("font_color", Color("#f33c39"))
	root.queue_redraw()

func piece_texture(world: int, player: int, rank: int) -> Texture2D:
	var key := "%d:%d:%d" % [world, player, rank]
	if piece_cache.has(key):
		return piece_cache[key]
	var image := Image.create(44, 44, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	var radius := 6.0 + float(rank) * 1.7
	var light := Color("#e5eff9") if world != 1 and world != 4 else Color("#f8d4a0")
	if world == 6:
		light = Color("#e8c4a0")
	var dark := Color("#466477") if world != 1 and world != 4 else Color("#4d2921")
	if world == 6:
		dark = Color("#a9d6ed")
	var body := light if player == 1 else dark
	var edge: Color = LINE_COLORS[world]
	for y in range(44):
		for x in range(44):
			var px := (float(x) - 21.5) / radius
			var py := (float(y) - 21.5) / radius
			var inside := false
			match world:
				0: # glass light hemisphere
					inside = px * px + py * py <= 0.97
				1: # brass-rimmed naval cap with wide brim
					inside = (px * px / 0.70 + (py + 0.14) * (py + 0.14) / 0.58 < 1.0) or (absf(px) < 0.96 and py > 0.33 and py < 0.59)
				2: # stepped Atlantean shrine
					inside = (absf(px) < 0.27 and py < 0.13 and py > -0.86) or (absf(px) < 0.51 and py >= -0.27 and py < 0.49) or (absf(px) < 0.83 and py >= 0.49 and py < 0.76)
				3: # deep-sea body, fins and tentacles
					inside = (px * px / 0.57 + (py + 0.24) * (py + 0.24) / 0.40 < 1.0) or (absf(px) < 0.72 and py > 0.19 and py < 0.87 and absf(sin(px * 11.0 + py * 3.0)) > 0.35)
				4: # Egyptian pyramid on plinth
					inside = (py > -0.91 and py < 0.68 and absf(px) < (py + 0.91) * 0.51) or (absf(px) < 0.96 and py >= 0.68 and py < 0.84)
				5: # Gothic beacon / lantern
					inside = (absf(px) < 0.37 and py > -0.45 and py < 0.77) or (py <= -0.45 and py > -0.88 and absf(px) < (py + 0.88) * 0.88) or (absf(px) < 0.70 and py > 0.64 and py < 0.82)
				6: # Ranked round Nordic rune stones, amber/blue sides
					inside = px * px + py * py <= 0.98
			if inside:
				var shading := clampf((0.55 - py) * 0.12, 0.0, 0.19)
				var c := body.lightened(shading)
				if absf(px) > 0.72 or py > 0.70:
					c = edge.darkened(0.25)
				if world == 0 and py < -0.34:
					c = c.lightened(0.24)
				if world == 6:
					var dist := sqrt(px * px + py * py)
					var glow := Color("#ff923a") if player == 1 else Color("#49bfff")
					c = body.darkened(0.23 * dist)
					if dist > 0.78:
						c = glow.lerp(Color("#fff0d4"), 0.25)
					elif dist > 0.57 and dist < 0.70:
						c = glow.darkened(0.15)
					elif dist > 0.70 and dist < 0.78:
						var rune_angle := atan2(py, px)
						if absf(sin(rune_angle * 8.0)) > 0.83:
							c = glow.lightened(0.42)
					if dist < 0.50 and (x * 37 + y * 19) % 23 < 3:
						c = c.darkened(0.08)
				image.set_pixel(x, y, c)
	var texture := ImageTexture.create_from_image(image)
	piece_cache[key] = texture
	return texture

# Procedural slab, separate from gameplay and from approved reference PNGs.
func _make_northern_stone_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge_distance := mini(mini(x, 255 - x), mini(y, 255 - y))
			var noise := float((x * 53 + y * 97 + x * y * 3) % 47) / 47.0
			var c := Color("#172d42").lerp(Color("#2d4354"), noise * 0.32)
			if edge_distance < 17:
				c = Color("#0a1727").lerp(Color("#35506b"), float(edge_distance) / 17.0)
				if y < 18 and (x * 11 + y * 13) % 31 < 12:
					c = Color("#d7ebf4")
				elif edge_distance == 4 or edge_distance == 12:
					c = Color("#b88952")
			elif x % 79 < 2 or y % 83 < 2:
				c = c.lightened(0.12)
			elif (x * 17 + y * 29) % 113 < 2:
				c = c.lightened(0.15)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _make_backdrop(world: int) -> Texture2D:
	var image := Image.create(512, 288, false, Image.FORMAT_RGB8)
	var top := Color("#070e20")
	var bottom := Color("#182637")
	match world:
		0: top = Color("#040910"); bottom = Color("#101a2b")
		1: top = Color("#24435b"); bottom = Color("#a15b30")
		2: top = Color("#083d4c"); bottom = Color("#123a3d")
		3: top = Color("#031326"); bottom = Color("#092f3b")
		4: top = Color("#bca474"); bottom = Color("#d4a65d")
		5: top = Color("#080f28"); bottom = Color("#29253d")
		6: top = Color("#406a84"); bottom = Color("#b3d1d9")
	for y in range(288):
		var v := float(y) / 287.0
		for x in range(512):
			var u := float(x) / 511.0
			var c := top.lerp(bottom, v)
			match world:
				0:
					var warm := Color("#b17a2c") if u < 0.5 else Color("#326aa4")
					c = c.lerp(warm, 0.10 + 0.11 * (1.0 - absf(2.0 * u - 1.0)))
				1:
					if v > 0.47:
						c = Color("#60371f").lerp(Color("#29170f"), v)
						if y % 34 < 2 or (x + int(y / 34) * 57) % 131 < 2:
							c = c.lightened(0.23)
					elif v > 0.35:
						c = Color("#20516a").lerp(Color("#d78c4d"), 0.2 + 0.4 * u)
					if absf(u - 0.83) < 0.007 and v < 0.47:
						c = Color("#151d24")
				2:
					if v > 0.53:
						c = Color("#234e4b")
						if y % 27 < 2 or x % 67 < 2:
							c = c.lightened(0.12)
					elif int(x / 74) % 2 == 0 and x % 74 < 14 and v > 0.19:
						c = Color("#2c7778")
				3:
					if v > 0.55:
						c = Color("#102f37")
						if x % 59 < 2 or y % 38 < 2:
							c = c.lightened(0.11)
					elif (x * 19 + y * 29) % 1309 < 2:
						c = Color("#4c9db2")
				4:
					if v > 0.54:
						c = Color("#c29a5b")
						if absf(sin(u * 22.0 + v * 9.0)) > 0.95:
							c = c.lightened(0.10)
					elif absf(u - 0.25) < (v - 0.22) * 0.75 and v > 0.22 and v < 0.48:
						c = Color("#a78349")
				5:
					if v > 0.54:
						c = Color("#1c263c")
						if x % 61 < 2 or y % 35 < 2:
							c = c.lightened(0.12)
					elif (x % 81 < 17 and v > 0.22) or (x % 81 < 7 and v > 0.10):
						c = Color("#0c1224")
				6:
					c = _northern_backdrop_color(u, v, x, y)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

# Northern Sea: procedural environment, never a flat canonical screenshot.
# Live board cells, reserve, ranks and hit targets are unchanged.
func _northern_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var c := Color("#031029").lerp(Color("#103958"), clampf(v * 1.5, 0.0, 1.0))
	var ridge := 0.35 - 0.22 * pow(absf(sin(u * 22.0 + sin(u * 4.0) * 2.1)), 5.0)
	if v < ridge:
		var aurora_center := 0.10 + 0.035 * sin(u * 13.0) + 0.018 * sin(u * 34.0)
		var ribbon := exp(-pow((v - aurora_center) / 0.065, 2.0))
		var curtain := 0.42 + 0.58 * absf(sin(u * 42.0 + v * 12.0))
		c = c.lerp(Color("#53e8b3"), clampf(ribbon * curtain * 0.78, 0.0, 0.78))
		if (x * 71 + y * 131 + x * y * 3) % 1301 < 2:
			c = c.lerp(Color("#e6f6ff"), 0.78)
	else:
		c = Color("#06182f").lerp(Color("#42617a"), clampf((v - ridge) * 1.8, 0.0, 1.0))
		if v < ridge + 0.028 + 0.008 * sin(u * 180.0):
			c = Color("#d0e8f4").lerp(Color("#84abc6"), 0.35 + 0.3 * sin(u * 18.0))
		elif v < ridge + 0.08 and sin(u * 113.0 + v * 41.0) > 0.55:
			c = c.lightened(0.23)
	if v > 0.56:
		var ripple := sin(v * 360.0 + sin(u * 25.0) * 3.0)
		c = Color("#0a2741").lerp(Color("#2c6584"), 0.28 + 0.18 * ripple)
		if absf(sin(v * 210.0 + u * 23.0)) > 0.985:
			c = c.lightened(0.22)
	if v > 0.81:
		c = Color("#332c30").lerp(Color("#131b28"), v)
		if y % 16 < 2 or x % 77 < 2:
			c = c.lightened(0.18)
	if u > 0.77 and u < 0.97 and v > 0.38 and v < 0.66:
		if absf(u - 0.86) < 0.004 and v < 0.60:
			c = Color("#100e19")
		if v > 0.44 and v < 0.58 and absf(u - 0.87) < (v - 0.38) * 0.29:
			c = Color("#a18b84").lerp(Color("#643c3c"), u)
		if v > 0.59 and v < 0.64 and absf(u - 0.87) < 0.11 * (1.0 - (v - 0.59) * 12.0):
			c = Color("#221927")
	for torch_u in [0.055, 0.965]:
		var distance := sqrt(pow((u - torch_u) * 1.6, 2.0) + pow((v - 0.66) * 1.4, 2.0))
		if distance < 0.11:
			c = c.lerp(Color("#ff9d36"), clampf((0.11 - distance) * 5.8, 0.0, 0.7))
		if distance < 0.016:
			c = Color("#fff0ad")
	return c
