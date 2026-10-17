extends SceneTree

# A5 v73 native Godot 4.7.2 smoke. Opt-in only:
# godot --headless --path sinee-more-godot --script res://tests/a5_v73_northern_runtime_smoke.gd
# A failed assertion is a failed run, never a claimed product qualification.
func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> void:
    push_error("A5_V73_NORTH_FAIL " + message)
    quit(1)

func _run() -> void:
    var scene := load("res://main.tscn") as PackedScene
    if scene == null:
        _fail("main scene missing")
        return
    var game := scene.instantiate() as Control
    if game == null:
        _fail("main scene is not Control")
        return
    root.add_child(game)
    await process_frame
    var stacks: Array = game.get("board_stacks").duplicate(true)
    var reserves: Array = game.get("reserve_available").duplicate(true)
    var turn: int = int(game.get("turn"))
    var moves: int = int(game.get("moves"))
    game.call("_set_world", 6)
    await process_frame
    var background := game.get_node_or_null("WorldBackdrop") as TextureRect
    var support := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
    if background == null or background.texture == null or background.texture.get_size() != Vector2(1024, 576):
        _fail("original layered fjord background not live")
        return
    if support == null or not support.visible or support.texture == null or support.texture.get_size() != Vector2(512, 512):
        _fail("Northern physical rune-stone support not live")
        return
    for i in range(9):
        var name: String = ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"][i]
        var cell := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + name) as Button
        if cell == null or cell.disabled:
            _fail("missing enabled live board cell " + name)
            return
        var art := cell.get_node_or_null("WorldCellArt") as TextureRect
        if art == null or art.texture == null or art.mouse_filter != Control.MOUSE_FILTER_IGNORE:
            _fail("missing noninteractive Northern empty-cell art " + name)
            return
    if game.get("board_stacks") != stacks or game.get("reserve_available") != reserves:
        _fail("visual world switch mutated gameplay state")
        return
    if int(game.get("turn")) != turn or int(game.get("moves")) != moves:
        _fail("visual world switch mutated turn/moves")
        return
    game.call("_set_world", 0)
    await process_frame
    var floating := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Panel
    if floating == null or floating.visible:
        _fail("Void physical support must be hidden")
        return
    print("A5_V73_NORTHERN_ENV_RUNTIME_PASS world=6 cells=9 support=512x512 background=1024x576 void=floating state=unchanged")
    quit(0)
