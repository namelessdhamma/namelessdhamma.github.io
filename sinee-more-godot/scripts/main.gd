extends Control

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

func _ready() -> void:
	set_process(true)
	_apply_requested_test_viewport()
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		cell.pressed.connect(_on_cell_pressed.bind(i))
	for player in [1, 2]:
		var reserve := get_node("SafeArea/Landscape/%s/Reserve%s" % ["LeftRail" if player == 1 else "RightRail", "One" if player == 1 else "Two"]) as GridContainer
		for i in range(reserve.get_child_count()):
			(reserve.get_child(i) as Button).pressed.connect(_on_reserve_pressed.bind(player, i))
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionPrimary") as Button).pressed.connect(_on_primary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionSecondary") as Button).pressed.connect(_on_secondary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionMenu") as Button).pressed.connect(_on_menu)
	_refresh_surface()
	_update_status("ready")
	print("BLUE_SEA_GODOT_GAME_SURFACE_READY ", get_viewport_rect().size)
	if DisplayServer.get_name() == "headless":
		call_deferred("_run_headless_geometry_and_interaction_smoke")

func _apply_requested_test_viewport() -> void:
	var args := OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--nd-test-size="):
			var parts := arg.trim_prefix("--nd-test-size=").split("x")
			if parts.size() == 2:
				var requested := Vector2i(int(parts[0]), int(parts[1]))
				if requested.x > 0 and requested.y > 0:
					get_window().size = requested
					print("BLUE_SEA_TEST_VIEWPORT_REQUEST ", requested)

func _process(_delta: float) -> void:
	var size := get_viewport_rect().size
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	var base := "P%d • %d×%d • moves %d" % [turn, int(size.x), int(size.y), moves]
	if size.x < size.y:
		base += " • rotate device"
	if selected_reserve >= 0:
		base += " • reserve %d selected" % selected_reserve
	if selected_cell >= 0:
		base += " • cell %d selected" % selected_cell
	status.text = base

func _reserve_node(player: int) -> GridContainer:
	return get_node("SafeArea/Landscape/%s/Reserve%s" % ["LeftRail" if player == 1 else "RightRail", "One" if player == 1 else "Two"]) as GridContainer

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
	selected_cell = index
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
	else:
		turn = 2 if moving_player == 1 else 1
		if not _has_legal_move(turn):
			turn = moving_player
			if not _has_legal_move(turn):
				game_over = true
	selected_reserve = -1
	selected_cell = -1
	_refresh_surface()
	_update_status("game won" if winner != 0 else "move committed")

func _on_secondary() -> void:
	selected_reserve = -1
	selected_cell = -1
	_update_status("selection cleared")

func _on_menu() -> void:
	_update_status("menu action")

func _refresh_surface() -> void:
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var top := _top_piece(i)
		cell.text = "·" if top.is_empty() else "P%d/%d" % [int(top.player), int(top.rank)]
		cell.disabled = game_over
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for i in range(reserve.get_child_count()):
			var piece := reserve.get_child(i) as Button
			piece.text = "%d" % (i + 1) if reserve_available[player - 1][i] else "—"
			piece.disabled = not reserve_available[player - 1][i]

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
	assert(viewport.x >= viewport.y, "landscape contract violated: %s" % viewport)
	var safe := get_node("SafeArea") as Control
	var landscape := get_node("SafeArea/Landscape") as Control
	var left := get_node("SafeArea/Landscape/LeftRail") as Control
	var center := get_node("SafeArea/Landscape/Center") as Control
	var right := get_node("SafeArea/Landscape/RightRail") as Control
	assert(safe.position.x >= 11.9 and safe.position.y >= 11.9)
	assert(safe.position.x + safe.size.x <= viewport.x - 11.9)
	assert(safe.position.y + safe.size.y <= viewport.y - 11.9)
	assert(left.size.x >= 145.0 and right.size.x >= 145.0)
	assert(center.size.x > 0.0 and center.size.y > 0.0)
	assert(left.position.x + left.size.x <= center.position.x + 0.01)
	assert(center.position.x + center.size.x <= right.position.x + 0.01)
	for name in CELL_NAMES:
		_assert_min_control_size(get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + name) as Control, Vector2(44, 44), "cell " + name)
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for i in range(reserve.get_child_count()):
			_assert_min_control_size(reserve.get_child(i) as Control, Vector2(44, 44), "P%d reserve %d" % [player, i])
	for action_name in ["ActionPrimary", "ActionSecondary", "ActionMenu"]:
		_assert_min_control_size(get_node("SafeArea/Landscape/RightRail/Actions/" + action_name) as Control, Vector2(44, 44), action_name)
	print("BLUE_SEA_GEOMETRY_PASS viewport=", viewport, " geometry=", _geometry_snapshot())

func _run_headless_geometry_and_interaction_smoke() -> void:
	await _assert_landscape_geometry()
	_run_headless_interaction_smoke()

func _run_headless_interaction_smoke() -> void:
	# D2 rules parity smoke: rank stacking, Stack-2 cap, ladder win and illegal preservation.
	_on_reserve_pressed(1, 0)
	_on_cell_pressed(0)
	_on_primary()
	assert(_top_piece(0) == {"player": 1, "rank": 1})
	assert(turn == 2 and moves == 1)

	# Opponent may cover with a strictly larger rank.
	_on_reserve_pressed(2, 1)
	_on_cell_pressed(0)
	_on_primary()
	assert(_top_piece(0) == {"player": 2, "rank": 2})
	assert(board_stacks[0].size() == 2)
	assert(turn == 1 and moves == 2)

	# CD uses Stack 2: a third piece cannot cover this cell.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(0)
	_on_primary()
	assert(board_stacks[0].size() == 2)
	assert(reserve_available[0][2] == true)
	assert(turn == 1 and moves == 2)

	# Build an increasing P1 ladder 1-2-3 across cells 3,4,5.
	_on_secondary()
	_on_reserve_pressed(1, 0)
	# rank 1 was already spent, so use 3/4/5 instead.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(3)
	_on_primary()
	_on_reserve_pressed(2, 0)
	_on_cell_pressed(6)
	_on_primary()
	_on_reserve_pressed(1, 3)
	_on_cell_pressed(4)
	_on_primary()
	_on_reserve_pressed(2, 2)
	_on_cell_pressed(7)
	_on_primary()
	_on_reserve_pressed(1, 4)
	_on_cell_pressed(5)
	_on_primary()
	assert(game_over and winner == 1)
	assert(win_line == [3,4,5])
	assert(_top_piece(3).rank == 3 and _top_piece(4).rank == 4 and _top_piece(5).rank == 5)
	print("BLUE_SEA_D2_RULES_SMOKE_PASS winner=", winner, " line=", win_line, " moves=", moves)
