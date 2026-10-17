extends RefCounted

# Seven interactive world treatments share the same D2 board and game state.
# The approved reference PNGs are art direction, never composited over gameplay.
const CANONICAL_CELL_ART_ROOT := "res://assets/a5_reference_cells"
const CANONICAL_SCENERY_ROOT := "res://assets/a5_scenery_perimeter"
# Original scenery-only art; the 9 live gameplay cells and dynamic ranks stay separate.
const NORTHERN_ENV_ROOT := "res://assets/a5_northern_environment"
# Original Gods scenery and full physical basalt support, baked at build time.
const GODS_ENV_ROOT := "res://assets/a5_gods_prebaked_environment"
# Reproducible original scenery and stone support, not baked game state.
const SAND_NIGHT_ENV_ROOT := "res://assets/a5_sand_night_prebaked_environment"
# Last two supported worlds now load their original source-math materials.
const PIRATE_ATLANTIS_ENV_ROOT := "res://assets/a5_pirate_atlantis_prebaked_environment"
# All seven worlds now load original scenery without a 512x288 startup pixel loop.
const VOID_ENV_ROOT := "res://assets/a5_void_prebaked_environment"
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
var pirate_cell_cache: Dictionary = {}
# A physical board slab is a world texture too. The previous six long-lived
# plinth variables retained every visited slab despite the two-world LRU.
var support_cache: Dictionary = {}
const SUPPORT_TEXTURE_PATHS := [
    "", # Void floats; no physical slab and no retained previous-world texture.
    PIRATE_ATLANTIS_ENV_ROOT + "/pirate_chart_support.png",
    PIRATE_ATLANTIS_ENV_ROOT + "/atlantis_stone_support.png",
    GODS_ENV_ROOT + "/gods_basalt_support.png",
    SAND_NIGHT_ENV_ROOT + "/sand_sandstone_support.png",
    SAND_NIGHT_ENV_ROOT + "/night_masonry_support.png",
    NORTHERN_ENV_ROOT + "/north_frozen_runestone_plinth.png",
]
var canonical_cell_cache: Dictionary = {}
var scenery_cache: Dictionary = {}

# On low-memory phones, retaining every previously visited 1672x941
# reference perimeter and all 126 ranked sprites can consume over 100 MiB
# of decoded textures. Keep the active and immediately previous world's
# explicit references; UI nodes retain their own live references until the
# next _refresh_surface() replaces them. No board state or art bytes change.
const RESIDENT_WORLD_LIMIT := 2
var resident_worlds: Array[int] = []

# Avoid an additional engine-level cache retaining large inactive art after
# the bounded dictionaries release their references. Scene nodes still own
# their visible textures, so this does not blank any live board or reserve.
static func _load_bounded_texture(path: String) -> Texture2D:
	return ResourceLoader.load(path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE) as Texture2D

func _touch_world_cache(world: int) -> void:
	assert(world >= 0 and world < WORLDS.size())
	if not resident_worlds.is_empty() and resident_worlds[-1] == world:
		return
	resident_worlds.erase(world)
	resident_worlds.append(world)
	while resident_worlds.size() > RESIDENT_WORLD_LIMIT:
		resident_worlds.pop_front()
	for key in backdrop_cache.keys():
		if not resident_worlds.has(int(key)):
			backdrop_cache.erase(key)
	for key in scenery_cache.keys():
		if not resident_worlds.has(int(key)):
			scenery_cache.erase(key)
	for key in support_cache.keys():
		if not resident_worlds.has(int(key)):
			support_cache.erase(key)
	for key in piece_cache.keys():
		if not resident_worlds.has(int(str(key).get_slice(":", 0))):
			piece_cache.erase(key)
	for key in canonical_cell_cache.keys():
		if not resident_worlds.has(int(str(key).get_slice(":", 0))):
			canonical_cell_cache.erase(key)

func _cache_within_budget() -> bool:
	if resident_worlds.size() > RESIDENT_WORLD_LIMIT:
		return false
	for cache in [backdrop_cache, scenery_cache, support_cache]:
		for key in cache.keys():
			if not resident_worlds.has(int(key)):
				return false
	for cache in [piece_cache, canonical_cell_cache]:
		for key in cache.keys():
			if not resident_worlds.has(int(str(key).get_slice(":", 0))):
				return false
	return true

