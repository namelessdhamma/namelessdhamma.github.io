extends Control

signal finished

const DURATION := 13.0
const FIXED_FPS := 24.0
const LIGHTNING_TIMES := [2.15, 6.25, 10.15]

@export var fixed_clock := false

@onready var background: TextureRect = $Background
@onready var ship: TextureRect = $Ship
@onready var foreground: ColorRect = $ForegroundWater
@onready var rain: ColorRect = $Rain
@onready var lightning: Control = $Lightning
@onready var fade: ColorRect = $Fade

var elapsed := 0.0
var start_frame := 0
var last_time := 0.0
var finished_sent := false
var lightning_triggered := [false, false, false]

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	start_frame = Engine.get_process_frames()
	ship.pivot_offset = ship.size * 0.5
	fade.color = Color(0.0, 0.0, 0.0, 1.0)
	_apply_time(0.0)
	print("BLUE_SEA_CONTINUOUS_STORM_READY")

func _process(delta: float) -> void:
	if finished_sent:
		return

	if fixed_clock:
		elapsed = float(Engine.get_process_frames() - start_frame) / FIXED_FPS
	else:
		elapsed += delta

	var t := minf(elapsed, DURATION)
	_apply_time(t)

	for i in range(LIGHTNING_TIMES.size()):
		var event_time: float = LIGHTNING_TIMES[i]
		if not lightning_triggered[i] and last_time < event_time and t >= event_time:
			lightning_triggered[i] = true
			lightning.call("trigger", 1.0 if i != 1 else 0.88, i + 3)

	last_time = t

	if elapsed >= DURATION:
		_finish_intro()

func _apply_time(t: float) -> void:
	var p := clampf(t / DURATION, 0.0, 1.0)
	var eased := p * p * (3.0 - 2.0 * p)
	var flash := _lightning_envelope(t)

	background.material.set_shader_parameter("anim_time", t)
	background.material.set_shader_parameter("progress", eased)
	background.material.set_shader_parameter("lightning_flash", flash)

	ship.material.set_shader_parameter("anim_time", t)
	ship.material.set_shader_parameter("progress", eased)
	ship.material.set_shader_parameter("lightning_flash", flash)

	foreground.material.set_shader_parameter("anim_time", t)
	foreground.material.set_shader_parameter("progress", eased)
	foreground.material.set_shader_parameter("lightning_flash", flash)

	rain.material.set_shader_parameter("anim_time", t)
	rain.material.set_shader_parameter("intensity", 1.0 + 0.10 * sin(t * 0.55))

	lightning.call("set_flash", flash)

	var view := size
	if view.x <= 1.0 or view.y <= 1.0:
		view = Vector2(1280.0, 720.0)

	var approach := pow(eased, 0.92)
	var center := Vector2(
		lerpf(view.x * 0.67, view.x * 0.56, approach),
		lerpf(view.y * 0.50, view.y * 0.51, approach)
	)

	var heavy_roll := 0.034 * sin(t * 0.72) + 0.012 * sin(t * 0.31 + 1.1)
	var bob := 8.5 * sin(t * 0.68 + 0.4) + 3.2 * sin(t * 1.31)
	var pitch := 0.018 * sin(t * 0.58 + 1.7)

	var base_scale := lerpf(0.22, 0.56, approach)
	ship.scale = Vector2(base_scale * (1.0 + pitch), base_scale * (1.0 - pitch * 0.65))
	ship.rotation = heavy_roll
	ship.position = center - ship.pivot_offset + Vector2(0.0, bob)

	var fade_in := 1.0 - smoothstep(0.0, 0.42, t)
	var fade_out := smoothstep(DURATION - 0.72, DURATION, t)
	fade.color.a = maxf(fade_in, fade_out)

func _lightning_envelope(t: float) -> float:
	var result := 0.0
	for event_time in LIGHTNING_TIMES:
		var dt: float = t - float(event_time)
		if dt >= 0.0 and dt < 0.60:
			var primary := exp(-dt * 12.0)
			var secondary_dt := dt - 0.105
			var secondary := 0.0
			if secondary_dt >= 0.0:
				secondary = 0.62 * exp(-secondary_dt * 18.0)
			result = maxf(result, clampf(primary + secondary, 0.0, 1.0))
	return result

func _finish_intro() -> void:
	if finished_sent:
		return
	finished_sent = true
	finished.emit()
	if not fixed_clock:
		queue_free()
