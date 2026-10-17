extends SceneTree

# Requires actual Godot 4.7.2. Not executed by the portable Python suite.
# godot --headless --path sinee-more-godot --script res://tests/a5_v104_world_cache_runtime_smoke.gd
func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> void:
    push_error("A5_V104_WORLD_CACHE_RUNTIME_FAIL " + message)
    quit(1)

func _run() -> void:
    var packed := load("res://main.tscn") as PackedScene
    if packed == null:
        _fail("main scene unavailable")
        return
    var game := packed.instantiate() as Control
    if game == null:
        _fail("invalid main scene root")
        return
    root.add_child(game)
    await process_frame
    var state_before: Array = game.get("board_stacks").duplicate(true)
    var reserves_before: Array = game.get("reserve_available").duplicate(true)
    var moves_before: int = int(game.get("moves"))
    var visuals: RefCounted = game.get("world_visuals")
    for world in [1, 2, 3, 4, 5, 6, 0, 6, 1, 5, 0, 2, 4, 0]:
        game.call("_set_world", world)
        await process_frame
        if not visuals.call("_cache_within_budget"):
            _fail("cache exceeded two-world budget after switch " + str(world))
            return
        var resident: Array = visuals.get("resident_worlds")
        var supports: Dictionary = visuals.get("support_cache")
        if resident.size() > 2:
            _fail("too many resident worlds")
            return
        for key in supports.keys():
            if not resident.has(int(key)):
                _fail("inactive support retained world=" + str(key))
                return
        var foundation := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
        if foundation == null:
            _fail("physical foundation missing")
            return
        if world == 0:
            if foundation.visible or foundation.texture != null:
                _fail("Void retained hidden physical support")
                return
        elif not foundation.visible or foundation.texture == null:
            _fail("solid world lost physical support")
            return
        for name in ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]:
            var cell := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + name) as Button
            if cell == null or cell.disabled:
                _fail("noninteractive board cell " + name)
                return
            var art := cell.get_node_or_null("WorldCellArt") as TextureRect
            if art == null:
                _fail("missing live cell art " + name)
                return
            if world == 0 and art.texture != null:
                _fail("Void retained hidden cell art " + name)
                return
            if world != 0 and art.texture == null:
                _fail("solid world missing live cell art " + name)
                return
        if game.get("board_stacks") != state_before or game.get("reserve_available") != reserves_before or int(game.get("moves")) != moves_before:
            _fail("world switch modified live match")
            return
    game.set("ai_enabled", false)
    game.call("_reset_round")
    game.call("_on_reserve_pressed", 1, 0)
    game.call("_on_cell_pressed", 0)
    if int(game.get("moves")) != 1:
        _fail("shared touch-handler placement did not commit")
        return
    print("A5_V104_WORLD_CACHE_RUNTIME_PASS switches=14 worlds=7 placements=1")
    quit(0)