func apply_world(root: Control, world: int) -> void:
	assert(world >= 0 and world < WORLDS.size())
	_touch_world_cache(world)
	var background := root.get_node("Background") as ColorRect
	background.color = BOARD_COLORS[world].darkened(0.7)
	var backdrop := root.get_node_or_null("WorldBackdrop") as TextureRect
	if backdrop == null:
		backdrop = TextureRect.new()
		backdrop.name = "WorldBackdrop"
		backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
		backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		# On ultra-wide phone-browser viewports, STRETCH_SCALE distorted every
		# approved harbor/ruin/fjord silhouette horizontally. Crop scenery at
		# its edges instead; the actual 3x3 game state stays a separate layer.
		backdrop.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		root.add_child(backdrop)
		root.move_child(backdrop, background.get_index() + 1)
		backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if not backdrop_cache.has(world):
		if world == 0:
			# Exact original minimal warm/cool split field, with NO screenshot UI.
			# This removes the final 147456 GDScript pixel writes at cold entry.
			var void_scene := _load_bounded_texture(VOID_ENV_ROOT + "/void_split_light_backdrop.png")
			assert(void_scene != null, "Missing minimal Void split-light scenery")
			backdrop_cache[world] = void_scene
		elif world == 1 or world == 2:
			# Preserve the original chart/table and underwater ruins exactly, while
			# avoiding 147456 per-pixel GDScript writes on first world entry.
			var scene_file := "/pirate_chart_backdrop.png" if world == 1 else "/atlantis_underwater_backdrop.png"
			var prepared := _load_bounded_texture(PIRATE_ATLANTIS_ENV_ROOT + scene_file)
			assert(prepared != null, "Missing Pirate/Atlantis scenery")
			backdrop_cache[world] = prepared
		elif world == 6:
			# Prebaked original fjord/aurora scenery contains no live game state.
			var northern_scene := _load_bounded_texture(NORTHERN_ENV_ROOT + "/north_fjord_backdrop.png")
			assert(northern_scene != null, "Missing Northern Sea environment")
			backdrop_cache[world] = northern_scene
		elif world == 3:
			# Deep-sea ruins/creature silhouettes are original scenery ONLY.
			# Remove 512x288 per-pixel GDScript work from first world entry.
			var gods_scene := _load_bounded_texture(GODS_ENV_ROOT + "/gods_underwater_backdrop.png")
			assert(gods_scene != null, "Missing Gods of the Deep environment")
			backdrop_cache[world] = gods_scene
		elif world == 4 or world == 5:
			# Sand/Night scenery is deterministic original art with no board or UI.
			# Load exact source-math textures instead of 147456 pixel loops per world.
			var backdrop_file := "/sand_sunset_backdrop.png" if world == 4 else "/night_gothic_harbor_backdrop.png"
			var prepared_scene := _load_bounded_texture(SAND_NIGHT_ENV_ROOT + backdrop_file)
			assert(prepared_scene != null, "Missing Sand/Night original scenery")
			backdrop_cache[world] = prepared_scene
		else:
			backdrop_cache[world] = _make_backdrop(world)
	backdrop.texture = backdrop_cache[world]
	# Extracted scenery-only ring: the approved screenshot's toolbar, reserve,
	# board, and pieces are fully transparent. All gameplay is rendered live.
	var scenery := root.get_node_or_null("SceneryPerimeter") as TextureRect
	if scenery == null:
		scenery = TextureRect.new()
		scenery.name = "SceneryPerimeter"
		scenery.mouse_filter = Control.MOUSE_FILTER_IGNORE
		scenery.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		# Decorative source-derived perimeter uses the same aspect-preserving
		# centered cover as the scenery; never squeeze the seven canonical arts.
		scenery.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		root.add_child(scenery)
		root.move_child(scenery, backdrop.get_index() + 1)
		scenery.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# The approved Void perimeter is NEVER displayed; avoid decoding its
	# 1672x941 screenshot at startup. Keep the exact source file as provenance.
	if world == 0:
		scenery.texture = null
	else:
		if not scenery_cache.has(world):
			var path := "%s/world_%02d.png" % [CANONICAL_SCENERY_ROOT, world]
			var texture := _load_bounded_texture(path) as Texture2D
			assert(texture != null, "Missing approved-reference scenery: " + path)
			scenery_cache[world] = texture
		scenery.texture = scenery_cache[world]
	# Void alone is an empty warm/cool field, with a floating board.
	scenery.visible = world != 0
	assert(_cache_within_budget(), "World texture cache exceeded two-world budget")
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
	# Void is the sole floating world: do not leave a hidden rectangular
	# physical slab beneath its inclined live polygon board.
	support.visible = world != 0
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
	# The physical slab follows the same bounded two-world residency as the
	# backdrop, live pieces and empty cells. In Void explicitly clear the
	# previous support reference even though its node is invisible.
	foundation.visible = world >= 1 and world <= 6
	if world == 0:
		foundation.texture = null
	else:
		if not support_cache.has(world):
			var support_texture := _load_bounded_texture(SUPPORT_TEXTURE_PATHS[world])
			assert(support_texture != null, "Missing physical board support: " + SUPPORT_TEXTURE_PATHS[world])
			support_cache[world] = support_texture
		foundation.texture = support_cache[world]
	var board := root.get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	board.add_theme_constant_override("h_separation", 5)
	board.add_theme_constant_override("v_separation", 5)
	for child in board.get_children():
		if not (child is Button):
			continue
		var cell := child as Button
		var chart := cell.get_node_or_null("WorldCellArt") as TextureRect
		if chart == null:
			chart = TextureRect.new()
			chart.name = "WorldCellArt"
			chart.mouse_filter = Control.MOUSE_FILTER_IGNORE
			chart.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			chart.stretch_mode = TextureRect.STRETCH_SCALE
			cell.add_child(chart)
			cell.move_child(chart, 0)
			chart.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		chart.visible = world >= 0 and world <= 6
		var cell_index := cell.get_index()
		# All SEVEN worlds project source-derived EMPTY cell art. Void has
		# luminous rings but no physical support; six others have grounded slabs.
		# The approved screenshot's figures/occupancy/UI are NEVER baked in.
		# Every world has nine live perspective tiles. In Void these are
		# the ONLY board material: never inherit the preceding world's slab.
		chart.texture = _canonical_cell_texture(world, cell_index)
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
	assert(_cache_within_budget(), "World texture cache exceeded two-world budget after slab/cells")
	root.queue_redraw()

