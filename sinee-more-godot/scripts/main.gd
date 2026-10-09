extends Control

const WorldVisuals = preload("res://scripts/world_visuals.gd")
const AIOpponent = preload("res://scripts/ai_opponent.gd")
const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")
var world_visuals = WorldVisuals.new()
var ai_engine = AIOpponent.new()
var current_world := 1
var ai_enabled := false
var ai_difficulty := 2
var ai_persona := 0
var world_picker: MenuButton
var ai_toggle: Button
var top_menu: MenuButton
var reset_dialog: ConfirmationDialog

const CELL_NAMES: Array[String] = ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]
var selected_cell := -1
var selected_reserve := -1
var turn := 1
var moves := 0
const RULE := "CD"
const LINES: Array[Array] = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
var board_stacks: Array[Array] = [[],[],[],[],[],[],[],[],[]]
var reserve_available: Array[Array] = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
var winner := 0
var win_line: Array = []
var game_over := false
var round_draw := false
const MATCH_TARGET := 3
var round_number := 1
var match_score: Array[int] = [0, 0]
var match_winner := 0
var blocked_player := 0

func _ready() -> void:
	set_process(true)
	_apply_requested_test_viewport()
	_prepare_world_shell()
	_create_perspective_layer()
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		cell.pressed.connect(_on_cell_pressed.bind(i))
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for i in range(reserve.get_child_count()):
			(reserve.get_child(i) as Button).pressed.connect(_on_reserve_pressed.bind(player, i))
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionPrimary") as Button).pressed.connect(_on_primary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionSecondary") as Button).pressed.connect(_on_secondary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionMenu") as Button).pressed.connect(_on_menu)
	_refresh_surface()
	_set_world(current_world)
	_update_status("ready")
	print("BLUE_SEA_GODOT_GAME_SURFACE_READY ", get_viewport_rect().size)
	if DisplayServer.get_name() == "headless":
		call_deferred("_run_headless_geometry_and_interaction_smoke")

func _prepare_world_shell() -> void:
	var center := get_node("SafeArea/Landscape/Center") as VBoxContainer
	var title := center.get_node("Title") as Label
	var topbar := HBoxContainer.new()
	topbar.name = "TopBar"
	center.add_child(topbar)
	center.move_child(topbar, 0)
	title.reparent(topbar, false)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_color_override("font_color", Color("#e32729"))
	world_picker = MenuButton.new()
	world_picker.name = "WorldPicker"
	world_picker.text = "МИР"
	world_picker.custom_minimum_size = Vector2(56, 44)
	topbar.add_child(world_picker)
	var popup := world_picker.get_popup()
	for i in range(WorldVisuals.WORLDS.size()):
		popup.add_radio_check_item(WorldVisuals.WORLDS[i], i)
	popup.id_pressed.connect(_set_world)
	ai_toggle = Button.new()
	ai_toggle.name = "AIToggle"
	ai_toggle.text = "ИИ: ВЫКЛ"
	ai_toggle.custom_minimum_size = Vector2(74, 44)
	topbar.add_child(ai_toggle)
	ai_toggle.pressed.connect(_toggle_ai)
	top_menu = MenuButton.new()
	top_menu.name = "GameMenu"
	top_menu.text = "МЕНЮ"
	top_menu.custom_minimum_size = Vector2(60, 44)
	topbar.add_child(top_menu)
	top_menu.get_popup().about_to_popup.connect(_populate_game_menu)
	top_menu.get_popup().id_pressed.connect(_on_game_menu_item)
	reset_dialog = ConfirmationDialog.new()
	reset_dialog.dialog_text = "Сбросить текущий матч?"
	add_child(reset_dialog)
	reset_dialog.confirmed.connect(_confirm_reset_match)
	center.get_node("WorldStrip").hide()
	var board := center.get_node("BoardAspect/Board") as GridContainer
	for i in range(CELL_NAMES.size()):
		board.move_child(board.get_node(CELL_NAMES[i]), i)
	var aspect := center.get_node("BoardAspect") as AspectRatioContainer
	aspect.custom_minimum_size = Vector2(0, 132)
	aspect.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var dock := HBoxContainer.new()
	dock.name = "ReserveDock"
	dock.alignment = BoxContainer.ALIGNMENT_CENTER
	dock.custom_minimum_size = Vector2(0, 44)
	center.add_child(dock)
	center.move_child(dock, aspect.get_index() + 1)
	for player in [1, 2]:
		var rail := get_node("SafeArea/Landscape/LeftRail" if player == 1 else "SafeArea/Landscape/RightRail") as VBoxContainer
		var reserve := rail.get_node("ReserveOne" if player == 1 else "ReserveTwo") as GridContainer
		reserve.reparent(dock, false)
		reserve.columns = 9
		reserve.add_theme_constant_override("h_separation", 1)
		for piece in reserve.get_children():
			(piece as Button).custom_minimum_size = Vector2(44, 44)
	get_node("SafeArea/Landscape/LeftRail").hide()
	get_node("SafeArea/Landscape/RightRail").hide()
	center.get_node("Status").visible = get_viewport_rect().size.y >= 360

func _set_world(world: int) -> void:
	if world < 0 or world >= WorldVisuals.WORLDS.size():
		return
	current_world = world
	world_visuals.apply_world(self, current_world)
	if world_picker != null:
		var popup := world_picker.get_popup()
		for i in range(popup.item_count):
			popup.set_item_checked(i, i == current_world)
	_refresh_surface()
	_refresh_perspective_layer()

func _toggle_ai() -> void:
	ai_enabled = not ai_enabled
	ai_toggle.text = "ИИ: ВКЛ" if ai_enabled else "ИИ: ВЫКЛ"
	if ai_enabled and turn == 2 and not game_over:
		call_deferred("_play_ai_turn")

func _play_ai_turn() -> void:
	if not ai_enabled or game_over or turn != 2:
		return
	var move: Dictionary = ai_engine.choose_move(board_stacks, reserve_available, 2, RULE, ai_difficulty, ai_persona)
	if move.is_empty():
		return
	selected_reserve = int(move["rank"]) - 1
	selected_cell = int(move["cell"])
	assert(_is_legal_move(2, selected_reserve + 1, selected_cell))
	_on_primary()

func _populate_game_menu() -> void:
	var popup := top_menu.get_popup()
	popup.clear()
	popup.add_item("Сбросить матч…", 1)
	if game_over:
		popup.add_item("Следующий раунд", 2)

func _on_game_menu_item(id: int) -> void:
	if id == 1:
		reset_dialog.popup_centered()
	elif id == 2 and game_over:
		_on_menu()

func _confirm_reset_match() -> void:
	match_score = [0, 0]
	match_winner = 0
	round_number = 1
	_reset_round()

func _set_piece_badge(button: Button, texture: Texture2D, rank: int) -> void:
	button.text = ""
	button.icon = null
	button.clip_contents = true
	var art := button.get_node_or_null("RankArt") as TextureRect
	if art == null:
		art = TextureRect.new()
		art.name = "RankArt"
		art.mouse_filter = Control.MOUSE_FILTER_IGNORE
		art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		button.add_child(art)
		art.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	art.texture = texture
	art.visible = texture != null
	var number := button.get_node_or_null("RankNumber") as Label
	if number == null:
		number = Label.new()
		number.name = "RankNumber"
		number.mouse_filter = Control.MOUSE_FILTER_IGNORE
		number.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		number.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		number.add_theme_font_size_override("font_size", 16)
		number.add_theme_color_override("font_color", Color("#fff8df"))
		number.add_theme_color_override("font_outline_color", Color("#142332"))
		number.add_theme_constant_override("outline_size", 4)
		button.add_child(number)
		number.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	number.text = str(rank) if rank > 0 else ""
	number.visible = rank > 0

func _apply_requested_test_viewport() -> void:
	var args := OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--nd-test-size="):
			var parts := arg.trim_prefix("--nd-test-size=").split("x")
			if parts.size() == 2:
				var requested := Vector2i(int(parts[0]), int(parts[1]))
				if requested.x > 0 and requested.y > 0:
					get_window().content_scale_size = requested
					get_window().size = requested
					print("BLUE_SEA_TEST_VIEWPORT_REQUEST ", requested)

func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_ENTER, KEY_SPACE:
			_on_primary()
			get_viewport().set_input_as_handled()
		KEY_ESCAPE, KEY_BACKSPACE:
			_on_secondary()
			get_viewport().set_input_as_handled()
		KEY_M:
			_on_menu()
			get_viewport().set_input_as_handled()


# A5 interactive perspective layer: one shared live board, not a screenshot.
# Native 3x3 buttons remain the semantic/test nodes; their visual layer is hidden.
var perspective_plinth: Polygon2D
var perspective_tiles: Array[Polygon2D] = []
var perspective_icons: Array[TextureRect] = []
var perspective_ranks: Array[Label] = []
var perspective_rect := Rect2()

func _create_perspective_layer() -> void:
	var board := get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	for cell in board.get_children():
		(cell as Button).modulate.a = 0.0
		(cell as Button).mouse_filter = Control.MOUSE_FILTER_IGNORE
	var topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	topbar.z_index = 5
	dock.z_index = 5
	perspective_plinth = Polygon2D.new()
	perspective_plinth.z_index = 1
	add_child(perspective_plinth)
	for i in range(9):
		var tile := Polygon2D.new()
		tile.z_index = 2
		add_child(tile)
		perspective_tiles.append(tile)
		var icon := TextureRect.new()
		icon.name = "PerspectivePiece%d" % i
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.z_index = 3
		add_child(icon)
		perspective_icons.append(icon)
		var rank := Label.new()
		rank.name = "PerspectiveRank%d" % i
		rank.mouse_filter = Control.MOUSE_FILTER_IGNORE
		rank.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		rank.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		rank.add_theme_font_size_override("font_size", 16)
		rank.add_theme_color_override("font_color", Color("#fff9df"))
		rank.add_theme_color_override("font_outline_color", Color("#142332"))
		rank.add_theme_constant_override("outline_size", 4)
		rank.z_index = 4
		add_child(rank)
		perspective_ranks.append(rank)
	call_deferred("_refresh_perspective_layer")

func _perspective_board_rect() -> Rect2:
	var size := get_viewport_rect().size
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	# Keep the nine playable cells above the active reserve at very low heights.
	var height := minf(size.y, maxf(100.0, (dock.global_position.y - 5.0) / 0.80))
	return Rect2(Vector2.ZERO, Vector2(size.x, height))

func _refresh_perspective_layer() -> void:
	if perspective_tiles.size() != 9:
		return
	perspective_rect = _perspective_board_rect()
	var base := PerspectiveGeometry.board_quad(current_world, perspective_rect)
	perspective_plinth.visible = current_world != 0
	var backing := PackedVector2Array()
	for p in base:
		backing.append(p + Vector2(0.0, 9.0))
	perspective_plinth.polygon = backing
	perspective_plinth.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.47)
	for i in range(9):
		var quad := PerspectiveGeometry.cell_quad(current_world, i, perspective_rect)
		var tile := perspective_tiles[i]
		tile.polygon = quad
		tile.color = WorldVisuals.BOARD_COLORS[current_world].lightened(0.06)
		var source := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var art := source.get_node_or_null("WorldCellArt") as TextureRect
		if art != null and art.visible and art.texture != null:
			tile.texture = art.texture
			var ts := art.texture.get_size()
			tile.uv = PackedVector2Array([Vector2.ZERO, Vector2(ts.x, 0), ts, Vector2(0, ts.y)])
			tile.color = Color.WHITE
		else:
			tile.texture = null
		var center := PerspectiveGeometry.cell_center(current_world, i, perspective_rect)
		var width := (quad[1] - quad[0]).length()
		var height := (quad[3] - quad[0]).length()
		var extent := minf(44.0, minf(width * 0.56, height * 0.88))
		var rect := Rect2(center - Vector2.ONE * extent * 0.5, Vector2.ONE * extent)
		var top := _top_piece(i)
		var icon := perspective_icons[i]
		var rank := perspective_ranks[i]
		icon.position = rect.position
		icon.size = rect.size
		rank.position = rect.position
		rank.size = rect.size
		icon.visible = not top.is_empty()
		rank.visible = not top.is_empty()
		if not top.is_empty():
			icon.texture = world_visuals.piece_texture(current_world, int(top.player), int(top.rank))
			rank.text = str(int(top.rank))
		else:
			icon.texture = null
			rank.text = ""

