extends SceneTree

# Opt-in Godot 4.7.2 native smoke. Do NOT mark runtime PASS without execution.
# godot --headless --path sinee-more-godot --script res://tests/a5_v74_gods_environment_runtime_smoke.gd
func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> void:
    push_error("A5_V74_GODS_FAIL " + message)
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
    var stacks: Array = game.get("board_stacks").duplicate(true)
    var reserves: Array = game.get("reserve_available").duplicate(true)
    var turn: int = int(game.get("turn"))
    var moves: int = int(game.get("moves"))
    game.call("_set_world", 3)
    await process_frame
    var background := game.get_node_or_null("WorldBackdrop") as TextureRect
    var support := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
    if background == null or background.texture == null or background.texture.get_size() != Vector2(512,288):
        _fail("gods_underwater background not live")
        return
    if support == null or not support.visible or support.texture == null or support.texture.get_size() != Vector2(256,256):
        _fail("gods_basalt physical support missing")
        return
    var cells := ["Cell00","Cell01","Cell02","Cell10","Cell11","Cell12","Cell20","Cell21","Cell22"]
    for i in range(9):
        var cell := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/Board/" + cells[i]) as Button
        if cell == null or cell.disabled:
            _fail("missing enabled live cell " + cells[i])
            return
        var art := cell.get_node_or_null("WorldCellArt") as TextureRect
        if art == null or art.texture == null or art.mouse_filter != Control.MOUSE_FILTER_IGNORE:
            _fail("missing live noninteractive Gods cell art")
            return
    if game.get("board_stacks") != stacks or game.get("reserve_available") != reserves:
        _fail("switching worlds mutated game state")
        return
    if int(game.get("turn")) != turn or int(game.get("moves")) != moves:
        _fail("switching worlds mutated turn/moves")
        return
    game.call("_set_world", 0)
    await process_frame
    var floating := game.get_node_or_null("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Panel
    if floating == null or floating.visible:
        _fail("Void must float without physical support")
        return
    print("A5_V74_GODS_ENV_RUNTIME_PASS world=3 cells=9 support=256x256 background=512x288 state=unchanged")
    quit(0)