func piece_texture(world: int, player: int, rank: int) -> Texture2D:
	# Native QA also probes piece textures without changing the displayed
	# world; those direct requests must not grow an unbounded hidden cache.
	_touch_world_cache(world)
	var key := "%d:%d:%d" % [world, player, rank]
	if piece_cache.has(key):
		return piece_cache[key]
	# ND Premium Void: the two original warm/cool glass domes from the accepted
	# reference, with baked screenshot numerals removed. Both reserve and live
	# board use the same rank-sized textures and the shared live rank label.
	if world == 0:
		assert(player == 1 or player == 2, "Void glass dome side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Void glass dome rank must be 1..9")
		var void_path := "res://assets/a5_void_ranked/void_rank_%02d_p%d.png" % [rank, player]
		var void_texture := _load_bounded_texture(void_path) as Texture2D
		assert(void_texture != null, "Missing approved Void glass dome: " + void_path)
		piece_cache[key] = void_texture
		return void_texture
	# Pirate Sea: both naval-cap materials are extracted from the exact approved
	# reference. Nine ranks have progressively larger transparent silhouettes;
	# actual rank numerals and game state remain live, never screenshot-baked.
	if world == 1:
		assert(player == 1 or player == 2, "Pirate naval cap side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Pirate naval cap rank must be 1..9")
		var pirate_path := "res://assets/a5_pirate_ranked/pirate_rank_%02d_p%d.png" % [rank, player]
		var pirate_texture := _load_bounded_texture(pirate_path) as Texture2D
		assert(pirate_texture != null, "Missing approved Pirate naval cap: " + pirate_path)
		piece_cache[key] = pirate_texture
		return pirate_texture
	# Atlantis: original stepped stone/shrine pieces from the exact approved
	# image, in opposing ivory-gold and black-cyan materials. No baked ranks.
	if world == 2:
		assert(player == 1 or player == 2, "Atlantis shrine side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Atlantis shrine rank must be 1..9")
		var atlantis_path := "res://assets/a5_atlantis_ranked/atlantis_rank_%02d_p%d.png" % [rank, player]
		var atlantis_texture := _load_bounded_texture(atlantis_path) as Texture2D
		assert(atlantis_texture != null, "Missing canonical Atlantis shrine: " + atlantis_path)
		piece_cache[key] = atlantis_texture
		return atlantis_texture
	# Gods of the Deep: nine DISTINCT abyssal beings lifted from the approved
	# reserve strip, plus a dark-cobalt opposing family. Numbers remain live.
	if world == 3:
		assert(player == 1 or player == 2, "Gods sea-creature side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Gods sea-creature rank must be 1..9")
		var gods_path := "res://assets/a5_gods_ranked/gods_rank_%02d_p%d.png" % [rank, player]
		var gods_texture := _load_bounded_texture(gods_path) as Texture2D
		assert(gods_texture != null, "Missing approved Gods sea creature: " + gods_path)
		piece_cache[key] = gods_texture
		return gods_texture
	# Sand Sea: two original Egyptian pyramid materials from the exact approved
	# 05 reference, ranked 1..9 with transparent source-derived silhouettes.
	# The gold ankhs remain artwork; numeric ranks are live Godot labels.
	if world == 4:
		assert(player == 1 or player == 2, "Sand pyramid side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Sand pyramid rank must be 1..9")
		var sand_path := "res://assets/a5_sand_ranked/sand_rank_%02d_p%d.png" % [rank, player]
		var sand_texture := _load_bounded_texture(sand_path) as Texture2D
		assert(sand_texture != null, "Missing canonical Sand pyramid: " + sand_path)
		piece_cache[key] = sand_texture
		return sand_texture
	# Night Sea: nine distinct original Gothic lanterns from the approved
	# reserve artwork. Cool opponent family uses a matching material transform.
	# Dynamic numeric ranks are rendered on neutral lower medallions.
	if world == 5:
		assert(player == 1 or player == 2, "Night Gothic beacon side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Night Gothic beacon rank must be 1..9")
		var night_path := "res://assets/a5_night_ranked/night_rank_%02d_p%d.png" % [rank, player]
		var night_texture := _load_bounded_texture(night_path) as Texture2D
		assert(night_texture != null, "Missing approved Night Gothic beacon: " + night_path)
		piece_cache[key] = night_texture
		return night_texture
	# Northern Sea: the accepted reference depicts distinct luminous runes on
	# frozen stones. The extracted base silhouettes were blank after removing
	# baked screenshot symbols. Use deterministic runic ENGRAVING derivatives;
	# original approved reference and original stone sprites remain untouched.
	# Rank numerals remain live UI, separate from this static rune artwork.
	if world == 6:
		assert(player == 1 or player == 2, "Northern rune stone side must be 1 or 2")
		assert(rank >= 1 and rank <= 9, "Northern rune stone rank must be 1..9")
		var runed_path := "res://assets/a5_northern_runed/north_runed_rank_%02d_p%d.png" % [rank, player]
		var runed_texture := _load_bounded_texture(runed_path) as Texture2D
		assert(runed_texture != null, "Missing ranked Northern rune engraving: " + runed_path)
		piece_cache[key] = runed_texture
		return runed_texture
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
				if world == 3:
					var eye_x := 0.19 + float(rank % 3) * 0.04
					if absf(py + 0.30) < 0.13 and absf(absf(px) - eye_x) < 0.12:
						c = Color("#72d8ff") if player == 2 else Color("#ffe5aa")
					elif py > 0.24 and absf(sin(px * (8.0 + float(rank)) + py * 4.0)) > 0.75:
						c = edge.lightened(0.27)
					elif rank >= 7 and py < -0.28 and absf(px) > 0.32:
						c = edge.lightened(0.4)
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



