extends SceneTree
# Native Godot 4.7.2 smoke; NOT PASSED until the engine executes this fixture.
# godot --headless --path sinee-more-godot --script res://tests/a5_v109_atlantis_canonical_cells_runtime_smoke.gd
func _initialize() -> void:
    call_deferred("_run")

func _fail(reason: String) -> void:
    push_error("A5_V109_NIGHT_CANON_FAIL " + reason)
    quit(1)

func _run() -> void:
    var scene := load("res://main.tscn") as PackedScene
    if scene == null:
        _fail("main scene missing")
        return
    var game := scene.instantiate() as Control
    root.add_child(game)
    await process_frame
    game.set("ai_enabled", false)
    game.call("_set_world", 5)
    await process_frame
    var stacks: Array = game.get("board_stacks").duplicate(true)
    var reserves: Array = game.get("reserve_available").duplicate(true)
    var projected: Array = game.get("perspective_tiles")
    var seen := {}
    if projected.size() != 9:
        _fail("expected nine perspective tiles")
        return
    var names := ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]
    for i in range(9):
        var cell := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + names[i]) as Button
        if cell == null or cell.disabled:
            _fail("missing interactive cell " + str(i))
            return
        var art := cell.get_node_or_null("WorldCellArt") as TextureRect
        if art == null or not art.visible or art.texture == null:
            _fail("missing Night Sea cell art " + str(i))
            return
        var path := art.texture.resource_path
        if path.is_empty() or seen.has(path):
            _fail("reused texture path " + str(i))
            return
        seen[path] = true
        if projected[i].texture != art.texture:
            _fail("perspective board did not adopt live Night Sea cell art " + str(i))
            return
    if game.get("board_stacks") != stacks or game.get("reserve_available") != reserves:
        _fail("Night Sea art changed live match state")
        return
    game.call("_reset_round")
    game.call("_on_reserve_pressed", 1, 0)
    game.call("_on_cell_pressed", 2)
    if int(game.get("moves")) != 1 or game.get("board_stacks")[2].size() != 1:
        _fail("empty Night Sea cell prevented legal placement")
        return
    print("A5_V109_NIGHT_CANON_PASS 9_live_textures source_gothic_compass 1_legal_move")
    quit(0)
