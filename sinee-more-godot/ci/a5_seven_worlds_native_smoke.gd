extends SceneTree

# A5 branch-only native smoke: checks seven live worlds and one legal game move.
# This is NOT real-phone touch or visual-parity qualification.
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("_exercise")

func _fail(message: String) -> void:
	failures.append(message)
	push_error("A5_NATIVE_FAIL " + message)

func _exercise() -> void:
	var packed := load("res://main.tscn") as PackedScene
	if packed == null:
		_fail("main scene cannot load")
		quit(1)
		return
	var game := packed.instantiate()
	root.add_child(game)
	await process_frame
	var board := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	if board == null:
		_fail("live board absent")
		quit(1)
		return
	for world in range(7):
		game.call("_set_world", world)
		await process_frame
		var title := game.get_node_or_null("SafeArea/Landscape/Center/TopBar/Title") as Label
		var backdrop := game.get_node_or_null("WorldBackdrop") as TextureRect
		var support := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Panel
		if int(game.get("current_world")) != world:
			_fail("world selection failed: %d" % world)
		if title == null or title.text != "СИНЕЕ МОРЕ":
			_fail("canonical masthead absent: %d" % world)
		if backdrop == null or backdrop.texture == null:
			_fail("live backdrop absent: %d" % world)
		if support == null:
			_fail("board support node absent: %d" % world)
		elif world != 0 and not support.visible:
			_fail("non-Void physical support hidden: %d" % world)
		for cell_index in range(9):
			var cell_name := "Cell%d%d" % [int(cell_index / 3), cell_index % 3]
			var cell := board.get_node_or_null(cell_name) as Button
			if cell == null:
				_fail("live cell absent: %d/%s" % [world, cell_name])
				continue
			if cell.get_node_or_null("WorldCellArt") == null:
				_fail("layered cell art absent: %d/%s" % [world, cell_name])
		if failures.is_empty():
			print("A5_WORLD_NATIVE_BOOTSTRAP_PASS ", world)
	game.call("_set_world", 1)
	var turn := int(game.get("turn"))
	var before := int(game.get("moves"))
	var played := false
	for rank in range(1, 10):
		if played:
			break
		for cell_index in range(9):
			if game.call("_is_legal_move", turn, rank, cell_index):
				game.call("_on_reserve_pressed", turn, rank - 1)
				game.call("_on_cell_pressed", cell_index)
				played = true
				break
	if not played or int(game.get("moves")) != before + 1:
		_fail("live reserve-to-board move failed")
	else:
		print("A5_LIVE_LEGAL_MOVE_PASS")
	if failures.is_empty():
		print("A5_SEVEN_WORLD_NATIVE_SMOKE_PASS")
		quit(0)
	else:
		print("A5_SEVEN_WORLD_NATIVE_SMOKE_FAIL count=", failures.size())
		quit(1)