# Atlantis: procedural stone layers, not a flattened reference screenshot.
func _make_atlantis_stone_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge := mini(mini(x, 255 - x), mini(y, 255 - y))
			var grain := float((x * 43 + y * 71 + x * y * 7) % 109) / 109.0
			var c := Color("#163c4a").lerp(Color("#316471"), grain * 0.45)
			if edge < 18:
				c = Color("#081e2d").lerp(Color("#305f69"), float(edge) / 18.0)
				if edge == 5 or edge == 14:
					c = Color("#16c7e2")
				elif edge == 9:
					c = Color("#d9b96a")
			elif x % 83 < 2 or y % 83 < 2:
				c = Color("#8ed7d7").lerp(c, 0.4)
			elif (x * 17 + y * 31) % 211 < 3:
				c = c.lightened(0.17)
			if y > 235:
				c = c.darkened(0.24)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _make_atlantis_stone_cell(index: int) -> Texture2D:
	var image := Image.create(96, 96, false, Image.FORMAT_RGB8)
	for y in range(96):
		for x in range(96):
			var noise := float((x * 47 + y * 29 + index * 67 + x * y) % 83) / 83.0
			var c := Color("#102d42").lerp(Color("#2a5668"), noise * 0.46)
			if x % 31 < 2 or y % 33 < 2:
				c = c.lerp(Color("#597e83"), 0.38)
			var dx := float(x) - 47.5
			var dy := float(y) - 47.5
			var radius := sqrt(dx * dx + dy * dy)
			if absf(radius - 30.0) < 1.4 or absf(radius - 17.0) < 0.7:
				c = Color("#b99d61")
			elif absf(dx) < 0.8 and absf(dy) < 30.0:
				c = c.lerp(Color("#c7b374"), 0.4)
			if x < 3 or y < 3 or x > 92 or y > 92:
				c = Color("#14d8f0") if (x + y) % 9 < 7 else Color("#b8f8fa")
			elif (x * 19 + y * 23 + index * 11) % 521 < 2:
				c = c.lightened(0.32)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _atlantis_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var c := Color("#02182c").lerp(Color("#067e99"), clampf(v * 1.25, 0.0, 1.0))
	var ray := absf(sin(u * 19.0 + v * 3.0))
	if v < 0.72:
		c = c.lerp(Color("#50c8e9"), 0.17 * pow(ray, 8.0) * (1.0 - v))
	for column_u in [0.065, 0.18, 0.82, 0.935]:
		var dx := absf(u - column_u)
		if dx < 0.018 and v > 0.06 and v < 0.88:
			c = Color("#134957").lerp(Color("#498b92"), 0.5 + 0.3 * sin(u * 260.0))
		elif dx < 0.033 and absf(v - 0.11) < 0.025:
			c = Color("#a3a079")
		if dx < 0.023 and (int(y) % 42) < 2 and v > 0.1:
			c = c.lightened(0.2)
	if (u < 0.035 or u > 0.965) and v > 0.15:
		c = c.lerp(Color("#5beaff"), 0.63 + 0.16 * sin(float(y) * 0.28))
	if v > 0.72:
		c = Color("#092d39").lerp(Color("#246171"), 0.4 + 0.22 * sin(u * 110.0))
		if y % 28 < 2 or x % 64 < 2:
			c = c.lerp(Color("#d4b86c"), 0.5)
	if (x * 73 + y * 37 + x * y * 3) % 1777 < 2 and v < 0.72:
		c = Color("#a5f1f4")
	return c

