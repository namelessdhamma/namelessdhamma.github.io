extends Control

var flash_strength := 0.0
var rng := RandomNumberGenerator.new()
var main_points := PackedVector2Array()
var branches: Array[PackedVector2Array] = []

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	rng.seed = 20260925
	set_process(false)

func set_flash(value: float) -> void:
	flash_strength = clampf(value, 0.0, 1.0)
	queue_redraw()

func trigger(strength: float = 1.0, shot: int = 0) -> void:
	flash_strength = clampf(strength, 0.0, 1.0)
	_generate_bolt(shot)
	queue_redraw()

func _generate_bolt(shot: int) -> void:
	main_points.clear()
	branches.clear()
	var w := size.x
	var h := size.y
	if w <= 1.0 or h <= 1.0:
		w = 1280.0
		h = 720.0
	var start_x := w * (0.62 + 0.16 * sin(float(shot) * 1.73))
	var p := Vector2(start_x, -20.0)
	main_points.append(p)
	var segments := 13
	for i in range(1, segments + 1):
		var y := h * 0.74 * float(i) / float(segments)
		var drift := rng.randf_range(-42.0, 42.0)
		p = Vector2(clampf(p.x + drift, w * 0.15, w * 0.92), y)
		main_points.append(p)
		if i > 2 and i < segments - 2 and rng.randf() > 0.58:
			var branch := PackedVector2Array()
			branch.append(p)
			var bp := p
			for j in range(rng.randi_range(2, 4)):
				bp += Vector2(rng.randf_range(-80.0, 80.0), rng.randf_range(28.0, 62.0))
				branch.append(bp)
			branches.append(branch)

func _draw() -> void:
	if flash_strength <= 0.002:
		return
	var a := flash_strength
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.55, 0.68, 1.0, a * 0.13), true)
	if main_points.size() > 1:
		draw_polyline(main_points, Color(0.72, 0.84, 1.0, a * 0.55), 8.0, true)
		draw_polyline(main_points, Color(0.96, 0.98, 1.0, a), 2.6, true)
	for branch in branches:
		if branch.size() > 1:
			draw_polyline(branch, Color(0.78, 0.88, 1.0, a * 0.68), 2.0, true)
