extends Control

func _ready() -> void:
	print("BLUE_SEA_GODOT_READY")
	var intro_scene: PackedScene = load("res://intro/storm_intro.tscn") as PackedScene
	if intro_scene == null:
		push_error("Storm intro scene failed to load")
		return
	var intro: Control = intro_scene.instantiate() as Control
	if intro == null:
		push_error("Storm intro root is not Control")
		return
	add_child(intro)
	intro.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	intro.finished.connect(_on_intro_finished)
	move_child(intro, get_child_count() - 1)

func _on_intro_finished() -> void:
	print("BLUE_SEA_STORM_INTRO_FINISHED")