# Pirate Sea: physically supported chart board; layers never intercept touch.
func _make_pirate_chart_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge := mini(mini(x, 255 - x), mini(y, 255 - y))
			var grain := 0.5 + 0.5 * sin(float(x) * 0.13 + float(y) * 0.019)
			var c := Color("#4b2515").lerp(Color("#9b5730"), grain * 0.45)
			if edge < 18:
				c = Color("#1a100e").lerp(Color("#63341b"), float(edge) / 18.0)
				if edge == 4 or edge == 13:
					c = Color("#d7a24b")
				elif edge < 12 and (x % 24 < 3 or y % 24 < 3):
					c = Color("#b47a38")
			elif x % 82 < 2 or y % 83 < 2:
				c = c.lightened(0.12)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _make_pirate_chart_cell(index: int) -> Texture2D:
	var image := Image.create(96, 96, false, Image.FORMAT_RGBA8)
	var col := index % 3
	var row := int(index / 3)
	for y in range(96):
		for x in range(96):
			var u := float(x + col * 96) / 288.0
			var v := float(y + row * 96) / 288.0
			var grain := float((x * 29 + y * 47 + index * 73 + x * y) % 71) / 71.0
			var c := Color("#eac48b").lerp(Color("#f7dfa8"), grain * 0.34)
			var coast := 0.23 + 0.10 * sin(u * 18.0) + 0.05 * sin(u * 49.0 + 2.0)
			var distance := absf(v - coast)
			if v < coast:
				c = c.lerp(Color("#b68b50"), 0.16)
			if distance < 0.005 or (distance < 0.018 and sin(u * 175.0) > 0.93):
				c = Color("#765136")
			if (x % 32 == 0 or y % 32 == 0) and distance > 0.02:
				c = c.lerp(Color("#a47a4b"), 0.32)
			var dx := u - 0.89
			var dy := v - 0.53
			var radius := sqrt(dx * dx + dy * dy)
			if radius < 0.092 and radius > 0.086:
				c = Color("#68482e")
			if radius < 0.080 and (absf(dx) < 0.003 or absf(dy) < 0.003 or absf(absf(dx) - absf(dy)) < 0.002):
				c = Color("#76502c")
			var island := sqrt(pow((u - 0.41) * 1.4, 2.0) + pow((v - 0.68) * 2.1, 2.0))
			if island < 0.085 + 0.015 * sin(u * 120.0 + v * 80.0):
				c = c.lerp(Color("#9e7543"), 0.42)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _pirate_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var horizon := 0.43
	var c := Color("#17354c").lerp(Color("#eaa35b"), clampf(v / horizon, 0.0, 1.0))
	if v < horizon:
		var sun_dist := sqrt(pow((u - 0.83) * 1.5, 2.0) + pow((v - 0.25) * 1.8, 2.0))
		if sun_dist < 0.070:
			c = c.lerp(Color("#fff0bb"), clampf((0.070 - sun_dist) * 12.0, 0.0, 1.0))
		if v > 0.34:
			c = Color("#19445d").lerp(Color("#b87545"), 0.2 + 0.3 * sin(v * 150.0 + u * 35.0))
		for mast in [0.12, 0.36, 0.72, 0.93]:
			if absf(u - mast) < 0.003 and v > 0.11:
				c = Color("#1b2024")
			if absf(v - 0.23) < 0.004 and absf(u - mast) < 0.044:
				c = Color("#1b2024")
		if v > 0.35 and absf(sin(u * 41.0)) > 0.87:
			c = c.lerp(Color("#161d25"), 0.9)
	else:
		var plank := sin(v * 75.0 + sin(u * 15.0) * 0.6)
		var grain := sin(u * 160.0 + v * 13.0)
		c = Color("#2a170f").lerp(Color("#684027"), 0.30 + 0.20 * plank + 0.12 * grain)
		if absf(plank) > 0.985:
			c = Color("#1b110e")
		if u < 0.07 or u > 0.93:
			c = c.lerp(Color("#a16a36"), 0.16)
		if (x * 23 + y * 17) % 827 < 2:
			c = c.lightened(0.2)
	return c