func _input(event: InputEvent) -> void:
	if perspective_tiles.size() != 9 or game_over:
		return
	var position := Vector2(-1, -1)
	if event is InputEventScreenTouch and event.pressed:
		position = event.position
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		position = event.position
	if position.x < 0.0:
		return
	var index := PerspectiveGeometry.cell_at(current_world, position, perspective_rect)
	if index >= 0:
		_on_cell_pressed(index)
		get_viewport().set_input_as_handled()

func _process(_delta: float) -> void:
	if perspective_tiles.size() == 9 and perspective_rect != _perspective_board_rect():
		_refresh_perspective_layer()
	var size := get_viewport_rect().size
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	var base := "R%d • P%d • score %d–%d • %d×%d • moves %d" % [round_number, turn, match_score[0], match_score[1], int(size.x), int(size.y), moves]
	if match_winner != 0:
		base = "MATCH • P%d wins • %d–%d • Menu: new match" % [match_winner, match_score[0], match_score[1]]
	elif game_over and winner != 0:
		base = "ROUND %d • P%d wins • %d–%d • Menu: next round" % [round_number, winner, match_score[0], match_score[1]]
	elif game_over and round_draw:
		base = "ROUND %d • DRAW • %d–%d • Menu: next round" % [round_number, match_score[0], match_score[1]]
	elif blocked_player != 0:
		base = "R%d • P%d blocked • P%d continues • score %d–%d" % [round_number, blocked_player, turn, match_score[0], match_score[1]]
	if size.x < size.y:
		base += " • rotate device"
	if selected_reserve >= 0:
		base += " • reserve %d selected" % selected_reserve
	if selected_cell >= 0:
		base += " • cell %d selected" % selected_cell
	status.text = base

