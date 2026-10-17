extends SceneTree
# Godot 4.7.2: --headless --path sinee-more-godot --script res://tests/a5_v105_pirate_unique_chart_runtime_smoke.gd
# This fixture is integrated, but its success must never be asserted until run.
func _initialize() -> void:
    call_deferred("_run")

func _fail(reason: String) -> void:
    push_error("A5_V105_PIRATE_CHART_FAIL " + reason)
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
    game.call("_set_world", 1)
    await process_frame
    var before_board: Array = game.get("board_stacks").duplicate(true)
    var before_reserves: Array = game.get("reserve_available").duplicate(true)
    var seen := {}
    var names := ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]
    var projected: Array = game.get("perspective_tiles")
    if projected.size() != 9:
        _fail("missing nine perspective gameplay tiles")
        return
    for i in range(9):
        var button := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + names[i]) as Button
        if button == null or button.disabled:
            _fail("noninteractive live cell " + str(i))
            return
        var art := button.get_node_or_null("WorldCellArt") as TextureRect
        if art == null or art.texture == null or not art.visible:
            _fail("missing live Pirate chart cell " + str(i))
            return
        var path := art.texture.resource_path
        if path.is_empty() or seen.has(path):
            _fail("duplicated/missing live Pirate chart texture " + str(i))
            return
        seen[path] = true
        if projected[i].texture != art.texture:
            _fail("perspective board not using the live Pirate chart texture")
            return
    if game.get("board_stacks") != before_board or game.get("reserve_available") != before_reserves:
        _fail("art changed the match state")
        return
    game.call("_reset_round")
    game.call("_on_reserve_pressed", 1, 0)
    game.call("_on_cell_pressed", 4)
    if int(game.get("moves")) != 1 or game.get("board_stacks")[4].size() != 1:
        _fail("Pirate chart prevented legal touch-handler placement")
        return
    print("A5_V105_PIRATE_CHART_PASS unique_live_tiles=9 placement=1")
    quit(0)