# Gods of the Deep: supported basalt board, nine distinct carved cells,
# and an underwater ruin environment. These textures sit BEHIND real Buttons.
func _make_gods_stone_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge := mini(mini(x, 255 - x), mini(y, 255 - y))
			var grain := float((x * 43 + y * 71 + x * y * 3) % 137) / 137.0
			var c := Color("#071826").lerp(Color("#31536a"), grain * 0.43)
			if edge < 19:
				c = Color("#020c16").lerp(Color("#315269"), float(edge) / 19.0)
				if edge == 6 or edge == 15:
					c = Color("#17c9ef")
				elif edge == 10:
					c = Color("#b58b55")
			elif x % 79 < 2 or y % 83 < 2:
				c = c.lightened(0.13)
			if edge < 25 and (x % 46 < 3 or y % 46 < 3):
				c = c.lerp(Color("#bb8b4d"), 0.65)
			if y > 235:
				c = c.darkened(0.3)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _make_gods_stone_cell(index: int) -> Texture2D:
	var image := Image.create(96, 96, false, Image.FORMAT_RGB8)
	for y in range(96):
		for x in range(96):
			var grain := float((x * 37 + y * 41 + x * y + index * 89) % 109) / 109.0
			var c := Color("#071724").lerp(Color("#2d4c60"), grain * 0.53)
			var dx := float(x) - 47.5
			var dy := float(y) - 47.5
			var radius := sqrt(dx * dx + dy * dy)
			var angle := atan2(dy, dx)
			var mark := false
			match index % 3:
				0: # abyssal eye / iris
					mark = absf(radius - 27.0) < 1.5 or (absf(radius - 12.0) < 1.2 and absf(dy) < 10.0)
				1: # whirlpool glyph
					mark = absf(radius - (9.0 + 3.0 * (angle + PI))) < 1.4 and radius < 30.0
				2: # trident / spear glyph
					mark = (absf(dx) < 1.8 and absf(dy) < 29.0) or (absf(dy + 10.0) < 1.8 and absf(dx) < 19.0) or (absf(absf(dx) - 19.0) < 1.8 and dy > -26.0 and dy < -8.0)
			if mark:
				c = c.lerp(Color("#7db9c7"), 0.66)
			if x < 3 or y < 3 or x > 92 or y > 92:
				c = Color("#23cfff") if (x + y) % 11 < 9 else Color("#e3fbff")
			elif (x * 19 + y * 31 + index * 13) % 487 < 2:
				c = c.lightened(0.34)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

func _gods_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var c := Color("#021225").lerp(Color("#073a5d"), v * 0.78)
	var beam := absf(sin(u * 17.0 + v * 3.0))
	c = c.lerp(Color("#11a9e3"), 0.15 * pow(beam, 13.0) * (1.0 - v))
	# Drowned stone towers physically rise from the sea floor.
	for pillar in [0.055, 0.14, 0.85, 0.94]:
		var dx := absf(u - pillar)
		if dx < 0.019 and v > 0.12 and v < 0.95:
			c = Color("#05101d").lerp(Color("#25455a"), 0.25 + 0.4 * float((x + y) % 17) / 17.0)
			if dx > 0.014:
				c = c.lerp(Color("#26b9e6"), 0.32)
	# Far-off jellyfish: soft bell and suspended filaments.
	for j in range(4):
		var cx := 0.1 + float(j) * 0.265
		var cy := 0.29 + float(j % 2) * 0.18
		var px := (u - cx) * 11.0
		var py := (v - cy) * 11.0
		if px * px + (py + 0.05) * (py + 0.05) < 0.13 and py < 0.18:
			c = c.lerp(Color("#58d8ff"), 0.58)
		elif py > 0.12 and py < 0.74 and absf(sin(px * 17.0 + py * 3.0)) > 0.91 and absf(px) < 0.28:
			c = c.lerp(Color("#3e95c8"), 0.32)
	if v > 0.89:
		c = c.lerp(Color("#030b17"), 0.65)
	if (x * 23 + y * 43) % 941 < 2:
		c = c.lightened(0.37)
	return c

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

# Exact approved-reference-derived EMPTY cell textures, not screenshots.
# Native semantic Button art is projected onto the nine LIVE perspective
# Polygon2D tiles by main.gd::_refresh_perspective_layer().
func _canonical_cell_texture(world: int, index: int) -> Texture2D:
	assert(world >= 0 and world <= 6)
	assert(index >= 0 and index < 9)
	var key := "%d:%d" % [world, index]
	if not canonical_cell_cache.has(key):
		var folders := ["void", "pirate", "atlantis", "gods", "sand", "night", "north"]
		var folder: String = folders[world]
		var path := "%s/%s/cell_%02d.png" % [CANONICAL_CELL_ART_ROOT, folder, index]
		var texture := _load_bounded_texture(path) as Texture2D
		assert(texture != null, "Missing reference-derived cell art: " + path)
		canonical_cell_cache[key] = texture
	return canonical_cell_cache[key]


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
					# Quiet continuous split light; no stars, vortex, debris or pillars.
					# A soft center blend avoids a seam while leaving the board dominant.
					var split_light := Color("#b17a45").lerp(Color("#6699c8"), smoothstep(0.40, 0.60, u))
					var edge_light := clampf(absf(u - 0.5) * 2.0, 0.0, 1.0)
					var intensity := (0.13 + 0.19 * edge_light) * (1.0 - 0.30 * v)
					c = c.lerp(split_light, intensity)
				1:
					c = _pirate_backdrop_color(u, v, x, y)
				2:
					c = _atlantis_backdrop_color(u, v, x, y)
				3:
					c = _gods_backdrop_color(u, v, x, y)
				4:
					c = _sand_backdrop_color(u, v, x, y)
				5:
					c = _night_backdrop_color(u, v, x, y)
				6:
					c = _northern_backdrop_color(u, v, x, y)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