func _reserve_node(player: int) -> GridContainer:
	return get_node("SafeArea/Landscape/Center/ReserveDock/ReserveOne" if player == 1 else "SafeArea/Landscape/Center/ReserveDock/ReserveTwo") as GridContainer

func _on_reserve_pressed(player: int, index: int) -> void:
	if player != turn:
		_update_status("wrong player reserve")
		return
	if not reserve_available[player - 1][index]:
		_update_status("piece already played")
		return
	selected_reserve = index
	selected_cell = -1
	_update_status("reserve %d" % index)

func _top_piece(cell: int) -> Dictionary:
	return {} if board_stacks[cell].is_empty() else board_stacks[cell][-1]

func _is_legal_move(player: int, rank: int, cell: int) -> bool:
	if game_over or player != turn or cell < 0 or cell > 8 or rank < 1 or rank > 9:
		return false
	if not reserve_available[player - 1][rank - 1]:
		return false
	var top := _top_piece(cell)
	if top.is_empty():
		return true
	if int(top.player) == player or rank <= int(top.rank):
		return false
	if (RULE == "C" or RULE == "CD") and board_stacks[cell].size() >= 2:
		return false
	return true

func _winning_line(player: int) -> Array:
	for line in LINES:
		var ranks: Array[int] = []
		var owned := true
		for cell in line:
			var top := _top_piece(cell)
			if top.is_empty() or int(top.player) != player:
				owned = false
				break
			ranks.append(int(top.rank))
		if not owned:
			continue
		var ladder := (ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2])
		if RULE == "C" or ladder:
			return line.duplicate()
	return []

