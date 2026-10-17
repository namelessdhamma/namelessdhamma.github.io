extends SceneTree

# Opt-in native Godot smoke. NOT certified until executed in Godot 4.7.2.
# godot --headless --path sinee-more-godot --script res://tests/a5_v75_sand_night_runtime_smoke.gd
func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> void:
    push_error("A5_V75_SAND_NIGHT_FAIL " + message)
    quit(1)

func _run() -> void:
    var scene := load("res://main.tscn") as PackedScene
    if scene == null:
        _fail("main scene missing")
        return
    var game := scene.instantiate() as Control
    if game == null:
        _fail("main scene root invalid")
        return
    root.add_child(game)
    await process_frame
    var board_before: Array = game.get("board_stacks").duplicate(true)
    var reserve_before: Array = game.get("reserve_available").duplicate(true)
    var turn_before: int = int(game.get("turn"))
    var moves_before: int = int(game.get("moves"))
    for world in [4, 5]:
        game.call("_set_world", world)
        await process_frame
        var backdrop := game.get_node_or_null("WorldBackdrop") as TextureRect
        var support := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Panel
        var foundation := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
        if backdrop == null or backdrop.texture == null or backdrop.texture.get_size() != Vector2(512,288):
            _fail("original background not live world=" + str(world))
            return
        if support == null or not support.visible or foundation == null or not foundation.visible or foundation.texture == null or foundation.texture.get_size() != Vector2(256,256):
            _fail("physical support missing world=" + str(world))
            return
        for cell_name in ["Cell00","Cell01","Cell02","Cell10","Cell11","Cell12","Cell20","Cell21","Cell22"]:
            var cell := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + cell_name) as Button
            if cell == null or cell.disabled:
                _fail("live cell missing " + cell_name)
                return
            var art := cell.get_node_or_null("WorldCellArt") as TextureRect
            if art == null or art.texture == null or art.mouse_filter != Control.MOUSE_FILTER_IGNORE:
                _fail("world cell art not live and input-safe " + cell_name)
                return
        if game.get("board_stacks") != board_before or game.get("reserve_available") != reserve_before or int(game.get("turn")) != turn_before or int(game.get("moves")) != moves_before:
            _fail("world switching mutated game state")
            return
    # One actual human placement through the shared input handlers; not a
    # substitute for 21 complete AI matches or physical phone-touch testing.
    game.set("ai_enabled", false)
    game.call("_reset_round")
    game.call("_on_reserve_pressed", 1, 0)
    game.call("_on_cell_pressed", 0)
    if int(game.get("moves")) != 1:
        _fail("shared human placement failed")
        return
    print("A5_V75_SAND_NIGHT_RUNTIME_PASS worlds=4,5 cells=18 textures=4 human_moves=1")
    quit(0)