# Night Sea: storm-lit Gothic harbor behind the LIVE board and exact accepted
# scenery perimeter. No reference screenshot UI, ranks, cells or occupancy here.
func _night_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var horizon := 0.51
	var c := Color("#03091b").lerp(Color("#16355a"), clampf(v / horizon, 0.0, 1.0))
	if v < horizon:
		# Layered storm banks with narrow moonlit blue gaps.
		var cloud := sin(u * 29.0 + v * 17.0 + sin(u * 9.0) * 2.2)
		cloud += 0.58 * sin(u * 61.0 - v * 26.0)
		cloud += 0.31 * sin(u * 103.0 + v * 71.0)
		var bank := 0.32 + 0.18 * sin(u * 16.0 + 0.7)
		if v < bank and cloud > 0.42:
			c = c.lerp(Color("#08132b"), clampf((cloud - 0.42) * 0.43, 0.0, 0.62))
		elif cloud < -0.67:
			c = c.lerp(Color("#3261a1"), clampf((-cloud - 0.67) * 0.24, 0.0, 0.29))
		# The moon belongs to the sky, not a baked game-state overlay.
		var mx := (u - 0.744) * 1.79
		var my := v - 0.118
		var moon_distance := sqrt(mx * mx + my * my)
		if moon_distance < 0.175:
			c = c.lerp(Color("#6d9fe0"), (0.175 - moon_distance) / 0.175 * 0.33)
		if moon_distance < 0.058:
			c = Color("#d8eaff").lerp(Color("#a7c9f4"), clampf(moon_distance / 0.058, 0.0, 1.0) * 0.27)
			if sin(u * 251.0 + v * 123.0) > 0.92:
				c = c.darkened(0.11)
		# Gothic silhouettes on both sides; the approved perimeter supplies
		# the detailed castle walls while the center retains a deep harbor.
		for tower in [Vector3(0.085, 0.20, 0.027), Vector3(0.18, 0.30, 0.022), Vector3(0.90, 0.16, 0.030), Vector3(0.955, 0.25, 0.024)]:
			var dx := absf(u - tower.x)
			if dx < tower.z and v > tower.y:
				c = Color("#071021")
			elif v > tower.y - 0.055 and v < tower.y and dx < tower.z * (v - (tower.y - 0.055)) / 0.055:
				c = Color("#071021")
			if dx < tower.z * 0.65 and v > tower.y + 0.10 and v < horizon and (y % 21) < 5:
				c = c.lerp(Color("#ff9e46"), 0.72)
		# Masts, triangular sails and dark hulls are scenery, not game pieces.
		for ship in [Vector3(0.30, 0.36, 0.075), Vector3(0.53, 0.31, 0.095), Vector3(0.68, 0.37, 0.068)]:
			var dx := absf(u - ship.x)
			if dx < 0.003 and v > ship.y - 0.09 and v < 0.49:
				c = Color("#060c1c")
			if v > ship.y and v < 0.465 and dx < ship.z * (0.465 - v) / (0.465 - ship.y):
				c = c.lerp(Color("#142943"), 0.94)
			if v > 0.463 and v < 0.49 and dx < ship.z:
				c = Color("#060d1c")
	else:
		# Cold rolling harbor water and a broken moon reflection.
		var wave := sin(v * 310.0 + sin(u * 33.0) * 5.0)
		var ripples := sin(u * 143.0 - v * 61.0)
		c = Color("#06162e").lerp(Color("#22528a"), clampf(0.29 + 0.17 * wave + 0.11 * ripples, 0.04, 0.61))
		var moon_reflection := exp(-pow((u - 0.744) / (0.065 + 0.19 * (v - horizon)), 2.0))
		if wave > 0.54:
			c = c.lerp(Color("#8fb9f0"), moon_reflection * (wave - 0.54) * 0.65)
		# The foreground quay anchors the board support to the environment.
		if v > 0.82:
			var grain := float((x * 41 + y * 67 + x * y) % 127) / 127.0
			c = Color("#111a2d").lerp(Color("#30445a"), grain * 0.48)
			if (y % 23 < 2) or ((x + (int(y / 23) % 2) * 35) % 79 < 2):
				c = c.darkened(0.34)
	# Distant amber harbor lamps are small points, not rank-bearing pieces.
	for lamp in [Vector2(0.13, 0.43), Vector2(0.39, 0.47), Vector2(0.59, 0.46), Vector2(0.88, 0.42)]:
		var glow := sqrt(pow((u - lamp.x) * 1.79, 2.0) + pow(v - lamp.y, 2.0))
		if glow < 0.035:
			c = c.lerp(Color("#ff9c42"), (0.035 - glow) / 0.035 * 0.65)
		if glow < 0.005:
			c = Color("#ffe7a4")
	return c