func _has_legal_move(player: int) -> bool:
	for rank in range(1, 10):
		if not reserve_available[player - 1][rank - 1]:
			continue
		for cell in range(9):
			if _is_legal_move_for(player, rank, cell):
				return true
	return false

func _is_legal_move_for(player: int, rank: int, cell: int) -> bool:
	if game_over or cell < 0 or cell > 8 or not reserve_available[player - 1][rank - 1]:
		return false
	var top := _top_piece(cell)
	if top.is_empty():
		return true
	if int(top.player) == player or rank <= int(top.rank):
		return false
	if (RULE == "C" or RULE == "CD") and board_stacks[cell].size() >= 2:
		return false
	return true

func _on_cell_pressed(index: int) -> void:
	if game_over or index < 0 or index >= CELL_NAMES.size():
		return
	selected_cell = index
	if selected_reserve >= 0:
		_on_primary()
	else:
		_update_status("cell %d" % index)

func _on_primary() -> void:
	if selected_reserve < 0 or selected_cell < 0:
		_update_status("select reserve and cell")
		return
	var rank := selected_reserve + 1
	if not _is_legal_move(turn, rank, selected_cell):
		_update_status("illegal move")
		return
	var moving_player := turn
	board_stacks[selected_cell].append({"player": moving_player, "rank": rank})
	reserve_available[moving_player - 1][selected_reserve] = false
	moves += 1
	win_line = _winning_line(moving_player)
	if not win_line.is_empty():
		winner = moving_player
		game_over = true
		match_score[moving_player - 1] += 1
		if match_score[moving_player - 1] >= MATCH_TARGET:
			match_winner = moving_player
	else:
		blocked_player = 0
		turn = 2 if moving_player == 1 else 1
		if not _has_legal_move(turn):
			blocked_player = turn
			turn = moving_player
			if not _has_legal_move(turn):
				game_over = true
				round_draw = true
				blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	_refresh_surface()
	_update_status("game won" if winner != 0 else "move committed")
	if ai_enabled and turn == 2 and not game_over:
		call_deferred("_play_ai_turn")

