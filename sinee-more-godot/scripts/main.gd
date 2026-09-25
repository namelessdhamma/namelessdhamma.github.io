extends Control

const CELL_NAMES: Array[String] = ["Cell00", "Cell01", "Cell10", "Cell11"]
var selected_cell := -1
var selected_reserve := -1
var turn := 1
var moves := 0
var board_occupancy: Array[int] = [0, 0, 0, 0]
var reserve_available: Array[Array] = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]

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

func _on_cell_pressed(index: int) -> void:
	if board_occupancy[index] != 0:
		_update_status("cell occupied")
		return
	selected_cell = index
	_update_status("cell %d" % index)

func _on_primary() -> void:
	if selected_reserve < 0 or selected_cell < 0:
		_update_status("select reserve and cell")
		return
	if board_occupancy[selected_cell] != 0 or not reserve_available[turn - 1][selected_reserve]:
		_update_status("illegal move")
		return
	var moving_player := turn
	board_occupancy[selected_cell] = moving_player
	reserve_available[moving_player - 1][selected_reserve] = false
	moves += 1
	turn = 2 if moving_player == 1 else 1
	selected_reserve = -1
	selected_cell = -1
	_refresh_surface()
	_update_status("move committed")

func _on_secondary() -> void:
	selected_reserve = -1
	selected_cell = -1
	_update_status("selection cleared")

func _on_menu() -> void:
	_update_status("menu action")

func _refresh_surface() -> void:
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var owner := board_occupancy[i]
		cell.text = "·" if owner == 0 else "P%d" % owner
		cell.disabled = owner != 0
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
	# Exercise the real interaction handlers and verify state + rendered controls.
	_on_reserve_pressed(1, 0)
	_on_cell_pressed(0)
	_on_primary()
	assert(board_occupancy == [1, 0, 0, 0])
	assert(reserve_available[0][0] == false)
	assert(turn == 2 and moves == 1)
	var cell0 := get_node("SafeArea/Landscape/Center/BoardAspect/Board/Cell00") as Button
	var p1r0 := get_node("SafeArea/Landscape/LeftRail/ReserveOne/R00") as Button
	assert(cell0.disabled and cell0.text == "P1")
	assert(p1r0.disabled and p1r0.text == "—")

	# Illegal occupied-cell attempt must preserve board, reserve, turn and move count.
	_on_reserve_pressed(2, 0)
	_on_cell_pressed(0)
	_on_primary()
	assert(board_occupancy == [1, 0, 0, 0])
	assert(reserve_available[1][0] == true)
	assert(turn == 2 and moves == 1)

	# Recovery after rejection: choose free cell and commit the still-selected P2 piece.
	_on_cell_pressed(1)
	_on_primary()
	assert(board_occupancy == [1, 2, 0, 0])
	assert(reserve_available[1][0] == false)
	assert(turn == 1 and moves == 2)
	print("BLUE_SEA_INTERACTION_SMOKE_PASS board=", board_occupancy, " turn=", turn, " moves=", moves)