# The board rests on one continuous, world-specific Gothic stone platform.
# Nine interactive compass cells are rendered separately above this material.
func _make_night_masonry_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge := mini(mini(x, 255 - x), mini(y, 255 - y))
			var grain := float((x * 31 + y * 71 + x * y * 5) % 149) / 149.0
			var c := Color("#111d30").lerp(Color("#354962"), grain * 0.51)
			if edge < 17:
				c = Color("#101326")
				if edge == 3 or edge == 14:
					c = Color("#c78c49")
				elif edge > 5 and edge < 13 and (x + y * 3) % 19 < 3:
					c = Color("#7b563a")
			elif y % 48 < 2 or (x + (int(y / 48) % 2) * 37) % 73 < 2:
				c = c.darkened(0.35)
			# Thin engraved navigation rings and compass rays belong to stone,
			# not to a pre-filled or noninteractive screenshot tile.
			var dx := float(x) - 127.5
			var dy := float(y) - 127.5
			var radius := sqrt(dx * dx + dy * dy)
			if edge >= 18 and (absf(radius - 85.0) < 0.8 or absf(radius - 61.0) < 0.8):
				c = c.lerp(Color("#b9814d"), 0.67)
			if edge >= 18 and radius < 86.0 and (absf(dx) < 0.8 or absf(dy) < 0.8):
				c = c.lerp(Color("#c28a50"), 0.55)
			image.set_pixel(x, y, c)
	return ImageTexture.create_from_image(image)

# Sand Sea: original sunset scenery beneath the separate approved-reference
# perimeter, physical board, interactive cells and dynamic pieces. The backdrop
# carries no board, UI, figures or reference-screenshot occupancy.
func _sand_backdrop_color(u: float, v: float, x: int, y: int) -> Color:
	var horizon := 0.54
	var c := Color("#522b38").lerp(Color("#f7a354"), clampf(v / horizon, 0.0, 1.0))
	if v < horizon:
		# Warm sunset with a localized sun disk and soft atmospheric glow.
		var sun_dist := sqrt(pow((u - 0.858) * 1.45, 2.0) + pow((v - 0.17) * 2.5, 2.0))
		if sun_dist < 0.13:
			c = c.lerp(Color("#ffd581"), (0.13 - sun_dist) / 0.13 * 0.63)
		if sun_dist < 0.040:
			c = Color("#fff8d6")
		# Layered Egyptian pyramids: left/right faces have different light.
		for pyramid in [Vector3(0.665, 0.035, 0.18), Vector3(0.805, 0.085, 0.17), Vector3(0.925, 0.21, 0.09)]:
			var py: float = pyramid.y
			var foot := 0.47
			var half_width: float = pyramid.z * clampf((v - py) / (foot - py), 0.0, 1.0)
			if v >= py and v <= foot and absf(u - pyramid.x) < half_width:
				var left_face: bool = u < pyramid.x
				c = Color("#9d6042") if left_face else Color("#d28b54")
				var course := absf(sin((v - py) * 420.0 + u * 7.0))
				if course > 0.95:
					c = c.darkened(0.16)
		# Distant Egyptian skyline and obelisks are grounded at the horizon.
		if v > 0.34 and v < horizon:
			var tower_band := int(u * 91.0)
			var tower_height := 0.38 + 0.055 * float((tower_band * 7) % 5) / 4.0
			if v >= tower_height and (tower_band % 7 < 4):
				c = c.lerp(Color("#8b4c39"), 0.63)
			for obelisk in [0.12, 0.24, 0.48, 0.95]:
				var dx := absf(u - obelisk)
				if (dx < 0.006 and v > 0.25) or (v > 0.22 and v < 0.25 and dx < (v - 0.22) * 0.20):
					c = Color("#75443b")
	else:
		# Sand/stone platform extends under the perspective-supported board.
		var dune := sin(u * 21.0 + v * 9.0) * 0.5 + sin(u * 54.0 - v * 14.0) * 0.25
		var grain := float((x * 37 + y * 61 + x * y) % 113) / 113.0
		c = Color("#96633f").lerp(Color("#d9a866"), clampf(0.52 + dune * 0.13 + grain * 0.18, 0.0, 1.0))
		if absf(sin(v * 160.0 + u * 19.0)) > 0.988:
			c = c.darkened(0.12)
	return c

# A real sandstone/lapis/gold SUPPORT material, shared by the board's
# perspective polygon and its semantic panel. Never includes board occupancy.
func _make_sandstone_plinth() -> Texture2D:
	var image := Image.create(256, 256, false, Image.FORMAT_RGB8)
	for y in range(256):
		for x in range(256):
			var edge := mini(mini(x, 255 - x), mini(y, 255 - y))
			var grain := float((x * 41 + y * 67 + x * y * 3) % 137) / 137.0
			var c := Color("#ad7945").lerp(Color("#e4b773"), grain * 0.66)
			if edge < 20:
				c = Color("#12364d")
				if edge < 3 or edge == 18:
					c = Color("#d6a347")
				elif edge > 5 and edge < 16:
					# Repeating lapis-and-gold border relief, no copied rank art.
					var glyph := (x + y * 3) % 27
					if glyph < 3 or glyph > 23:
						c = Color("#efb75c")
			elif x % 83 < 2 or y % 83 < 2:
				c = c.darkened(0.16)
			elif (x * 13 + y * 29) % 421 < 3:
				c = c.lightened(0.18)
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