func _on_secondary() -> void:
	selected_reserve = -1
	selected_cell = -1
	_update_status("selection cleared")

func _reset_round() -> void:
	board_stacks = [[],[],[],[],[],[],[],[],[]]
	reserve_available = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
	winner = 0
	win_line = []
	game_over = false
	round_draw = false
	blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	moves = 0
	turn = 1 if round_number % 2 == 1 else 2
	_refresh_surface()

func _on_menu() -> void:
	if not game_over:
		_update_status("menu action")
		return
	if match_winner != 0:
		match_score = [0, 0]
		match_winner = 0
		round_number = 1
		_reset_round()
		_update_status("new match")
	else:
		round_number += 1
		_reset_round()
		_update_status("next round")

func _refresh_surface() -> void:
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionMenu") as Button).visible = game_over
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var top := _top_piece(i)
		_set_piece_badge(cell, null if top.is_empty() else world_visuals.piece_texture(current_world, int(top.player), int(top.rank)), 0 if top.is_empty() else int(top.rank))
		cell.disabled = game_over
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		reserve.visible = player == turn and not game_over
		for i in range(reserve.get_child_count()):
			var piece := reserve.get_child(i) as Button
			_set_piece_badge(piece, world_visuals.piece_texture(current_world, player, i + 1) if reserve_available[player - 1][i] else null, i + 1 if reserve_available[player - 1][i] else 0)
			piece.disabled = game_over or player != turn or not reserve_available[player - 1][i]
	_refresh_perspective_layer()

func _update_status(event: String) -> void:
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	status.tooltip_text = event

