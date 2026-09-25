extends Control

signal finished

const DURATIONS := [2.8, 3.2, 3.4, 3.8, 3.8, 3.6, 3.5, 3.8, 4.2]
const CROSSFADE := 0.72

@onready var storm_image: TextureRect = $StormImage
@onready var lightning: Control = $Lightning
@onready var fade: ColorRect = $Fade

var shot := 0
var shot_time := 0.0
var total_time := 0.0
var next_random_flash := 1.55
var finished_sent := false

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	storm_image.material.set_shader_parameter("shot_a", 0)
	storm_image.material.set_shader_parameter("shot_b", 1)
	storm_image.material.set_shader_parameter("mix_amount", 0.0)
	storm_image.material.set_shader_parameter("anim_time", 0.0)
	storm_image.material.set_shader_parameter("lightning_flash", 0.0)
	lightning.call("set_flash", 0.0)
	print("BLUE_SEA_STORM_INTRO_READY")

func _process(delta: float) -> void:
	if finished_sent:
		return

	total_time += delta
	shot_time += delta
	storm_image.material.set_shader_parameter("anim_time", total_time)

	if total_time >= next_random_flash:
		if shot >= 1:
			_trigger_lightning(0.48 if shot < 3 else 0.74)
		next_random_flash = total_time + randf_range(2.1, 4.0)
	else:
		var f: float = maxf(float(lightning.get("flash_strength")) - delta * 5.8, 0.0)
		lightning.call("set_flash", f)
		storm_image.material.set_shader_parameter("lightning_flash", f)

	var duration: float = DURATIONS[shot]
	var transition_start: float = duration - CROSSFADE
	var blend := 0.0
	if shot < DURATIONS.size() - 1 and shot_time > transition_start:
		blend = smoothstep(transition_start, duration, shot_time)

	storm_image.material.set_shader_parameter("shot_a", shot)
	storm_image.material.set_shader_parameter("shot_b", mini(shot + 1, DURATIONS.size() - 1))
	storm_image.material.set_shader_parameter("mix_amount", blend)

	if shot == DURATIONS.size() - 1:
		var fade_start: float = duration - 1.0
		if shot_time > fade_start:
			fade.color.a = smoothstep(fade_start, duration, shot_time)

	if shot_time >= duration:
		if shot < DURATIONS.size() - 1:
			shot += 1
			shot_time = 0.0
			if shot == 3 or shot == 8:
				_trigger_lightning(1.0)
		else:
			_finish_intro()

func _trigger_lightning(strength: float) -> void:
	lightning.call("trigger", strength, shot)
	storm_image.material.set_shader_parameter("lightning_flash", strength)

func _finish_intro() -> void:
	finished_sent = true
	finished.emit()
	queue_free()