func _geometry_snapshot() -> Dictionary:
	var paths := {
		"safe": "SafeArea",
		"landscape": "SafeArea/Landscape",
		"left": "SafeArea/Landscape/LeftRail",
		"center": "SafeArea/Landscape/Center",
		"board": "SafeArea/Landscape/Center/BoardAspect/Board",
		"right": "SafeArea/Landscape/RightRail",
		"reserve1": "SafeArea/Landscape/LeftRail/ReserveOne",
		"reserve2": "SafeArea/Landscape/RightRail/ReserveTwo",
		"actions": "SafeArea/Landscape/RightRail/Actions"
	}
	var out := {}
	for key in paths:
		var control := get_node(paths[key]) as Control
		out[key] = {"x": control.position.x, "y": control.position.y, "w": control.size.x, "h": control.size.y}
	return out

func _assert_min_control_size(control: Control, minimum: Vector2, label: String) -> void:
	assert(control.size.x + 0.01 >= minimum.x, "%s width %.2f < %.2f" % [label, control.size.x, minimum.x])
	assert(control.size.y + 0.01 >= minimum.y, "%s height %.2f < %.2f" % [label, control.size.y, minimum.y])

func _assert_landscape_geometry() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	var viewport := get_viewport_rect().size
	assert(viewport.x >= viewport.y, "landscape contract violated")
	var board := get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as HBoxContainer
	assert(dock.size.y >= 44.0, "reserve dock too small")
	for i in range(CELL_NAMES.size()):
		assert(board.get_child(i).name == CELL_NAMES[i], "board order mismatch")
		_assert_min_control_size(board.get_child(i) as Control, Vector2(44, 44), "cell")
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		assert(reserve.visible == (player == turn and not game_over), "inactive reserve visible")
		for piece in reserve.get_children():
			_assert_min_control_size(piece as Control, Vector2(44, 44), "reserve")
	print("BLUE_SEA_MOBILE_DOCK_GEOMETRY_PASS ", viewport)

func _run_headless_geometry_and_interaction_smoke() -> void:
	await _assert_landscape_geometry()
	_run_headless_interaction_smoke()
	await _run_headless_input_parity_smoke()
	await _run_headless_orientation_reload_smoke()

func _run_headless_input_parity_smoke() -> void:
	_reset_round()
	var pointer_reserve := 2
	var pointer_cell := 4
	_on_cell_pressed(pointer_cell)
	assert(moves == 0 and _top_piece(pointer_cell).is_empty())
	_on_reserve_pressed(1, pointer_reserve)
	_on_cell_pressed(pointer_cell)
	assert(_top_piece(pointer_cell) == {"player": 1, "rank": pointer_reserve + 1})
	assert(turn == 2 and moves == 1)
	_reset_round()
	_on_reserve_pressed(1, pointer_reserve)
	selected_cell = pointer_cell
	var primary_key := InputEventKey.new()
	primary_key.keycode = KEY_ENTER
	primary_key.pressed = true
	_unhandled_key_input(primary_key)
	assert(_top_piece(pointer_cell) == {"player": 1, "rank": pointer_reserve + 1})
	assert(turn == 2 and moves == 1)
	var clear_key := InputEventKey.new()
	clear_key.keycode = KEY_ESCAPE
	clear_key.pressed = true
	selected_reserve = 3
	selected_cell = 3
	_unhandled_key_input(clear_key)
	assert(selected_reserve == -1 and selected_cell == -1)
	var menu_key := InputEventKey.new()
	menu_key.keycode = KEY_M
	menu_key.pressed = true
	game_over = true
	round_draw = true
	var before_round := round_number
	_unhandled_key_input(menu_key)
	assert(round_number == before_round + 1 and not game_over)
	print("BLUE_SEA_INPUT_PARITY_PASS touch_pointer_buttons=PRIMARY/CLEAR/MENU keyboard=ENTER_ESCAPE_M")

func _run_headless_orientation_reload_smoke() -> void:
	var window := get_window()
	var original := Vector2i(window.content_scale_size)
	if original.x <= 0 or original.y <= 0:
		original = Vector2i(int(get_viewport_rect().size.x), int(get_viewport_rect().size.y))
	var portrait := Vector2i(mini(original.x, original.y), maxi(original.x, original.y))
	window.content_scale_size = portrait
	window.size = portrait
	await get_tree().process_frame
	await get_tree().process_frame
	_process(0.0)
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	assert(status.text.contains("rotate device"))
	window.content_scale_size = original
	window.size = original
	await get_tree().process_frame
	await get_tree().process_frame
	_process(0.0)
	assert(not status.text.contains("rotate device"))
	await _assert_landscape_geometry()
	print("BLUE_SEA_ORIENTATION_RELOAD_PASS portrait=", portrait, " restored=", original)

func _run_headless_interaction_smoke() -> void:
	# D2 rules parity smoke: rank stacking, Stack-2 cap, ladder win and illegal preservation.
	_on_reserve_pressed(1, 0)
	_on_cell_pressed(0)
	assert(_top_piece(0) == {"player": 1, "rank": 1})
	assert(turn == 2 and moves == 1)

	# Opponent may cover with a strictly larger rank.
	_on_reserve_pressed(2, 1)
	_on_cell_pressed(0)
	assert(_top_piece(0) == {"player": 2, "rank": 2})
	assert(board_stacks[0].size() == 2)
	assert(turn == 1 and moves == 2)

	# CD uses Stack 2: a third piece cannot cover this cell.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(0)
	assert(board_stacks[0].size() == 2)
	assert(reserve_available[0][2] == true)
	assert(turn == 1 and moves == 2)

	# Build an increasing P1 ladder 1-2-3 across cells 3,4,5.
	_on_secondary()
	_on_reserve_pressed(1, 0)
	# rank 1 was already spent, so use 3/4/5 instead.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(3)
	_on_reserve_pressed(2, 0)
	_on_cell_pressed(6)
	_on_reserve_pressed(1, 3)
	_on_cell_pressed(4)
	_on_reserve_pressed(2, 2)
	_on_cell_pressed(7)
	_on_reserve_pressed(1, 4)
	_on_cell_pressed(5)
	assert(game_over and winner == 1)
	assert(win_line == [3,4,5])
	assert(_top_piece(3).rank == 3 and _top_piece(4).rank == 4 and _top_piece(5).rank == 5)
	assert(match_score == [1, 0])
	_on_menu()
	assert(round_number == 2 and turn == 2 and not game_over and winner == 0 and moves == 0)
	assert(match_score == [1, 0])
	for stack in board_stacks:
		assert(stack.is_empty())
	print("BLUE_SEA_D2_RULES_SMOKE_PASS round=", round_number, " starter=", turn, " score=", match_score)

	# Draw/stalemate must advance the round without changing match score.
	var score_before_draw := match_score.duplicate()
	round_draw = true
	game_over = true
	winner = 0
	_on_menu()
	assert(round_number == 3 and turn == 1 and not game_over and not round_draw and winner == 0 and moves == 0)
	assert(match_score == score_before_draw)
	for stack in board_stacks:
		assert(stack.is_empty())
	print("BLUE_SEA_DRAW_FLOW_SMOKE_PASS round=", round_number, " starter=", turn, " score=", match_score)

	# A player with no legal move is explicitly surfaced and skipped while the opponent continues.
	_reset_round()
	turn = 2
	reserve_available[1] = [false,false,false,false,false,false,false,false,false]
	assert(not _has_legal_move(2) and _has_legal_move(1))
	blocked_player = 2
	turn = 1
	assert(blocked_player == 2 and turn == 1 and not game_over)
	_reset_round()
	assert(blocked_player == 0)
	assert((_reserve_node(1).get_child(0) as Button).disabled == false)
	assert((_reserve_node(2).get_child(0) as Button).disabled == true)
	print("BLUE_SEA_BLOCKED_PLAYER_SMOKE_PASS blocked=P2 continuing=P1 reset=PASS")
	print("BLUE_SEA_TURN_AWARE_RESERVES_SMOKE_PASS active=P1 inactive=P2")